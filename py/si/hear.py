"""Turn the ways a person says a PCB edit into a tool call.

The transformer vocabulary does not contain these words. This file does.
"""

from __future__ import annotations

import re

from py.si.engine import tokenize

_REF = re.compile(r"\b(tp|sw|[rcdlqjuy])(\d+)\b", re.I)
_NUM = re.compile(r"\b\d+(?:\.\d+)?\b")
_PKG = {
    "resistor": "res",
    "capacitor": "cap",
    "inductor": "ind",
    "coil": "ind",
    "diode": "diode",
    "led": "led",
    "transistor": "bjt",
    "bjt": "bjt",
    "npn": "bjt",
    "fet": "fet",
    "mosfet": "fet",
    "mcu": "mcu",
    "connector": "conn",
    "conn": "conn",
    "crystal": "crystal",
    "oscillator": "crystal",
    "dip": "dip",
    "sip": "sip",
    "sop": "sop",
    "soic": "soic",
    "ssop": "ssop",
    "tsop": "tsop",
    "qfp": "qfp",
    "tqfp": "tqfp",
    "qfn": "qfn",
    "dfn": "dfn",
    "bga": "bga",
    "lga": "lga",
    "wlcsp": "wlcsp",
    "pga": "pga",
    "sot": "sot",
}
_PREFIX = {
    "r": "res",
    "c": "cap",
    "l": "ind",
    "d": "diode",
    "q": "bjt",
    "u": "mcu",
    "j": "conn",
    "y": "crystal",
    "tp": "tp",
    "sw": "sw",
}
_NET = (
    "vbus",
    "gnd",
    "ground",
    "vcc",
    "vdd",
    "vss",
    "tx",
    "rx",
    "clk",
    "clock",
    "sda",
    "scl",
    "mosi",
    "miso",
    "sck",
    "cs",
    "can",
    "i2c",
    "usb",
    "sw",
    "3v3",
    "5v",
)
_SKIP = re.compile(
    r"\b(what|explain|define|meaning|datasheet|autoroute|trace|creepage|clearance|impedance|ohm|filter|thermal|kicad|allegro|altium|ipc|layer|layers|stackup|stack|decoupling|caps|integrity|reset|boot|pinout|erc|dfm|bom|gerber|pour|flow|status|simulate|transient|operating)\b",
    re.I,
)


def _refs(text: str) -> list[str]:
    return [f"{prefix}{number}" for prefix, number in _REF.findall(text.lower())]


def _nums(text: str) -> list[float]:
    scale = 0.0254 if re.search(r"\bmil\b", text, re.I) and not re.search(r"\bmm\b", text, re.I) else 1.0
    return [float(item) * scale for item in _NUM.findall(text)]


def _pkg(words: list[str], ref: str) -> str:
    for word in words:
        if word in _PKG:
            return _PKG[word]
    prefix = "tp" if ref.startswith("tp") else "sw" if ref.startswith("sw") else ref[0]
    return _PREFIX.get(prefix, "conn")


def _net(words: list[str]) -> str | None:
    for word in words:
        if word in _NET and not (word == "sw" and any(item.startswith("sw") for item in words)):
            return "gnd" if word == "ground" else "clk" if word == "clock" else word
    return None


def _note(text: str) -> dict:
    return {"op": "note", "text": text}


def hear(text: str) -> dict | None:
    if _SKIP.search(text):
        return None
    low = text.lower()
    words = tokenize(text)
    refs = _refs(low)
    nums = _nums(low)
    bag = set(words)
    if {"drop", "replacement"} <= bag or "replacement" in bag:
        return None
    if "delete" in bag or "remove" in bag or "erase" in bag:
        if not refs:
            return _note("Name the reference to remove, for example delete r1.")
        return {"op": "pcb_delete", "ref": refs[0]}
    if "move" in bag:
        if not refs or len(nums) < 2:
            return _note("Say move r1 to 10 12. Add mil if the numbers are not millimetres.")
        return {"op": "pcb_move", "ref": refs[0], "x": nums[0], "y": nums[1]}
    if "rotate" in bag:
        if not refs:
            return _note("Say rotate u1 90. The drawing does not turn the pads.")
        angle = nums[0] if nums else 90
        return {"op": "pcb_rotate", "ref": refs[0], "angle": angle}
    if "copy" in bag:
        if len(refs) < 2:
            return _note("Say copy r1 to r2. A coordinate is optional.")
        action = {"op": "pcb_copy", "ref": refs[0], "to": refs[1]}
        if len(nums) >= 2:
            action["x"] = nums[0]
            action["y"] = nums[1]
        return action
    if "swap" in bag:
        if len(refs) < 2:
            return _note("Say swap r1 and c1. Only the coordinates are exchanged.")
        return {"op": "pcb_swap", "a": refs[0], "b": refs[1]}
    if "flip" in bag or "mirror" in bag:
        if not refs:
            return _note("Say flip u1. The side is stored. The drawing stays a top view.")
        return {"op": "pcb_flip", "ref": refs[0]}
    if "find" in bag and refs:
        return {"op": "pcb_find", "ref": refs[0]}
    if bag & {"place", "put", "mount", "insert", "add"} and "sheet" not in bag and "symbols" not in bag:
        if refs and len(nums) >= 2:
            return {"op": "pcb_add", "ref": refs[0], "pkg": _pkg(words, refs[0]), "x": nums[0], "y": nums[1]}
        if refs:
            return _note(f"Give x and y for {refs[0]}, for example place {refs[0]} at 10 12.")
    if bag & {"connect", "tie", "join"} or ("net" in bag and "schematic" not in bag):
        if "schematic" in bag or ("from" in bag and "to" in bag and "connect" not in bag):
            return None
        net = _net(words)
        if net and len(refs) >= 2:
            return {"op": "pcb_net", "name": net, "a": refs[0], "b": refs[1]}
        if len(refs) >= 2 and not net:
            return _note("Name the net, for example connect vcc to r1 and c1.")
    if "check" in bag and "industry" not in bag:
        if "schematic" in bag or "electrical" in bag:
            return {"op": "sch_erc"}
        return {"op": "pcb_drc"}
    if bag & {"undo", "redo"}:
        return _note("There is no undo stack. The last board edit stays until you move or delete it.")
    if bag & {"save", "load"}:
        return _note("The board is already stored in the session. There is no separate file to load.")
    if bag & {"lock", "unlock", "group", "align"}:
        return _note("Lock, group, and align are not on this board. Place or move a reference instead.")
    if bag & {"select", "highlight", "hide", "zoom", "pan"}:
        return _note("The view has no selection or camera. Ask for status to list the parts.")
    if bag & {"fanout", "teardrop", "stitch", "tune"}:
        return _note("Fanout, teardrops, via stitching, and length tuning are not drawn. Routing is one orthogonal layer.")
    if "import" in bag:
        return _note("Import a datasheet by pasting it. A CAD or EDA file is not read.")
    if "edit" in bag:
        return _note("Edit by placing, moving, deleting, or connecting a reference.")
    if bag & {"measure", "calculate"}:
        return _note("Ask for a trace width, a via current, creepage at a voltage, or a 50, 90, or 100 ohm pair.")
    return None
