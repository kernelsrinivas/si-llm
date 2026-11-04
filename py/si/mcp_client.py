"""MCP client. You add a connection. Tool calls wait for approval."""

from __future__ import annotations

import json
import os
import secrets
import select
import shlex
import subprocess
import threading
import urllib.error
import urllib.request

from py.si.engine import HELP, ROOT, load_state, parse_cli, snapshot
from py.si.net import load, predict, program_to_action

CONFIG = ROOT / "mcp.json"
PCB_MCP = os.environ.get("SI_PCB_MCP", "http://127.0.0.1:8766/mcp")
CAD_MCP = os.environ.get("SI_CAD_MCP", "http://127.0.0.1:8767/mcp")
PRESETS = {
    "pcb": {"name": "pcb", "title": "PCB", "transport": "http", "target": PCB_MCP},
    "cad": {"name": "cad", "title": "CAD", "transport": "http", "target": CAD_MCP},
}

_MODEL = None
_RPC_ID = 0
_PENDING: dict[str, dict] = {}
_STDIO: dict[str, "StdioSession"] = {}
_GUARD = threading.Lock()


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
    if not clean or len(clean) > 240:
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

    def rpc(self, method: str, params: dict | None = None) -> dict:
        global _RPC_ID
        if self.proc.poll() is not None or self.proc.stdin is None or self.proc.stdout is None:
            raise RuntimeError("stdio MCP exited")
        _RPC_ID += 1
        body = {"jsonrpc": "2.0", "id": _RPC_ID, "method": method}
        if params is not None:
            body["params"] = params
        self.proc.stdin.write(json.dumps(body) + "\n")
        self.proc.stdin.flush()
        ready, _, _ = select.select([self.proc.stdout], [], [], 8)
        if not ready:
            raise TimeoutError("stdio MCP timed out")
        line = self.proc.stdout.readline()
        payload = json.loads(line or "{}")
        if "error" in payload:
            raise RuntimeError(payload["error"].get("message") or "MCP error")
        return payload.get("result") or {}

    def close(self) -> None:
        if self.proc.poll() is None:
            self.proc.terminate()


def http_rpc(url: str, method: str, params: dict | None = None) -> dict:
    global _RPC_ID
    _RPC_ID += 1
    body = {"jsonrpc": "2.0", "id": _RPC_ID, "method": method}
    if params is not None:
        body["params"] = params
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=8) as res:
        payload = json.loads(res.read().decode())
    if "error" in payload:
        raise RuntimeError(payload["error"].get("message") or "MCP error")
    return payload.get("result") or {}


def rpc(row: dict, method: str, params: dict | None = None) -> dict:
    if row.get("transport") == "stdio":
        with _GUARD:
            session = _STDIO.get(row["id"])
            if session is None or session.proc.poll() is not None:
                session = StdioSession(row["target"])
                _STDIO[row["id"]] = session
        return session.rpc(method, params)
    return http_rpc(row["target"], method, params)


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
            }
        )
    return rows


def probe() -> list[dict]:
    found = []
    for row in configured():
        try:
            init = rpc(row, "initialize")
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
    result = rpc(row, "tools/call", {"name": name, "arguments": arguments or {}})
    text = ""
    content = result.get("content") or []
    if content:
        text = str(content[0].get("text") or "")
    state = (result.get("structuredContent") or {}).get("state")
    return {"text": text, "state": state, "server": server_id, "tool": name}


def plan(action: dict) -> list[tuple[str, str, dict]]:
    op = action.get("op")
    if op == "pcb_add":
        return [("pcb", "pcb_add", {"ref": action["ref"], "pkg": action["pkg"], "x": action["x"], "y": action["y"]})]
    if op == "pcb_net":
        return [("pcb", "pcb_net", {"name": action["name"], "a": action["a"], "b": action["b"]})]
    if op == "pcb_flow":
        return [("pcb", "pcb_flow", {})]
    if op == "pcb_drc":
        return [("pcb", "pcb_drc", {})]
    if op == "pcb_status":
        return [("pcb", "pcb_status", {})]
    if op == "pcb_reset":
        return [("pcb", "pcb_reset", {})]
    if op == "sch_add":
        return [("pcb", "sch_add", {"ref": action["ref"], "pkg": action["pkg"]})]
    if op == "sch_wire":
        return [("pcb", "sch_wire", {"name": action["name"], "a": action["a"], "b": action["b"]})]
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


READONLY = {"pcb_drc", "pcb_status", "cad_mass", "cad_status", "sch_erc", "sim_dc", "sim_tran", "view_3d", "fab_stack", "asm_bom", "chip_check", "industry_check", "cover_all", "impedance", "dfm", "via", "ipc_check"}


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


def pack(reply: str, commands: list[str], runtime: str, op: str, state: dict, needs: bool = False, proposal_id: str = "", calls: list | None = None) -> dict:
    _model, _vocab, _stoi, meta = model_bundle()
    return {
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


def execute(calls: list[tuple[str, str, dict]], runtime: str, program: list[str], op: str) -> dict:
    state = snapshot(load_state())
    replies: list[str] = []
    commands: list[str] = []
    for server_id, tool, args in calls:
        try:
            hit = call_tool(server_id, tool, args)
        except (urllib.error.URLError, RuntimeError, TimeoutError, OSError) as exc:
            replies.append(f"{server_id} refused the call ({exc.__class__.__name__}).")
            commands.append(f"{server_id}.{tool}")
            continue
        replies.append(hit["text"] or "Done.")
        commands.append(f"{server_id}.{tool}")
        if hit.get("state"):
            state = hit["state"]
    return pack(" ".join(replies), commands, runtime, op, state, calls=public_calls(calls))


def designer_turn(text: str, approved: bool = False, mode: str | None = None) -> dict:
    action = parse_cli(text)
    program: list[str] = []
    runtime = "cli-client"
    if action is None:
        model, vocab, stoi, _meta = model_bundle()
        program = predict(model, text, vocab, stoi, "cpu")
        action = program_to_action(program)
        runtime = "pytorch-client"
    calls = plan(action)
    state = snapshot(load_state())
    op = str(action.get("op") or "")
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
            _PENDING[proposal_id] = {"calls": resolved, "runtime": runtime, "program": program, "op": op}
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
    from pathlib import Path

    from py.si.datasheet import parse

    sheet = Path("/workspace/model/datasheet.txt")
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
            _PENDING[proposal_id] = {"calls": resolved, "runtime": "datasheet", "program": [], "op": "build_datasheet"}
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


def decide(proposal_id: str, decision: str) -> dict:
    with _GUARD:
        item = _PENDING.pop(proposal_id, None)
    state = snapshot(load_state())
    if item is None:
        return pack("That approval expired. Ask again.", [], "client", "", state)
    if decision == "deny":
        return pack("Denied. The MCP server was not called.", [], item["runtime"], item["op"], state)
    if decision == "always":
        grant(item["calls"])
    elif decision != "allow":
        return pack("Use allow, always, or deny.", [], item["runtime"], item["op"], state)
    return execute(item["calls"], item["runtime"], item["program"], item["op"])
