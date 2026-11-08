"""MCP client. You add a connection. Tool calls wait for approval."""

from __future__ import annotations

import itertools
import json
import os
import queue
import re
import secrets
import shlex
import subprocess
import threading
import time
import urllib.error
import urllib.request

from py.si.engine import HELP, ROOT, load_state, parse_cli, snapshot
from py.si.net import load, predict, program_to_action

CONFIG = ROOT / "mcp.json"
PCB_MCP = os.environ.get("SI_PCB_MCP", "http://127.0.0.1:8766/mcp")
CAD_MCP = os.environ.get("SI_CAD_MCP", "http://127.0.0.1:8767/mcp")
VERSION = "0.9.5"
PRESETS = {
    "pcb": {"name": "pcb", "title": "PCB", "transport": "http", "target": PCB_MCP},
    "cad": {"name": "cad", "title": "CAD", "transport": "http", "target": CAD_MCP},
}

_MODEL = None
_RPC_IDS = itertools.count(1)
_RPC_LOCK = threading.Lock()
_PENDING: dict[str, dict] = {}
PENDING_TTL = 600.0
_STDIO: dict[str, "StdioSession"] = {}
_HTTP: dict[str, dict] = {}
_GUARD = threading.Lock()


def _next_id() -> int:
    with _RPC_LOCK:
        return next(_RPC_IDS)


def _hold(proposal_id: str, item: dict) -> None:
    """Drop approvals older than 10 minutes, then keep this one. Caller holds _GUARD."""
    now = time.monotonic()
    for key in [k for k, row in _PENDING.items() if now - row.get("at", now) > PENDING_TTL]:
        del _PENDING[key]
    _PENDING[proposal_id] = {**item, "at": now}


def _summary(text: str) -> str:
    """Turn a DRC or ERC JSON result into one sentence. Leave other text alone."""
    if not text.lstrip().startswith("{"):
        return text
    try:
        data = json.loads(text)
    except ValueError:
        return text
    if isinstance(data, dict) and ("undone" in data or "redone" in data):
        done = int(data.get("undone") or data.get("redone") or 0)
        verb = "Undid" if "undone" in data else "Redid"
        return f"{verb} {done} step{'s' if done != 1 else ''}."
    if isinstance(data, dict) and not isinstance(data.get("violations"), list):
        bits = []
        for key, value in data.items():
            if isinstance(value, bool):
                bits.append(f"{key} {str(value).lower()}")
            elif isinstance(value, (int, float)) or (isinstance(value, str) and len(value) <= 80):
                bits.append(f"{key} {value}")
            elif isinstance(value, list):
                bits.append(f"{key}: {len(value)}")
            if len(bits) == 8:
                break
        return (", ".join(bits) + ".") if bits else text
    if not isinstance(data, dict):
        return text
    errors, warnings = int(data.get("errors") or 0), int(data.get("warnings") or 0)
    line = f"{errors} error{'s' if errors != 1 else ''}, {warnings} warning{'s' if warnings != 1 else ''}"
    worst = [
        str(row.get("message") or row.get("code") or "")
        for row in data["violations"]
        if isinstance(row, dict) and row.get("severity") in ("error", "warning")
    ][:3]
    return f"Check: {line}" + (f" ({'; '.join(worst)})." if worst else ".")


def rpc_timeout(tool: bool = False) -> float:
    raw = os.environ.get("SI_MCP_TIMEOUT")
    if raw:
        try:
            return max(1.0, float(raw))
        except ValueError:
            pass
    return 60.0 if tool else 8.0


def model_bundle():
    global _MODEL
    if _MODEL is None:
        _MODEL = load()
    return _MODEL


def empty_config() -> dict:
    return {"mcpServers": {}, "alwaysAllow": [], "mode": "man"}


def load_config() -> dict:
    if not CONFIG.exists():
        return empty_config()
    try:
        raw = json.loads(CONFIG.read_text())
    except json.JSONDecodeError:
        return empty_config()
    raw.setdefault("mcpServers", {})
    raw.setdefault("alwaysAllow", [])
    if raw.get("mode") not in {"auto", "semi", "man"}:
        raw["mode"] = "man"
    return raw


def save_config(cfg: dict) -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    CONFIG.write_text(json.dumps(cfg, indent=2))


def _safe_name(name: str) -> str:
    clean = "".join(ch for ch in name.strip().lower() if ch.isalnum() or ch in "-_")[:32]
    if not clean:
        raise ValueError("Name the connection.")
    return clean


def _safe_target(target: str) -> str:
    clean = target.strip()
    if not clean or len(clean) > 2000:
        raise ValueError("Give an MCP URL or command.")
    if any(ch in clean for ch in "\n;&|`$><"):
        raise ValueError("That command is not allowed.")
    return clean


class StdioSession:
    def __init__(self, command: str):
        self.proc = subprocess.Popen(
            shlex.split(command),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,
        )
        self.lines: queue.Queue[str | None] = queue.Queue()
        self.lock = threading.Lock()
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self) -> None:
        if self.proc.stdout is None:
            self.lines.put(None)
            return
        for line in self.proc.stdout:
            self.lines.put(line)
        self.lines.put(None)

    def rpc(self, method: str, params: dict | None = None, tool: bool = False) -> dict:
        if self.proc.poll() is not None or self.proc.stdin is None:
            raise RuntimeError("stdio MCP exited")
        rid = _next_id()
        body = {"jsonrpc": "2.0", "id": rid, "method": method}
        if params is not None:
            body["params"] = params
        with self.lock:
            self.proc.stdin.write(json.dumps(body) + "\n")
            self.proc.stdin.flush()
            deadline = time.monotonic() + rpc_timeout(tool)
            while True:
                left = deadline - time.monotonic()
                try:
                    line = self.lines.get(timeout=max(0.0, left))
                except queue.Empty:
                    raise TimeoutError("stdio MCP timed out") from None
                if not line:
                    raise RuntimeError("stdio MCP exited")
                try:
                    payload = json.loads(line)
                except ValueError:
                    continue
                if isinstance(payload, dict) and payload.get("id") == rid:
                    break
        if "error" in payload:
            raise RuntimeError(payload["error"].get("message") or "MCP error")
        return payload.get("result") or {}

    def notify(self, method: str, params: dict | None = None) -> None:
        if self.proc.poll() is not None or self.proc.stdin is None:
            raise RuntimeError("stdio MCP exited")
        body = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            body["params"] = params
        self.proc.stdin.write(json.dumps(body) + "\n")
        self.proc.stdin.flush()

    def close(self) -> None:
        if self.proc.poll() is None:
            self.proc.terminate()


def _sse_payload(raw: str) -> dict:
    data = ""
    for line in raw.splitlines():
        if line.startswith("data:"):
            data += line[5:].strip()
    if not data:
        raise RuntimeError("empty MCP stream")
    return json.loads(data)


def _auth_headers(row: dict) -> dict[str, str]:
    headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
    token = str(row.get("token") or os.environ.get("SI_MCP_TOKEN") or "")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    session = _HTTP.get(row.get("id") or "") or {}
    if session.get("id"):
        headers["Mcp-Session-Id"] = session["id"]
    return headers


def http_rpc(url: str, method: str, params: dict | None = None, row: dict | None = None, tool: bool = False) -> dict:
    body = {"jsonrpc": "2.0", "id": _next_id(), "method": method}
    if params is not None:
        body["params"] = params
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=_auth_headers(row or {}))
    with urllib.request.urlopen(req, timeout=rpc_timeout(tool)) as res:
        session_id = res.headers.get("Mcp-Session-Id")
        raw = res.read().decode()
        ctype = res.headers.get("Content-Type") or ""
    if row and row.get("id") and session_id:
        _HTTP.setdefault(row["id"], {})["id"] = session_id
    payload = _sse_payload(raw) if "text/event-stream" in ctype or raw.lstrip().startswith("data:") else json.loads(raw or "{}")
    if "error" in payload:
        raise RuntimeError(payload["error"].get("message") or "MCP error")
    return payload.get("result") or {}


def http_notify(url: str, method: str, row: dict | None = None) -> None:
    body = {"jsonrpc": "2.0", "method": method}
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=_auth_headers(row or {}))
    try:
        with urllib.request.urlopen(req, timeout=rpc_timeout(False)) as res:
            res.read()
    except (urllib.error.URLError, TimeoutError, OSError):
        return


def rpc(row: dict, method: str, params: dict | None = None, tool: bool = False) -> dict:
    if row.get("transport") == "stdio":
        with _GUARD:
            session = _STDIO.get(row["id"])
            if session is None or session.proc.poll() is not None:
                session = StdioSession(row["target"])
                _STDIO[row["id"]] = session
        return session.rpc(method, params, tool)
    return http_rpc(row["target"], method, params, row, tool)


def notify(row: dict, method: str) -> None:
    if row.get("transport") == "stdio":
        with _GUARD:
            session = _STDIO.get(row["id"])
        if session is not None:
            session.notify(method)
        return
    http_notify(row["target"], method, row)


def handshake(row: dict) -> dict:
    init = rpc(
        row,
        "initialize",
        {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "si-llm", "version": VERSION},
        },
    )
    notify(row, "notifications/initialized")
    return init


def configured() -> list[dict]:
    cfg = load_config()
    rows = []
    for name, spec in cfg["mcpServers"].items():
        rows.append(
            {
                "id": name,
                "title": name.upper() if name in {"pcb", "cad"} else name,
                "transport": spec.get("transport") or "http",
                "target": spec.get("target") or "",
                "token": spec.get("token") or "",
            }
        )
    return rows


def probe() -> list[dict]:
    found = []
    for row in configured():
        try:
            init = handshake(row)
            listed = rpc(row, "tools/list")
            tools = [t.get("name") for t in listed.get("tools") or [] if t.get("name")]
            info = (init.get("serverInfo") or {}).get("name") or row["id"]
            found.append({**row, "ok": True, "server": info, "tools": tools})
        except (urllib.error.URLError, RuntimeError, TimeoutError, json.JSONDecodeError, OSError, ValueError):
            found.append({**row, "ok": False, "server": "", "tools": []})
    return found


def add_server(name: str, transport: str, target: str) -> dict:
    transport = "stdio" if transport == "stdio" else "http"
    if transport == "http" and not target.startswith("http"):
        return {"ok": False, "error": "An HTTP connection needs a URL."}
    try:
        clean = _safe_name(name)
        target = _safe_target(target)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    cfg = load_config()
    cfg["mcpServers"][clean] = {"transport": transport, "target": target}
    if os.environ.get("SI_MCP_TOKEN"):
        cfg["mcpServers"][clean]["token"] = os.environ["SI_MCP_TOKEN"]
    save_config(cfg)
    row = next((item for item in probe() if item["id"] == clean), None)
    if not row or not row["ok"]:
        cfg = load_config()
        cfg["mcpServers"].pop(clean, None)
        save_config(cfg)
        close_stdio(clean)
        return {"ok": False, "error": "Could not connect. Check the URL or command."}
    return {"ok": True, "server": row}


def add_preset(name: str) -> dict:
    preset = PRESETS.get(name)
    if not preset:
        return {"ok": False, "error": "Unknown preset."}
    if name == "pcb" and os.environ.get("SI_PCB_MCP_CMD"):
        return add_server("pcb", "stdio", os.environ["SI_PCB_MCP_CMD"])
    if name == "cad" and os.environ.get("SI_CAD_MCP_CMD"):
        return add_server("cad", "stdio", os.environ["SI_CAD_MCP_CMD"])
    return add_server(preset["name"], preset["transport"], preset["target"])


def close_stdio(name: str) -> None:
    with _GUARD:
        session = _STDIO.pop(name, None)
    if session:
        session.close()


def remove_server(name: str) -> dict:
    try:
        clean = _safe_name(name)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    cfg = load_config()
    cfg["mcpServers"].pop(clean, None)
    cfg["alwaysAllow"] = [item for item in cfg["alwaysAllow"] if not str(item).startswith(clean + ".")]
    save_config(cfg)
    close_stdio(clean)
    return {"ok": True, "servers": probe()}


def call_tool(server_id: str, name: str, arguments: dict | None = None) -> dict:
    row = next((item for item in configured() if item["id"] == server_id), None)
    if row is None:
        raise RuntimeError("not connected")
    result = rpc(row, "tools/call", {"name": name, "arguments": arguments or {}}, tool=True)
    content = result.get("content") or []
    texts = [str(item.get("text") or "") for item in content if item.get("type", "text") == "text" and item.get("text")]
    text = "\n".join(texts)
    if not text and any(item.get("type") == "image" for item in content):
        text = "3D view returned a picture and no height summary."
    if result.get("isError"):
        raise RuntimeError(text or "The tool refused the call.")
    text = _summary(text)
    state = (result.get("structuredContent") or {}).get("state")
    return {"text": text, "state": state, "server": server_id, "tool": name}


def _part_args(action: dict, placed: bool) -> dict:
    args = {"ref": action["ref"], "pkg": action["pkg"]}
    if placed:
        args["x"] = action["x"]
        args["y"] = action["y"]
    for key in ("value", "size", "mpn"):
        if action.get(key):
            args[key] = action[key]
    return args


def _net_args(action: dict) -> dict:
    pins = action.get("pins") or [action.get("a"), action.get("b")]
    if isinstance(pins, str):
        pins = [part.strip() for part in pins.split(",") if part.strip()]
    pins = [str(pin) for pin in pins if pin and str(pin) != "<none>"]
    args = {"name": action["name"], "a": pins[0], "b": pins[1] if len(pins) > 1 else pins[0]}
    if len(pins) != 2 or any("." in pin for pin in pins):
        args["pins"] = pins
    return args


def plan(action: dict) -> list[tuple[str, str, dict]]:
    op = action.get("op")
    if op == "batch":
        calls = []
        for step in action.get("steps") or []:
            calls.extend(plan(step))
        if len(calls) > 1 and len({server for server, _tool, _args in calls}) == 1:
            steps = [{"tool": tool, **args} for _server, tool, args in calls]
            return [(calls[0][0], "batch", {"steps": steps, "undo": "one"})]
        return calls
    if op == "pcb_add":
        return [("pcb", "pcb_add", _part_args(action, True))]
    if op == "pcb_net":
        return [("pcb", "pcb_net", _net_args(action))]
    if op == "pcb_delete":
        return [("pcb", "pcb_delete", {"ref": action["ref"]})]
    if op == "pcb_move":
        return [("pcb", "pcb_move", {"ref": action["ref"], "x": action["x"], "y": action["y"]})]
    if op == "pcb_rotate":
        return [("pcb", "pcb_rotate", {"ref": action["ref"], "angle": action["angle"]})]
    if op == "pcb_copy":
        return [("pcb", "pcb_copy", {"ref": action["ref"], "to": action["to"], "x": action.get("x"), "y": action.get("y")})]
    if op == "pcb_swap":
        return [("pcb", "pcb_swap", {"a": action["a"], "b": action["b"]})]
    if op == "pcb_flip":
        return [("pcb", "pcb_flip", {"ref": action["ref"]})]
    if op == "pcb_find":
        return [("pcb", "pcb_find", {"ref": action["ref"]})]
    if op == "power_select":
        return [("pcb", "power_select", {"kind": action.get("kind") or "", "draw": bool(action.get("draw"))})]
    if op == "robot_select":
        return [("pcb", "robot_select", {"kind": action.get("kind") or ""})]
    if op == "computer_select":
        return [("pcb", "computer_select", {"kind": action.get("kind") or ""})]
    if op == "sensor_select":
        return [("pcb", "sensor_select", {"kind": action.get("kind") or ""})]
    if op == "pcb_flow":
        return [("pcb", "pcb_flow", {})]
    if op == "pcb_drc":
        return [("pcb", "pcb_drc", {})]
    if op == "pcb_status":
        return [("pcb", "pcb_status", {})]
    if op == "pcb_reset":
        return [("pcb", "pcb_reset", {})]
    if op == "sch_add":
        return [("pcb", "sch_add", _part_args(action, False))]
    if op == "sch_set":
        args = {"ref": action["ref"]}
        for key in ("value", "size", "mpn"):
            if action.get(key):
                args[key] = action[key]
        return [("pcb", "sch_set", args)]
    if op == "pcb_set":
        args = {"ref": action["ref"]}
        for key in ("value", "size", "mpn"):
            if action.get(key):
                args[key] = action[key]
        return [("pcb", "pcb_set", args)]
    if op == "sch_wire":
        return [("pcb", "sch_wire", _net_args(action))]
    if op == "sch_erc":
        return [("pcb", "sch_erc", {})]
    if op == "fp_assign":
        return [("pcb", "fp_assign", {"ref": action["ref"]})]
    if op == "sim_dc":
        return [("pcb", "sim_dc", {})]
    if op == "sim_tran":
        return [("pcb", "sim_tran", {})]
    if op == "view_3d":
        return [("pcb", "view_3d", {})]
    if op == "fab_gerber":
        return [("pcb", "fab_gerber", {})]
    if op == "fab_stack":
        return [("pcb", "fab_stack", {})]
    if op == "asm_bom":
        return [("pcb", "asm_bom", {})]
    if op == "asm_pos":
        return [("pcb", "asm_pos", {})]
    if op == "chip_check":
        return [("pcb", "chip_check", {"kind": action.get("kind") or "pin"})]
    if op == "server_tool":
        return [("pcb", str(action["tool"]), dict(action.get("args") or {}))]
    if op == "set_industry":
        return [("pcb", "set_industry", {"kind": action.get("kind") or ""})]
    if op == "set_board":
        return [("pcb", "set_board", {"kind": action.get("kind") or ""})]
    if op == "set_outline":
        return [("pcb", "set_outline", {"length": action["length"], "width": action["width"]})]
    if op == "industry_check":
        return [("pcb", "industry_check", {})]
    if op == "cover_all":
        return [("pcb", "cover_all", {})]
    if op == "place_sheet":
        return [("pcb", "place_sheet", {})]
    if op == "build_datasheet":
        return [("pcb", "build_datasheet", {"variants": action.get("variants") or []})]
    if op == "datasheet_rebuild":
        return [("pcb", "datasheet_rebuild", {})]
    if op == "impedance":
        return [("pcb", "impedance", {"ohms": action.get("ohms") or 50})]
    if op == "pour":
        return [("pcb", "pour", {})]
    if op == "dfm":
        return [("pcb", "dfm", {})]
    if op == "via":
        return [("pcb", "via", {"amps": action.get("amps") or 1})]
    if op == "diff":
        return [("pcb", "diff", {"name": action.get("name") or "usb"})]
    if op == "cad_chamfer":
        return [("cad", "cad_chamfer", {"size": action["size"]})]
    if op == "cad_shell":
        return [("cad", "cad_shell", {"wall": action["wall"]})]
    if op == "set_ipc":
        return [("pcb", "set_ipc", {"kind": action.get("kind") or "2"})]
    if op == "ipc_check":
        return [("pcb", "ipc_check", {"doc": action.get("doc") or ""})]
    if op == "desk":
        return [("pcb", "desk", {"kind": action.get("kind") or "", "value": action.get("value"), "name": action.get("name") or ""})]
    if op == "feature_audit":
        return [("pcb", "feature_audit", {})]
    if op == "autoroute":
        return [("pcb", "autoroute", {"which": action.get("which") or "all"})]
    if op == "build_circuit":
        return [("pcb", "build_circuit", {"kind": action.get("kind") or "mcu"})]
    if op == "design_cell":
        return [("pcb", "design_cell", {"kind": action.get("kind") or "inv"})]
    if op == "handle_all":
        return [("pcb", "handle_all", {})]
    if op == "handle_industry":
        return [("pcb", "handle_industry", {"kind": action.get("kind") or ""})]
    if op == "handle_board":
        return [("pcb", "handle_board", {"kind": action.get("kind") or ""})]
    if op == "cad_sketch":
        return [("cad", "cad_sketch", {"length": action["length"], "width": action["width"]})]
    if op == "cad_extrude":
        return [("cad", "cad_extrude", {"thickness": action["thickness"]})]
    if op == "cad_hole":
        return [("cad", "cad_hole", {"diameter": action["diameter"]})]
    if op == "cad_fillet":
        return [("cad", "cad_fillet", {"radius": action["radius"]})]
    if op == "cad_mass":
        return [("cad", "cad_mass", {})]
    if op == "cad_status":
        return [("cad", "cad_status", {})]
    if op == "cad_reset":
        return [("cad", "cad_reset", {})]
    if op == "reset":
        return [("pcb", "pcb_reset", {}), ("cad", "cad_reset", {})]
    if op == "status":
        return [("pcb", "pcb_status", {}), ("cad", "cad_status", {})]
    return []


def public_calls(calls: list[tuple[str, str, dict]]) -> list[dict]:
    out = []
    for server, tool, args in calls:
        out.append(
            {
                "server": server,
                "tool": tool,
                "args": [{"key": key, "value": str(value)[:180]} for key, value in args.items()],
            }
        )
    return out


def resolve(calls: list[tuple[str, str, dict]]) -> tuple[list[tuple[str, str, dict]], str]:
    live = {row["id"]: row for row in probe() if row["ok"]}
    if not live:
        return [], "Add an MCP connection first. Nothing was called."
    resolved = []
    for preferred, tool, args in calls:
        host = None
        if preferred in live and tool in live[preferred]["tools"]:
            host = preferred
        else:
            for sid, row in live.items():
                if tool in row["tools"]:
                    host = sid
                    break
        if host is None:
            return [], f"No connected MCP server exposes {tool}. Nothing was called."
        resolved.append((host, tool, args))
    return resolved, ""


READONLY = {"pcb_drc", "pcb_status", "pcb_find", "cad_mass", "cad_status", "sch_erc", "sim_dc", "sim_tran", "view_3d", "fab_stack", "asm_bom", "chip_check", "industry_check", "cover_all", "impedance", "dfm", "via", "ipc_check", "desk", "feature_audit"}


def current_mode() -> str:
    mode = str(load_config().get("mode") or "man")
    return mode if mode in {"auto", "semi", "man"} else "man"


def set_mode(mode: str) -> dict:
    if mode not in {"auto", "semi", "man"}:
        return {"ok": False, "error": "Mode is auto, semi, or man."}
    cfg = load_config()
    cfg["mode"] = mode
    save_config(cfg)
    return {"ok": True, "mode": mode}


def allowed(calls: list[tuple[str, str, dict]]) -> bool:
    granted = set(load_config().get("alwaysAllow") or [])
    return all(f"{server}.{tool}" in granted for server, tool, _args in calls)


def gated(calls: list[tuple[str, str, dict]], mode: str | None = None) -> bool:
    chosen = mode if mode in {"auto", "semi", "man"} else current_mode()
    if chosen == "auto":
        return False
    if chosen == "semi" and all(tool in READONLY for _server, tool, _args in calls):
        return False
    return not allowed(calls)


def grant(calls: list[tuple[str, str, dict]]) -> None:
    cfg = load_config()
    have = set(cfg["alwaysAllow"])
    for server, tool, _args in calls:
        have.add(f"{server}.{tool}")
    cfg["alwaysAllow"] = sorted(have)
    save_config(cfg)


def pack(reply: str, commands: list[str], runtime: str, op: str, state: dict, needs: bool = False, proposal_id: str = "", calls: list | None = None, question: dict | None = None, suggestions: list | None = None) -> dict:
    _model, _vocab, _stoi, meta = model_bundle()
    body = {
        "ok": True,
        "reply": reply,
        "commands": commands,
        "runtime": runtime,
        "op": op,
        "state": state,
        "needsApproval": needs,
        "proposalId": proposal_id,
        "calls": calls or [],
        "model": {
            "name": "si-pcb-cad",
            "stack": "pytorch",
            "heldout_exact": meta.get("heldout_exact"),
            "params": meta.get("params"),
        },
    }
    if question:
        body["question"] = question
    if suggestions:
        body["suggestions"] = suggestions
    return body


def execute(calls: list[tuple[str, str, dict]], runtime: str, program: list[str], op: str) -> dict:
    state = snapshot(load_state())
    replies: list[str] = []
    commands: list[str] = []
    for server_id, tool, args in calls:
        try:
            hit = call_tool(server_id, tool, args)
        except (urllib.error.URLError, RuntimeError, TimeoutError, OSError) as exc:
            detail = str(exc).strip()
            if not detail or detail == exc.__class__.__name__:
                detail = "the server gave no reason"
            replies.append(f"{server_id} refused the call: {detail}")
            commands.append(f"{server_id}.{tool}")
            continue
        replies.append(hit["text"] or "Done.")
        commands.append(f"{server_id}.{tool}")
        if hit.get("state"):
            state = hit["state"]
    return pack(" ".join(replies), commands, runtime, op, state, calls=public_calls(calls))


_ROBOT_HINT = re.compile(r"\b(robot|robotics|humanoid|drone|uav|joint|gripper|amr|agv|quadruped|manipulator|flight)\b", re.I)
_COMPUTER_HINT = re.compile(r"\b(computer|motherboard|cpu|gpu|ddr|pcie|laptop|server|atx|dimm|nvme|desktop|workstation|thunderbolt|hdmi|chipset|bios|uefi|sodimm|nic)\b", re.I)


_SENSOR_HINT = re.compile(r"\b(sensor|sensors|switch|switches|thermistor|thermocouple|relay|humidity|proximity)\b", re.I)
_POWER_HINT = re.compile(r"\b(power|converter|inverter|rectifier|bms|smps)\b", re.I)
_LABELS = {"power": "Power", "robot": "Robotics", "computer": "Computer", "sensor": "Sensor"}


def _choose_catalog(text: str, hits: list[tuple[str, dict | None]]) -> tuple[str | None, dict | None]:
    """Keep the longest board name. A tie stays on the catalog the words point to."""
    hits = [(name, row) for name, row in hits if row]
    if not hits:
        return None, None
    if len(hits) == 1:
        return hits[0]
    best = max(int(row.get("span") or 0) for _, row in hits)
    top = [(name, row) for name, row in hits if int(row.get("span") or 0) == best]
    if len(top) == 1:
        return top[0]
    hints = {"power": _POWER_HINT, "robot": _ROBOT_HINT, "computer": _COMPUTER_HINT, "sensor": _SENSOR_HINT}
    hinted = [(name, row) for name, row in top if hints[name].search(text)]
    if len(hinted) == 1:
        return hinted[0]
    text_out = "That name is in more than one catalog. " + " ".join(f"{_LABELS[name]}: {row['text']}" for name, row in top)
    return "both", {"mode": "ask", "id": "", "text": text_out, "span": best}


def designer_turn(text: str, approved: bool = False, mode: str | None = None) -> dict:
    from py.si.engine import _params, _work, absorb_answer, design_sonar_booster, load_state, remember, save_state, snapshot, sonar_booster_task, sonar_decision, sonar_suggestions
    from py.si.graph import answer

    state = load_state()
    pending = _work(state).get("ask") or {}
    waiting = pending.get("task") == "sonar-booster"
    ratings = bool(re.search(r"\d+(?:\.\d+)?\s*(?:v|a|khz|%)?\b", text.lower())) or bool(re.search(r"\b(?:use )?(?:the )?suggestions?\b", text.lower()))
    if sonar_booster_task(text) or (waiting and ratings):
        prior = pending.get("text") or ""
        asked = int(pending.get("n") or 0)
        field = str(pending.get("field") or "")
        utterance = text.strip()
        if waiting and not sonar_booster_task(text):
            combined = absorb_answer(field, utterance, prior) if field else f"{prior} {utterance}".strip()
        else:
            combined = f"{prior} {utterance}".strip() if waiting else utterance
        prefer = None
        if not waiting:
            model, vocab, stoi, _meta = model_bundle()
            program = predict(model, utterance, vocab, stoi, "cpu")
            if program and program[0] == "ASK" and program[1] in {"vin", "vout", "iout", "freq", "eff"}:
                prefer = program[1]
        decision = sonar_decision(combined, asked, prefer)
        if decision["kind"] == "ask":
            card = decision["card"]
            field = str(card.get("field") or "")
            options = ", ".join(option["label"] + (" (recommended)" if i == card["recommendedIndex"] else "") for i, option in enumerate(card["options"]))
            report = f"{card['header']}\n{card['question']}\nSuggestions: {options}\nCustom: type your own value"
            _work(state)["ask"] = {"task": "sonar-booster", "text": combined, "field": field, "n": asked + 1}
            remember(state, utterance, report, ["ask"])
            save_state(state)
            return pack(report, ["ask"], "power", "ask_user", snapshot(state), question=card)
        note = decision.get("note") or ""
        report = (note + " " if note else "") + design_sonar_booster(state, decision["spec"])
        _work(state)["ask"] = {}
        remember(state, utterance, report, ["sonar-booster"])
        save_state(state)
        return pack(report, ["sonar-booster"], "power", "design_sonar", snapshot(state), suggestions=sonar_suggestions(decision["spec"]))

    from py.si.engine import series_led_task

    if series_led_task(text):
        from py.si.engine import design_series_led

        model, vocab, stoi, _meta = model_bundle()
        program = predict(model, text, vocab, stoi, "cpu", raw=True)
        state = load_state()
        report = f"Decision: {program[0]}.\n" + design_series_led(state, text)
        remember(state, text.strip(), report, ["series-led"])
        save_state(state)
        return pack(report, ["series-led"], "pytorch-client", "design_series_led", snapshot(state))

    planned = sentence_plan(text)
    if planned:
        action = planned
        runtime = "sieda"
        calls = plan(action)
        state = snapshot(load_state())
        resolved, problem = resolve(calls)
        if problem:
            return pack(problem, [], runtime, "batch", state)
        if not approved and gated(resolved, mode):
            proposal_id = secrets.token_hex(4)
            with _GUARD:
                _hold(proposal_id, {"calls": resolved, "runtime": runtime, "program": [], "op": "batch"})
            return pack(
                "Approval required before this MCP call.",
                [f"{server}.{tool}" for server, tool, _args in resolved],
                runtime,
                "batch",
                state,
                needs=True,
                proposal_id=proposal_id,
                calls=public_calls(resolved),
            )
        return execute(resolved, runtime, [], "batch")

    beside = place_beside(text)
    if beside is not None:
        action = beside
        runtime = "sieda"
        if action.get("op") == "note":
            return pack(str(action.get("text")), ["hear"], runtime, "note", snapshot(load_state()))
        calls = plan(action)
        state = snapshot(load_state())
        resolved, problem = resolve(calls)
        if problem:
            return pack(problem, [], runtime, action["op"], state)
        if not approved and gated(resolved, mode):
            proposal_id = secrets.token_hex(4)
            with _GUARD:
                _hold(proposal_id, {"calls": resolved, "runtime": runtime, "program": [], "op": action["op"]})
            return pack(
                "Approval required before this MCP call.",
                [f"{server}.{tool}" for server, tool, _args in resolved],
                runtime,
                action["op"],
                state,
                needs=True,
                proposal_id=proposal_id,
                calls=public_calls(resolved),
            )
        return execute(resolved, runtime, [], action["op"])

    hit = answer(text, float(_params(load_state())["min_clearance_mm"]))
    power_action = None
    robot_action = None
    computer_action = None
    sensor_action = None
    if hit is None:
        from py.si.computer import lookup as computer_lookup
        from py.si.power import lookup
        from py.si.robot import lookup as robot_lookup
        from py.si.sensor import lookup as sensor_lookup

        name, chosen = _choose_catalog(text, [
            ("power", lookup(text)),
            ("robot", robot_lookup(text)),
            ("computer", computer_lookup(text)),
            ("sensor", sensor_lookup(text)),
        ])
        if chosen and chosen["mode"] == "ask":
            state = load_state()
            _work(state)["focus"] = chosen["text"].split(".")[0]
            remember(state, text.strip(), chosen["text"], [name or "both"])
            save_state(state)
            return pack(chosen["text"], [name or "both"], name or "both", "lookup", snapshot(state))
        if chosen and chosen["mode"] == "set" and name == "power":
            power_action = {"op": "power_select", "kind": chosen["id"], "draw": bool(chosen.get("draw"))}
        elif chosen and chosen["mode"] == "set" and name == "robot":
            robot_action = {"op": "robot_select", "kind": chosen["id"]}
        elif chosen and chosen["mode"] == "set" and name == "computer":
            computer_action = {"op": "computer_select", "kind": chosen["id"]}
        elif chosen and chosen["mode"] == "set" and name == "sensor":
            sensor_action = {"op": "sensor_select", "kind": chosen["id"]}
    if hit:
        state = load_state()
        work = _work(state)
        work["focus"] = hit["focus"]
        chosen = hit.get("set")
        if chosen:
            params = work.setdefault("params", {})
            if chosen.get("layers"):
                params["layers"] = chosen["layers"]
            if chosen.get("material"):
                params["material"] = chosen["material"]
            from py.si.engine import stack_line

            work["stack"] = stack_line(state)
        remember(state, text.strip(), hit["text"], ["graph"])
        save_state(state)
        return pack(hit["text"], ["graph"], "graph", "lookup", snapshot(state))
    action = None
    program: list[str] = []
    runtime = "power"
    if power_action:
        action = power_action
    elif robot_action:
        action = robot_action
        runtime = "robot"
    elif computer_action:
        action = computer_action
        runtime = "computer"
    elif sensor_action:
        action = sensor_action
        runtime = "sensor"
    else:
        runtime = "hear"
        from py.si.hear import hear

        heard = hear(text)
        if heard is not None:
            action = heard
        else:
            action = parse_cli(text)
            runtime = "cli-client"
    if action is None:
        model, vocab, stoi, _meta = model_bundle()
        program = predict(model, text, vocab, stoi, "cpu")
        action = program_to_action(program)
        runtime = "pytorch-client"
    if action and action.get("op") == "ask_spec":
        state = load_state()
        reply = (
            "I need the ratings before I design this. Pick a suggestion or type your own value.\n"
            "What is the input voltage?\n  suggestions: 12 V, 24 V\n  custom: type your own value\n"
            "What is the output voltage?\n  suggestions: 48 V, 60 V\n  custom: type your own value\n"
            "What is the continuous output current?\n  suggestions: 1 A, 1.5 A, 2 A\n  custom: type your own value\n"
            "What switching frequency should the booster use?\n  suggestions: 100 kHz, 200 kHz, 500 kHz\n  custom: type your own value\n"
            "What efficiency should I use to calculate the input current?\n  suggestions: 85%, 90%, 95%\n  custom: type your own value"
        )
        remember(state, text.strip(), reply, ["ask"])
        save_state(state)
        return pack(reply, ["ask"], runtime, "ask_spec", snapshot(state))
    if action and action.get("op") == "crew":
        from py.si.agents import run_crew

        return run_crew(text, approved=approved, mode=mode)
    if action and action.get("op") == "agent":
        from py.si.agents import run_agent

        return run_agent(str(action.get("agent") or ""), text, approved=approved, mode=mode)
    calls = plan(action)
    state = snapshot(load_state())
    op = str(action.get("op") or "")
    if op == "note":
        return pack(str(action.get("text")), ["hear"], runtime, op, state)
    asked_help = bool(re.search(r"\b(help|commands|what can you do)\b", text.lower()))
    if not calls and op != "error" and not asked_help:
        guess = fallback_plan(text)
        if guess and guess.get("note"):
            return pack(guess["note"], ["fallback"], "fallback", "note", state)
        if guess:
            resolved = [guess["call"]]
            if not approved and (not guess["readonly"] or gated(resolved, mode)):
                proposal_id = secrets.token_hex(4)
                with _GUARD:
                    _hold(proposal_id, {"calls": resolved, "runtime": "fallback", "program": [], "op": guess["call"][1]})
                return pack(
                    f"Approval required: no si-llm command matched, so this would call {guess['call'][1]}.",
                    [f"{server}.{tool}" for server, tool, _args in resolved],
                    "fallback",
                    guess["call"][1],
                    state,
                    needs=True,
                    proposal_id=proposal_id,
                    calls=public_calls(resolved),
                )
            return execute(resolved, "fallback", [], guess["call"][1])
    if op == "help" or (not calls and op != "error"):
        reply = HELP if op == "help" else "Say that again as a PCB place/net/flow or a CAD sketch/extrude/hole."
        return pack(reply, ["help"], runtime, op, state)
    if op == "error":
        return pack(str(action.get("text")), [text.strip()], runtime, op, state)
    resolved, problem = resolve(calls)
    if problem:
        return pack(problem, [], runtime, op, state)
    if not approved and gated(resolved, mode):
        proposal_id = secrets.token_hex(4)
        with _GUARD:
            _hold(proposal_id, {"calls": resolved, "runtime": runtime, "program": program, "op": op})
        return pack(
            "Approval required before this MCP call.",
            [f"{server}.{tool}" for server, tool, _args in resolved],
            runtime,
            op,
            state,
            needs=True,
            proposal_id=proposal_id,
            calls=public_calls(resolved),
        )
    return execute(resolved, runtime, program, op)


def datasheet_turn(text: str, mode: str | None = None) -> dict:
    from py.si.datasheet import parse

    sheet = ROOT / "datasheet.txt"
    clean = text.strip()
    if not clean:
        return pack("The datasheet was empty.", [], "datasheet", "build_datasheet", snapshot(load_state()))
    sheet.parent.mkdir(parents=True, exist_ok=True)
    sheet.write_text(clean[:200_000])
    variants, gaps = parse(clean)
    state = snapshot(load_state())
    if not variants:
        return pack("Datasheet held. " + " ".join(gaps), [], "datasheet", "build_datasheet", state)
    calls = plan({"op": "build_datasheet", "variants": variants})
    resolved, problem = resolve(calls)
    if problem:
        return pack(problem, [], "datasheet", "build_datasheet", state)
    if gated(resolved, mode):
        proposal_id = secrets.token_hex(4)
        with _GUARD:
            _hold(proposal_id, {"calls": resolved, "runtime": "datasheet", "program": [], "op": "build_datasheet"})
        reply = "Approval required before building " + ", ".join(row["package"] for row in variants) + " from the datasheet."
        if gaps:
            reply += " " + " ".join(gaps)
        return pack(
            reply,
            [f"{server}.{tool}" for server, tool, _args in resolved],
            "datasheet",
            "build_datasheet",
            state,
            needs=True,
            proposal_id=proposal_id,
            calls=public_calls(resolved),
        )
    result = execute(resolved, "datasheet", [], "build_datasheet")
    if gaps:
        result["reply"] = result["reply"] + " " + " ".join(gaps)
    return result


_MPN = (
    ("esp32-s3-wroom-1", "ESP32-S3-WROOM-1"),
    ("esp32-s3", "ESP32-S3-WROOM-1"),
    ("esp32-wroom-32e", "ESP32-WROOM-32E"),
    ("ams1117-3.3", "AMS1117-3.3"),
    ("ams1117", "AMS1117-3.3"),
    ("ap2112k-3.3", "AP2112K-3.3"),
    ("ap2112", "AP2112K-3.3"),
)
_PIN = re.compile(r"\b([a-z]+\d+)\.([a-z0-9]+)\b", re.I)
_BESIDE = re.compile(r"\b([rcdlqjuy]\d+)\b.*\bnext to\b.*\b([rcdlqjuy]\d+)\b", re.I)
_COORD = re.compile(r"\b([A-Za-z]+\d+)\b(?:\s+[A-Za-z0-9.+-]+)?\s+\(\s*([-+]?\d+(?:\.\d+)?)\s*,\s*([-+]?\d+(?:\.\d+)?)\s*\)")
_NET_SKIP = {"the", "a", "an", "this", "that", "to", "from", "and", "on", "its", "their", "one", "new", "between"}
_GROUP_WORDS = {"pcb", "sch", "schematic", "sim", "output", "project", "library", "verify", "si", "render", "mcp"}
_FALLBACK_SKIP = {
    "project_new",
    "project_open",
    "project_load_example",
    "project_load_json",
    "project_save",
    "project_cloud",
    "project_git",
    "project_live",
    "project_lessons",
    "project_assistant",
    "pcb_reset",
    "batch",
}


def _stem(word: str) -> str:
    return word[:-1] if len(word) > 3 and word.endswith("s") and not word.endswith("ss") else word


def fallback_plan(text: str) -> dict | None:
    """A server tool whose name words are all in the sentence, or a note if two tie."""
    said = {_stem(word) for word in re.findall(r"[a-z0-9]+", text.lower())}
    refs = [ref.upper() for ref in re.findall(r"\b([a-z]{1,3}\d+)\b", text.lower())]
    found: list[tuple[int, str, dict, bool]] = []
    for row in _live_rows():
        try:
            listed = rpc(row, "tools/list").get("tools") or []
        except Exception:
            continue
        for tool in listed:
            name = str(tool.get("name") or "")
            parts = [_stem(part) for part in name.lower().split("_") if part]
            core = [part for part in parts if part not in _GROUP_WORDS]
            if not core or name in _FALLBACK_SKIP or not all(part in said for part in core):
                continue
            required = list((tool.get("inputSchema") or {}).get("required") or [])
            if required == ["ref"] and refs:
                args = {"ref": refs[0]}
            elif required:
                continue
            else:
                args = {}
            hints = tool.get("annotations") or {}
            readonly = bool(hints.get("readOnlyHint")) or name in READONLY
            score = 10 * len(core) + (1 if parts and parts[0] in said else 0)
            found.append((score, row["id"], {"name": name, "args": args}, readonly))
    if not found:
        return None
    found.sort(key=lambda hit: (-hit[0], len(hit[2]["name"])))
    best = [hit for hit in found if hit[0] == found[0][0]]
    names = sorted({hit[2]["name"] for hit in best})
    if len(names) > 1:
        return {"note": "Did you mean " + " or ".join(names[:4]) + "? Say it with that tool's words."}
    _score, server, picked, readonly = best[0]
    return {"call": (server, picked["name"], picked["args"]), "readonly": readonly}


_CHIP_KINDS = {
    "pin": "pin",
    "pins": "pin",
    "pinout": "pin",
    "decap": "decap",
    "decoupling": "decap",
    "power": "power",
    "io": "io",
    "clock": "clock",
    "reset": "reset",
    "boot": "boot",
    "thermal": "thermal",
    "si": "si",
    "pi": "pi",
}
_INDUSTRY_ALIAS = {
    "auto": "automotive",
    "car": "automotive",
    "automatic": "automotive",
    "aviation": "aerospace",
    "avionics": "aerospace",
    "robotics": "robot",
    "robots": "robot",
}


def _live_rows() -> list[dict]:
    """Connected servers that answer. Empty when none are up."""
    try:
        return [row for row in probe() if row.get("ok")]
    except Exception:
        return []


def _offers(rows: list[dict], tool: str) -> bool:
    return any(tool in (row.get("tools") or []) for row in rows)


def _server_refs(rows: list[dict]) -> set[str]:
    """References already used on the connected board."""
    used: set[str] = set()
    for row in rows:
        if "pcb_status" not in (row.get("tools") or []):
            continue
        try:
            text = call_tool(row["id"], "pcb_status", {})["text"]
        except Exception:
            continue
        used |= {ref.upper() for ref in re.findall(r"\b([A-Za-z]{1,3}\d+)\b", text)}
    return used


def _free_ref(prefix: str) -> str:
    state = load_state()
    used = {str(row.get("ref") or "").upper() for row in (state.get("work") or {}).get("symbols") or []}
    used |= {str(row.get("ref") or "").upper() for row in state["pcb"].get("parts") or []}
    used |= _server_refs(_live_rows())
    number = 1
    while f"{prefix}{number}" in used and number < 400:
        number += 1
    return f"{prefix}{number}"


def _net_name(text: str) -> str:
    """Keep the name the sentence gives. 'led net' is LED, not NET."""
    low = text.lower()
    before = re.search(r"\b([a-z][a-z0-9]{0,15})\s+net\b", low)
    if before and before.group(1) not in _NET_SKIP:
        return before.group(1).upper()
    after = re.search(r"\bnet\s+([a-z][a-z0-9]{0,15})\b", low)
    if after and after.group(1) not in _NET_SKIP:
        return after.group(1).upper()
    if re.search(r"\b(gnd|ground)\b", low):
        return "GND"
    if re.search(r"\b5\s*v\b", low) or "5v" in low:
        return "5V"
    if re.search(r"\b3\s*v3\b|\b3v3\b", low):
        return "3V3"
    return ""


def _named_part(text: str) -> str:
    low = text.lower()
    for alias, part in _MPN:
        if alias in low:
            return part
    return ""


def _without_sieda_duplicates(plan_: dict) -> dict:
    """SiEDA's pcb_net also ties the schematic, so the same sch_wire is not sent again."""
    if plan_.get("op") != "batch":
        return plan_
    rows = _live_rows()
    if not any(str(row.get("server") or "").lower() == "sieda" for row in rows):
        return plan_
    boards = {(step.get("name"), tuple(step.get("pins") or [])) for step in plan_["steps"] if step.get("op") == "pcb_net"}
    steps = [
        step
        for step in plan_["steps"]
        if not (step.get("op") == "sch_wire" and (step.get("name"), tuple(step.get("pins") or [])) in boards)
    ]
    return {**plan_, "steps": steps}


def sentence_plan(text: str) -> dict | None:
    planned = _sentence_plan(text)
    return _without_sieda_duplicates(planned) if planned else planned


def _sentence_plan(text: str) -> dict | None:
    """One sentence can be several adds and pin nets. SiEDA should not have to guess."""
    words = re.findall(r"[a-z0-9]+", text.lower())
    bag = set(words)
    if len(words) <= 4 and bag & {"undo", "redo"}:
        tool = "project_redo" if "redo" in bag else "project_undo"
        if _offers(_live_rows(), tool):
            return {"op": "server_tool", "tool": tool}
    if "check" in bag and "industry" not in bag:
        kinds = [_CHIP_KINDS[word] for word in words if word in _CHIP_KINDS]
        if kinds:
            return {"op": "chip_check", "kind": kinds[0]}
    if "industry" in bag:
        from py.si.engine import INDUSTRY

        if "check" in bag:
            return {"op": "industry_check"}
        for word in words:
            kind = _INDUSTRY_ALIAS.get(word, word)
            if kind != "industry" and kind in INDUSTRY:
                return {"op": "set_industry", "kind": kind}
    change = re.search(r"\b(?:change|set|update)\s+([rcdlqjuy]\d+)\b", text, re.I)
    if change:
        ref = change.group(1).upper()
        value = re.search(r"\b(\d+(?:\.\d+)?[kKmMuUnNpPrR]?\d*)\b", text[change.end() :])
        size = re.search(r"\b(0201|0402|0603|0805|1206)\b", text, re.I)
        step = {"op": "sch_set", "ref": ref}
        if value:
            step["value"] = value.group(1)
        if size:
            step["size"] = size.group(1)
        if len(step) > 2:
            return step
    low = re.sub(r"[^a-z0-9.+]+", " ", text.lower())
    pins = [f"{ref.upper()}.{pin.upper()}" for ref, pin in _PIN.findall(text)]
    net = _net_name(text)
    if len(pins) >= 2 and net:
        return {"op": "batch", "steps": [{"op": "sch_wire", "name": net, "pins": pins}, {"op": "pcb_net", "name": net, "pins": pins}]}
    if "led" in low.split() and "resistor" in low.split() and ("5v" in low or "5 v" in text.lower()):
        return {
            "op": "batch",
            "steps": [
                {"op": "sch_add", "ref": "D1", "pkg": "led", "size": "0603"},
                {"op": "sch_add", "ref": "R1", "pkg": "res", "value": "330", "size": "0603"},
                {"op": "sch_add", "ref": "J1", "pkg": "conn"},
                {"op": "sch_wire", "name": "5V", "pins": ["J1.1", "R1.1"]},
                {"op": "sch_wire", "name": "LED", "pins": ["R1.2", "D1.A"]},
                {"op": "sch_wire", "name": "GND", "pins": ["D1.K", "J1.2"]},
                {"op": "pcb_add", "ref": "J1", "pkg": "conn", "x": 12, "y": 20},
                {"op": "pcb_add", "ref": "R1", "pkg": "res", "x": 28, "y": 20, "value": "330", "size": "0603"},
                {"op": "pcb_add", "ref": "D1", "pkg": "led", "x": 44, "y": 20, "size": "0603"},
                {"op": "pcb_net", "name": "5V", "pins": ["J1.1", "R1.1"]},
                {"op": "pcb_net", "name": "LED", "pins": ["R1.2", "D1.A"]},
                {"op": "pcb_net", "name": "GND", "pins": ["D1.K", "J1.2"]},
            ],
        }
    part = _named_part(text)
    if part and any(word in low.split() for word in ("place", "add", "use")):
        pkg = "mcu" if part.startswith("ESP32") else "ldo"
        named = re.findall(r"\b([uU]\d+)\b", text)
        ref = named[-1].upper() if named else _free_ref("U")
        step = {"op": "sch_add", "ref": ref, "pkg": pkg, "mpn": part}
        return {"op": "batch", "steps": [step]}
    return None


def _status_coord(text: str, ref: str) -> tuple[float, float] | None:
    for found, x, y in _COORD.findall(text):
        if found.upper() != ref:
            continue
        try:
            return float(x), float(y)
        except ValueError:
            continue
    return None


def place_beside(text: str) -> dict | None:
    match = _BESIDE.search(text)
    if match is None:
        return None
    ref, anchor = match.group(1).upper(), match.group(2).upper()
    status = ""
    if any(row["id"] == "pcb" and row.get("target") for row in configured()):
        try:
            status = str(call_tool("pcb", "pcb_status", {}).get("text") or "")
        except (urllib.error.URLError, RuntimeError, TimeoutError, OSError, ValueError):
            status = ""
    if not status:
        from py.si.engine import apply

        try:
            status = apply(load_state(), {"op": "pcb_status"})
        except (KeyError, TypeError, ValueError):
            return {"op": "note", "text": f"The board status could not be read, so {ref} was not moved next to {anchor}."}
    pos = _status_coord(status, anchor)
    if pos is None:
        return {"op": "note", "text": f"{anchor} is not on the board, so {ref} has nowhere to sit."}
    pkg = {"r": "res", "c": "cap", "l": "ind", "d": "led", "q": "fet", "u": "mcu", "j": "conn", "y": "crystal"}.get(ref[0].lower(), "conn")
    return {"op": "pcb_add", "ref": ref, "pkg": pkg, "x": pos[0] + 4, "y": pos[1]}


def decide(proposal_id: str, decision: str) -> dict:
    with _GUARD:
        item = _PENDING.pop(proposal_id, None)
    state = snapshot(load_state())
    if item is not None and time.monotonic() - item.get("at", 0.0) > PENDING_TTL:
        item = None
    if item is None:
        return pack("That approval expired. Ask again.", [], "client", "", state)
    if decision == "deny":
        return pack("Denied. The MCP server was not called.", [], item["runtime"], item["op"], state)
    if decision == "always":
        grant(item["calls"])
    elif decision != "allow":
        return pack("Use allow, always, or deny.", [], item["runtime"], item["op"], state)
    return execute(item["calls"], item["runtime"], item["program"], item["op"])
