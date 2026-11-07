"""PCB and CAD session the model and the CLI both drive."""

from __future__ import annotations

import json
import math
import os
import re
from pathlib import Path

ROOT = Path(os.environ.get("SI_MODEL") or Path(__file__).resolve().parents[2] / "model")
SESSION = ROOT / "session.json"

PKG_ALIAS = {
    "usbc": "USB-C",
    "usb": "USB-C",
    "esp32": "ESP32",
    "ldo": "LDO",
    "imu": "IMU",
    "conn": "CONN",
    "connector": "CONN",
    "res": "RES",
    "resistor": "RES",
    "cap": "CAP",
    "capacitor": "CAP",
    "mcu": "MCU",
    "buck": "BUCK",
    "ant": "ANT",
    "antenna": "ANT",
    "bjt": "BJT",
    "transistor": "BJT",
    "npn": "BJT",
    "diode": "DIODE",
    "led": "LED",
    "ind": "IND",
    "inductor": "IND",
    "coil": "IND",
    "fet": "FET",
    "mosfet": "FET",
}

FP_OF = {
    "USB-C": "USB-C-16",
    "ESP32": "ESP32-WROOM",
    "LDO": "SOT-23-5",
    "IMU": "LGA-14",
    "CONN": "HDR-4",
    "RES": "0402",
    "CAP": "0402",
    "MCU": "QFN-32",
    "BUCK": "QFN-16",
    "ANT": "SMA",
    "ISO": "SOIC-16",
    "BJT": "SOT-23",
    "FET": "SOT-23",
    "DIODE": "SOD-123",
    "LED": "0603",
    "IND": "0805",
}
ICS = {"ESP32", "MCU", "LDO", "IMU", "BUCK"}
HEIGHT = {"ESP32": 3.3, "USB-C": 3.2, "CONN": 2.5, "ANT": 8.0, "BUCK": 0.9, "LDO": 1.1, "IMU": 0.9, "MCU": 0.9, "RES": 0.5, "CAP": 0.5, "ISO": 1.75, "BJT": 1.1, "FET": 1.1, "DIODE": 1.1, "LED": 0.6, "IND": 1.2}

INDUSTRY = {
    "automotive": {"title": "Automotive", "temp": "-40 to 125 °C", "gap": 12, "coat": "conformal coat", "copper": "2 oz on power"},
    "aerospace": {"title": "Aerospace", "temp": "-55 to 125 °C", "gap": 14, "coat": "low-outgassing coat", "copper": "1 oz, derated"},
    "defense": {"title": "Defense", "temp": "-55 to 125 °C", "gap": 14, "coat": "low-outgassing coat", "copper": "1 oz, derated"},
    "space": {"title": "Space and satellite", "temp": "-55 to 125 °C", "gap": 14, "coat": "low-outgassing coat", "copper": "1 oz, derated"},
    "marine": {"title": "Marine", "temp": "-20 to 70 °C", "gap": 16, "coat": "thick conformal coat", "copper": "2 oz"},
    "robot": {"title": "Robotics and automation", "temp": "0 to 85 °C", "gap": 10, "coat": "coat on the power area", "copper": "2 oz on the motor stage"},
    "medical": {"title": "Medical and healthcare", "temp": "0 to 70 °C", "gap": 18, "coat": "coat, no mask opening on the barrier", "copper": "1 oz"},
    "agri": {"title": "Agriculture", "temp": "-40 to 85 °C", "gap": 12, "coat": "thick conformal coat", "copper": "2 oz"},
    "audio": {"title": "Audio and broadcasting", "temp": "0 to 70 °C", "gap": 8, "coat": "no coat called out", "copper": "1 oz"},
    "compute": {"title": "Computing and data centers", "temp": "0 to 70 °C", "gap": 6, "coat": "no coat called out", "copper": "2 oz on the rail"},
    "consumer": {"title": "Consumer electronics", "temp": "0 to 70 °C", "gap": 6, "coat": "no coat called out", "copper": "1 oz"},
    "industrial": {"title": "Industrial and manufacturing", "temp": "-20 to 85 °C", "gap": 12, "coat": "conformal coat", "copper": "2 oz"},
    "iot": {"title": "IoT and wearables", "temp": "0 to 60 °C", "gap": 6, "coat": "no coat called out", "copper": "1 oz"},
    "oil": {"title": "Oil and gas", "temp": "-40 to 125 °C", "gap": 16, "coat": "thick conformal coat", "copper": "2 oz"},
    "light": {"title": "Optoelectronics and lighting", "temp": "-20 to 85 °C", "gap": 8, "coat": "no coat called out", "copper": "2 oz"},
    "energy": {"title": "Power and energy", "temp": "-40 to 105 °C", "gap": 14, "coat": "conformal coat", "copper": "2 oz"},
    "quantum": {"title": "Quantum and cryogenic", "temp": "cryogenic, not a normal range", "gap": 8, "coat": "no coat called out", "copper": "1 oz"},
    "rail": {"title": "Railway and mass transit", "temp": "-40 to 85 °C", "gap": 14, "coat": "conformal coat", "copper": "2 oz"},
    "instrument": {"title": "Scientific and test", "temp": "10 to 40 °C", "gap": 8, "coat": "no coat called out", "copper": "1 oz"},
    "security": {"title": "Security and access", "temp": "-20 to 70 °C", "gap": 8, "coat": "coat over the controller", "copper": "1 oz"},
    "telecom": {"title": "Telecommunications and RF", "temp": "-40 to 85 °C", "gap": 8, "coat": "no coat called out", "copper": "1 oz"},
}
BOARD = {
    "tiny": {"title": "Tiny circuit", "layers": "2", "span": "under 50 mm", "copper": "1 oz", "gap": 4},
    "power": {"title": "Power electronics", "layers": "4", "span": "to 150 mm", "copper": "2 oz", "gap": 12},
    "bms": {"title": "BMS", "layers": "4", "span": "cell-sense board", "copper": "2 oz", "gap": 14},
    "motor": {"title": "Motor control", "layers": "4", "span": "inverter stage", "copper": "2 oz", "gap": 12},
    "cpu": {"title": "CPU motherboard", "layers": "8", "span": "ATX class", "copper": "1 oz", "gap": 6},
    "gpu": {"title": "GPU board", "layers": "10", "span": "to 300 mm", "copper": "2 oz on Vcore", "gap": 6},
    "modem": {"title": "Network modem", "layers": "6", "span": "RF module", "copper": "1 oz", "gap": 8},
    "motherboard": {"title": "Large motherboard", "layers": "8 to 12", "span": "over 200 mm", "copper": "1 oz", "gap": 6},
}

NET_ALIAS = {
    "vbus": "VBUS",
    "gnd": "GND",
    "ground": "GND",
    "i2c": "I2C",
    "sw": "SW",
    "usb": "USB",
    "3v3": "3V3",
    "vcc": "VCC",
    "vdd": "VDD",
    "vss": "VSS",
    "tx": "TX",
    "rx": "RX",
    "clk": "CLK",
    "clock": "CLK",
    "sda": "SDA",
    "scl": "SCL",
    "mosi": "MOSI",
    "miso": "MISO",
    "sck": "SCK",
    "cs": "CS",
    "can": "CAN",
    "5v": "5V",
}


def empty_work() -> dict:
    return {
        "symbols": [],
        "wires": [],
        "footprints": [],
        "sim": "",
        "view3d": "",
        "fab": "",
        "assembly": "",
        "stack": "",
        "industry": "",
        "board": "",
        "chip": [],
        "rules": [],
        "coverage": [],
        "outline": [],
        "datasheets": [],
        "signal": "",
        "ipc_class": "2",
        "ipc": [],
        "desk": "",
        "params": {},
        "cell": {},
        "focus": "",
        "ask": {},
    }


def empty_state() -> dict:
    return {
        "pcb": {"parts": [], "nets": [], "tracks": [], "released": False},
        "cad": {
            "length": None,
            "width": None,
            "thickness": None,
            "hole": 0.0,
            "fillet": 0.0,
            "chamfer": 0.0,
            "shell": 0.0,
        },
        "work": empty_work(),
        "history": [],
    }


def load_state() -> dict:
    if not SESSION.exists():
        return empty_state()
    try:
        data = json.loads(SESSION.read_text())
    except json.JSONDecodeError:
        return empty_state()
    base = empty_state()
    base["pcb"].update(data.get("pcb") or {})
    if not isinstance(base["pcb"].get("tracks"), list):
        base["pcb"]["tracks"] = []
    base["cad"].update(data.get("cad") or {})
    saved = data.get("work") or {}
    work = base["work"]
    for key in ("symbols", "wires", "footprints", "chip", "rules", "coverage", "outline", "datasheets", "ipc", "bom"):
        if isinstance(saved.get(key), list):
            work[key] = saved[key]
    if isinstance(saved.get("signal"), str):
        work["signal"] = saved["signal"]
    if isinstance(saved.get("desk"), str):
        work["desk"] = saved["desk"]
    if isinstance(saved.get("params"), dict):
        work["params"] = saved["params"]
    if isinstance(saved.get("cell"), dict) and saved["cell"].get("name"):
        work["cell"] = saved["cell"]
    if isinstance(saved.get("focus"), str):
        work["focus"] = saved["focus"]
    if isinstance(saved.get("ask"), dict):
        work["ask"] = saved["ask"]
    if isinstance(saved.get("power"), str):
        work["power"] = saved["power"]
    if saved.get("ipc_class") in {"1", "2", "3"}:
        work["ipc_class"] = saved["ipc_class"]
    for key in ("sim", "view3d", "fab", "assembly", "stack", "industry", "board"):
        if isinstance(saved.get(key), str):
            work[key] = saved[key]
    base["history"] = list(data.get("history") or [])[-40:]
    return base


def save_state(state: dict) -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    tmp = SESSION.with_suffix(".tmp")
    tmp.write_text(json.dumps(state))
    tmp.replace(SESSION)


def canon_pkg(raw: str) -> str:
    key = raw.strip().lower().replace("-", "")
    return PKG_ALIAS.get(key, raw.strip().upper())


def canon_net(raw: str) -> str:
    key = raw.strip().lower().replace("-", "")
    return NET_ALIAS.get(key, raw.strip().upper())


def canon_ref(raw: str) -> str:
    return raw.strip().upper()


def clearance_mm(state: dict) -> float:
    work = state.get("work") or {}
    gaps = [8.0]
    ind = INDUSTRY.get(str(work.get("industry") or ""))
    brd = BOARD.get(str(work.get("board") or ""))
    if ind:
        gaps.append(float(ind["gap"]))
    if brd:
        gaps.append(float(brd["gap"]))
    return max(gaps)


def stack_line(state: dict) -> str:
    work = state.get("work") or {}
    ind = INDUSTRY.get(str(work.get("industry") or ""))
    brd = BOARD.get(str(work.get("board") or ""))
    who = " ".join(part["title"] for part in (ind, brd) if part) or "Unclassified"
    stack = _stack_numbers(state)
    coat = ind["coat"] if ind else "no coat called out"
    temp = ind["temp"] if ind else "0 to 70 °C"
    material = str(_params(state).get("material") or "FR-4")
    return (
        f"{who}. {stack['layers']} layers, {stack['thick']:g} mm {material}, {stack['oz']:g} oz, ENIG, {coat}. Rating {temp}."
    )


def _facts(state: dict) -> dict:
    symbols = _symbols(state)
    return {
        "pkgs": {s["pkg"] for s in symbols},
        "names": {n["name"] for n in _nets(state)},
        "mcus": sum(1 for s in symbols if s["pkg"] in {"ESP32", "MCU"}),
        "parts": state["pcb"]["parts"],
        "span": _span(state),
    }


def _span(state: dict) -> tuple[float, float]:
    outline = (_work(state).get("outline") or [])
    if len(outline) == 2:
        return float(outline[0]), float(outline[1])
    parts = state["pcb"]["parts"]
    if not parts:
        return 0.0, 0.0
    return max(part["x"] for part in parts), max(part["y"] for part in parts)


def industry_verdict(key: str, facts: dict) -> tuple[str, str]:
    ind = INDUSTRY[key]
    mcus, names, pkgs = facts["mcus"], facts["names"], facts["pkgs"]
    if key == "automotive":
        if mcus <= 1:
            return "warn", f"One controller is not an ASIL path. {ind['temp']}."
        return "pass", f"More than one controller. {ind['temp']}."
    if key == "aerospace":
        if mcus < 2:
            return "warn", f"A flight function needs a second path. {ind['temp']}."
        return "pass", f"Two controllers. {ind['temp']}."
    if key == "marine":
        if "GND" not in names:
            return "warn", "Name a logic ground before it can be kept off the hull."
        return "pass", f"Logic ground is named. Creepage opens for salt fog. {ind['temp']}."
    if key == "robot":
        if "ESTOP" in names:
            return "pass", "E-stop net cuts the gate drive."
        return "warn", "The e-stop has to cut the gate drive, not only the controller."
    if key == "defense":
        if mcus < 2:
            return "warn", f"A second path is not on the sheet. This is not a MIL-STD or ITAR check. {ind['temp']}."
        return "pass", f"Two controllers. This is not a MIL-STD or ITAR check. {ind['temp']}."
    if key == "space":
        if mcus < 2:
            return "warn", f"A second path is not on the sheet. Radiation and outgassing are not simulated. {ind['temp']}."
        return "pass", f"Two controllers. Radiation and outgassing are not simulated. {ind['temp']}."
    if key == "agri":
        if "CONN" not in pkgs:
            return "warn", f"No field connector. {ind['temp']}. Coat is {ind['coat']}."
        return "pass", f"A field connector is on the sheet. {ind['temp']}."
    if key == "audio":
        return "warn", "Analog and digital returns are not separate nets. Broadcast delay is not checked."
    if key == "compute":
        if {"BUCK", "LDO"} & pkgs:
            return "pass", "A regulator is on the sheet for the rail."
        return "warn", "A data-center board wants a point-of-load regulator."
    if key == "consumer":
        return "pass" if pkgs else "warn", f"Consumer range {ind['temp']}." if pkgs else "Nothing is on the sheet yet."
    if key == "industrial":
        if "ISO" in pkgs:
            return "pass", "Field I/O has an isolator."
        return "warn", "Factory I/O is not isolated."
    if key == "iot":
        if "ANT" in pkgs:
            return "pass", "A radio footprint is on the sheet. Battery life is not estimated."
        return "warn", "No radio footprint. Battery life is not estimated."
    if key == "oil":
        if "CONN" in pkgs:
            return "pass", f"A field connector is present. This is not an ATEX or IECEx certificate. {ind['temp']}."
        return "warn", f"No field connector. This is not an ATEX or IECEx certificate. {ind['temp']}."
    if key == "light":
        if "LED" in pkgs:
            return "pass", "An LED is on the sheet. Heat still wants a metal-core stack, which is a separate construction."
        return "warn", "No LED. A lighting board is not inferred from the stack."
    if key == "energy":
        if {"BUCK", "LDO"} & pkgs:
            return "pass", f"A regulator is on the sheet. {ind['copper']}."
        return "warn", "Power and energy wants a regulator. This is not a grid-code check."
    if key == "quantum":
        return "warn", "FR-4 and these parts are not a cryogenic design. No qubit and no cold wiring are modeled."
    if key == "rail":
        if "ISO" in pkgs:
            return "pass", f"An isolator is present. This is not an EN 50155 check. {ind['temp']}."
        return "warn", f"Train I/O is not isolated. This is not an EN 50155 check. {ind['temp']}."
    if key == "instrument":
        return "warn", "This is not a calibrated measurement path."
    if key == "security":
        if mcus:
            return "warn", "A controller is present. There is no secure element and no tamper mesh."
        return "warn", "No controller. There is no secure element and no tamper mesh."
    if key == "telecom":
        if "ANT" in pkgs:
            return "pass", "An antenna footprint is on the sheet. RF match is not simulated."
        return "warn", "No antenna footprint. RF match is not simulated."
    if "ISO" in pkgs:
        return "pass", "An isolator sits between the interface and the patient circuit."
    if "USB-C" in pkgs or "USB" in names:
        return "warn", "USB is not a patient barrier. Isolate the patient circuit."
    return "warn", "No patient isolation barrier is on the sheet."


def board_verdict(key: str, facts: dict) -> tuple[str, str]:
    pkgs, parts = facts["pkgs"], facts["parts"]
    if key == "tiny":
        length, width = facts["span"]
        far = [p["ref"] for p in parts if p["x"] > 50 or p["y"] > 50]
        if far or length > 50 or width > 50:
            return "warn", "Outside a 50 mm module."
        return "pass", "The outline fits a module under 50 mm." if (parts or length) else "Nothing placed on the module."
    if key == "power":
        if {"BUCK", "LDO"} & pkgs:
            return "pass", "A regulator is on the sheet."
        return "warn", "Power electronics wants a switch or a regulator."
    if key == "bms":
        if "SENSE" in facts["names"]:
            return "pass", "Cell sense is on its own net, off the pack power."
        return "warn", "Cell sense is not isolated from pack power."
    if key == "motor":
        if "PHASE" in facts["names"] and "ENC" in facts["names"]:
            return "pass", "Phase current and the encoder are on separate nets."
        return "warn", "Phase nodes have to stay off the encoder."
    if key == "cpu":
        length, width = facts["span"]
        if length >= 170 and width >= 170:
            return "pass", f"Outline {length:g} × {width:g} mm can carry an 8-layer CPU board."
        return "warn", f"Outline {length:g} × {width:g} mm is below 170 mm. A CPU board is not this size."
    if key == "gpu":
        if "BUCK" not in pkgs:
            return "warn", "A GPU board wants a multiphase Vcore."
        return "pass", "A regulator is present for Vcore."
    if key == "modem":
        if "ANT" not in pkgs:
            return "warn", "No antenna footprint yet."
        return "pass", "An antenna footprint is on the sheet."
    length, width = facts["span"]
    if length >= 200 and width >= 200:
        return "pass", f"Outline {length:g} × {width:g} mm is a large motherboard."
    return "warn", f"Outline {length:g} × {width:g} mm is still a small sketch of a large motherboard."


def industry_rules(state: dict) -> str:
    work = _work(state)
    key_i = str(work.get("industry") or "")
    key_b = str(work.get("board") or "")
    if key_i not in INDUSTRY and key_b not in BOARD:
        return "Name an industry or a board class."
    facts = _facts(state)
    rules: list[dict] = []
    if key_i in INDUSTRY:
        status, detail = industry_verdict(key_i, facts)
        rules.append({"name": INDUSTRY[key_i]["title"], "status": status, "detail": detail})
    if key_b in BOARD:
        status, detail = board_verdict(key_b, facts)
        rules.append({"name": BOARD[key_b]["title"], "status": status, "detail": detail})
    work["rules"] = rules
    work["stack"] = stack_line(state)
    return " ".join(f"{row['name']} {row['status']}." for row in rules) + " " + work["stack"]


def _ensure_symbol(state: dict, ref: str, pkg: str) -> str:
    work = _work(state)
    ref, pkg = canon_ref(ref), canon_pkg(pkg)
    if any(row["ref"] == ref for row in work["symbols"]):
        return f"{ref} already on the sheet."
    work["symbols"].append({"ref": ref, "pkg": pkg})
    return f"Added {pkg} symbol {ref}."


def _ensure_wire(state: dict, name: str, a: str, b: str) -> str:
    work = _work(state)
    name, a, b = canon_net(name), canon_ref(a), canon_ref(b)
    if any(row["name"] == name and row["a"] == a and row["b"] == b for row in work["wires"]):
        return f"{name} already ties {a} to {b}."
    work["wires"].append({"name": name, "a": a, "b": b})
    return f"Wired {name} from {a} to {b}."


def handle_industry(state: dict, kind: str) -> str:
    if kind not in INDUSTRY:
        return "That field is not in the profile list. Ask to list PCB fields."
    facts = _facts(state)
    title = INDUSTRY[kind]["title"]
    if kind in {"automotive", "aerospace", "defense", "space"}:
        note = _ensure_symbol(state, "U9", "MCU") if facts["mcus"] < 2 else "A second controller is already there."
        hosts = [row["ref"] for row in _symbols(state) if row["pkg"] in {"ESP32", "MCU"}]
        if len(hosts) >= 2 and "GND" not in _facts(state)["names"]:
            note += " " + _ensure_wire(state, "GND", hosts[0], hosts[1])
        return f"{title}: {note}"
    if kind == "marine":
        hosts = [row["ref"] for row in _symbols(state)]
        if "GND" in facts["names"]:
            return f"{title}: logic ground is already named."
        if len(hosts) < 2:
            _ensure_symbol(state, "U1", "MCU")
            _ensure_symbol(state, "J1", "CONN")
            hosts = ["J1", "U1"]
        return f"{title}: " + _ensure_wire(state, "GND", hosts[0], hosts[1])
    if kind == "robot":
        _ensure_symbol(state, "J9", "CONN")
        host = next((row["ref"] for row in _symbols(state) if row["pkg"] in {"ESP32", "MCU"}), "U1")
        if host == "J9":
            host = "U1"
            _ensure_symbol(state, "U1", "MCU")
        return f"{title}: " + _ensure_wire(state, "ESTOP", "J9", host)
    if kind == "medical":
        return f"{title}: " + _ensure_symbol(state, "U4", "ISO")
    status, detail = industry_verdict(kind, _facts(state))
    return f"{title}: {status}. {detail}"


def handle_board(state: dict, kind: str) -> str:
    if kind not in BOARD:
        return "Board class is tiny, power, bms, motor, cpu, gpu, modem, or motherboard."
    facts = _facts(state)
    title = BOARD[kind]["title"]
    if kind == "power" and not ({"BUCK", "LDO"} & facts["pkgs"]):
        return f"{title}: " + _ensure_symbol(state, "U8", "LDO")
    if kind == "bms" and "SENSE" not in facts["names"]:
        _ensure_symbol(state, "U7", "MCU")
        return f"{title}: " + _ensure_wire(state, "SENSE", "U7", "U2" if any(row["ref"] == "U2" for row in _symbols(state)) else "U1")
    if kind == "motor" and not ("PHASE" in facts["names"] and "ENC" in facts["names"]):
        _ensure_symbol(state, "U5", "MCU")
        phase = _ensure_wire(state, "PHASE", "U5", "U1" if any(row["ref"] == "U1" for row in _symbols(state)) else "U5")
        enc = _ensure_wire(state, "ENC", "U5", "J1" if any(row["ref"] == "J1" for row in _symbols(state)) else "U9")
        return f"{title}: {phase} {enc}"
    if kind == "gpu" and "BUCK" not in facts["pkgs"]:
        return f"{title}: " + _ensure_symbol(state, "U6", "BUCK")
    if kind == "modem" and "ANT" not in facts["pkgs"]:
        return f"{title}: " + _ensure_symbol(state, "AE1", "ANT")
    if kind in {"cpu", "motherboard", "tiny"}:
        status, detail = board_verdict(key=kind, facts=_facts(state))
        return f"{title}: {status}. {detail}"
    status, detail = board_verdict(kind, _facts(state))
    return f"{title}: {status}. {detail}"


def handle_all(state: dict) -> str:
    notes = [handle_industry(state, key) for key in INDUSTRY]
    for key in ("power", "bms", "motor", "gpu", "modem", "tiny", "cpu", "motherboard"):
        notes.append(handle_board(state, key))
    summary = cover_all(state)
    return summary + " " + " ".join(notes)


def _seat(state: dict, ref: str, pkg: str) -> tuple[float, float]:
    import math

    pcb = state["pcb"]
    gap = clearance_mm(state)
    occupied = [(float(part["x"]), float(part["y"])) for part in pcb["parts"]]

    def fits(x: float, y: float) -> bool:
        return all(math.hypot(x - ox, y - oy) + 1e-6 >= gap for ox, oy in occupied)

    for step in range(1, 24):
        for y in (gap * step,):
            for x in (gap * i for i in range(1, 24)):
                if fits(x, y):
                    pcb["parts"].append({"ref": ref, "pkg": pkg, "x": x, "y": y})
                    return x, y
    raise RuntimeError("No open spot left at the required clearance.")


def _next_ref(state: dict) -> str:
    used = {row["ref"] for row in _symbols(state)} | {part["ref"] for part in state["pcb"]["parts"]}
    number = 20
    while f"U{number}" in used:
        number += 1
    return f"U{number}"


def build_datasheet(state: dict, variants: list[dict]) -> str:
    from py.si.datasheet import lands

    work = _work(state)
    notes: list[str] = []
    built: list[dict] = []
    known_nets: dict[str, str] = {}
    for wire in work["wires"] + state["pcb"]["nets"]:
        known_nets.setdefault(str(wire["name"]), str(wire["a"]))
    for spec in variants:
        package = str(spec.get("package") or "")
        needed = [key for key in ("package", "pins", "length", "width", "height") if not spec.get(key)]
        if spec.get("family") != "chip" and not spec.get("pitch"):
            needed.append("pitch")
        if needed:
            notes.append(f"{package or 'part'} held. Missing {', '.join(needed)}.")
            continue
        ref = _next_ref(state)
        pads = lands(spec)
        names = spec.get("pin_names") or {}
        work["symbols"].append({"ref": ref, "pkg": package, "mpn": spec.get("mpn") or "", "pins": pads})
        work["footprints"] = [row for row in work["footprints"] if row["ref"] != ref]
        work["footprints"].append(
            {
                "ref": ref,
                "fp": package,
                "mpn": spec.get("mpn") or "",
                "pads": pads,
                "body": {"l": float(spec["length"]), "w": float(spec["width"]), "h": float(spec["height"])},
                "land": "calculated",
            }
        )
        x, y = _seat(state, ref, package)
        tied = []
        for pad in pads:
            net = str(pad["name"])
            other = known_nets.get(net)
            if not other or other == ref:
                continue
            if any(wire["name"] == net and wire["b"] == ref for wire in work["wires"]):
                continue
            work["wires"].append({"name": net, "a": other, "b": ref})
            state["pcb"]["nets"].append({"name": net, "a": other, "b": ref})
            tied.append(net)
        state["pcb"]["released"] = False
        named = f"{len(names)} pin names" if names else "pin names were not in the sheet"
        nets = ", ".join(dict.fromkeys(tied)) if tied else "no board net matched a pin name"
        body = spec["length"], spec["width"], spec["height"]
        notes.append(
            f"{spec.get('mpn') or package} {package} as {ref} at ({x:g}, {y:g}) mm. "
            f"{len(pads)} pads, {named}, tied {nets}. "
            f"3D body {body[0]:g} × {body[1]:g} × {body[2]:g} mm. "
            "Calculated land pattern. Confirm the datasheet drawing before you order boards."
        )
        built.append(
            {
                "ref": ref,
                "mpn": spec.get("mpn") or "",
                "package": package,
                "pins": len(pads),
                "pitch": spec.get("pitch") or 0,
                "body": f"{body[0]:g} × {body[1]:g} × {body[2]:g} mm",
                "land": "calculated",
                "nets": nets,
            }
        )
    work["datasheets"] = built
    if not notes:
        return "Nothing in that datasheet could be built."
    return " ".join(notes)


def place_sheet(state: dict) -> str:
    import math

    work = _work(state)
    pcb = state["pcb"]
    gap = clearance_mm(state)
    occupied = [(float(part["x"]), float(part["y"])) for part in pcb["parts"]]
    have = {part["ref"] for part in pcb["parts"]}

    def fits(x: float, y: float) -> bool:
        return all(math.hypot(x - ox, y - oy) + 1e-6 >= gap for ox, oy in occupied)

    placed: list[str] = []
    for sym in work["symbols"]:
        if sym["ref"] in have:
            continue
        found = None
        steps = [gap * i for i in range(1, 24)]
        for y in steps:
            for x in steps:
                if fits(x, y):
                    found = (x, y)
                    break
            if found:
                break
        if found is None:
            return "No open spot left at the required clearance."
        pcb["parts"].append({"ref": sym["ref"], "pkg": sym["pkg"], "x": found[0], "y": found[1]})
        occupied.append(found)
        have.add(sym["ref"])
        placed.append(sym["ref"])
    for sym in work["symbols"]:
        if any(row["ref"] == sym["ref"] for row in work["footprints"]):
            continue
        work["footprints"].append({"ref": sym["ref"], "fp": FP_OF.get(sym["pkg"], sym["pkg"])})
    refs = {part["ref"] for part in pcb["parts"]}
    for wire in work["wires"]:
        if wire["a"] not in refs or wire["b"] not in refs:
            continue
        if any(net["name"] == wire["name"] and net["a"] == wire["a"] and net["b"] == wire["b"] for net in pcb["nets"]):
            continue
        pcb["nets"].append({"name": wire["name"], "a": wire["a"], "b": wire["b"]})
    pcb["released"] = False
    cover_all(state)
    if not placed:
        return "Every schematic symbol is already on the layout."
    return "Placed " + ", ".join(placed) + " and assigned footprints."


def cover_all(state: dict) -> str:
    work = _work(state)
    facts = _facts(state)
    rows: list[dict] = []
    for key, ind in INDUSTRY.items():
        status, detail = industry_verdict(key, facts)
        rows.append({"group": "industry", "name": ind["title"], "status": status, "detail": detail})
    for key, brd in BOARD.items():
        status, detail = board_verdict(key, facts)
        rows.append({"group": "board", "name": brd["title"], "status": status, "detail": detail})
    work["coverage"] = rows
    warns = sum(1 for row in rows if row["status"] == "warn")
    return f"Covered {len(rows)} industries and board classes. {warns} warn."


def drc(state: dict) -> list[dict]:
    parts = state["pcb"]["parts"]
    nets = list(state["pcb"]["nets"]) + list((state.get("work") or {}).get("wires") or [])
    items: list[dict] = []
    refs = [p["ref"] for p in parts]
    if len(refs) != len(set(refs)):
        items.append({"rule": "Duplicate ref", "status": "warn", "detail": "Two parts share a reference."})
    else:
        items.append({"rule": "Duplicate ref", "status": "pass", "detail": f"{len(parts)} unique references."})
    tight = 0
    gap = clearance_mm(state)
    for i, a in enumerate(parts):
        for b in parts[i + 1 :]:
            dist = math.hypot(a["x"] - b["x"], a["y"] - b["y"])
            if dist < gap:
                tight += 1
    if tight:
        items.append({"rule": "Placement", "status": "warn", "detail": f"{tight} pair(s) closer than {gap:g} mm."})
    else:
        items.append({"rule": "Placement", "status": "pass", "detail": f"Courtyards clear at {gap:g} mm."})
    names = {n["name"] for n in nets}
    pkgs = {p["pkg"] for p in parts}
    if "USB-C" in pkgs and "ESP32" in pkgs and "VBUS" not in names:
        items.append({"rule": "VBUS", "status": "warn", "detail": "USB-C and ESP32 are on the board with no VBUS net."})
    elif parts:
        items.append({"rule": "Power nets", "status": "pass", "detail": "Named nets: " + (", ".join(sorted(names)) or "none yet") + "."})
    else:
        items.append({"rule": "Parts", "status": "warn", "detail": "Board has no parts yet."})
    return items


def _params(state: dict) -> dict:
    work = _work(state)
    saved = work.get("params") if isinstance(work.get("params"), dict) else {}
    base = {
        "thickness_mm": 1.6,
        "layers": None,
        "copper_oz": None,
        "min_track_mm": 0.1,
        "min_clearance_mm": 0.1,
        "ring_mm": 0.15,
        "via_drill_mm": 0.3,
        "material": "FR-4",
    }
    for key, value in saved.items():
        if key in base:
            base[key] = value
    return base


def _stack_numbers(state: dict) -> dict:
    work = _work(state)
    p = _params(state)
    brd = BOARD.get(work.get("board") or "")
    ind = INDUSTRY.get(work.get("industry") or "")
    copper = (brd or {}).get("copper") or (ind or {}).get("copper") or "1 oz"
    layers = 2
    if brd:
        found = re.findall(r"\d+", brd["layers"])
        if found:
            layers = int(found[0])
    if p.get("layers"):
        layers = int(p["layers"])
    oz = float(p["copper_oz"]) if p.get("copper_oz") else (2.0 if "2 oz" in copper else 1.0)
    t = 0.035 * oz
    thick = float(p["thickness_mm"] or 1.6)
    if layers <= 2:
        height = max(0.08, thick - 2 * t)
    elif layers <= 4:
        height = 0.21
    else:
        height = 0.10
    return {
        "h": height,
        "er": 4.3 if layers < 6 else 3.8,
        "t": t,
        "layers": layers,
        "oz": oz,
        "thick": thick,
        "b": max(0.2, thick - 0.42),
    }


def _z_microstrip(width: float, h: float, er: float, t: float) -> float:
    return (87 / math.sqrt(er + 1.41)) * math.log(5.98 * h / (0.8 * width + t))


def _width_for_z(target: float, h: float, er: float, t: float) -> float | None:
    if _z_microstrip(0.05, h, er, t) < target:
        return None
    lo, hi = 0.05, max(0.2, h * 8)
    for _ in range(48):
        mid = (lo + hi) / 2
        if _z_microstrip(mid, h, er, t) > target:
            lo = mid
        else:
            hi = mid
    return hi


def _z_stripline(width: float, gap: float, er: float, t: float) -> float:
    return (60 / math.sqrt(er)) * math.log(1.9 * gap / (0.8 * width + t))


def _width_for_stripline(target: float, gap: float, er: float, t: float) -> float | None:
    if gap <= t or _z_stripline(0.05, gap, er, t) < target:
        return None
    lo, hi = 0.05, max(0.2, gap * 4)
    for _ in range(48):
        mid = (lo + hi) / 2
        if _z_stripline(mid, gap, er, t) > target:
            lo = mid
        else:
            hi = mid
    return hi


def profile_text(state: dict) -> str:
    work = _work(state)
    stack = _stack_numbers(state)
    p = _params(state)
    outline = work.get("outline") or []
    size = f"{outline[0]:g} × {outline[1]:g} mm" if len(outline) == 2 else "outline not set"
    return (
        f"Board {size}. {stack['layers']} layers, {stack['thick']:g} mm, {stack['oz']:g} oz. "
        f"Min track {p['min_track_mm']:g} mm, min space {p['min_clearance_mm']:g} mm. "
        f"Via drill {p['via_drill_mm']:g} mm, annular ring {p['ring_mm']:g} mm. "
        "JLCPCB standard 2-layer is often quoted near 0.1 mm trace and space. Confirm the current capability sheet. "
        "Impedance here is one dielectric number, not a field solver."
    )


def impedance(state: dict, ohms: float) -> str:
    stack = _stack_numbers(state)
    single = ohms if ohms <= 60 else ohms / 2
    width = _width_for_z(single, stack["h"], stack["er"], stack["t"])
    if width is None:
        return f"{ohms:g} ohm is above what this {stack['layers']}-layer stack can do with a 0.05 mm trace."
    gap = stack["h"] * 1.5 if ohms > 60 else 0
    note = f"{ohms:g} Ω uses a {width:.3f} mm trace"
    if gap:
        note += f" with {gap:.2f} mm pair spacing"
    note += f" on {stack['layers']} layers, dielectric {stack['h']:g} mm, Er {stack['er']}. Approximate microstrip, not a field solver."
    _work(state)["signal"] = note
    return note


def pour_ground(state: dict) -> str:
    _work(state)["signal"] = "GND pour on the outer copper. Not a filled polygon."
    return "Ground pour noted on the outer layers. The board file does not contain a filled polygon yet."


def size_via(state: dict, amps: float) -> str:
    drill = max(0.2, 0.3 * amps)
    pad = drill + 0.30
    note = f"Via for {amps:g} A: drill {drill:.2f} mm, pad {pad:.2f} mm. About 1 A per 0.3 mm at a 10 °C rise. Not an IPC-2152 certificate."
    _work(state)["signal"] = note
    return note


def diff_pair(state: dict, name: str) -> str:
    net = canon_net(name)
    text = impedance(state, 90)
    note = f"Differential {net} at 90 Ω. {text}"
    _work(state)["signal"] = note
    return note


def _ipc_facts(state: dict) -> dict[str, bool]:
    work = _work(state)
    pcb = state["pcb"]
    return {
        "outline": bool(work.get("outline")),
        "parts": bool(pcb["parts"]),
        "footprints": bool(work.get("footprints")),
        "nets": bool(pcb["nets"]),
        "fab": bool(work.get("fab")) or bool(pcb.get("released")),
        "assembly": bool(work.get("assembly")),
        "signal": bool(work.get("signal")),
        "datasheet": bool(work.get("datasheets")),
        "data": False,
        "cable": False,
    }


def ipc_report(state: dict, doc: str = "") -> str:
    from py.si.ipc import BY_ID, CATALOG, CLASSES, lookup

    work = _work(state)
    grade = work.get("ipc_class") if work.get("ipc_class") in CLASSES else "2"
    work["ipc_class"] = grade
    facts = _ipc_facts(state)
    chosen = CATALOG
    if doc:
        hit = lookup(doc) or BY_ID.get(doc)
        if hit is None:
            return f"{doc} is not in the PCB IPC set used here."
        chosen = [hit]
    rows = []
    missing = 0
    for item in chosen:
        gaps = [name for name in item["needs"] if not facts.get(name)]
        if gaps:
            missing += 1
            rows.append({"name": item["id"], "status": "warn", "detail": item["title"] + ". Missing " + ", ".join(gaps) + "."})
        else:
            rows.append({"name": item["id"], "status": "pass", "detail": item["title"] + ". Evidence is on the board."})
    work["ipc"] = rows
    addendum = ""
    industry = work.get("industry") or ""
    if industry == "aerospace":
        addendum = " Name the space addendum on the order."
    elif industry == "medical":
        addendum = " Name the medical addendum on the order."
    elif industry == "automotive":
        addendum = " Name the automotive addendum on the order."
    if len(chosen) == 1:
        return f"{CLASSES[grade]}. {rows[0]['name']} {rows[0]['status']}. {rows[0]['detail']} Not a licensed IPC certificate.{addendum}"
    return (
        f"{CLASSES[grade]}. {len(rows) - missing} of {len(rows)} IPC documents have evidence on this board. "
        f"{missing} still missing. Not a licensed IPC certificate.{addendum}"
    )


def desk_job(state: dict, kind: str, value: float | None = None, name: str = "") -> str:
    from py.si.desk import lc_cutoff, rc_cutoff, spacing_text, trace_ipc2221, write_bom, write_eda, _ALT

    work = _work(state)
    params = work.setdefault("params", {})
    stack = _stack_numbers(state)
    oz = stack["oz"]
    if kind == "rules":
        text = profile_text(state)
    elif kind == "layers":
        count = int(value or 0)
        if count < 1 or count > 32:
            text = "Layer count is 1 to 32. The impedance model still uses one outer dielectric."
        else:
            params["layers"] = count
            work["stack"] = stack_line(state)
            text = profile_text(state)
    elif kind == "copper":
        ounces = 0.5 if name == "half" else value
        if ounces is None or ounces < 0.5 or ounces > 2:
            text = "Copper weight here is 0.5 to 2 oz."
        else:
            params["copper_oz"] = ounces
            work["stack"] = stack_line(state)
            text = profile_text(state)
    elif kind == "thick":
        thick = 1.6 if name == "standard" or value is None else value
        if thick < 0.4 or thick > 3.2:
            text = "Board thickness here is 0.4 to 3.2 mm. 1.6 mm is the usual board."
        else:
            params["thickness_mm"] = thick
            work["stack"] = stack_line(state)
            text = profile_text(state)
    elif kind == "strip":
        if stack["layers"] < 4:
            text = "Stripline needs planes on both sides. This profile is under 4 layers, so use microstrip."
        else:
            target = value or 50.0
            single = target if target <= 60 else target / 2
            width = _width_for_stripline(single, stack["b"], stack["er"], stack["t"])
            if width is None:
                text = f"{target:g} Ω does not fit this stripline spacing."
            else:
                text = (
                    f"Stripline {target:g} Ω is about {width:.3f} mm wide. Plane spacing {stack['b']:.2f} mm, Er {stack['er']}. "
                    "Symmetric-stripline approximation, not a field solver."
                )
                if target > 60:
                    text += " The pair uses two of those lines. Spacing is not solved."
    elif kind == "ring":
        drill = value or float(_params(state)["via_drill_mm"])
        ring = float(_params(state)["ring_mm"])
        pad = drill + 2 * ring
        amps = drill / 0.3
        text = (
            f"Drill {drill:.2f} mm, annular ring {ring:.2f} mm, pad {pad:.2f} mm. "
            f"About {amps:.2f} A using 1 A per 0.3 mm, not IPC-2152. "
            "Via-in-pad only if the fab fills and caps the hole. This board does not place one."
        )
    elif kind == "fab":
        p = _params(state)
        text = (
            f"Stored limits: track {p['min_track_mm']:g} mm, space {p['min_clearance_mm']:g} mm, "
            f"mask swell 0.05 mm, silk 0.15 mm, edge 0.25 mm. "
            "JLCPCB standard 2-layer is often quoted near 0.1 mm trace and space. "
            "That is not their current capability sheet."
        )
    elif kind == "width":
        amps = value or 1.0
        outer = trace_ipc2221(amps, oz=oz)
        inner = trace_ipc2221(amps, oz=oz, internal=True)
        text = (
            f"IPC-2221 curve fit, not the IPC-2152 charts. {amps:g} A, 10 °C rise, {oz:g} oz, 50 mm. "
            f"Outer {outer['width_mm']:.3f} mm, {outer['loss_w'] * 1000:.1f} mW. "
            f"Inner {inner['width_mm']:.3f} mm."
        )
    elif kind == "filter":
        rc = rc_cutoff(10_000, 100e-9)
        lc = lc_cutoff(10e-6, 100e-9)
        text = f"RC 10 kΩ and 100 nF cuts at {rc:.1f} Hz. LC 10 µH and 100 nF cuts at {lc / 1000:.2f} kHz. Change the parts if those are not yours."
    elif kind == "thermal":
        amps = value or 1.0
        row = trace_ipc2221(amps, oz=oz)
        text = (
            f"Loss on the {amps:g} A outer trace is {row['loss_w'] * 1000:.1f} mW over {row['length_mm']:g} mm "
            f"({row['ohms'] * 1000:.2f} mΩ). This is I²R, not a board thermal simulation."
        )
    elif kind in {"kicad", "skill", "altium"}:
        path, note = write_eda(state, kind)
        text = f"{note}. Wrote {path.name}. The EDA tool was not opened."
    elif kind == "replace":
        sheets = work.get("datasheets") or []
        bits = []
        if sheets:
            for sheet in sheets:
                alt = _ALT.get(sheet.get("package") or "", "")
                pin = f"{sheet.get('pins', '?')} pins" if sheet.get("pins") else "pins not fully read"
                bits.append(f"{sheet.get('mpn') or sheet.get('ref')} {sheet.get('package')} {pin}. {alt or 'No alternate is on file for this package.'}")
        else:
            pkgs = {part["pkg"] for part in state["pcb"]["parts"]}
            for pkg in sorted(pkgs):
                bits.append(f"{pkg}: {_ALT.get(pkg, 'No alternate is on file.')}")
        if not bits:
            bits.append("No datasheet and no parts. Upload a datasheet or place a part first.")
        text = " ".join(bits) + " Absolute maximum ratings are not compared unless the datasheet line states them. Stock was not checked."
    elif kind == "creepage":
        text = spacing_text(value or 50.0)
    elif kind == "emi":
        layers = stack["layers"]
        has_gnd = any(net["name"] == "GND" for net in state["pcb"]["nets"])
        has_cap = any(part["pkg"] == "CAP" for part in state["pcb"]["parts"])
        held = []
        if not has_gnd:
            held.append("no GND net for the return")
        if not has_cap:
            held.append("no capacitor on the board for a local 100 nF")
        if not work.get("signal"):
            held.append("no pour noted")
        text = (
            f"{layers}-layer stack. Put the continuous ground next to the signal layer and do not cross a split under a fast net. "
            "Place one 100 nF at each power pin before the bulk cap."
        )
        if held:
            text += " Held: " + ", ".join(held) + "."
        else:
            text += " GND, a capacitor, and a pour note are already on the board."
    elif kind == "table":
        path, note = write_bom(state)
        text = f"BOM table {note}. Wrote {path.name}."
    else:
        text = "Ask for trace width, a filter, thermal loss, a KiCad script, a replacement, creepage, EMI, or a BOM table."
    work["desk"] = text
    return text


def autoroute(state: dict, which: str = "") -> str:
    from py.si.router import route_board

    pcb = state["pcb"]
    work = _work(state)
    params = _params(state)
    name = which if which and which not in {"all", "<none>"} else ""
    if which == "rip":
        pcb["tracks"] = []
        return "Routes removed."
    chosen = pcb["nets"]
    if name:
        chosen = [net for net in pcb["nets"] if net["name"] == name or net["a"] == name or net["b"] == name]
        if not chosen:
            return f"No net named {name}."
    tracks, failed = route_board(pcb["parts"], chosen, work.get("outline") or [], float(params["min_track_mm"]))
    if name:
        keep = [row for row in pcb.get("tracks") or [] if row["name"] != name]
        pcb["tracks"] = keep + tracks
    else:
        pcb["tracks"] = tracks
    pcb["released"] = False
    if not tracks and failed:
        return "Autoroute held. " + " ".join(failed)
    text = f"Autorouted {len(tracks)} net(s) on one layer, 0.5 mm grid, orthogonal tracks."
    if failed:
        text += " Unrouted: " + ", ".join(failed) + "."
    else:
        text += " No length matching, no diff-pair spacing, no layer changes."
    return text


def dfm(state: dict) -> str:
    stack = _stack_numbers(state)
    width = _width_for_z(50, stack["h"], stack["er"], stack["t"]) or 0.1
    work = _work(state)
    gaps = []
    if not work.get("outline"):
        gaps.append("outline is not set")
    if not any(net["name"] == "GND" for net in state["pcb"]["nets"]):
        gaps.append("no GND net")
    grade = work.get("ipc_class") if work.get("ipc_class") in {"1", "2", "3"} else "2"
    note = (
        f"DFM for {stack['layers']} layers, IPC class {grade}: 50 Ω track {width:.3f} mm. "
        "Shop start: drill 0.20–0.30 mm, annular ring 0.15 mm, trace and space 0.13–0.15 mm, "
        "mask swell 0.05 mm, mask bridge 0.10 mm, silk line 0.15 mm, silk text 1.00 mm. "
        "Typical factory numbers, not a capability sheet. Silk and the mask web are not measured on this board."
    )
    if gaps:
        note += " Held: " + ", ".join(gaps) + "."
    work["signal"] = note
    return note


def cad_mass(cad: dict) -> dict | None:
    if cad["length"] is None or cad["width"] is None or cad["thickness"] is None:
        return None
    length, width, thick = float(cad["length"]), float(cad["width"]), float(cad["thickness"])
    hole = float(cad["hole"] or 0)
    vol = length * width * thick
    wall = float(cad.get("shell") or 0)
    if wall > 0 and wall * 2 < length and wall * 2 < width and wall < thick:
        vol -= (length - 2 * wall) * (width - 2 * wall) * (thick - wall)
    if hole > 0:
        vol -= math.pi * (hole / 2) ** 2 * thick
    vol = max(0.0, vol)
    grams = vol * 2.70 / 1000.0
    return {"cm3": vol / 1000.0, "grams": grams}


def _put(state: dict, ref: str, pkg: str, x: float, y: float) -> None:
    pcb = state["pcb"]
    work = _work(state)
    ref, pkg = canon_ref(ref), canon_pkg(pkg)
    if not any(part["ref"] == ref for part in pcb["parts"]):
        pcb["parts"].append({"ref": ref, "pkg": pkg, "x": x, "y": y})
    if not any(row["ref"] == ref for row in work["symbols"]):
        work["symbols"].append({"ref": ref, "pkg": pkg})
    if not any(row["ref"] == ref for row in work["footprints"]):
        work["footprints"].append({"ref": ref, "fp": FP_OF.get(pkg, pkg)})


def _tie(state: dict, name: str, a: str, b: str) -> None:
    pcb = state["pcb"]
    work = _work(state)
    name, a, b = canon_net(name), canon_ref(a), canon_ref(b)
    if not any(net["name"] == name and net["a"] == a and net["b"] == b for net in pcb["nets"]):
        pcb["nets"].append({"name": name, "a": a, "b": b})
    if not any(net["name"] == name and net["a"] == a and net["b"] == b for net in work["wires"]):
        work["wires"].append({"name": name, "a": a, "b": b})


def sonar_booster_task(text: str) -> bool:
    words = re.sub(r"[^a-z0-9]+", " ", text.lower()).split()
    return "sonar" in words and any(word.startswith("boost") for word in words)


_SUGGESTIONS = {
    "vin": ("12 V", "24 V"),
    "vout": ("48 V", "60 V"),
    "iout": ("1 A", "1.5 A", "2 A"),
    "freq": ("100 kHz", "200 kHz", "500 kHz"),
    "eff": ("85%", "90%", "95%"),
}


def _ask_line(prompt: str, key: str) -> str:
    choices = ", ".join(_SUGGESTIONS[key])
    return f"{prompt}\n  suggestions: {choices}\n  custom: type your own value"


def _labeled_number(low: str, names: str, unit: str) -> float | None:
    found = re.search(rf"\b(?:{names})\b[^0-9]{{0,16}}(\d+(?:\.\d+)?)\s*{unit}", low)
    return float(found.group(1)) if found else None


_CARDS = (
    {
        "field": "vout",
        "header": "Output",
        "question": "What output voltage does the sonar panel need?",
        "reason": "Output voltage changes the duty cycle, the switch rating, and the feedback divider.",
        "options": (
            {"label": "48 V", "description": "A common panel rail.", "prompt": "output 48v"},
            {"label": "60 V", "description": "A higher transmit rail.", "prompt": "output 60v"},
        ),
    },
    {
        "field": "iout",
        "header": "Current",
        "question": "What continuous output current does it need?",
        "reason": "Current changes the inductor, the switch, and the copper width.",
        "options": (
            {"label": "1.5 A", "description": "A small panel.", "prompt": "current 1.5a"},
            {"label": "1 A", "description": "A light load.", "prompt": "current 1a"},
            {"label": "2 A", "description": "A heavier panel.", "prompt": "current 2a"},
        ),
    },
    {
        "field": "vin",
        "header": "Input",
        "question": "What is the input voltage?",
        "reason": "Input voltage changes the duty cycle and the input current.",
        "options": (
            {"label": "12 V", "description": "A 12 V battery.", "prompt": "input 12v"},
            {"label": "24 V", "description": "A 24 V battery.", "prompt": "input 24v"},
        ),
    },
)
_FILL = {"vout": ("output", "v", 48.0), "iout": ("current", "a", 1.5), "vin": ("input", "v", 12.0), "freq": ("frequency", "khz", 200.0), "eff": ("efficiency", "%", 90.0)}


def _card(field: str) -> dict:
    row = next(item for item in _CARDS if item["field"] == field)
    return {
        "header": row["header"],
        "question": row["question"],
        "options": [dict(option) for option in row["options"]],
        "recommendedIndex": 0,
        "allowFreeText": True,
        "reason": row["reason"],
        "field": row["field"],
    }


def _known_ratings(text: str) -> dict[str, float]:
    low = text.lower()
    known: dict[str, float] = {}
    vin = _labeled_number(low, "input|vin", "v")
    vout = _labeled_number(low, "output|vout", "v")
    iout = _labeled_number(low, "current|iout|amps?", "a")
    freq = _labeled_number(low, "frequency|freq|switching", "khz")
    eff = _labeled_number(low, "efficiency|eff", "%")
    volts = [float(v) for v in re.findall(r"(\d+(?:\.\d+)?)\s*v\b", low)]
    amps = [float(a) for a in re.findall(r"(\d+(?:\.\d+)?)\s*a\b", low)]
    khz = re.search(r"(\d+(?:\.\d+)?)\s*khz\b", low)
    pct = re.search(r"(\d+(?:\.\d+)?)\s*%", low)
    if (vin is None or vout is None) and len(volts) >= 2 and re.search(r"\b(?:from|to)\b", low):
        vin, vout = volts[0], volts[1]
    if iout is None and amps:
        iout = amps[0]
    if freq is None and khz is not None:
        freq = float(khz.group(1))
    if eff is None and pct is not None:
        eff = float(pct.group(1))
    if vin is not None and vin > 0:
        known["vin"] = vin
    if vout is not None and vout > 0:
        known["vout"] = vout
    if iout is not None and 0 < iout <= 20:
        known["iout"] = iout
    if freq is not None and freq > 0:
        known["freq"] = freq
    if eff is not None and 0 < eff <= 100:
        known["eff"] = eff
    return known


def absorb_answer(field: str, utterance: str, combined: str) -> str:
    low = utterance.lower().strip()
    bare = re.fullmatch(r"(\d+(?:\.\d+)?)(?:\s*(v|a|khz|%))?", low)
    if bare is None:
        return f"{combined} {utterance}".strip()
    number = bare.group(1)
    spoken, _unit, _value = _FILL[field]
    suffix = {"v": "v", "a": "a", "khz": "khz", "%": "%"}[_FILL[field][1]]
    return f"{combined} {spoken} {number}{suffix}".strip()


def sonar_decision(text: str, asked: int, prefer: str | None = None) -> dict:
    """One question per turn. After three questions the remaining ratings use the recommended option and say so."""
    low = text.lower()
    known = _known_ratings(text)
    if re.search(r"\b(?:use )?(?:the )?suggestions?\b", low):
        for field, (_spoken, _unit, value) in _FILL.items():
            known.setdefault(field, value)
    missing = [field for field in ("vout", "iout", "vin", "freq", "eff") if field not in known]
    if prefer in missing:
        missing = [prefer] + [field for field in missing if field != prefer]
    note = ""
    if missing and asked >= 3:
        used = []
        for field in missing:
            _spoken, unit, value = _FILL[field]
            known[field] = value
            used.append(f"{value:g} {unit}")
        missing = []
        note = "I used the recommended " + ", ".join(used) + " for the ratings still open."
    if missing:
        return {"kind": "ask", "card": _card(missing[0]), "known": known}
    spec = {
        "vin": known["vin"],
        "vout": known["vout"],
        "iout": known["iout"],
        "freq": known["freq"] * 1000.0,
        "eff": known["eff"] / 100.0,
    }
    if spec["vout"] <= spec["vin"] or spec["vout"] > 120:
        return {"kind": "ask", "card": _card("vout"), "known": {key: value for key, value in known.items() if key != "vout"}}
    return {"kind": "design", "spec": spec, "note": note}


def sonar_suggestions(spec: dict) -> list[dict]:
    freq = spec["freq"] / 1000.0
    eff = spec["eff"] * 100.0
    return [
        {"label": "Use 2 A out", "prompt": f"design sonar panel booster input {spec['vin']:g}v output {spec['vout']:g}v current 2a frequency {freq:g}khz efficiency {eff:g}%", "type": "action"},
        {"label": "Use 24 V in", "prompt": f"design sonar panel booster input 24v output {spec['vout']:g}v current {spec['iout']:g}a frequency {freq:g}khz efficiency {eff:g}%", "type": "action"},
        {"label": "Show the board", "prompt": "show the board", "type": "navigation"},
    ]


_ROLE = {"R": "resistor", "C": "capacitor", "L": "inductor", "D": "diode", "Q": "transistor", "U": "integrated circuit", "J": "connector", "Y": "crystal"}


def think_bom(state: dict, values: dict | None = None) -> list[dict]:
    """Group placed parts by what they are, not only by package name."""
    work = _work(state)
    lands = {row["ref"]: row.get("fp") or "" for row in work.get("footprints") or []}
    given = values or {}
    grouped: dict[tuple, dict] = {}
    for part in state["pcb"]["parts"]:
        ref = str(part["ref"])
        prefix = "TP" if ref.startswith("TP") else "SW" if ref.startswith("SW") else ref[:1]
        role = _ROLE.get(prefix, str(part["pkg"]).lower())
        value = str(given.get(ref) or part.get("value") or "")
        if value:
            part["value"] = value
        land = lands.get(ref, "")
        key = (part["pkg"], land, role, value)
        row = grouped.setdefault(key, {"pkg": part["pkg"], "footprint": land, "role": role, "value": value, "refs": [], "qty": 0})
        row["refs"].append(ref)
        row["qty"] += 1
    rows = list(grouped.values())
    rows.sort(key=lambda row: (row["role"], row["value"], row["pkg"]))
    return rows


def bom_sentence(state: dict, values: dict | None = None) -> str:
    rows = think_bom(state, values)
    work = _work(state)
    work["bom"] = rows
    bits = []
    for row in rows:
        value = f" {row['value']}" if row["value"] else ""
        land = f" {row['footprint']}" if row["footprint"] else ""
        bits.append(f"{row['qty']} {row['role']}{value}{land} ({', '.join(row['refs'])})")
    work["assembly"] = "BOM " + "; ".join(bits)
    return work["assembly"] + "."


def design_sonar_booster(state: dict, spec: dict) -> str:
    """DC boost that feeds a sonar panel. Ping energy and the transducer match are not designed."""
    vin = float(spec["vin"])
    vout = float(spec["vout"])
    iout = float(spec["iout"])
    freq = float(spec["freq"])
    eff = float(spec["eff"])
    duty = 1.0 - vin / vout
    iin = iout * vout / (vin * eff)
    ripple = 0.30 * iin
    henry = vin * duty / (freq * ripple)
    ipeak = iin + ripple / 2.0
    vripple = vout * 0.01
    farad = iout * duty / (freq * vripple)
    cout_uf = max(farad * 1e6, 47.0)
    switch_v = vout * 1.5
    from py.si.desk import spacing_for, trace_ipc2221

    power_trace = trace_ipc2221(iin, rise=10.0, oz=2.0, length_mm=40.0)
    out_trace = trace_ipc2221(iout, rise=10.0, oz=2.0, length_mm=40.0)
    gap = spacing_for(vout) or {"external": 0.2, "coated": 0.1}
    vfb = 0.8
    r_bottom = 10_000.0
    r_top = r_bottom * (vout / vfb - 1.0)
    parts = [
        ("JB", "CONN", 12, 24),
        ("CB1", "CAP", 28, 24),
        ("LB", "IND", 46, 24),
        ("QB", "FET", 64, 24),
        ("DB", "DIODE", 82, 24),
        ("CB2", "CAP", 100, 24),
        ("UB", "BUCK", 64, 44),
        ("RB1", "RES", 82, 44),
        ("RB2", "RES", 100, 44),
    ]
    for ref, pkg, x, y in parts:
        _put(state, ref, pkg, x, y)
    lands = {"LB": "power-shielded", "QB": "DPAK", "DB": "SMC", "CB1": "1210", "CB2": "1210", "UB": "QFN-16"}
    for row in _work(state)["footprints"]:
        if row["ref"] in lands:
            row["fp"] = lands[row["ref"]]
    for name, a, b in (
        ("VIN", "JB", "CB1"),
        ("VIN", "CB1", "LB"),
        ("SW", "LB", "QB"),
        ("SW", "QB", "DB"),
        ("VBOOST", "DB", "CB2"),
        ("GND", "CB1", "QB"),
        ("GND", "QB", "CB2"),
        ("FB", "CB2", "RB1"),
        ("FB", "RB1", "RB2"),
        ("GND", "RB2", "UB"),
    ):
        _tie(state, name, a, b)
    work = _work(state)
    work["industry"] = "marine"
    work["board"] = "power"
    work["focus"] = "Sonar panel booster"
    params = work.setdefault("params", {})
    params["layers"] = 4
    params["material"] = "FR4"
    params["thickness_mm"] = 1.6
    params["copper_oz"] = 2
    pcb = state["pcb"]
    pcb["outline"] = {"length": 120, "width": 70}
    pcb["tracks"] = []
    pcb["released"] = False
    return (
        f"Sonar panel booster. {vin:.0f} V in, {vout:.0f} V out, {iout:.2f} A continuous. "
        f"Duty {duty:.2f}. Input current {iin:.2f} A at {eff * 100:.0f}% efficiency. "
        f"Inductor {henry * 1e6:.1f} uH at {freq / 1000:.0f} kHz, 30% ripple, peak {ipeak:.2f} A. "
        f"Switch and diode rated {switch_v:.0f} V, switch current {ipeak:.2f} A, diode current {iout:.2f} A. "
        f"Output capacitor at least {cout_uf:.0f} uF (the ripple formula gives {farad * 1e6:.0f} uF; 47 uF is the floor because that formula ignores ESR). "
        f"Feedback {r_top / 1000:.1f} kohm over {r_bottom / 1000:.0f} kohm into 0.8 V. "
        f"2 oz copper: input trace {power_trace['width_mm']:.2f} mm, output trace {out_trace['width_mm']:.2f} mm, 10 C rise. "
        f"Coated clearance {gap['coated']:.2f} mm at {vout:.0f} V. "
        "Placed JB, CB1, LB, QB, DB, CB2, UB, RB1, RB2 on a 120 x 70 mm, 4-layer marine board. "
        "The acoustic ping, the transducer match, and the control-loop compensation are not designed. "
        + bom_sentence(state, {"LB": f"{henry * 1e6:.1f} uH", "CB2": f"{cout_uf:.0f} uF", "RB1": f"{r_top / 1000:.1f} kohm", "RB2": f"{r_bottom / 1000:.0f} kohm"})
    )


def design_bms(state: dict) -> str:
    """Place a BMS starter. Cell limits are not taken from a datasheet."""
    steps = (
        "Design order: pack connector, cell-sense taps off the pack current, "
        "a monitor on the sense net, a passive balance resistor, "
        "back-to-back charge and discharge FETs, a shunt, and a local capacitor. "
        "Cell limits and balance current come from the cell datasheet. No fuel-gauge integration."
    )
    names = {net["name"] for net in state["pcb"]["nets"]}
    placed = {part["ref"] for part in state["pcb"]["parts"]}
    if "J8" in placed and "SENSE" in names:
        return steps
    for ref, pkg, x, y in (
        ("J8", "CONN", 12, 64),
        ("U8", "MCU", 48, 64),
        ("R8", "RES", 30, 52),
        ("R9", "RES", 30, 76),
        ("Q8", "FET", 72, 56),
        ("Q9", "FET", 72, 76),
        ("R10", "RES", 92, 64),
        ("C8", "CAP", 48, 80),
    ):
        _put(state, ref, pkg, x, y)
    for name, a, b in (
        ("SENSE", "J8", "U8"),
        ("BAL", "R9", "U8"),
        ("PACK", "J8", "Q8"),
        ("GND", "Q8", "Q9"),
        ("SHUNT", "R10", "U8"),
        ("GND", "U8", "C8"),
    ):
        _tie(state, name, a, b)
    state["pcb"]["tracks"] = []
    state["pcb"]["released"] = False
    return "Placed J8, U8, R8, R9, Q8, Q9, R10, C8. " + steps


def design_bridge(state: dict) -> str:
    """Place a diode bridge and a bulk capacitor. Ripple and the transformer are not sized."""
    steps = (
        "Design order: AC connector, four diodes as a bridge, bulk capacitor on the rectified rail. "
        "No transformer, no regulator, and the ripple current is not calculated."
    )
    placed = {part["ref"] for part in state["pcb"]["parts"]}
    if "D11" in placed and "C7" in placed:
        return steps
    for ref, pkg, x, y in (
        ("J7", "CONN", 12, 100),
        ("D11", "DIODE", 36, 88),
        ("D12", "DIODE", 36, 112),
        ("D13", "DIODE", 60, 88),
        ("D14", "DIODE", 60, 112),
        ("C7", "CAP", 84, 100),
    ):
        _put(state, ref, pkg, x, y)
    for name, a, b in (
        ("AC1", "J7", "D11"),
        ("AC1", "D11", "D12"),
        ("AC2", "J7", "D13"),
        ("AC2", "D13", "D14"),
        ("VRECT", "D11", "C7"),
        ("VRECT", "D13", "C7"),
        ("GND", "D12", "C7"),
        ("GND", "D14", "C7"),
    ):
        _tie(state, name, a, b)
    state["pcb"]["tracks"] = []
    state["pcb"]["released"] = False
    return "Placed J7, D11, D12, D13, D14, C7. " + steps


def build_circuit(state: dict, kind: str) -> str:
    """Place a starter circuit. This is not a silicon layout and not a SPICE run."""
    kind = kind if kind in {"switch", "plc", "pac", "mcu"} else "mcu"
    if kind == "switch":
        parts = [("Q1", "FET", 16, 20), ("D1", "DIODE", 36, 20), ("R1", "RES", 16, 40), ("C1", "CAP", 36, 40), ("L1", "IND", 56, 40)]
        nets = [("SW", "Q1", "D1"), ("GND", "Q1", "C1"), ("VBUS", "C1", "L1"), ("3V3", "R1", "Q1")]
        limit = "Low-side FET, gate resistor, freewheel diode, inductor, and a local capacitor. Switching loss and dead time are not simulated."
    elif kind == "plc":
        parts = [("J1", "CONN", 12, 28), ("U1", "MCU", 32, 28), ("R1", "RES", 52, 16), ("D1", "DIODE", 72, 16), ("C1", "CAP", 52, 40), ("Q1", "FET", 72, 40), ("D2", "LED", 92, 28)]
        nets = [("GND", "J1", "U1"), ("SW", "J1", "R1"), ("3V3", "R1", "U1"), ("VBUS", "U1", "Q1"), ("GND", "Q1", "D2")]
        limit = "PLC-style field input and FET output. Not an IEC 61131 scan cycle."
    elif kind == "pac":
        parts = [("J1", "CONN", 12, 24), ("U2", "LDO", 32, 24), ("U1", "MCU", 52, 24), ("C1", "CAP", 52, 44), ("R1", "RES", 72, 16), ("Q1", "FET", 72, 36), ("D1", "DIODE", 92, 24)]
        nets = [("VBUS", "J1", "U2"), ("3V3", "U2", "U1"), ("GND", "U1", "C1"), ("SW", "U1", "Q1"), ("GND", "Q1", "D1")]
        limit = "PAC-style controller: MCU, regulator, discrete input resistor, and a FET output. Not a PAC runtime."
    else:
        parts = [("J1", "USB-C", 12, 24), ("U2", "LDO", 32, 24), ("U1", "MCU", 56, 24), ("C1", "CAP", 56, 44), ("R1", "RES", 76, 24), ("D2", "LED", 96, 24)]
        nets = [("VBUS", "J1", "U2"), ("3V3", "U2", "U1"), ("GND", "U1", "C1"), ("SW", "U1", "R1"), ("GND", "R1", "D2")]
        limit = "MCU board with a regulator, decoupling, and an LED. The chip itself is not laid out. A bare MCU still needs a crystal."
    for ref, pkg, x, y in parts:
        _put(state, ref, pkg, x, y)
    for name, a, b in nets:
        _tie(state, name, a, b)
    state["pcb"]["tracks"] = []
    state["pcb"]["released"] = False
    by_ref = {part["ref"]: part for part in state["pcb"]["parts"]}
    far = ""
    if "Q1" in by_ref and "D1" in by_ref:
        gap = math.hypot(by_ref["Q1"]["x"] - by_ref["D1"]["x"], by_ref["Q1"]["y"] - by_ref["D1"]["y"])
        if gap > 30:
            far = f" Freewheel diode is {gap:.0f} mm from the switch."
    names = ", ".join(ref for ref, _pkg, _x, _y in parts)
    return f"Placed {names}. {limit}{far}"


def _box(kind: str, x: float, y: float, w: float, h: float) -> dict:
    return {"kind": kind, "x": x, "y": y, "w": w, "h": h}


def design_cell(state: dict, kind: str) -> str:
    """CMOS cell from transistors on a 1 µm teaching grid. Not a foundry layout."""
    kind = {"inv": "inverter", "inverter": "inverter", "nand": "nand2", "nor": "nor2"}.get(kind, "inverter")
    if kind == "nand2":
        devices = [
            {"name": "MP1", "type": "PMOS", "w": 2, "l": 1, "g": "A", "d": "Y", "s": "VDD"},
            {"name": "MP2", "type": "PMOS", "w": 2, "l": 1, "g": "B", "d": "Y", "s": "VDD"},
            {"name": "MN1", "type": "NMOS", "w": 1, "l": 1, "g": "A", "d": "Y", "s": "Z"},
            {"name": "MN2", "type": "NMOS", "w": 1, "l": 1, "g": "B", "d": "Z", "s": "VSS"},
        ]
        shapes = [
            _box("metal", 0, 0, 12, 1),
            _box("metal", 0, 17, 12, 1),
            _box("ndiff", 2, 2, 8, 2.5),
            _box("pdiff", 2, 12.5, 8, 2.5),
            _box("poly", 3.2, 1.2, 1.2, 15.4),
            _box("poly", 7.2, 1.2, 1.2, 15.4),
            _box("contact", 2.2, 2.8, 0.7, 0.7),
            _box("contact", 5.2, 2.8, 0.7, 0.7),
            _box("contact", 9.0, 2.8, 0.7, 0.7),
            _box("contact", 2.2, 13.3, 0.7, 0.7),
            _box("contact", 5.2, 13.3, 0.7, 0.7),
            _box("contact", 9.0, 13.3, 0.7, 0.7),
            _box("metal", 2.2, 1, 0.7, 2.5),
            _box("metal", 2.2, 13.3, 0.7, 3.7),
            _box("metal", 9.0, 13.3, 0.7, 3.7),
            _box("metal", 5.2, 2.8, 0.7, 11.2),
        ]
        width, height = 12, 18
    elif kind == "nor2":
        devices = [
            {"name": "MP1", "type": "PMOS", "w": 2, "l": 1, "g": "A", "d": "Y", "s": "P"},
            {"name": "MP2", "type": "PMOS", "w": 2, "l": 1, "g": "B", "d": "P", "s": "VDD"},
            {"name": "MN1", "type": "NMOS", "w": 1, "l": 1, "g": "A", "d": "Y", "s": "VSS"},
            {"name": "MN2", "type": "NMOS", "w": 1, "l": 1, "g": "B", "d": "Y", "s": "VSS"},
        ]
        shapes = [
            _box("metal", 0, 0, 12, 1),
            _box("metal", 0, 17, 12, 1),
            _box("ndiff", 2, 2, 8, 2.5),
            _box("pdiff", 2, 12.5, 8, 2.5),
            _box("poly", 3.2, 1.2, 1.2, 15.4),
            _box("poly", 7.2, 1.2, 1.2, 15.4),
            _box("contact", 2.2, 2.8, 0.7, 0.7),
            _box("contact", 5.2, 2.8, 0.7, 0.7),
            _box("contact", 9.0, 2.8, 0.7, 0.7),
            _box("contact", 2.2, 13.3, 0.7, 0.7),
            _box("contact", 5.2, 13.3, 0.7, 0.7),
            _box("contact", 9.0, 13.3, 0.7, 0.7),
            _box("metal", 2.2, 1, 0.7, 2.5),
            _box("metal", 9.0, 1, 0.7, 2.5),
            _box("metal", 5.2, 2.8, 0.7, 11.2),
            _box("metal", 9.0, 13.3, 0.7, 3.7),
        ]
        width, height = 12, 18
    else:
        devices = [
            {"name": "MP1", "type": "PMOS", "w": 2, "l": 1, "g": "A", "d": "Y", "s": "VDD"},
            {"name": "MN1", "type": "NMOS", "w": 1, "l": 1, "g": "A", "d": "Y", "s": "VSS"},
        ]
        shapes = [
            _box("metal", 0, 0, 8, 1),
            _box("metal", 0, 15, 8, 1),
            _box("ndiff", 2, 2, 4, 2.5),
            _box("pdiff", 2, 11.5, 4, 2.5),
            _box("poly", 3.4, 1.2, 1.2, 13.6),
            _box("contact", 2.3, 2.8, 0.7, 0.7),
            _box("contact", 5.0, 2.8, 0.7, 0.7),
            _box("contact", 2.3, 12.3, 0.7, 0.7),
            _box("contact", 5.0, 12.3, 0.7, 0.7),
            _box("metal", 2.3, 1, 0.7, 2.5),
            _box("metal", 2.3, 12.3, 0.7, 2.7),
            _box("metal", 5.0, 2.8, 0.7, 10.2),
        ]
        width, height = 8, 16
    note = "1 µm teaching grid. PMOS is drawn twice as wide as NMOS. Not a foundry PDK, not DRC, and not GDSII."
    _work(state)["cell"] = {"name": kind, "devices": devices, "shapes": shapes, "width": width, "height": height, "note": note}
    bits = ", ".join(f"{row['name']} {row['type']} W/L {row['w']}/{row['l']} g={row['g']}" for row in devices)
    return f"{kind} from transistors: {bits}. {note}"


def _work(state: dict) -> dict:
    work = state.setdefault("work", empty_work())
    for key, value in empty_work().items():
        work.setdefault(key, value)
    return work


def _symbols(state: dict) -> list[dict]:
    symbols = list(_work(state)["symbols"])
    if symbols:
        return symbols
    return [{"ref": p["ref"], "pkg": p["pkg"]} for p in state["pcb"]["parts"]]


def _nets(state: dict) -> list[dict]:
    return list(_work(state)["wires"]) + list(state["pcb"]["nets"])


def _note(work: dict, name: str, status: str, detail: str) -> str:
    work["chip"] = [row for row in work["chip"] if row["name"] != name]
    work["chip"].append({"name": name, "status": status, "detail": detail})
    return f"{name}: {status}. {detail}"


def chip_check(state: dict, kind: str) -> str:
    work = _work(state)
    symbols = _symbols(state)
    pkgs = {s["pkg"] for s in symbols}
    names = {n["name"] for n in _nets(state)}
    caps = sum(1 for s in symbols if s["pkg"] == "CAP")
    ics = pkgs & ICS
    if not symbols:
        return _note(work, kind, "warn", "Add a symbol or a placed part first.")
    if kind == "pin":
        if "ESP32" in pkgs or "MCU" in pkgs:
            if "3V3" in names and "GND" in names:
                return _note(work, kind, "pass", "3V3 and GND reach the chip. Keep EN high and GPIO0 strapped for boot.")
            return _note(work, kind, "warn", "The chip is missing 3V3 or GND.")
        return _note(work, kind, "pass", "No MCU yet. Power pins will be checked when one is added.")
    if kind == "decap":
        if ics and caps >= len(ics):
            return _note(work, kind, "pass", f"{caps} capacitor(s) for {len(ics)} chip(s).")
        if ics:
            return _note(work, kind, "warn", f"Want one capacitor per chip. Have {caps} for {len(ics)}.")
        return _note(work, kind, "pass", "No chip that needs a local capacitor.")
    if kind == "power":
        if ("ESP32" in pkgs or "MCU" in pkgs) and "3V3" in names and ({"LDO", "BUCK"} & pkgs) and "VBUS" in names:
            return _note(work, kind, "pass", "VBUS feeds a regulator, and 3V3 reaches the chip.")
        if "ESP32" in pkgs or "MCU" in pkgs:
            return _note(work, kind, "warn", "Chip power wants VBUS, a regulator, and a 3V3 net.")
        return _note(work, kind, "pass", "No digital chip on the sheet yet.")
    if kind == "io":
        if "USB-C" in pkgs and ("ESP32" in pkgs or "MCU" in pkgs):
            return _note(work, kind, "pass", "USB is 5 V on VBUS only. Chip IO stays on 3V3.")
        return _note(work, kind, "pass", "IO stays on the 3V3 domain. Do not tie a chip pin to VBUS.")
    if kind == "clock":
        if "ESP32" in pkgs:
            return _note(work, kind, "pass", "The module crystal is inside the can.")
        if "MCU" in pkgs:
            return _note(work, kind, "warn", "A bare MCU still needs its crystal and load capacitors.")
        return _note(work, kind, "pass", "No clock domain yet.")
    if kind == "reset":
        if ("ESP32" in pkgs or "MCU" in pkgs) and caps:
            return _note(work, kind, "pass", "EN can rise through the capacitor. Hold it high in run.")
        if "ESP32" in pkgs or "MCU" in pkgs:
            return _note(work, kind, "warn", "Add a capacitor on EN so reset is not a glitch.")
        return _note(work, kind, "pass", "No reset pin in the design yet.")
    if kind == "boot":
        if "ESP32" in pkgs or "MCU" in pkgs:
            return _note(work, kind, "warn", "GPIO0 must idle high. Pull it down only to enter the bootloader.")
        return _note(work, kind, "pass", "No boot strap yet.")
    if kind == "thermal":
        hot = "ESP32" in pkgs or "BUCK" in pkgs
        if hot:
            return _note(work, kind, "pass", "Give the chip a copper pour. Module budget is about 0.5 W.")
        return _note(work, kind, "pass", "Nothing hot on the sheet.")
    if kind == "si":
        if "I2C" in names and any(s["pkg"] == "RES" for s in symbols):
            return _note(work, kind, "pass", "I2C has a pull-up resistor. Rise time stays inside the bus budget.")
        if "I2C" in names:
            return _note(work, kind, "warn", "I2C needs a pull-up, typically 4.7 kΩ to 3V3.")
        return _note(work, kind, "pass", "No fast net to check yet.")
    if kind == "pi":
        if "GND" in names and caps:
            return _note(work, kind, "pass", "Ground is named and capacitors are on the sheet.")
        return _note(work, kind, "warn", "Power integrity wants a GND net and a capacitor at each chip.")
    return _note(work, kind, "warn", "Unknown chip discipline.")


def design_person(state: dict) -> str:
    """Walk the open board the way a designer would, and do the steps that are still missing."""
    work = _work(state)
    pcb = state["pcb"]
    board = BOARD.get(str(work.get("board") or ""), {})
    industry = INDUSTRY.get(str(work.get("industry") or ""), {})
    subject = str(work.get("focus") or board.get("title") or "the open board")
    field = industry.get("title") or "general electronics"
    kind = board.get("title") or "unclassified board"
    lines = [
        f"I am designing {subject}.",
        f"Purpose: a {kind} for {field}.",
        "Outcome: a board a fab can build and a house can assemble. That means a wired schematic, routed copper, a simulation note, a 3D check, fabrication files, a centroid, and a BOM.",
    ]
    wires = list(work.get("wires") or [])
    if wires:
        shown = [f"{row['name']} from {row['a']} to {row['b']}" for row in wires[:8]]
        extra = f", plus {len(wires) - 8} more" if len(wires) > 8 else ""
        lines.append("Schematic wires: " + "; ".join(shown) + extra + ".")
    else:
        lines.append("Schematic wires: none yet. I will not invent nets.")
    lines.append(apply(state, {"op": "sch_erc"}))
    if pcb["nets"] and not pcb.get("tracks"):
        lines.append(autoroute(state))
    elif pcb.get("tracks"):
        lines.append(f"PCB traces: {len(pcb['tracks'])} already routed. I did not rip them up.")
    else:
        lines.append("PCB traces: no nets to route.")
    tracks = list(pcb.get("tracks") or [])
    if tracks:
        shown = [f"{row['name']} {row['a']} to {row['b']} at {row['width']} mm" for row in tracks[:6]]
        extra = f", plus {len(tracks) - 6} more" if len(tracks) > 6 else ""
        lines.append("Routes: " + "; ".join(shown) + extra + ".")
    lines.append("Simulation activity: DC reads the rails the nets name. Transient asks whether those rails settle inside 10 ms.")
    lines.append(apply(state, {"op": "sim_dc"}))
    lines.append(apply(state, {"op": "sim_tran"}))
    lines.append("3D board: I check the placed bodies and the tallest part. This is not a rendered picture.")
    lines.append(apply(state, {"op": "view_3d"}))
    lines.append(apply(state, {"op": "fab_stack"}))
    lines.append("Fabrication files: " + apply(state, {"op": "fab_gerber"}))
    lines.append(apply(state, {"op": "asm_bom"}))
    lines.append(apply(state, {"op": "asm_pos"}))
    return "\n".join(lines)


def apply(state: dict, action: dict) -> str:
    op = action.get("op")
    pcb = state["pcb"]
    cad = state["cad"]
    work = _work(state)
    if op == "sch_add":
        ref = canon_ref(str(action["ref"]))
        pkg = canon_pkg(str(action["pkg"]))
        work["symbols"] = [s for s in work["symbols"] if s["ref"] != ref]
        work["symbols"].append({"ref": ref, "pkg": pkg})
        return f"Schematic symbol {pkg} as {ref}."
    if op == "sch_wire":
        name = canon_net(str(action["name"]))
        a, b = canon_ref(str(action["a"])), canon_ref(str(action["b"]))
        work["wires"] = [n for n in work["wires"] if not (n["name"] == name and n["a"] == a and n["b"] == b)]
        work["wires"].append({"name": name, "a": a, "b": b})
        return f"Schematic wire {name} from {a} to {b}."
    if op == "sch_erc":
        symbols = work["symbols"]
        if not symbols:
            return "Schematic is empty."
        refs = [s["ref"] for s in symbols]
        wires = work["wires"]
        touched = {n["a"] for n in wires} | {n["b"] for n in wires}
        names = {n["name"] for n in wires}
        pkgs = {s["pkg"] for s in symbols}
        notes = []
        notes.append("duplicate refs" if len(refs) != len(set(refs)) else f"{len(symbols)} symbols")
        loose = [r for r in refs if r not in touched]
        notes.append("unwired " + ",".join(loose) if loose else "every symbol is wired")
        if "USB-C" in pkgs and "VBUS" not in names:
            notes.append("USB-C has no VBUS wire")
        if ({"ESP32", "MCU"} & pkgs) and "GND" not in names:
            notes.append("chip has no GND")
        return "ERC: " + ". ".join(notes) + "."
    if op == "fp_assign":
        ref = canon_ref(str(action["ref"]))
        known = {s["ref"]: s["pkg"] for s in _symbols(state)}
        if ref not in known:
            return f"{ref} is not on the schematic or the layout."
        current = next((row for row in work["footprints"] if row["ref"] == ref and row.get("pads")), None)
        if current:
            return f"{ref} already has a datasheet footprint {current['fp']}."
        fp = FP_OF.get(known[ref], known[ref])
        work["footprints"] = [row for row in work["footprints"] if row["ref"] != ref]
        work["footprints"].append({"ref": ref, "fp": fp})
        return f"Footprint {fp} assigned to {ref}."
    if op == "sim_dc":
        names = {n["name"] for n in _nets(state)}
        pkgs = {s["pkg"] for s in _symbols(state)}
        if not names and not pkgs:
            return "Nothing to simulate. Add a symbol and a wire."
        lines = []
        lines.append("GND 0.00 V" if "GND" in names else "GND missing")
        if "VBUS" in names:
            lines.append("VBUS 5.00 V")
        if "3V3" in names and ({"LDO", "BUCK"} & pkgs) and "VBUS" in names:
            lines.append("3V3 3.30 V")
        elif "3V3" in names:
            lines.append("3V3 is open")
        if "I2C" in names:
            lines.append("I2C idle high")
        work["sim"] = "DC " + ", ".join(lines)
        return work["sim"] + "."
    if op == "sim_tran":
        pkgs = {s["pkg"] for s in _symbols(state)}
        if not _symbols(state):
            return "Nothing to simulate."
        extra = " ESP32 EN rises after 1 ms." if "ESP32" in pkgs else ""
        work["sim"] = "Transient 0–10 ms, rails settle by 2 ms." + extra
        return work["sim"]
    if op == "view_3d":
        parts = pcb["parts"]
        if not parts:
            return "Layout is empty. Place a part before the 3D view."
        assigned = {row["ref"] for row in work["footprints"]}
        missing = [p["ref"] for p in parts if p["ref"] not in assigned]
        bodies = [float(row["body"]["h"]) for row in work["footprints"] if isinstance(row.get("body"), dict) and row["body"].get("h")]
        tall = max([HEIGHT.get(p["pkg"], 0.6) for p in parts] + bodies)
        work["view3d"] = f"{len(parts)} models, tallest {tall:.1f} mm"
        if missing:
            return work["view3d"] + ". Missing footprints: " + ", ".join(missing) + "."
        return "3D viewer: " + work["view3d"] + "."
    if op == "fab_stack":
        work["stack"] = stack_line(state)
        return "Stackup: " + work["stack"]
    if op == "set_industry":
        kind = str(action.get("kind") or "")
        if kind not in INDUSTRY:
            return "That field is not in the profile list. Ask to list PCB fields."
        work["industry"] = kind
        work["stack"] = stack_line(state)
        return f"Industry set to {INDUSTRY[kind]['title']}."
    if op == "set_board":
        kind = str(action.get("kind") or "")
        if kind not in BOARD:
            return "Board class is tiny, power, bms, motor, cpu, gpu, modem, or motherboard."
        work["board"] = kind
        work["stack"] = stack_line(state)
        return f"Board class set to {BOARD[kind]['title']}."
    if op == "power_select":
        from py.si.power import describe

        picked = describe(str(action.get("kind") or ""))
        if picked is None:
            return "That power board is not in the catalog."
        board, text = picked
        work["board"] = board
        work["power"] = str(action.get("kind") or "")
        work["stack"] = stack_line(state)
        work["focus"] = text.split(".")[0]
        kind = str(action.get("kind") or "")
        if action.get("draw") and kind.startswith("bms_"):
            text = text + " " + design_bms(state)
        if action.get("draw") and kind == "acdc_bridge":
            text = text + " " + design_bridge(state)
        return text
    if op == "robot_select":
        from py.si.robot import describe as describe_robot

        picked = describe_robot(str(action.get("kind") or ""))
        if picked is None:
            return "That robot board is not in the catalog."
        title, text = picked
        work["industry"] = "robot"
        work["robot"] = str(action.get("kind") or "")
        work["focus"] = title
        work["stack"] = stack_line(state)
        return text
    if op == "computer_select":
        from py.si.computer import describe as describe_computer

        picked = describe_computer(str(action.get("kind") or ""))
        if picked is None:
            return "That computer board is not in the catalog."
        title, text = picked
        work["computer"] = str(action.get("kind") or "")
        work["focus"] = title
        work["stack"] = stack_line(state)
        return text
    if op == "sensor_select":
        from py.si.sensor import describe as describe_sensor

        picked = describe_sensor(str(action.get("kind") or ""))
        if picked is None:
            return "That sensor or switch board is not in the catalog."
        title, text = picked
        work["sensor"] = str(action.get("kind") or "")
        work["focus"] = title
        work["stack"] = stack_line(state)
        return text
    if op == "set_outline":
        length, width = float(action["length"]), float(action["width"])
        if length <= 0 or width <= 0:
            return "Outline needs a positive length and width."
        work["outline"] = [length, width]
        return f"Board outline {length:g} × {width:g} mm."
    if op == "industry_check":
        return industry_rules(state)
    if op == "handle_all":
        return handle_all(state)
    if op == "handle_industry":
        return handle_industry(state, str(action.get("kind") or ""))
    if op == "handle_board":
        return handle_board(state, str(action.get("kind") or ""))
    if op == "place_sheet":
        return place_sheet(state)
    if op == "build_datasheet":
        variants = action.get("variants") or []
        if isinstance(variants, str):
            variants = json.loads(variants)
        if not isinstance(variants, list):
            return "The datasheet did not contain a package list."
        return build_datasheet(state, variants)
    if op == "datasheet_rebuild":
        sheet = ROOT / "datasheet.txt"
        if not sheet.exists() or not sheet.read_text().strip():
            return "Upload a datasheet first. PDF or text."
        from py.si.datasheet import parse

        variants, gaps = parse(sheet.read_text())
        if not variants:
            return "Datasheet held. " + " ".join(gaps)
        note = build_datasheet(state, variants)
        if gaps:
            note += " " + " ".join(gaps)
        return note
    if op == "cover_all":
        return cover_all(state)
    if op == "fab_gerber":
        if not pcb["parts"]:
            return "Fabrication needs a layout."
        placed = {p["ref"] for p in pcb["parts"]}
        unplaced = [s["ref"] for s in work["symbols"] if s["ref"] not in placed]
        assigned = {row["ref"] for row in work["footprints"]}
        missing = [p["ref"] for p in pcb["parts"] if p["ref"] not in assigned]
        warns = [i for i in drc(state) if i["status"] == "warn"]
        if unplaced:
            return "Fabrication held. Schematic refs are not on the layout: " + ", ".join(unplaced) + "."
        if missing or warns:
            why = "Missing footprints: " + ", ".join(missing) if missing else warns[0]["detail"]
            return f"Fabrication held. {why}"
        pcb["released"] = True
        work["fab"] = "Gerber, drill, and paste packed."
        return work["fab"] + " " + (work["stack"] or "Run the stackup if the fab needs it.")
    if op == "asm_bom":
        if not pcb["parts"]:
            return "Assembly needs placed parts."
        placed = {p["ref"] for p in pcb["parts"]}
        unplaced = [s["ref"] for s in work["symbols"] if s["ref"] not in placed]
        if unplaced:
            return "Assembly held. Schematic refs are not on the layout: " + ", ".join(unplaced) + "."
        return bom_sentence(state)
    if op == "asm_pos":
        if not pcb["parts"]:
            return "Assembly needs placed parts."
        placed = {p["ref"] for p in pcb["parts"]}
        unplaced = [s["ref"] for s in work["symbols"] if s["ref"] not in placed]
        if unplaced:
            return "Pick-and-place held. Schematic refs are not on the layout: " + ", ".join(unplaced) + "."
        assigned = {row["ref"]: row["fp"] for row in work["footprints"]}
        missing = [p["ref"] for p in pcb["parts"] if p["ref"] not in assigned]
        if missing:
            return "Pick-and-place held. Missing footprints: " + ", ".join(missing) + "."
        lines = [f"{p['ref']} {assigned[p['ref']]} {p['x']:g} {p['y']:g} top" for p in pcb["parts"]]
        work["assembly"] = "Centroid " + "; ".join(lines)
        return work["assembly"] + "."
    if op == "chip_check":
        return chip_check(state, str(action.get("kind") or "pin"))
    if op == "pcb_add":
        ref = canon_ref(str(action["ref"]))
        pkg = canon_pkg(str(action["pkg"]))
        x, y = float(action["x"]), float(action["y"])
        pcb["parts"] = [p for p in pcb["parts"] if p["ref"] != ref]
        pcb["parts"].append({"ref": ref, "pkg": pkg, "x": x, "y": y})
        pcb["tracks"] = []
        pcb["released"] = False
        return f"Placed {pkg} as {ref} at ({x:g}, {y:g}) mm."
    if op == "pcb_delete":
        ref = canon_ref(str(action["ref"]))
        before = len(pcb["parts"])
        pcb["parts"] = [part for part in pcb["parts"] if part["ref"] != ref]
        if len(pcb["parts"]) == before:
            return f"{ref} is not on the board."
        pcb["nets"] = [net for net in pcb["nets"] if net["a"] != ref and net["b"] != ref]
        pcb["tracks"] = []
        pcb["released"] = False
        return f"Removed {ref}."
    if op == "pcb_move":
        ref = canon_ref(str(action["ref"]))
        part = next((item for item in pcb["parts"] if item["ref"] == ref), None)
        if part is None:
            return f"{ref} is not on the board."
        part["x"], part["y"] = float(action["x"]), float(action["y"])
        pcb["tracks"] = []
        pcb["released"] = False
        return f"Moved {ref} to ({part['x']:g}, {part['y']:g}) mm."
    if op == "pcb_rotate":
        ref = canon_ref(str(action["ref"]))
        part = next((item for item in pcb["parts"] if item["ref"] == ref), None)
        if part is None:
            return f"{ref} is not on the board."
        part["rot"] = int(float(action["angle"])) % 360
        return f"{ref} rotation stored as {part['rot']}°. The drawing does not turn the pads."
    if op == "pcb_copy":
        src = canon_ref(str(action["ref"]))
        dest = canon_ref(str(action["to"]))
        part = next((item for item in pcb["parts"] if item["ref"] == src), None)
        if part is None:
            return f"{src} is not on the board."
        x = float(action["x"]) if action.get("x") is not None else float(part["x"]) + 5
        y = float(action["y"]) if action.get("y") is not None else float(part["y"]) + 5
        pcb["parts"] = [item for item in pcb["parts"] if item["ref"] != dest]
        pcb["parts"].append({"ref": dest, "pkg": part["pkg"], "x": x, "y": y, "rot": part.get("rot", 0), "side": part.get("side", "top")})
        pcb["tracks"] = []
        pcb["released"] = False
        return f"Copied {src} to {dest} at ({x:g}, {y:g}) mm."
    if op == "pcb_swap":
        left = canon_ref(str(action["a"]))
        right = canon_ref(str(action["b"]))
        a = next((item for item in pcb["parts"] if item["ref"] == left), None)
        b = next((item for item in pcb["parts"] if item["ref"] == right), None)
        if a is None or b is None:
            missing = left if a is None else right
            return f"{missing} is not on the board."
        a["x"], b["x"] = b["x"], a["x"]
        a["y"], b["y"] = b["y"], a["y"]
        pcb["tracks"] = []
        pcb["released"] = False
        return f"Swapped {left} and {right}."
    if op == "pcb_flip":
        ref = canon_ref(str(action["ref"]))
        part = next((item for item in pcb["parts"] if item["ref"] == ref), None)
        if part is None:
            return f"{ref} is not on the board."
        part["side"] = "bottom" if part.get("side") != "bottom" else "top"
        return f"{ref} is stored on the {part['side']}. The drawing stays a top view."
    if op == "pcb_find":
        ref = canon_ref(str(action["ref"]))
        part = next((item for item in pcb["parts"] if item["ref"] == ref), None)
        if part is None:
            return f"{ref} is not on the board."
        return f"{ref} is {part['pkg']} at ({float(part['x']):g}, {float(part['y']):g}) mm, rotation {int(part.get('rot') or 0)}°, {part.get('side') or 'top'}."
    if op == "note":
        return str(action.get("text") or "")
    if op == "pcb_net":
        name = canon_net(str(action["name"]))
        a, b = canon_ref(str(action["a"])), canon_ref(str(action["b"]))
        pcb["nets"] = [n for n in pcb["nets"] if not (n["name"] == name and n["a"] == a and n["b"] == b)]
        pcb["nets"].append({"name": name, "a": a, "b": b})
        pcb["tracks"] = []
        pcb["released"] = False
        return f"Net {name} ties {a} to {b}."
    if op == "pcb_flow":
        return design_person(state)
    if op == "pcb_drc":
        items = drc(state)
        return "DRC: " + " ".join(f"{i['rule']} {i['status']}." for i in items)
    if op == "pcb_status":
        if not pcb["parts"]:
            return "PCB is empty."
        bits = ", ".join(f"{p['ref']} {p['pkg']} ({p['x']:g},{p['y']:g})" for p in pcb["parts"])
        nets = ", ".join(f"{n['name']}:{n['a']}-{n['b']}" for n in pcb["nets"]) or "none"
        return f"Board: {bits}. Nets: {nets}. Released: {pcb['released']}."
    if op == "cad_sketch":
        cad["length"] = float(action["length"])
        cad["width"] = float(action["width"])
        cad["thickness"] = None
        return f"Sketch {cad['length']:g} × {cad['width']:g} mm."
    if op == "cad_extrude":
        if cad["length"] is None:
            return "Sketch a rectangle before extruding."
        cad["thickness"] = float(action["thickness"])
        return f"Extruded {cad['thickness']:g} mm."
    if op == "cad_hole":
        if cad["thickness"] is None:
            return "Extrude the solid before the hole."
        dia = float(action["diameter"])
        limit = min(float(cad["length"]), float(cad["width"]))
        if dia >= limit:
            return f"Hole Ø{dia:g} does not fit inside {limit:g} mm."
        cad["hole"] = dia
        return f"Through hole Ø{dia:g} mm."
    if op == "cad_fillet":
        if cad["thickness"] is None:
            return "Extrude the solid before the fillet."
        cad["fillet"] = float(action["radius"])
        return f"Fillet R{cad['fillet']:g} mm."
    if op == "cad_chamfer":
        if cad["thickness"] is None:
            return "Extrude the solid before the chamfer."
        size = float(action["size"])
        if size <= 0 or size * 2 >= min(float(cad["length"]), float(cad["width"])):
            return "Chamfer does not fit this solid."
        cad["chamfer"] = size
        return f"Chamfer {size:g} mm on the vertical edges."
    if op == "cad_shell":
        if cad["thickness"] is None:
            return "Extrude the solid before the shell."
        wall = float(action["wall"])
        if wall <= 0 or wall * 2 >= min(float(cad["length"]), float(cad["width"])) or wall >= float(cad["thickness"]):
            return "Shell wall does not fit this solid."
        cad["shell"] = wall
        return f"Shell wall {wall:g} mm, open on the top."
    if op == "impedance":
        return impedance(state, float(action.get("ohms") or 50))
    if op == "pour":
        return pour_ground(state)
    if op == "dfm":
        return dfm(state)
    if op == "desk":
        return desk_job(state, str(action.get("kind") or ""), action.get("value"), str(action.get("name") or ""))
    if op == "feature_audit":
        from py.si.audit import summarize

        text = summarize()
        _work(state)["desk"] = text
        return text
    if op == "autoroute":
        return autoroute(state, str(action.get("which") or ""))
    if op == "build_circuit":
        return build_circuit(state, str(action.get("kind") or "mcu"))
    if op == "design_cell":
        return design_cell(state, str(action.get("kind") or "inv"))
    if op == "set_ipc":
        kind = str(action.get("kind") or "")
        if kind not in {"1", "2", "3"}:
            return "IPC class is 1, 2, or 3."
        _work(state)["ipc_class"] = kind
        return ipc_report(state)
    if op == "ipc_check":
        return ipc_report(state, str(action.get("doc") or ""))
    if op == "via":
        return size_via(state, float(action.get("amps") or 1))
    if op == "diff":
        return diff_pair(state, str(action.get("name") or "usb"))
    if op == "cad_mass":
        mass = cad_mass(cad)
        if not mass:
            return "No solid yet. Sketch and extrude first."
        return f"6061-T6 plate {mass['cm3']:.2f} cm³, {mass['grams']:.1f} g."
    if op == "cad_status":
        if cad["length"] is None:
            return "CAD solid is empty."
        thick = "not extruded" if cad["thickness"] is None else f"{float(cad['thickness']):g} mm thick"
        return (
            f"Plate {float(cad['length']):g} × {float(cad['width']):g} mm, {thick}, "
            f"hole Ø{float(cad['hole']):g}, fillet R{float(cad['fillet']):g}."
        )
    if op == "reset":
        fresh = empty_state()
        state["pcb"] = fresh["pcb"]
        state["cad"] = fresh["cad"]
        state["work"] = fresh["work"]
        return "Session cleared."
    if op == "help":
        return HELP
    return "Say that again as a PCB place/net/flow or a CAD sketch/extrude/hole."


HELP = (
    "Schematic, layout, footprint, simulation, 3D, design check, fabrication, assembly. "
    "Chip checks: pin, decoupling, power, IO, clock, reset, boot, thermal, SI, PI. "
    "CLI: sch add --ref U1 --pkg ESP32 · sch wire --name VBUS --a J1 --b U1 · "
    "fp assign --ref U1 · sim dc · view 3d · fab gerber · asm bom · chip decap."
)


def _num(text: str | None) -> float | None:
    if text is None:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _flags(parts: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    i = 0
    pos: list[str] = []
    while i < len(parts):
        tok = parts[i]
        if tok.startswith("--") and i + 1 < len(parts):
            out[tok[2:]] = parts[i + 1]
            i += 2
            continue
        pos.append(tok)
        i += 1
    out["$"] = " ".join(pos)
    return out


def parse_cli(line: str) -> dict | None:
    raw = line.strip()
    if not raw:
        return None
    bits = raw.split()
    if not bits:
        return None
    head = bits[0].lower()
    if head in {"help", "?"}:
        return {"op": "help"}
    if head in {"reset", "clear"}:
        return {"op": "reset"}
    if head in {"status"}:
        return {"op": "status"}
    if head in {"sch", "schematic"} and len(bits) >= 2:
        cmd = bits[1].lower()
        flags = _flags(bits[2:])
        pos = [p for p in flags.pop("$", "").split() if p]

        def pick(name: str, index: int) -> str | None:
            if name in flags:
                return flags[name]
            if index < len(pos):
                return pos[index]
            return None

        if cmd == "add":
            ref, pkg = pick("ref", 0), pick("pkg", 1)
            if not (ref and pkg):
                return {"op": "error", "text": "sch add needs --ref --pkg"}
            return {"op": "sch_add", "ref": ref, "pkg": pkg}
        if cmd in {"wire", "net"}:
            name, a, b = pick("name", 0), pick("a", 1), pick("b", 2)
            if not (name and a and b):
                return {"op": "error", "text": "sch wire needs --name --a --b"}
            return {"op": "sch_wire", "name": name, "a": a, "b": b}
        if cmd == "erc":
            return {"op": "sch_erc"}
    if head in {"fp", "footprint"} and len(bits) >= 2 and bits[1].lower() in {"assign", "set"}:
        flags = _flags(bits[2:])
        pos = [p for p in flags.pop("$", "").split() if p]
        ref = flags.get("ref") or (pos[0] if pos else None)
        if not ref:
            return {"op": "error", "text": "fp assign needs --ref"}
        return {"op": "fp_assign", "ref": ref}
    if head == "sim" and len(bits) >= 2 and bits[1].lower() in {"dc", "tran", "transient"}:
        return {"op": "sim_tran" if bits[1].lower().startswith("tran") else "sim_dc"}
    if head == "view" and len(bits) >= 2 and bits[1].lower() in {"3d", "board"}:
        return {"op": "view_3d"}
    if head == "fab" and len(bits) >= 2 and bits[1].lower() in {"gerber", "pack"}:
        return {"op": "fab_gerber"}
    if head == "fab" and len(bits) >= 2 and bits[1].lower() in {"stack", "stackup"}:
        return {"op": "fab_stack"}
    if head == "asm" and len(bits) >= 2 and bits[1].lower() == "bom":
        return {"op": "asm_bom"}
    if head == "asm" and len(bits) >= 2 and bits[1].lower() in {"pos", "place", "centroid"}:
        return {"op": "asm_pos"}
    if head == "place" and len(bits) >= 2 and bits[1].lower() in {"sheet", "symbols", "schematic"}:
        return {"op": "place_sheet"}
    if head == "outline" and len(bits) >= 3:
        length, width = _num(bits[1]), _num(bits[2] if bits[2] != "by" else bits[3] if len(bits) > 3 else None)
        if length is None or width is None:
            return {"op": "error", "text": "outline needs a length and a width"}
        return {"op": "set_outline", "length": length, "width": width}
    if head in {"cover", "covet", "handle"}:
        if len(bits) >= 2 and bits[1].lower() not in {"all", "industries", "industry", "every"}:
            kind = {"automatic": "automotive", "auto": "automotive", "battery": "bms"}.get(bits[1].lower(), bits[1].lower())
            if kind in INDUSTRY:
                return {"op": "handle_industry", "kind": kind}
            if kind in BOARD:
                return {"op": "handle_board", "kind": kind}
        return {"op": "handle_all"}
    if head == "chip" and len(bits) >= 2:
        kind = bits[1].lower()
        alias = {"decoupling": "decap", "pins": "pin", "pinout": "pin"}
        kind = alias.get(kind, kind)
        if kind in {"pin", "decap", "power", "io", "clock", "reset", "boot", "thermal", "si", "pi"}:
            return {"op": "chip_check", "kind": kind}
        return {"op": "error", "text": "chip needs a discipline: pin, decap, power, io, clock, reset, boot, thermal, si, pi"}
    if head in {"industry", "automatic", "automotive"}:
        if len(bits) >= 2 and bits[1].lower() == "check":
            return {"op": "industry_check"}
        if len(bits) >= 2:
            kind = {"automatic": "automotive", "auto": "automotive", "car": "automotive"}.get(bits[1].lower(), bits[1].lower())
            if kind in INDUSTRY:
                return {"op": "set_industry", "kind": kind}
        if head == "industry":
            return {"op": "error", "text": "That field is not in the profile list. Ask to list PCB fields."}
        return None
    if head == "board" and len(bits) >= 2:
        kind = bits[1].lower()
        alias = {"motherboard": "motherboard", "tiny": "tiny", "power": "power", "bms": "bms", "battery": "bms", "motor": "motor", "cpu": "cpu", "gpu": "gpu", "modem": "modem"}
        kind = alias.get(kind, kind)
        if kind not in BOARD:
            return {"op": "error", "text": "board needs tiny, power, bms, motor, cpu, gpu, modem, or motherboard"}
        return {"op": "set_board", "kind": kind}
    if head not in {"pcb", "cad"} or len(bits) < 2:
        return None
    cmd = bits[1].lower()
    flags = _flags(bits[2:])
    pos = [p for p in flags.pop("$", "").split() if p]

    def pick(name: str, index: int) -> str | None:
        if name in flags:
            return flags[name]
        if index < len(pos):
            return pos[index]
        return None

    if head == "pcb" and cmd == "add":
        ref, pkg, x, y = pick("ref", 0), pick("pkg", 1), _num(pick("x", 2)), _num(pick("y", 3))
        if not (ref and pkg and x is not None and y is not None):
            return {"op": "error", "text": "pcb add needs --ref --pkg --x --y"}
        return {"op": "pcb_add", "ref": ref, "pkg": pkg, "x": x, "y": y}
    if head == "pcb" and cmd == "net":
        name, a, b = pick("name", 0), pick("a", 1), pick("b", 2)
        if not (name and a and b):
            return {"op": "error", "text": "pcb net needs --name --a --b"}
        return {"op": "pcb_net", "name": name, "a": a, "b": b}
    if head == "pcb" and cmd in {"flow", "release", "gerber"}:
        return {"op": "pcb_flow"}
    if head == "pcb" and cmd == "drc":
        return {"op": "pcb_drc"}
    if head == "pcb" and cmd == "status":
        return {"op": "pcb_status"}
    if head == "pcb" and cmd == "reset":
        fresh = empty_state()
        return {"op": "pcb_reset"}
    if head == "cad" and cmd in {"sketch", "rect", "rectangle"}:
        length, width = _num(pick("length", 0) or pick("l", 0)), _num(pick("width", 1) or pick("w", 1))
        if length is None or width is None:
            return {"op": "error", "text": "cad sketch needs --length --width"}
        return {"op": "cad_sketch", "length": length, "width": width}
    if head == "cad" and cmd == "extrude":
        thick = _num(pick("thickness", 0) or pick("t", 0))
        if thick is None:
            return {"op": "error", "text": "cad extrude needs --thickness"}
        return {"op": "cad_extrude", "thickness": thick}
    if head == "cad" and cmd == "hole":
        dia = _num(pick("diameter", 0) or pick("d", 0))
        if dia is None:
            return {"op": "error", "text": "cad hole needs --diameter"}
        return {"op": "cad_hole", "diameter": dia}
    if head == "cad" and cmd == "fillet":
        radius = _num(pick("radius", 0) or pick("r", 0))
        if radius is None:
            return {"op": "error", "text": "cad fillet needs --radius"}
        return {"op": "cad_fillet", "radius": radius}
    if head == "cad" and cmd == "mass":
        return {"op": "cad_mass"}
    if head == "cad" and cmd == "status":
        return {"op": "cad_status"}
    if head == "cad" and cmd == "reset":
        return {"op": "cad_reset"}
    return None


def dispatch(state: dict, action: dict) -> str:
    if action.get("op") == "error":
        return str(action.get("text"))
    if action.get("op") == "status":
        return apply(state, {"op": "pcb_status"}) + " " + apply(state, {"op": "cad_status"})
    if action.get("op") == "pcb_reset":
        state["pcb"] = empty_state()["pcb"]
        return "PCB cleared."
    if action.get("op") == "cad_reset":
        state["cad"] = empty_state()["cad"]
        return "CAD cleared."
    return apply(state, action)


def snapshot(state: dict) -> dict:
    items = drc(state)
    mass = cad_mass(state["cad"])
    return {
        "pcb": state["pcb"],
        "cad": state["cad"],
        "drc": items,
        "mass": None
        if not mass
        else {"cm3": round(mass["cm3"], 3), "grams": round(mass["grams"], 2)},
        "work": state.get("work") or empty_work(),
        "history": state["history"][-12:],
    }


_WORD = re.compile(r"[a-z0-9]+", re.I)


def tokenize(text: str) -> list[str]:
    lowered = text.lower().replace("usb-c", "usbc")
    lowered = re.sub(r"\busb c\b", "usbc", lowered)
    return _WORD.findall(lowered)


def remember(state: dict, line: str, reply: str, commands: list[str]) -> None:
    state["history"].append({"line": line, "reply": reply, "commands": commands})
    state["history"] = state["history"][-40:]
