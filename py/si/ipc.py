"""IPC documents that govern this PCB product. Titles only. Not the licensed text."""

from __future__ import annotations

# needs: outline, parts, footprints, nets, fab, assembly, signal, datasheet
CATALOG = [
    {"id": "IPC-2221", "group": "Design", "title": "Generic standard on printed board design", "needs": ["outline", "parts"]},
    {"id": "IPC-2222", "group": "Design", "title": "Sectional design standard for rigid organic boards", "needs": ["outline", "parts"]},
    {"id": "IPC-2223", "group": "Design", "title": "Sectional design standard for flexible boards", "needs": ["outline"]},
    {"id": "IPC-2226", "group": "Design", "title": "Sectional design standard for HDI boards", "needs": ["outline", "parts"]},
    {"id": "IPC-2141", "group": "Design", "title": "Controlled impedance circuit boards", "needs": ["signal"]},
    {"id": "IPC-2152", "group": "Design", "title": "Current-carrying capacity in printed board design", "needs": ["signal"]},
    {"id": "IPC-2251", "group": "Design", "title": "High-speed packaging design guide", "needs": ["signal"]},
    {"id": "IPC-2252", "group": "Design", "title": "Design guide for RF and microwave boards", "needs": ["signal"]},
    {"id": "IPC-7351", "group": "Design", "title": "Generic requirements for surface-mount land patterns", "needs": ["footprints"]},
    {"id": "IPC-7093", "group": "Design", "title": "Design and assembly for bottom-termination components", "needs": ["footprints"]},
    {"id": "IPC-7095", "group": "Design", "title": "Design and assembly process for BGAs", "needs": ["footprints"]},
    {"id": "IPC-4761", "group": "Design", "title": "Design guide for protection of printed board vias", "needs": ["signal"]},
    {"id": "IPC-2615", "group": "Design", "title": "Printed board dimensions and tolerances", "needs": ["outline"]},
    {"id": "IPC-6011", "group": "Fabrication", "title": "Generic performance specification for printed boards", "needs": ["fab"]},
    {"id": "IPC-6012", "group": "Fabrication", "title": "Qualification and performance for rigid printed boards", "needs": ["fab"]},
    {"id": "IPC-6013", "group": "Fabrication", "title": "Qualification and performance for flexible boards", "needs": ["fab"]},
    {"id": "IPC-6018", "group": "Fabrication", "title": "High-frequency (microwave) printed boards", "needs": ["fab", "signal"]},
    {"id": "IPC-A-600", "group": "Fabrication", "title": "Acceptability of printed boards", "needs": ["fab"]},
    {"id": "IPC-9252", "group": "Fabrication", "title": "Electrical test requirements for unpopulated boards", "needs": ["nets", "fab"]},
    {"id": "IPC-TM-650", "group": "Fabrication", "title": "Test methods manual", "needs": ["fab"]},
    {"id": "IPC-SM-840", "group": "Fabrication", "title": "Qualification of permanent solder mask", "needs": ["fab"]},
    {"id": "IPC-4552", "group": "Material", "title": "Electroless nickel immersion gold (ENIG)", "needs": ["fab"]},
    {"id": "IPC-4553", "group": "Material", "title": "Immersion silver", "needs": ["fab"]},
    {"id": "IPC-4554", "group": "Material", "title": "Immersion tin", "needs": ["fab"]},
    {"id": "IPC-4556", "group": "Material", "title": "Electroless nickel electroless palladium immersion gold (ENEPIG)", "needs": ["fab"]},
    {"id": "IPC-4562", "group": "Material", "title": "Metal foil for printed boards", "needs": ["fab"]},
    {"id": "IPC-4101", "group": "Material", "title": "Base materials for rigid and multilayer boards", "needs": ["fab"]},
    {"id": "IPC-4202", "group": "Material", "title": "Flexible base dielectrics", "needs": ["fab"]},
    {"id": "IPC-4203", "group": "Material", "title": "Adhesive coated dielectric films", "needs": ["fab"]},
    {"id": "IPC-4781", "group": "Material", "title": "Qualification of permanent legend", "needs": ["fab"]},
    {"id": "IPC-1601", "group": "Material", "title": "Handling and storage of printed boards", "needs": ["fab"]},
    {"id": "J-STD-001", "group": "Assembly", "title": "Requirements for soldered electrical and electronic assemblies", "needs": ["assembly", "footprints"]},
    {"id": "IPC-A-610", "group": "Assembly", "title": "Acceptability of electronic assemblies", "needs": ["assembly", "footprints"]},
    {"id": "J-STD-002", "group": "Assembly", "title": "Solderability tests for component leads and terminations", "needs": ["datasheet"]},
    {"id": "J-STD-006", "group": "Assembly", "title": "Requirements for electronic grade solder alloys", "needs": ["assembly"]},
    {"id": "J-STD-020", "group": "Assembly", "title": "Moisture sensitivity classification for non-hermetic devices", "needs": ["datasheet"]},
    {"id": "J-STD-033", "group": "Assembly", "title": "Handling, packing, and use of moisture-sensitive devices", "needs": ["datasheet"]},
    {"id": "J-STD-609", "group": "Assembly", "title": "Marking and labeling to identify lead content", "needs": ["assembly"]},
    {"id": "IPC-7711", "group": "Assembly", "title": "Rework of electronic assemblies", "needs": ["assembly"]},
    {"id": "IPC-7721", "group": "Assembly", "title": "Repair and modification of printed boards and assemblies", "needs": ["assembly"]},
    {"id": "IPC-7525", "group": "Assembly", "title": "Stencil design guidelines", "needs": ["footprints"]},
    {"id": "IPC-9701", "group": "Assembly", "title": "Performance test methods for surface-mount attachments", "needs": ["assembly"]},
    {"id": "IPC-1752", "group": "Assembly", "title": "Materials declaration", "needs": ["datasheet"]},
    {"id": "IPC-2581", "group": "Data", "title": "Generic requirements for printed board assembly products manufacturing description data", "needs": ["data"]},
    {"id": "IPC-D-356", "group": "Data", "title": "Bare-board electrical test data", "needs": ["data"]},
    {"id": "IPC/WHMA-A-620", "group": "Cable", "title": "Requirements and acceptance for cable and wire harness assemblies", "needs": ["cable"]},
]

BY_ID = {row["id"]: row for row in CATALOG}
CLASSES = {
    "1": "Class 1, general electronic products",
    "2": "Class 2, dedicated service",
    "3": "Class 3, high reliability",
}


def lookup(token: str) -> dict | None:
    key = token.upper().replace("IPC", "").replace("-", "").strip()
    for row in CATALOG:
        compact = row["id"].upper().replace("IPC-", "").replace("J-STD-", "").replace("IPC/", "").replace("-", "")
        if key and (key == compact or key in row["id"].replace("-", "")):
            return row
    return None
