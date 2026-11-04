"""MCP servers exposed by the PCB tool and the CAD tool."""

from __future__ import annotations

import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from py.si.engine import dispatch, load_state, remember, save_state, snapshot

HOST = "127.0.0.1"

PCB_TOOLS = [
    {
        "name": "pcb_add",
        "description": "Place a package on the board.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "ref": {"type": "string"},
                "pkg": {"type": "string"},
                "x": {"type": "number"},
                "y": {"type": "number"},
            },
            "required": ["ref", "pkg", "x", "y"],
        },
    },
    {
        "name": "pcb_net",
        "description": "Tie two refs onto a named net.",
        "inputSchema": {
            "type": "object",
            "properties": {"name": {"type": "string"}, "a": {"type": "string"}, "b": {"type": "string"}},
            "required": ["name", "a", "b"],
        },
    },
    {"name": "pcb_flow", "description": "Run DRC, then pack Gerber and BOM if the board is clean.", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "pcb_drc", "description": "Design rule check for the current board.", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "pcb_status", "description": "List parts and nets.", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "pcb_reset", "description": "Clear the board.", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "sch_add", "description": "Add a symbol to the schematic.", "inputSchema": {"type": "object", "properties": {"ref": {"type": "string"}, "pkg": {"type": "string"}}, "required": ["ref", "pkg"]}},
    {"name": "sch_wire", "description": "Draw a schematic wire.", "inputSchema": {"type": "object", "properties": {"name": {"type": "string"}, "a": {"type": "string"}, "b": {"type": "string"}}, "required": ["name", "a", "b"]}},
    {"name": "sch_erc", "description": "Electrical rule check on the schematic.", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "fp_assign", "description": "Assign the library footprint for a ref.", "inputSchema": {"type": "object", "properties": {"ref": {"type": "string"}}, "required": ["ref"]}},
    {"name": "sim_dc", "description": "DC operating point.", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "sim_tran", "description": "Transient rail check.", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "view_3d", "description": "3D view of the placed board.", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "fab_gerber", "description": "Pack fabrication gerbers when footprints and DRC are clean.", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "fab_stack", "description": "State the fabrication stackup.", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "asm_bom", "description": "Assembly bill of materials.", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "asm_pos", "description": "Pick-and-place centroid file.", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "chip_check", "description": "Chip discipline check: pin, decap, power, io, clock, reset, boot, thermal, si, pi.", "inputSchema": {"type": "object", "properties": {"kind": {"type": "string"}}, "required": ["kind"]}},
    {"name": "set_industry", "description": "Set the industry: automotive, aerospace, marine, robot, or medical.", "inputSchema": {"type": "object", "properties": {"kind": {"type": "string"}}, "required": ["kind"]}},
    {"name": "set_board", "description": "Set the board class from a tiny circuit to a large motherboard.", "inputSchema": {"type": "object", "properties": {"kind": {"type": "string"}}, "required": ["kind"]}},
    {"name": "set_outline", "description": "Set the board outline in millimetres.", "inputSchema": {"type": "object", "properties": {"length": {"type": "number"}, "width": {"type": "number"}}, "required": ["length", "width"]}},
    {"name": "industry_check", "description": "Run the industry and board-class rules.", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "cover_all", "description": "Score the current board against every industry and every board class.", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "place_sheet", "description": "Place every schematic symbol that is not on the layout and assign footprints.", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "build_datasheet", "description": "Build a symbol, calculated footprint, circuit nets, placement, and 3D body for every package in a datasheet.", "inputSchema": {"type": "object", "properties": {"variants": {"type": "array"}}, "required": ["variants"]}},
    {"name": "datasheet_rebuild", "description": "Build from the last uploaded datasheet.", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "impedance", "description": "Approximate microstrip width for a target impedance.", "inputSchema": {"type": "object", "properties": {"ohms": {"type": "number"}}, "required": ["ohms"]}},
    {"name": "pour", "description": "Note a ground pour on the outer layers.", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "dfm", "description": "Shop starting numbers for track, annular ring, and mask.", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "via", "description": "Approximate via drill for a current.", "inputSchema": {"type": "object", "properties": {"amps": {"type": "number"}}, "required": ["amps"]}},
    {"name": "diff", "description": "Approximate a 90 ohm differential pair.", "inputSchema": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}},
    {"name": "set_ipc", "description": "Set IPC class 1, 2, or 3 and score the IPC set.", "inputSchema": {"type": "object", "properties": {"kind": {"type": "string"}}, "required": ["kind"]}},
    {"name": "ipc_check", "description": "Score the PCB IPC document set. Not a licensed certificate.", "inputSchema": {"type": "object", "properties": {"doc": {"type": "string"}}}},
    {"name": "handle_industry", "description": "Add the PCB element an industry still lacks.", "inputSchema": {"type": "object", "properties": {"kind": {"type": "string"}}, "required": ["kind"]}},
    {"name": "handle_board", "description": "Add the PCB element a board class still lacks.", "inputSchema": {"type": "object", "properties": {"kind": {"type": "string"}}, "required": ["kind"]}},
]

CAD_TOOLS = [
    {
        "name": "cad_sketch",
        "description": "Sketch a rectangular plate.",
        "inputSchema": {
            "type": "object",
            "properties": {"length": {"type": "number"}, "width": {"type": "number"}},
            "required": ["length", "width"],
        },
    },
    {
        "name": "cad_extrude",
        "description": "Extrude the current sketch.",
        "inputSchema": {
            "type": "object",
            "properties": {"thickness": {"type": "number"}},
            "required": ["thickness"],
        },
    },
    {
        "name": "cad_hole",
        "description": "Drill a through hole.",
        "inputSchema": {
            "type": "object",
            "properties": {"diameter": {"type": "number"}},
            "required": ["diameter"],
        },
    },
    {
        "name": "cad_fillet",
        "description": "Fillet the solid edges.",
        "inputSchema": {
            "type": "object",
            "properties": {"radius": {"type": "number"}},
            "required": ["radius"],
        },
    },
    {"name": "cad_chamfer", "description": "Chamfer the vertical edges.", "inputSchema": {"type": "object", "properties": {"size": {"type": "number"}}, "required": ["size"]}},
    {"name": "cad_shell", "description": "Hollow the solid to a wall thickness.", "inputSchema": {"type": "object", "properties": {"wall": {"type": "number"}}, "required": ["wall"]}},
    {"name": "cad_mass", "description": "Mass of the current 6061-T6 solid.", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "cad_status", "description": "Describe the current solid.", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "cad_reset", "description": "Clear the solid.", "inputSchema": {"type": "object", "properties": {}}},
]


def action_for(name: str, args: dict) -> dict | None:
    if name == "pcb_add":
        return {"op": "pcb_add", "ref": args.get("ref"), "pkg": args.get("pkg"), "x": args.get("x"), "y": args.get("y")}
    if name == "pcb_net":
        return {"op": "pcb_net", "name": args.get("name"), "a": args.get("a"), "b": args.get("b")}
    if name in {"pcb_flow", "pcb_drc", "pcb_status", "pcb_reset", "cad_mass", "cad_status", "cad_reset", "sch_erc", "sim_dc", "sim_tran", "view_3d", "fab_gerber", "fab_stack", "asm_bom", "asm_pos", "industry_check", "cover_all", "handle_all", "place_sheet", "datasheet_rebuild", "pour", "dfm", "ipc_check"}:
        return {"op": name, **({"doc": args.get("doc")} if name == "ipc_check" else {})}
    if name == "set_ipc":
        return {"op": "set_ipc", "kind": args.get("kind")}
    if name == "impedance":
        return {"op": "impedance", "ohms": args.get("ohms")}
    if name == "via":
        return {"op": "via", "amps": args.get("amps")}
    if name == "diff":
        return {"op": "diff", "name": args.get("name")}
    if name == "cad_chamfer":
        return {"op": "cad_chamfer", "size": args.get("size")}
    if name == "cad_shell":
        return {"op": "cad_shell", "wall": args.get("wall")}
    if name == "build_datasheet":
        return {"op": "build_datasheet", "variants": args.get("variants") or []}
    if name == "sch_add":
        return {"op": "sch_add", "ref": args.get("ref"), "pkg": args.get("pkg")}
    if name == "sch_wire":
        return {"op": "sch_wire", "name": args.get("name"), "a": args.get("a"), "b": args.get("b")}
    if name == "fp_assign":
        return {"op": "fp_assign", "ref": args.get("ref")}
    if name == "chip_check":
        return {"op": "chip_check", "kind": args.get("kind")}
    if name == "set_industry":
        return {"op": "set_industry", "kind": args.get("kind")}
    if name == "set_board":
        return {"op": "set_board", "kind": args.get("kind")}
    if name == "set_outline":
        return {"op": "set_outline", "length": args.get("length"), "width": args.get("width")}
    if name == "handle_industry":
        return {"op": "handle_industry", "kind": args.get("kind")}
    if name == "handle_board":
        return {"op": "handle_board", "kind": args.get("kind")}
    if name == "cad_sketch":
        return {"op": "cad_sketch", "length": args.get("length"), "width": args.get("width")}
    if name == "cad_extrude":
        return {"op": "cad_extrude", "thickness": args.get("thickness")}
    if name == "cad_hole":
        return {"op": "cad_hole", "diameter": args.get("diameter")}
    if name == "cad_fillet":
        return {"op": "cad_fillet", "radius": args.get("radius")}
    return None


def execute(name: str, args: dict) -> dict:
    action = action_for(name, args)
    if action is None:
        return {"text": f"Unknown tool {name}", "state": snapshot(load_state()), "isError": True}
    try:
        state = load_state()
        reply = dispatch(state, action)
        remember(state, name, reply, [name])
        save_state(state)
        return {"text": reply, "state": snapshot(state), "isError": False}
    except (KeyError, TypeError, ValueError):
        return {"text": f"{name} needs its arguments.", "state": snapshot(load_state()), "isError": True}


def make_handler(server_name: str, tools: list[dict]):
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
                self._send(200, {"ok": True, "server": server_name, "tools": [t["name"] for t in tools]})
                return
            self._send(404, {"ok": False})

        def do_POST(self) -> None:  # noqa: N802
            if self.path.split("?", 1)[0] != "/mcp":
                self._send(404, {"ok": False})
                return
            try:
                body = self._read()
            except json.JSONDecodeError:
                self._send(400, {"ok": False})
                return
            req_id = body.get("id")
            method = body.get("method")
            if method == "initialize":
                self._send(
                    200,
                    {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "result": {
                            "protocolVersion": "2024-11-05",
                            "capabilities": {"tools": {}},
                            "serverInfo": {"name": server_name, "version": "1.0.0"},
                        },
                    },
                )
                return
            if method == "tools/list":
                self._send(200, {"jsonrpc": "2.0", "id": req_id, "result": {"tools": tools}})
                return
            if method == "tools/call":
                params = body.get("params") or {}
                done = execute(str(params.get("name") or ""), params.get("arguments") or {})
                self._send(
                    200,
                    {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "result": {
                            "content": [{"type": "text", "text": done["text"]}],
                            "isError": done["isError"],
                            "structuredContent": {"state": done["state"]},
                        },
                    },
                )
                return
            self._send(
                200,
                {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": f"Unknown method {method}"}},
            )

    return Handler


def stdio_loop(server_name: str, tools: list[dict]) -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            body = json.loads(line)
        except json.JSONDecodeError:
            continue
        req_id = body.get("id")
        method = body.get("method")
        if method == "initialize":
            result = {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": server_name, "version": "1.0.0"},
            }
            response = {"jsonrpc": "2.0", "id": req_id, "result": result}
        elif method == "tools/list":
            response = {"jsonrpc": "2.0", "id": req_id, "result": {"tools": tools}}
        elif method == "tools/call":
            params = body.get("params") or {}
            done = execute(str(params.get("name") or ""), params.get("arguments") or {})
            response = {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": done["text"]}],
                    "isError": done["isError"],
                    "structuredContent": {"state": done["state"]},
                },
            }
        else:
            response = {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": f"Unknown method {method}"}}
        sys.stdout.write(json.dumps(response) + "\n")
        sys.stdout.flush()


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "stdio":
        which = sys.argv[2] if len(sys.argv) > 2 else "pcb"
        if which == "cad":
            stdio_loop("cad", CAD_TOOLS)
        else:
            stdio_loop("pcb", PCB_TOOLS)
        return
    which = sys.argv[1] if len(sys.argv) > 1 else "pcb"
    if which == "cad":
        name, port, tools = "cad", 8767, CAD_TOOLS
    else:
        name, port, tools = "pcb", 8766, PCB_TOOLS
    server = ThreadingHTTPServer((HOST, port), make_handler(name, tools))
    print(f"{name} mcp listening on {HOST}:{port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
