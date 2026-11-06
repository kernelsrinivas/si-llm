"""What this product actually runs. Not the ChatGPT roadmap percentages."""

from __future__ import annotations

# have = the command changes the board or returns a calculated result
# partial = a note, a named file list, or a small fixed catalog
# no = not implemented
ROWS = [
    ("Schematic", "have", "Symbol place, wires, net names, basic ERC"),
    ("Schematic", "partial", "Datasheet builds one circuit. No hierarchy, buses, net classes, or cross-probe"),
    ("Schematic", "no", "SPICE models. DC and transient here are operating-point notes"),
    ("Library", "partial", "Fixed packages, datasheet pin extract, local alternates"),
    ("Library", "no", "Parametric search, lifecycle, and live manufacturer stock"),
    ("Footprint", "have", "Calculated lands for chip, gull-wing, and QFN"),
    ("Footprint", "no", "BGA, paste, silkscreen geometry, courtyard drawing, STEP"),
    ("Layout", "have", "Outline, placement, layer count from the board class"),
    ("Layout", "partial", "Track width and via size are calculators. Pour is a note"),
    ("Layout", "partial", "Orthogonal one-layer autoroute on a 0.5 mm grid. No length match or diff pairs"),
    ("DRC", "have", "Duplicate refs, placement gap, industry clearance, report"),
    ("DRC", "no", "Copper shorts, track geometry, silk, mask, hole-to-copper, auto-fix"),
    ("3D", "partial", "Tallest body height and a separate enclosure solid"),
    ("3D", "no", "STEP, collision, enclosure fit, 3D export"),
    ("Signal", "have", "Microstrip and 90 ohm pair approximation"),
    ("Signal", "partial", "Return-path and decoupling notes"),
    ("Signal", "no", "Delay, crosstalk, PDN, reflection, DDR, PCIe"),
    ("Thermal", "have", "I²R loss on an IPC-2221 trace"),
    ("Thermal", "no", "Junction temperature, thermal vias, heatsink, hotspot simulation"),
    ("Manufacturing", "have", "BOM text, centroid text, stackup, DFM starting numbers"),
    ("Manufacturing", "partial", "Gerber is a layer-name list, not Gerber files"),
    ("Manufacturing", "no", "Excellon, drawings, panel, fiducials, DFA"),
    ("Assistant", "have", "Trained commands, MCP approval, datasheet, placement, DRC, fab pack"),
    ("Assistant", "no", "Routing proposals, DRC auto-fix, revision diff"),
]


def summarize() -> str:
    have = sum(1 for _m, status, _d in ROWS if status == "have")
    partial = sum(1 for _m, status, _d in ROWS if status == "partial")
    missing = sum(1 for _m, status, _d in ROWS if status == "no")
    return (
        f"Feature audit: {have} running, {partial} partial, {missing} not in this product. "
        "ChatGPT's 100/90/65 figures are roadmap targets, not this build. "
        "No STEP, no SPICE, no real Gerber geometry. The autorouter is one orthogonal layer."
    )
