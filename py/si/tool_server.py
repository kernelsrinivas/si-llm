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
                "value": {"type": "string"},
                "size": {"type": "string"},
                "mpn": {"type": "string"},
            },
            "required": ["ref", "pkg", "x", "y"],
        },
    },
    {
        "name": "pcb_net",
        "description": "Tie two refs onto a named net.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "a": {"type": "string"},
                "b": {"type": "string"},
                "pins": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["name", "a", "b"],
        },
    },
    {"name": "pcb_delete", "description": "Remove a reference from the board.", "inputSchema": {"type": "object", "properties": {"ref": {"type": "string"}}, "required": ["ref"]}},
    {"name": "pcb_move", "description": "Move a reference to a new millimetre coordinate.", "inputSchema": {"type": "object", "properties": {"ref": {"type": "string"}, "x": {"type": "number"}, "y": {"type": "number"}}, "required": ["ref", "x", "y"]}},
    {"name": "pcb_rotate", "description": "Store a rotation in degrees. The drawing does not turn the pads.", "inputSchema": {"type": "object", "properties": {"ref": {"type": "string"}, "angle": {"type": "number"}}, "required": ["ref", "angle"]}},
    {"name": "pcb_copy", "description": "Copy a placed part to a new reference.", "inputSchema": {"type": "object", "properties": {"ref": {"type": "string"}, "to": {"type": "string"}, "x": {"type": "number"}, "y": {"type": "number"}}, "required": ["ref", "to"]}},
    {"name": "pcb_swap", "description": "Exchange the coordinates of two references.", "inputSchema": {"type": "object", "properties": {"a": {"type": "string"}, "b": {"type": "string"}}, "required": ["a", "b"]}},
    {"name": "pcb_flip", "description": "Store the part on the other side. The drawing stays a top view.", "inputSchema": {"type": "object", "properties": {"ref": {"type": "string"}}, "required": ["ref"]}},
    {"name": "pcb_find", "description": "Report one reference.", "inputSchema": {"type": "object", "properties": {"ref": {"type": "string"}}, "required": ["ref"]}},
    {"name": "power_select", "description": "Select a power-electronics board profile. A BMS design request also places the starter sheet.", "inputSchema": {"type": "object", "properties": {"kind": {"type": "string"}, "draw": {"type": "boolean"}}, "required": ["kind"]}},
    {"name": "robot_select", "description": "Select a robotics board profile. It stores the class and does not place a mechanism.", "inputSchema": {"type": "object", "properties": {"kind": {"type": "string"}}, "required": ["kind"]}},
    {"name": "computer_select", "description": "Select a computer board profile. It stores the class and does not solve signal integrity.", "inputSchema": {"type": "object", "properties": {"kind": {"type": "string"}}, "required": ["kind"]}},
    {"name": "sensor_select", "description": "Select a sensor or switch board profile. It stores the class and does not calculate the front end.", "inputSchema": {"type": "object", "properties": {"kind": {"type": "string"}}, "required": ["kind"]}},
    {"name": "pcb_flow", "description": "Run DRC, then pack Gerber and BOM if the board is clean.", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "pcb_drc", "description": "Design rule check for the current board.", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "pcb_status", "description": "List parts and nets.", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "pcb_reset", "description": "Clear the board.", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "sch_add", "description": "Add a symbol to the schematic.", "inputSchema": {"type": "object", "properties": {"ref": {"type": "string"}, "pkg": {"type": "string"}, "value": {"type": "string"}, "size": {"type": "string"}, "mpn": {"type": "string"}}, "required": ["ref", "pkg"]}},
    {"name": "sch_wire", "description": "Draw a schematic wire. pins may name more than two ends, such as U1.GND.", "inputSchema": {"type": "object", "properties": {"name": {"type": "string"}, "a": {"type": "string"}, "b": {"type": "string"}, "pins": {"type": "array", "items": {"type": "string"}}}, "required": ["name", "a", "b"]}},
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
    {"name": "desk", "description": "Trace width, filter, thermal loss, EDA script, replacement, spacing, EMI, or BOM table.", "inputSchema": {"type": "object", "properties": {"kind": {"type": "string"}, "value": {"type": "number"}}, "required": ["kind"]}},
    {"name": "feature_audit", "description": "Say which PCB features this product actually runs.", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "autoroute", "description": "Orthogonal single-layer autoroute, or rip the tracks.", "inputSchema": {"type": "object", "properties": {"which": {"type": "string"}}}},
    {"name": "build_circuit", "description": "Place a switch, PLC, PAC, or MCU starter board. Not a silicon layout.", "inputSchema": {"type": "object", "properties": {"kind": {"type": "string"}}, "required": ["kind"]}},
    {"name": "design_cell", "description": "Build an inverter, NAND2, or NOR2 from NMOS and PMOS. Teaching grid, not a foundry PDK.", "inputSchema": {"type": "object", "properties": {"kind": {"type": "string"}}, "required": ["kind"]}},
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
        return {"op": "pcb_add", "ref": args.get("ref"), "pkg": args.get("pkg"), "x": args.get("x"), "y": args.get("y"), "value": args.get("value"), "size": args.get("size"), "mpn": args.get("mpn")}
    if name == "pcb_net":
        return {"op": "pcb_net", "name": args.get("name"), "a": args.get("a"), "b": args.get("b"), "pins": args.get("pins")}
    if name == "pcb_delete":
        return {"op": "pcb_delete", "ref": args.get("ref")}
    if name == "pcb_move":
        return {"op": "pcb_move", "ref": args.get("ref"), "x": args.get("x"), "y": args.get("y")}
    if name == "pcb_rotate":
        return {"op": "pcb_rotate", "ref": args.get("ref"), "angle": args.get("angle")}
    if name == "pcb_copy":
        return {"op": "pcb_copy", "ref": args.get("ref"), "to": args.get("to"), "x": args.get("x"), "y": args.get("y")}
    if name == "pcb_swap":
        return {"op": "pcb_swap", "a": args.get("a"), "b": args.get("b")}
    if name == "pcb_flip":
        return {"op": "pcb_flip", "ref": args.get("ref")}
    if name == "pcb_find":
        return {"op": "pcb_find", "ref": args.get("ref")}
    if name == "power_select":
        return {"op": "power_select", "kind": args.get("kind"), "draw": bool(args.get("draw"))}
    if name == "robot_select":
        return {"op": "robot_select", "kind": args.get("kind")}
    if name == "computer_select":
        return {"op": "computer_select", "kind": args.get("kind")}
    if name == "sensor_select":
        return {"op": "sensor_select", "kind": args.get("kind")}
    if name in {"pcb_flow", "pcb_drc", "pcb_status", "pcb_reset", "cad_mass", "cad_status", "cad_reset", "sch_erc", "sim_dc", "sim_tran", "view_3d", "fab_gerber", "fab_stack", "asm_bom", "asm_pos", "industry_check", "cover_all", "handle_all", "place_sheet", "datasheet_rebuild", "pour", "dfm", "ipc_check"}:
        return {"op": name, **({"doc": args.get("doc")} if name == "ipc_check" else {})}
    if name == "feature_audit":
        return {"op": "feature_audit"}
    if name == "autoroute":
        return {"op": "autoroute", "which": args.get("which") or "all"}
    if name == "build_circuit":
        return {"op": "build_circuit", "kind": args.get("kind") or "mcu"}
    if name == "design_cell":
        return {"op": "design_cell", "kind": args.get("kind") or "inv"}
    if name == "desk":
        return {"op": "desk", "kind": args.get("kind"), "value": args.get("value"), "name": args.get("name") or ""}
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
        return {"op": "sch_add", "ref": args.get("ref"), "pkg": args.get("pkg"), "value": args.get("value"), "size": args.get("size"), "mpn": args.get("mpn")}
    if name == "sch_wire":
        return {"op": "sch_wire", "name": args.get("name"), "a": args.get("a"), "b": args.get("b"), "pins": args.get("pins")}
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
                self._send(200, {"ok": True, "server": server_name, "version": "0.9.0", "api": ["mcp"], "tools": [t["name"] for t in tools]})
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
            if method == "notifications/initialized" or req_id is None:
                self._send(202, {"ok": True})
                return
            if method == "initialize":
                self._send(
                    200,
                    {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "result": {
                            "protocolVersion": "2024-11-05",
                            "capabilities": {"tools": {}},
                            "serverInfo": {"name": server_name, "version": "0.9.0"},
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
        if method == "notifications/initialized" or req_id is None:
            continue
        if method == "initialize":
            result = {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": server_name, "version": "0.9.0"},
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
