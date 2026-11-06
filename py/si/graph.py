"""Package graph the harness reads. The model never sees these strings or numbers."""

from __future__ import annotations

import re

from py.si.datasheet import lands

_CHIP = {
    "0402": {"length": 1.0, "width": 0.5, "height": 0.35, "power_w": 0.063},
    "0603": {"length": 1.6, "width": 0.8, "height": 0.45, "power_w": 0.1},
    "0805": {"length": 2.0, "width": 1.25, "height": 0.5, "power_w": 0.125},
    "1206": {"length": 3.2, "width": 1.6, "height": 0.55, "power_w": 0.25},
}
_PKG = {
    "SOT-23": "FET and BJT footprint on this board. Lands wait for a datasheet.",
    "SOD-123": "Diode footprint on this board. Lands wait for a datasheet.",
    "QFN-32": "MCU footprint name. Lands wait for a datasheet.",
    "SOIC-16": "Isolator footprint name. Lands wait for a datasheet.",
}
_BOARD = {
    "single": {
        "title": "Single-sided",
        "layers": 1,
        "material": "FR-4",
        "text": "One copper layer on the substrate. No plated via to a second side. Used for simple, low-cost boards.",
    },
    "double": {
        "title": "Double-sided",
        "layers": 2,
        "material": "FR-4",
        "text": "Copper on both sides. A drilled via joins the two sides. The autorouter here still draws one layer.",
    },
    "multi": {
        "title": "Multi-layer",
        "layers": 4,
        "material": "FR-4",
        "text": "Three or more copper layers with insulation between them. This profile stores 4 until you set another count. Impedance still uses one dielectric, not a field solver.",
    },
    "rigid": {
        "title": "Rigid",
        "layers": None,
        "material": "FR-4",
        "text": "Solid FR-4 fiberglass. It does not bend. This is the usual board.",
    },
    "flex": {
        "title": "Flex",
        "layers": None,
        "material": "Polyimide",
        "text": "Polyimide, so the circuit can bend. Bend radius is not calculated, and a flex tail is not drawn.",
    },
    "rigidflex": {
        "title": "Rigid-flex",
        "layers": None,
        "material": "Rigid-flex",
        "text": "Rigid and flex layers in one piece, so a connector between two boards is not required. The flex region is not drawn.",
    },
    "metal": {
        "title": "Metal core",
        "layers": 1,
        "material": "Aluminum core",
        "text": "A metal base, usually aluminum, under a thin dielectric. It moves heat for LEDs and regulators. It is not a high-speed stack.",
    },
    "ptfe": {
        "title": "PTFE",
        "layers": None,
        "material": "PTFE",
        "text": "Low-loss material for RF, often a Rogers laminate. Impedance here is still one dielectric number, not a Rogers field solver.",
    },
    "ceramic": {
        "title": "Ceramic",
        "layers": None,
        "material": "Ceramic",
        "text": "Alumina-type board for heat and harsh temperature. This product does not model ceramic cracking or a thick-film process.",
    },
    "hdi": {
        "title": "HDI",
        "layers": None,
        "material": None,
        "text": "High-density board. The vias are laser microvias. This product does not drill a microvia or build a stacked via.",
    },
}
_FAMILY = {
    "dip": "DIP is through-hole. Two rows of pins go through the board. Drill size still comes from the datasheet.",
    "soic": "SOIC is the smaller surface-mount form of a DIP. Gull-wing leads solder on top of the board. Lands are not copied from a drawing.",
    "qfp": "QFP is square, with gull-wing leads on all four sides. The pin count comes from the datasheet.",
    "qfn": "QFN has no extending leads. Pads sit on the underside, usually with a thermal pad. Lands wait for a datasheet.",
    "bga": "BGA uses a grid of solder balls under the package, not edge pins. This product does not place a ball map or escape-route the balls.",
    "wlcsp": "WLCSP is the size of the silicon die. This product does not do wafer-level layout.",
    "lga": "LGA is a grid of flat lands, not solder balls. This product does not place a land map.",
    "pga": "PGA is a grid of pins, usually through a socket. This product does not place that pin field.",
    "dfn": "DFN is a dual flat no-lead package. Pads are on the underside. Lands wait for a datasheet.",
    "tqfp": "TQFP is a thin QFP. Gull-wing leads are on all four sides. The pitch comes from the datasheet.",
    "ssop": "SSOP is a shrink small-outline package. The pitch is finer than a SOIC. Lands wait for a datasheet.",
    "tsop": "TSOP is a thin small-outline package. Lands wait for a datasheet.",
    "sop": "SOP is a small-outline leaded package. Lands wait for a datasheet.",
    "sot": "SOT is a small-outline transistor package. Lands wait for a datasheet.",
    "sip": "SIP is a single row of through-hole pins. Drill size comes from the datasheet.",
    "to": "TO is a transistor outline, often a tabbed through-hole part. The hole size comes from the datasheet.",
}
_FAB = {
    "pth": "PTH: plated hole for a through-hole pin or a layer change. Standard minimum drill is 0.20 mm to 0.30 mm. This board stores 0.30 mm.",
    "npth": "NPTH: a bare hole for a screw or a peg. The wall is not plated. This product does not tag a hole as NPTH.",
    "microvia": "Microvia: a laser hole, typically 0.10 mm to 0.15 mm, for HDI. This product does not drill one.",
    "ring": "Annular ring: copper left around the hole. Standard minimum is 0.15 mm per side, about 6 mil. 1 mil is 0.0254 mm.",
    "trace": "Trace width: standard minimum 0.13 mm to 0.15 mm (5 to 6 mil). High-density minimum 0.075 mm to 0.10 mm (3 to 4 mil). This profile stores 0.10 mm, which is the dense edge, not a promise from a shop.",
    "space": "Shop trace clearance starts at 0.13 mm to 0.15 mm. This profile stores 0.10 mm. For voltage spacing ask IPC-2221 at a voltage. That is Table 6-1, not this shop minimum.",
    "copper": "Copper weight: 1 oz is 0.035 mm (35 µm). 2 oz is 0.070 mm, used for power and motor current. The current calculator is separate from this rule.",
    "silk": "Silkscreen: minimum line 0.15 mm, minimum text height 1.00 mm, and keep ink 0.10 mm to 0.15 mm off exposed copper. This board does not draw silk, so the gap is not measured.",
    "mask": "Solder mask: swell the opening 0.05 mm past the pad. The mask bridge between pads should be at least 0.10 mm. Closer than that, a shop usually removes the web. Pad gaps on this board are not measured.",
}
_MPN = re.compile(r"\b(?=[A-Z0-9]*[A-Z])(?=[A-Z0-9]*\d)[A-Z][A-Z0-9]{5,19}\b")
_ASK = re.compile(r"\b(clearance|pad|pads|power|dissipation|footprint|package|rating|size|land|lands|what|datasheet)\b", re.I)
_LEAVE = re.compile(
    r"\b(place|add|mount|route|autoroute|sketch|extrude|inverter|nand|nor|plc|pac|delete|remove|move|rotate|copy|flip|swap|connect|tie|fanout|teardrop|stitch|lock|unlock|align|undo|redo|zoom|pan|export|generate|simulate|pour|check|calculate|measure|ripup|rip)\b",
    re.I,
)


def _lands(code: str, row: dict) -> str:
    pads = lands(
        {
            "family": "chip",
            "pins": 2,
            "pitch": 0,
            "width": row["width"],
            "length": row["length"],
            "package": code,
            "pin_names": {},
        }
    )
    one = pads[0]
    return f"two {one['w']:.2f} × {one['h']:.2f} mm lands, centers {abs(pads[1]['x'] - one['x']):.2f} mm apart"


def _construction(text: str) -> str | None:
    if "hdi" in text or "high-density interconnect" in text or "high density interconnect" in text:
        return "hdi"
    if "rogers" in text or "ptfe" in text:
        return "ptfe"
    if "ceramic" in text or "alumina" in text:
        return "ceramic"
    if "rigid-flex" in text or "rigid flex" in text:
        return "rigidflex"
    if "metal core" in text or "mcpcb" in text or "aluminum core" in text:
        return "metal"
    if "single-sided" in text or "single sided" in text:
        return "single"
    if "double-sided" in text or "double sided" in text:
        return "double"
    if "multi-layer" in text or "multilayer" in text or "multi layer" in text:
        return "multi"
    if re.search(r"\bflex", text):
        return "flex"
    if re.search(r"\brigid\b", text):
        return "rigid"
    return None


def _family(text: str) -> str | None:
    if "wlcsp" in text or "wafer-level" in text or "wafer level" in text or "chip scale" in text:
        return "wlcsp"
    if re.search(r"\blga\b", text) or "land grid" in text:
        return "lga"
    if re.search(r"\bpga\b", text) or "pin grid" in text:
        return "pga"
    if re.search(r"\bbga\b", text) or "ball grid" in text:
        return "bga"
    if re.search(r"\bdfn\b", text):
        return "dfn"
    if re.search(r"\bqfn\b", text) or "no-lead" in text or "no lead" in text:
        return "qfn"
    if re.search(r"\btqfp\b", text):
        return "tqfp"
    if re.search(r"\bqfp\b", text) or "quad flat package" in text:
        return "qfp"
    if re.search(r"\bssop\b", text):
        return "ssop"
    if re.search(r"\btsop\b", text):
        return "tsop"
    if re.search(r"\bsop\b", text) and "soic" not in text:
        return "sop"
    if re.search(r"\bsoic\b", text) or "small outline ic" in text:
        return "soic"
    if re.search(r"\bsot\b", text) or "small outline transistor" in text:
        return "sot"
    if re.search(r"\bsip\b", text) or "single in-line" in text or "single inline" in text:
        return "sip"
    if re.search(r"\bdip\b", text) or "dual in-line" in text or "dual inline" in text:
        return "dip"
    if "transistor outline" in text or re.search(r"\bto-220\b", text) or re.search(r"\bto-92\b", text):
        return "to"
    return None


def _fab_keys(text: str) -> list[str]:
    if re.search(r"trace width for|width for \d|via for \d|set copper|copper \d|amps", text):
        return []
    if re.search(r"fab rule|fabrication rule|shop rule|manufacturing rule", text):
        return list(_FAB)
    keys = []
    if "npth" in text or "non-plated" in text or "non plated" in text:
        keys.append("npth")
    elif "pth" in text or "plated through" in text:
        keys.append("pth")
    if "microvia" in text or "micro via" in text or "laser drill" in text:
        keys.append("microvia")
    if "annular" in text:
        keys.append("ring")
    if re.search(r"trace (width|rule|minimum)|minimum trace|copper line", text) and "for" not in text:
        keys.append("trace")
    if re.search(r"trace clearance|spacing rule|minimum clearance|minimum space", text):
        keys.append("space")
    if "copper weight" in text or "1 oz" in text or "2 oz" in text:
        keys.append("copper")
    if "silkscreen" in text or "legend" in text or re.search(r"\bsilk\b", text):
        keys.append("silk")
    if "solder mask" in text or "mask swell" in text or "mask bridge" in text or "soldermask" in text:
        keys.append("mask")
    return keys


def _ipc_clearance(text: str) -> str | None:
    if re.search(r"\b(0402|0603|0805|1206)\b", text):
        return None
    low = text.lower()
    named = "2221" in low or "conductor spacing" in low
    numbered = "clearance" in low and re.search(r"\d", low)
    if not named and not numbered:
        return None
    if re.search(r"trace width|via for|set copper", low):
        return None
    from py.si.desk import spacing_text

    nums = [item for item in re.findall(r"\d+(?:\.\d+)?", low) if item not in {"2221", "2221b"}]
    if not nums:
        return (
            "IPC-2221B Table 6-1 uses the peak voltage. B1 is internal, B2 is external uncoated up to 3050 m, "
            "B4 is a permanent polymer coating. Solder mask alone is not B4. "
            "Above 500 V add 0.0025, 0.005, and 0.00305 mm per volt. B3 is not stored. This is not creepage. "
            "Ask with a voltage, for example IPC-2221 at 50 V."
        )
    return spacing_text(float(nums[0]))


_LEX = (
    (("ipc-7351", "ipc 7351"), "IPC-7351 is the land-pattern math for surface-mount pads. Lands here are a simple calculated pair, not the Most, Nominal, and Least density formulas."),
    (("fr-4", "fr4"), "FR-4 is glass-epoxy laminate. It does not bend. It is the usual board material here."),
    (("polyimide",), "Polyimide is the film in a flex board. Bend radius is not calculated."),
    (("ipc-2152", "ipc 2152"), "IPC-2152 is the current and temperature-rise standard. Trace width here is the older IPC-2221 curve, not the 2152 charts."),
    (("i2c",), "I2C is a slow open-drain bus. Pull-up value and bus capacitance are not calculated unless you ask for a filter."),
    (("spi",), "SPI is a clocked bus. This autorouter does not length-match MOSI, MISO, and the clock."),
    (("can bus", "can-bus"), "CAN is a differential bus, often 120 ohm. A pair can be marked. The impedance is not proven."),
    (("usb",), "USB is a differential pair. 90 ohm is a target you can set. This is not a USB compliance test."),
    (("asic",), "An ASIC is a chip built for one task. This product does not tape out silicon."),
    (("soc", "system on a chip", "system-on-a-chip"), "An SoC puts a processor, memory, and radios on one die. This product places a package, not the die."),
    (("fpga",), "An FPGA is reprogrammable logic. This product does not make a bitstream."),
    (("tape-out", "tape out"), "Tape-out is the layout handoff to a foundry. This product does not tape out."),
    (("watchdog", "wdt"), "A watchdog reboots stuck firmware. It is not a part on the sheet unless you place one."),
    (("bootloader",), "A bootloader is startup code. The boot-pin check is a sheet note, not a firmware image."),
    (("gpio",), "GPIO is a programmable pin. Input or output is firmware, not a PCB net."),
    (("adc",), "An ADC turns analog into a number. The front end is not designed unless the datasheet states it."),
    (("dac",), "A DAC turns a number into analog. It is not simulated."),
    (("pwm",), "PWM fakes an analog level by switching. Switching loss is not simulated."),
    (("interrupt",), "An interrupt is a firmware event. It is not a trace."),
    (("alu",), "The ALU is the CPU's math block. It is not a board feature."),
    (("risc-v", "x86", "arm", "isa"), "An ISA is the processor instruction set. This board tool does not choose x86, ARM, or RISC-V."),
    (("vram",), "VRAM is GPU memory. It is not placed as a die."),
    (("tdp",), "TDP is the chip's heat budget in watts. Thermal loss here is I²R on a trace, not TDP."),
    (("cache",), "Cache is on-die memory. It is not a PCB net."),
    (("pipeline",), "A pipeline overlaps instruction stages. It is not modeled."),
    (("teardrop",), "A teardrop widens a trace into a pad. This product does not draw one."),
    (("fanout",), "Fanout is the escape routing from a fine package. BGA balls are not escaped here."),
    (("stitch", "via stitch"), "Via stitching ties planes together. This autorouter does not add a stitch field."),
    (("keepout", "keep-out", "keep out"), "A keep-out is copper or parts that must stay out of a region. No keep-out polygon is stored on this board."),
    (("test point",), "TP marks a test point. The placed refs here are J, U, R, C, L, Q, and D, not TP."),
    (("crystal", "oscillator"), "Y marks a crystal. Load capacitors are not calculated unless you ask."),
    (("coplanar",), "A coplanar waveguide is an RF trace with ground beside it. Impedance here is a microstrip estimate, not a coplanar solver."),
    (("pure tin", "tin whisker"), "Aerospace work avoids pure tin because of whiskers. This product does not check the finish for tin."),
    (("outgassing",), "Space and aerospace coats should be low-outgassing. Outgassing is not simulated."),
    (("radiation",), "Space parts may be radiation-hardened. This product does not model total dose."),
    (("200 c", "200°c", "downhole"), "Downhole tools can see well above 125 °C. The oil profile still stores −40 to 125 °C. It is not a 200 °C qualification."),
    (("clearance",), "Clearance is the air gap between conductors. Ask for a voltage, for example clearance at 50 V, and the IPC-2221B table is used."),
    (("creepage",), "Creepage is the distance along the surface. It is not the air gap. Ask creepage at a voltage."),
    (("skew",), "Skew is the timing difference between traces. This autorouter does not match lengths."),
    (("crosstalk",), "Crosstalk is coupling between neighbors. There is no field solver here."),
    (("drc",), "DRC checks duplicates, clearance between placed parts, and the profile rules. It is not a full manufacturer rule deck."),
    (("erc",), "ERC checks unwired symbols and a missing ground or VBUS on the schematic. It does not read pin types."),
    (("solder mask", "mask bridge"), "The solder mask opening is usually 0.05 mm larger than the pad, and the web between pads wants 0.10 mm. Pad gaps on this board are not measured."),
    (("silkscreen",), "Silkscreen wants a 0.15 mm line and 1 mm text, kept off the pads. This board does not draw silk."),
    (("die",), "The die is the bare silicon. This product places a package, not a die."),
    (("wafer",), "A wafer is the slice the die is cut from. There is no wafer layout here."),
    (("logic gate", "xor", "nand gate", "nor gate"), "A logic gate is a Boolean block. The cells here are an inverter, NAND2, and NOR2 on a teaching grid, not a foundry library."),
    (("mcu",), "An MCU is a small computer on one chip. A starter board can be placed. Firmware is not generated."),
    (("thread",), "A thread is a software sequence on a core. It is not a PCB object."),
    (("clock speed",), "Clock speed is the part's rate in hertz. The clock check only looks for a crystal symbol."),
    (("differential",), "A differential pair is two traces that carry opposite signals. Ask for a 90 or 100 ohm pair. It is not proven on the layout."),
    (("analog",), "Analog and digital want separate regions and a quiet return. This product does not split a plane."),
    (("digital",), "Digital edges need a continuous return. This product does not check the return path."),
    (("pull-up", "pullup", "pull up"), "A pull-up holds an open-drain net high. The resistor value is not chosen unless you ask for a filter."),
    (("mil",), "A mil is 0.0254 mm. Coordinates said in mil are converted when you place or move."),
    (("via",), "A via is a plated hole that changes layer. This autorouter stays on one layer, so it does not drop a via."),
)


def _lexicon(text: str) -> dict | None:
    asking = re.search(r"\b(what|explain|define|meaning)\b", text)
    best = None
    for aliases, blurb in _LEX:
        for alias in aliases:
            if alias not in text:
                continue
            if re.search(r"(?<![a-z0-9])" + re.escape(alias) + r"(?![a-z0-9])", text) is None:
                continue
            if best is None or len(alias) > best[0]:
                best = (len(alias), blurb, alias)
    if best is None:
        return None
    if not asking:
        stripped = re.sub(r"[^a-z0-9]+", " ", text).strip()
        stripped = re.sub(r"^(a|an|the|pcb) ", "", stripped)
        if stripped != best[2]:
            return None
    return {"focus": best[2], "text": best[1], "set": None}


def answer(text: str, clearance_mm: float = 0.1) -> dict | None:
    if _LEAVE.search(text):
        return None
    low = text.lower()
    if re.search(r"\b(list pcb fields|pcb fields|which fields)\b", low):
        from py.si.engine import INDUSTRY

        titles = ", ".join(row["title"] for row in INDUSTRY.values())
        return {"focus": "Fields", "text": titles, "set": None}
    ipc = _ipc_clearance(text)
    if ipc:
        return {"focus": "IPC-2221", "text": ipc, "set": None}
    fab = _fab_keys(low)
    if fab:
        return {"focus": "Fab rules", "text": " ".join(_FAB[key] for key in fab), "set": None}
    if re.search(r"types of (pcb|boards|board)", low):
        lines = [f"{row['title']}: {row['text']}" for row in _BOARD.values()]
        return {"focus": "PCB types", "text": " ".join(lines)}
    if re.search(r"types of (chip|packages|package)", low):
        return {"focus": "Package types", "text": " ".join(_FAMILY.values())}
    construction = _construction(low)
    family = _family(low)
    chips = re.findall(r"\b(0402|0603|0805|1206)\b", text)
    packages = [item.upper() for item in re.findall(r"\b(SOT-23|SOD-123|QFN-32|SOIC-16)\b", text, re.I)]
    mpns = [item for item in _MPN.findall(text.upper()) if item not in set(chips)]
    if not chips and not packages and not mpns and not construction and not family:
        term = _lexicon(low)
        if term:
            return term
        return None
    asking = re.search(r"\b(what|explain|difference|why)\b", low)
    if not _ASK.search(text) and not mpns and not construction and not family:
        return None
    lines = []
    focus = ""
    setting = None
    if construction:
        row = _BOARD[construction]
        focus = row["title"]
        lines.append(f"{row['title']}. {row['text']}")
        if not asking and re.search(r"\b(board|pcb|use|set|make)\b", low):
            setting = {"layers": row["layers"], "material": row["material"]}
            lines.append(f"Set on this board: {row['material']}.")
    if family:
        focus = focus or family.upper()
        lines.append(_FAMILY[family])
    for code in dict.fromkeys(chips):
        row = _CHIP[code]
        lines.append(
            f"{code}: body {row['length']:.2f} × {row['width']:.2f} × {row['height']:.2f} mm. "
            f"Lands are calculated, {_lands(code, row)}. "
            f"Usual catalog rating {row['power_w']:g} W, confirm the datasheet. "
            f"Board minimum clearance is {clearance_mm:g} mm, not a package rule."
        )
    for name in dict.fromkeys(packages):
        lines.append(f"{name}: {_PKG[name]}")
    for mpn in dict.fromkeys(mpns):
        lines.append(f"{mpn} was read whole. It is not in the graph. Attach the datasheet before any pin or land is invented.")
    if not focus:
        focus = chips[0] if chips else packages[0] if packages else mpns[0]
    return {"focus": focus, "text": " ".join(lines), "set": setting}
