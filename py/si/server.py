"""Designer gateway. Tool calls go out through the MCP client."""

from __future__ import annotations

import base64
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from py.si.agents import roster, run_agent, run_crew
from py.si.engine import load_state, snapshot
from py.si.mcp_client import VERSION, add_preset, add_server, current_mode, datasheet_turn, decide, designer_turn, pack, probe, remove_server, set_mode
from py.si.net import META

HOST = "127.0.0.1"
PORT = 8765


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args) -> None:
        return

    def _send(self, code: int, payload: dict) -> None:
        raw = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _read(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        return json.loads(self.rfile.read(length).decode() or "{}")

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path == "/health":
            servers = probe()
            meta = {}
            if META.exists():
                meta = json.loads(META.read_text())
            self._send(
                200,
                {
                    "ok": True,
                    "role": "mcp-client",
                    "version": VERSION,
                    "api": ["ask", "approve", "crew", "agent", "datasheet", "mcp"],
                    "auth": "bearer" if os.environ.get("SI_TOKEN") else "none",
                    "model": {
                        "name": "si-pcb-cad",
                        "stack": "pytorch",
                        "heldout_exact": meta.get("heldout_exact"),
                        "params": meta.get("params"),
                    },
                    "servers": servers,
                    "mode": current_mode(),
                    "tools": [f"{row['id']}.{name}" for row in servers for name in row["tools"]],
                },
            )
            return
        if path == "/state":
            self._send(200, {"ok": True, "state": snapshot(load_state())})
            return
        if path == "/agents":
            self._send(200, {"ok": True, "agents": roster()})
            return
        self._send(404, {"ok": False, "error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        if self.headers.get("Origin"):
            self._send(403, {"ok": False, "error": "browser origin is not accepted"})
            return
        token = os.environ.get("SI_TOKEN")
        if token:
            auth = self.headers.get("Authorization") or ""
            if auth != f"Bearer {token}" and self.headers.get("X-SI-Token") != token:
                self._send(401, {"ok": False, "error": "token required"})
                return
        path = self.path.split("?", 1)[0]
        try:
            body = self._read()
        except json.JSONDecodeError:
            self._send(400, {"ok": False, "error": "bad json"})
            return
        if path in {"/ask", "/cli"}:
            text = str(body.get("text") or body.get("line") or "").strip()
            if not text:
                self._send(400, {"ok": False, "error": "empty"})
                return
            approved = bool(body.get("approved"))
            mode = str(body.get("mode") or "").strip() or None
            if mode and mode not in {"auto", "semi", "man"}:
                self._send(400, {"ok": False, "error": "Mode is auto, semi, or man."})
                return
            self._send(200, designer_turn(text[:500], approved=approved, mode=mode))
            return
        if path == "/datasheet":
            raw_pdf = str(body.get("pdf") or "")
            text = str(body.get("text") or "")
            if raw_pdf:
                try:
                    data = base64.b64decode(raw_pdf[:2_000_000], validate=False)
                except (ValueError, TypeError):
                    self._send(400, {"ok": False, "error": "bad pdf"})
                    return
                text = pdf_text(data)
                if not text:
                    self._send(200, pack("This PDF has no text layer. A scan cannot be built. Upload a text datasheet or a PDF with selectable text.", [], "datasheet", "build_datasheet", snapshot(load_state())))
                    return
            if len(text) > 200_000:
                text = text[:200_000]
            self._send(200, datasheet_turn(text))
            return
        if path == "/approve":
            proposal_id = str(body.get("proposalId") or "").strip()
            decision = str(body.get("decision") or "").strip()
            if decision not in {"allow", "always", "deny"} or not proposal_id:
                self._send(400, {"ok": False, "error": "missing approval"})
                return
            self._send(200, decide(proposal_id[:32], decision))
            return
        if path == "/mode":
            self._send(200, set_mode(str(body.get("mode") or "")))
            return
        if path == "/agents":
            self._send(200, {"ok": True, "agents": roster()})
            return
        if path in {"/agent", "/crew"}:
            text = str(body.get("text") or "").strip()
            approved = bool(body.get("approved"))
            mode = str(body.get("mode") or "").strip() or None
            if mode and mode not in {"auto", "semi", "man"}:
                self._send(400, {"ok": False, "error": "Mode is auto, semi, or man."})
                return
            if path == "/agent":
                self._send(200, run_agent(str(body.get("agent") or "").strip(), text[:500], approved=approved, mode=mode))
                return
            self._send(200, run_crew(text[:500], approved=approved, mode=mode, resume=bool(body.get("resume"))))
            return
        if path == "/mcp/add":
            if body.get("preset"):
                self._send(200, add_preset(str(body.get("preset"))))
                return
            self._send(
                200,
                add_server(str(body.get("name") or ""), str(body.get("transport") or "http"), str(body.get("target") or "")),
            )
            return
        if path == "/mcp/remove":
            self._send(200, remove_server(str(body.get("name") or "")))
            return
        self._send(404, {"ok": False, "error": "not found"})


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"si client gateway on {HOST}:{PORT}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
