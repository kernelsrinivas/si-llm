"""Calculators and EDA files. Formulas are named. Nothing here is a licensed IPC table or a live EDA session."""

from __future__ import annotations

import csv
import math
import os
from pathlib import Path

OUT = Path(os.environ.get("SI_MODEL") or Path(__file__).resolve().parents[2] / "model") / "out"

# IPC-2221B Table 6-1 bands, upper voltage then B1, B2, B4 in mm.
# Open-calculator figures. Not a licensed copy. Not creepage. B3 is not stored.
_SPACE = (
    (15, 0.05, 0.10, 0.05),
    (30, 0.05, 0.10, 0.05),
    (50, 0.10, 0.60, 0.13),
    (100, 0.10, 0.60, 0.13),
    (150, 0.20, 0.60, 0.40),
    (170, 0.20, 1.25, 0.40),
    (250, 0.20, 1.25, 0.40),
    (300, 0.20, 1.25, 0.40),
    (500, 0.25, 2.50, 0.80),
)

# Same land pattern is not an electrical drop-in.
_ALT = {
    "ESP32": "ESP32-S3 is the same module family, not a drop-in. Check the pinout.",
    "MCU": "Another QFN-32 MCU can share the land. It is not a drop-in until the pinout matches.",
    "LDO": "Another SOT-23-5 LDO can share the land. Pin 1 is not the same on every part.",
    "BUCK": "Another QFN-16 buck can share the land. The feedback pin is not standard.",
    "CAP": "A 0402 cap of the same value, voltage, and dielectric can replace it.",
    "RES": "A 0402 resistor of the same value and power can replace it.",
    "USB-C": "Another USB-C-16 receptacle can share the land. Check the shell pins.",
    "CONN": "Another 4-pin header can share the land.",
}


def trace_ipc2221(amps: float, rise: float = 10.0, oz: float = 1.0, internal: bool = False, length_mm: float = 50.0) -> dict:
    """IPC-2221 curve fit I = k * dT^0.44 * A^0.725. Not the IPC-2152 charts."""
    k = 0.024 if internal else 0.048
    thick_mil = 1.378 * oz
    area = (amps / (k * rise**0.44)) ** (1 / 0.725)
    width_mm = area / thick_mil * 0.0254
    thick_mm = thick_mil * 0.0254
    temp = 25.0 + rise
    rho = 0.017241 * (1 + 0.00393 * (temp - 20.0))
    resistance = rho * (length_mm / 1000.0) / (width_mm * thick_mm)
    return {
        "width_mm": width_mm,
        "ohms": resistance,
        "loss_w": amps * amps * resistance,
        "drop_v": amps * resistance,
        "internal": internal,
        "oz": oz,
        "rise": rise,
        "length_mm": length_mm,
    }


def spacing_for(volts: float) -> dict | None:
    if volts < 0:
        return None
    if volts > 500:
        extra = volts - 500.0
        return {
            "band": "above 500",
            "internal": 0.25 + extra * 0.0025,
            "external": 2.5 + extra * 0.005,
            "coated": 0.80 + extra * 0.00305,
        }
    low = 0
    for limit, internal, external, coated in _SPACE:
        if volts <= limit:
            return {
                "band": f"{low}–{limit}",
                "internal": internal,
                "external": external,
                "coated": coated,
            }
        low = limit + 1
    return None


def spacing_text(volts: float) -> str:
    row = spacing_for(volts)
    if row is None:
        return "Voltage has to be zero or positive."
    return (
        f"IPC-2221B Table 6-1 at {volts:g} V peak, band {row['band']} V: "
        f"B1 internal {row['internal']:.2f} mm, "
        f"B2 external uncoated {row['external']:.2f} mm, "
        f"B4 permanent coating {row['coated']:.2f} mm. "
        "Solder mask alone is not B4. Above 3050 m (B3) is not stored. "
        "Above 500 V the adders are 0.0025, 0.005, and 0.00305 mm per volt. "
        "This is not creepage and not a licensed copy."
    )


def rc_cutoff(ohms: float, farads: float) -> float:
    return 1.0 / (2 * math.pi * ohms * farads)


def lc_cutoff(henries: float, farads: float) -> float:
    return 1.0 / (2 * math.pi * math.sqrt(henries * farads))


def _placements(state: dict) -> list[dict]:
    assigned = {row["ref"]: row["fp"] for row in state["work"].get("footprints") or []}
    rows = []
    for part in state["pcb"]["parts"]:
        rows.append({"ref": part["ref"], "pkg": part["pkg"], "fp": assigned.get(part["ref"], ""), "x": part["x"], "y": part["y"]})
    return rows


def write_eda(state: dict, kind: str) -> tuple[Path, str]:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = _placements(state)
    if kind == "kicad":
        path = OUT / "place_kicad.py"
        body = [
            "# Starting KiCad pcbnew script. Not executed here.",
            "import pcbnew",
            "board = pcbnew.GetBoard()",
            "if board is None:",
            "    raise SystemExit('Open a board in KiCad first.')",
        ]
        for row in rows:
            body.append(f"fp = board.FindFootprintByReference({row['ref']!r})")
            body.append("if fp is not None:")
            body.append(f"    fp.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM({row['x']}), pcbnew.FromMM({row['y']})))")
        if not rows:
            body.append("# Board has no parts yet.")
        body.append("pcbnew.Refresh()")
        path.write_text("\n".join(body) + "\n")
        return path, f"KiCad script for {len(rows)} parts"
    if kind == "skill":
        path = OUT / "place.il"
        lines = ["; Starting Allegro placement list. Not executed in Allegro.", "; Ref x_mm y_mm"]
        lines += [f"; {row['ref']} {row['x']} {row['y']}" for row in rows] or ["; Board has no parts yet."]
        path.write_text("\n".join(lines) + "\n")
        return path, f"Allegro placement list for {len(rows)} parts"
    path = OUT / "place.pas"
    lines = [
        "// Starting Altium Delphi script. Not executed in Altium.",
        "procedure SIPlace;",
        "var",
        "  Board: IPCB_Board;",
        "  Comp: IPCB_Component;",
        "begin",
        "  Board := PCBServer.GetCurrentPCBBoard;",
        "  if Board = nil then Exit;",
    ]
    for row in rows:
        lines.append(f"  Comp := Board.GetPcbComponentByRefDes('{row['ref']}');")
        lines.append("  if Comp <> nil then")
        lines.append(f"    Comp.MoveToXY(MMsToCoord({row['x']}), MMsToCoord({row['y']}));")
    if not rows:
        lines.append("  // Board has no parts yet.")
    lines.append("end;")
    path.write_text("\n".join(lines) + "\n")
    return path, f"Altium script for {len(rows)} parts"


def write_bom(state: dict) -> tuple[Path, str]:
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "bom.csv"
    rows = _placements(state)
    missing = [row["ref"] for row in rows if not row["fp"]]
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["ref", "package", "footprint", "x_mm", "y_mm", "qty"])
        for row in rows:
            writer.writerow([row["ref"], row["pkg"], row["fp"], row["x"], row["y"], 1])
    note = f"{len(rows)} lines"
    if missing:
        note += ". Missing footprints: " + ", ".join(missing)
    elif rows:
        note += ". Every reference has a footprint."
    else:
        note += ". Board is empty."
    return path, note
