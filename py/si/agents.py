"""Specialist agents the CLI can run one at a time, or as a crew."""

from __future__ import annotations

import re

# Trained stage sentences. The model already maps these to one command.
_STAGES = {
    "schematic": "run the schematic stage",
    "layout": "show the layout stage",
    "check": "run the design check stage",
    "simulation": "run the simulation stage",
    "transient": "run the transient stage",
    "viewer": "run the 3d stage",
    "stackup": "run the stackup stage",
    "fabrication": "run the fabrication stage",
    "bom": "run the bom stage",
    "assembly": "run the assembly stage",
}

AGENTS = (
    {"id": "schematic", "role": "Schematic", "does": "ERC and the schematic stage", "words": ("schematic", "erc", "symbol", "wire")},
    {"id": "layout", "role": "Layout", "does": "Placement and what is on the board", "words": ("layout", "place", "route", "board")},
    {"id": "footprint", "role": "Footprint", "does": "Which placed parts have a land", "words": ("footprint", "land", "package")},
    {"id": "check", "role": "Design check", "does": "DRC", "words": ("drc", "check", "rule")},
    {"id": "simulation", "role": "Simulation", "does": "DC operating point, and transient when asked", "words": ("sim", "simulation", "transient", "spice")},
    {"id": "viewer", "role": "3D", "does": "Board height and models", "words": ("3d", "viewer", "height")},
    {"id": "fabrication", "role": "Fabrication", "does": "Stackup, and Gerber only when you ask to release", "words": ("fab", "fabrication", "gerber", "stack", "stackup")},
    {"id": "assembly", "role": "Assembly", "does": "BOM, and the centroid when you ask for assembly", "words": ("bom", "assembly", "centroid", "pick")},
    {"id": "power", "role": "Power", "does": "The power catalog and a booster design", "words": ("power", "boost", "bms", "converter", "sonar")},
)

_BROAD = ("entire", "whole", "finish", "flow", "everything", "all", "complete", "crew")
_CREW: dict = {"left": [], "reports": [], "text": "", "mode": None, "approved": False}


def roster() -> list[dict]:
    return [{"id": row["id"], "role": row["role"], "does": row["does"]} for row in AGENTS]


def _by_id(agent_id: str) -> dict | None:
    for row in AGENTS:
        if row["id"] == agent_id:
            return row
    return None


def choose(text: str) -> list[dict]:
    low = text.lower()
    named = [row for row in AGENTS if any(re.search(rf"\b{re.escape(word)}\b", low) for word in row["words"])]
    broad = any(re.search(rf"\b{word}\b", low) for word in _BROAD) or not named
    if broad and not named:
        return [row for row in AGENTS if row["id"] != "power"]
    if broad and named:
        # A wide request that also names a domain still runs the board crew, plus power when it was named.
        picked = [row for row in AGENTS if row["id"] != "power" or row in named]
        return picked
    return named


def _briefs(agent_id: str, text: str) -> list[str]:
    low = text.lower()
    if agent_id == "schematic":
        return [_STAGES["schematic"]]
    if agent_id == "layout":
        return [_STAGES["layout"]]
    if agent_id == "check":
        return [_STAGES["check"]]
    if agent_id == "simulation":
        briefs = [_STAGES["simulation"]]
        if "transient" in low:
            briefs.append(_STAGES["transient"])
        return briefs
    if agent_id == "viewer":
        return [_STAGES["viewer"]]
    if agent_id == "fabrication":
        briefs = [_STAGES["stackup"]]
        if re.search(r"\b(gerber|gerbers|release|pack)\b", low):
            briefs.append(_STAGES["fabrication"])
        return briefs
    if agent_id == "assembly":
        briefs = [_STAGES["bom"]]
        if re.search(r"\b(assembly|centroid|pick)\b", low):
            briefs.append(_STAGES["assembly"])
        return briefs
    if agent_id == "power":
        return [text.strip()]
    return []


def _footprint_line() -> str:
    from py.si.engine import load_state

    state = load_state()
    parts = state["pcb"]["parts"]
    lands = {str(row.get("ref")) for row in (state["work"].get("footprints") or [])}
    if not parts:
        return "Nothing is placed, so there is no footprint to check."
    missing = [str(part["ref"]) for part in parts if str(part["ref"]) not in lands]
    if missing:
        return "Missing footprints: " + ", ".join(missing) + "."
    return f"Footprints assigned for {len(parts)} placed parts."


def _run_one(agent: dict, text: str, approved: bool, mode: str | None) -> dict:
    from py.si.mcp_client import designer_turn

    if agent["id"] == "footprint" and "assign" not in text.lower():
        line = _footprint_line()
        return {"id": agent["id"], "role": agent["role"], "reply": line, "commands": ["footprint.read"], "needsApproval": False, "turn": None}
    replies = []
    commands: list[str] = []
    for brief in _briefs(agent["id"], text):
        # Status stages are reads. A release, an assign, or a power design keeps the caller's approval.
        read = brief in _STAGES.values() and brief not in {_STAGES["fabrication"], _STAGES["assembly"]}
        turn = designer_turn(brief, approved=approved or read, mode=mode)
        if turn.get("needsApproval"):
            return {"id": agent["id"], "role": agent["role"], "reply": str(turn.get("reply") or ""), "commands": list(turn.get("commands") or []), "needsApproval": True, "turn": turn}
        if turn.get("question"):
            return {"id": agent["id"], "role": agent["role"], "reply": str(turn.get("reply") or ""), "commands": list(turn.get("commands") or []), "needsApproval": False, "turn": turn, "question": turn["question"]}
        replies.append(str(turn.get("reply") or "").strip())
        commands.extend(str(cmd) for cmd in (turn.get("commands") or []))
    return {"id": agent["id"], "role": agent["role"], "reply": " ".join(part for part in replies if part), "commands": commands, "needsApproval": False, "turn": None}


def _transcript(reports: list[dict], waiting: str = "") -> str:
    names = ", ".join(row["role"] for row in reports)
    if waiting:
        names = (names + ", " if names else "") + waiting
    lines = [f"Lead: {names}."]
    for row in reports:
        lines.append("")
        lines.append(row["role"])
        lines.append(row["reply"])
    return "\n".join(lines)


def run_agent(agent_id: str, text: str, approved: bool = False, mode: str | None = None) -> dict:
    from py.si.engine import load_state, snapshot
    from py.si.mcp_client import pack

    agent = _by_id(agent_id)
    if agent is None:
        known = ", ".join(row["id"] for row in AGENTS)
        return pack(f"Unknown agent. Use one of: {known}.", [], "crew", "agent", snapshot(load_state()))
    report = _run_one(agent, text or agent["does"], approved, mode)
    if report.get("turn") and (report["needsApproval"] or report["turn"].get("question")):
        turn = report["turn"]
        turn["reply"] = f"{agent['role']}\n{report['reply']}"
        turn["agent"] = agent["id"]
        return turn
    body = pack(f"{agent['role']}\n{report['reply']}", report["commands"], "crew", "agent", snapshot(load_state()))
    body["agent"] = agent["id"]
    body["agents"] = [{"id": report["id"], "role": report["role"], "reply": report["reply"], "commands": report["commands"]}]
    return body


def run_crew(text: str, approved: bool = False, mode: str | None = None, resume: bool = False) -> dict:
    from py.si.engine import load_state, snapshot
    from py.si.mcp_client import pack

    if resume:
        if not _CREW["left"]:
            return pack("No crew is waiting.", [], "crew", "crew", snapshot(load_state()))
        text = str(_CREW["text"] or text)
        mode = _CREW["mode"]
        approved = True
        left = list(_CREW["left"])
        reports = list(_CREW["reports"])
    else:
        if not text.strip():
            return pack("Say what the crew should do.", [], "crew", "crew", snapshot(load_state()))
        left = [row["id"] for row in choose(text)]
        reports = []
        _CREW["text"] = text.strip()
        _CREW["mode"] = mode
    while left:
        agent = _by_id(left[0])
        if agent is None:
            left.pop(0)
            continue
        report = _run_one(agent, text, approved, mode)
        if report["needsApproval"] and report.get("turn"):
            _CREW["left"] = left
            _CREW["reports"] = reports
            turn = report["turn"]
            turn["reply"] = _transcript(reports, agent["role"]) + f"\n\n{agent['role']}\n{report['reply']}"
            turn["agent"] = agent["id"]
            turn["crewRest"] = True
            turn["agents"] = reports
            return turn
        if report.get("question") and report.get("turn"):
            _CREW["left"] = left[1:]
            _CREW["reports"] = reports + [{"id": report["id"], "role": report["role"], "reply": report["reply"], "commands": report["commands"]}]
            turn = report["turn"]
            turn["reply"] = _transcript(reports, agent["role"]) + f"\n\n{agent['role']}\n{report['reply']}"
            turn["agent"] = agent["id"]
            turn["crewRest"] = bool(_CREW["left"])
            return turn
        reports.append({"id": report["id"], "role": report["role"], "reply": report["reply"], "commands": report["commands"]})
        left.pop(0)
    _CREW["left"] = []
    _CREW["reports"] = []
    commands = [cmd for row in reports for cmd in row["commands"]]
    body = pack(_transcript(reports), commands, "crew", "crew", snapshot(load_state()))
    body["agents"] = reports
    return body
