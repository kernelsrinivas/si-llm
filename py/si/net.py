"""Causal transformer that turns a PCB/CAD sentence into a command."""

from __future__ import annotations

import json
import os
import random
from pathlib import Path

import torch
import torch.nn as nn
import torch.nn.functional as F

ROOT = Path(os.environ.get("SI_MODEL") or Path(__file__).resolve().parents[2] / "model")
WEIGHTS = ROOT / "si.pt"
META = ROOT / "meta.json"

INTENTS = [
    "PCB_ADD",
    "PCB_NET",
    "PCB_FLOW",
    "PCB_DRC",
    "PCB_STATUS",
    "SCH_ADD",
    "SCH_WIRE",
    "SCH_ERC",
    "FP_ASSIGN",
    "SIM_DC",
    "SIM_TRAN",
    "VIEW_3D",
    "FAB_PACK",
    "FAB_STACK",
    "ASM_BOM",
    "ASM_POS",
    "CHIP",
    "INDUSTRY",
    "BOARD",
    "CLASS",
    "HANDLE",
    "OUTLINE",
    "DATASHEET",
    "PLACE",
    "IMPEDANCE",
    "POUR",
    "DFM",
    "VIA",
    "DIFF",
    "CAD_CHAMFER",
    "CAD_SHELL",
    "IPC",
    "GEM",
    "AUDIT",
    "ROUTE",
    "CIRCUIT",
    "DEL",
    "MOVE",
    "ROT",
    "COPY",
    "SWAP",
    "FLIP",
    "FIND",
    "POWER",
    "ROBOT",
    "COMPUTER",
    "SENSOR",
    "CAD_SKETCH",
    "CAD_EXTRUDE",
    "CAD_HOLE",
    "CAD_FILLET",
    "CAD_MASS",
    "CAD_STATUS",
    "HELP",
    "ASK",
]
PKGS = ["usbc", "esp32", "ldo", "imu", "conn", "res", "cap", "mcu", "buck", "ant", "bjt", "diode", "led", "ind", "fet"]
REFS = ["j1", "u1", "u2", "u3", "r1", "r2", "c1", "c2", "l1", "q1", "d1", "d2", "y1", "tp1", "sw1"]
NETS = ["vbus", "gnd", "i2c", "sw", "usb", "3v3"]
NUMS = ["1", "2", "3", "4", "5", "6", "8", "10", "12", "16", "20", "24", "28", "30", "40", "50", "60", "80", "90"]
SLOTS = [
    "all", "0", "45", "100", "150", "170", "180", "200", "244", "270", "305",
    "vcc", "vdd", "vss", "tx", "rx", "clk", "sda", "scl", "mosi", "miso", "sck", "cs", "can", "5v",
    "soic", "qfp", "qfn", "tqfp", "bga", "dip", "sip", "sop", "ssop", "tsop", "dfn", "lga", "wlcsp", "pga", "sot", "crystal",
    "vin", "vout", "iout", "freq", "eff",
]
DISCIPLINES = ["pin", "decap", "power", "io", "clock", "reset", "boot", "thermal", "si", "pi"]
INDUSTRIES = [
    "automotive",
    "aerospace",
    "defense",
    "space",
    "marine",
    "robot",
    "medical",
    "agri",
    "audio",
    "compute",
    "consumer",
    "industrial",
    "iot",
    "oil",
    "light",
    "energy",
    "quantum",
    "rail",
    "instrument",
    "security",
    "telecom",
]
BOARDS = ["tiny", "power", "bms", "motor", "cpu", "gpu", "modem", "motherboard"]
SPECIAL = ["<pad>", "<bos>", "<eos>", "<sep>", "<unk>", "<none>"]

BLOCK = 28
N_EMBD = 384
N_HEAD = 8
N_LAYER = 11
DROP = 0.15


def build_vocab() -> list[str]:
    from py.si.computer import tokens as computer_tokens
    from py.si.power import tokens as power_tokens
    from py.si.robot import tokens as robot_tokens
    from py.si.sensor import tokens as sensor_tokens

    words = set(SPECIAL) | set(INTENTS) | set(PKGS) | set(REFS) | set(NETS) | set(NUMS) | set(DISCIPLINES) | set(INDUSTRIES) | set(BOARDS) | set(SLOTS)
    words.update(power_tokens())
    words.update(robot_tokens())
    words.update(computer_tokens())
    words.update(sensor_tokens())
    extras = """
    add place put mount insert drop connect net wire tie link join
    flow run release finish gerber bom drc check status show list board pcb schematic
    sketch draw plate rectangle rect extrude thicken hole drill bore fillet round edge
    mass weight volume cad part solid as named called ref at x y by mm to from and on
    the a an of with my its please make create what is how do can you
    length width thickness diameter radius
    symbol erc footprint assign simulation dc transient viewer fabrication stackup
    assembly centroid pick discipline pinout decoupling caps voltage clock boot thermal
    integrity signal open files layer
    industry automatic automotive aerospace marine robot medical tiny battery modem
    motherboard cpu gpu network car flight ship patient electronics class module
    outline all datasheet sheet symbols
    ohm impedance trace pour via dfm annular differential pair chamfer shell wall amps
    ipc class jstd std
    trace width filter cutoff thermal loss kicad allegro skill altium replacement replace creepage emi emc table audit feature
    autoroute route rip
    plc pac switching switch fet mosfet transistor bjt diode led inductor coil inverter nand nor cell inv
    v clearance current circuit
    quantum cryogenic satellite defense defence railway transit oil drilling agriculture agri agrotech
    audio broadcast broadcasting computing datacenter data center consumer industrial manufacturing factory
    iot wearable wearables lighting opto optoelectronics energy instrument instrumentation scientific
    security access control telecom telecommunication telecommunications rf healthcare automation
    delete remove erase move rotate copy flip mirror swap find undo redo zoom pan lock unlock
    group align select deselect highlight hide fanout teardrop stitch tune edit import measure calculate
    vcc vdd vss tx rx sda scl mosi miso can mil oz volt amp watt resistor capacitor inductor diode led crystal connector
    up me the gerbers routes
    """.split()
    words.update(extras)
    ordered = SPECIAL + [w for w in sorted(words) if w not in SPECIAL]
    return ordered


class Block(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.ln1 = nn.LayerNorm(N_EMBD)
        self.qkv = nn.Linear(N_EMBD, 3 * N_EMBD)
        self.proj = nn.Linear(N_EMBD, N_EMBD)
        self.ln2 = nn.LayerNorm(N_EMBD)
        self.fc1 = nn.Linear(N_EMBD, 4 * N_EMBD)
        self.fc2 = nn.Linear(4 * N_EMBD, N_EMBD)
        self.drop = nn.Dropout(DROP)
        self.n_head = N_HEAD

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        b, t, c = x.shape
        h = self.ln1(x)
        qkv = self.qkv(h)
        q, k, v = qkv.split(c, dim=2)
        hs = c // self.n_head
        q = q.view(b, t, self.n_head, hs).transpose(1, 2)
        k = k.view(b, t, self.n_head, hs).transpose(1, 2)
        v = v.view(b, t, self.n_head, hs).transpose(1, 2)
        att = (q @ k.transpose(-2, -1)) * (hs**-0.5)
        mask = torch.tril(torch.ones(t, t, device=x.device, dtype=torch.bool))
        att = att.masked_fill(~mask, -1e9)
        att = torch.softmax(att, dim=-1)
        y = att @ v
        y = y.transpose(1, 2).contiguous().view(b, t, c)
        x = x + self.drop(self.proj(y))
        h = self.ln2(x)
        x = x + self.drop(self.fc2(F.gelu(self.fc1(h))))
        return x


class GPT(nn.Module):
    def __init__(self, n_vocab: int) -> None:
        super().__init__()
        self.tok = nn.Embedding(n_vocab, N_EMBD)
        self.pos = nn.Embedding(BLOCK, N_EMBD)
        self.blocks = nn.ModuleList(Block() for _ in range(N_LAYER))
        self.ln_f = nn.LayerNorm(N_EMBD)
        self.head = nn.Linear(N_EMBD, n_vocab, bias=False)

    def forward(self, idx: torch.Tensor) -> torch.Tensor:
        b, t = idx.shape
        x = self.tok(idx) + self.pos(torch.arange(t, device=idx.device))
        for block in self.blocks:
            x = block(x)
        return self.head(self.ln_f(x))


def stoi_of(vocab: list[str]) -> dict[str, int]:
    return {t: i for i, t in enumerate(vocab)}


def encode_words(words: list[str], stoi: dict[str, int]) -> list[int]:
    unk = stoi["<unk>"]
    return [stoi.get(w, unk) for w in words]


def samples(rng: random.Random) -> list[tuple[str, list[str]]]:
    """(prompt, target tokens) with the target a fixed 5-slot program."""
    none = "<none>"
    rows: list[tuple[str, list[str]]] = []

    def add(prompt: str, target: list[str]) -> None:
        rows.append((prompt, target))

    add_tpl = [
        "add {pkg} as {ref} at {x} {y}",
        "place {pkg} {ref} at {x} {y}",
        "put {pkg} on the board ref {ref} x {x} y {y}",
        "mount {ref} {pkg} at {x} {y}",
        "pcb add {ref} {pkg} {x} {y}",
        "insert {pkg} called {ref} at {x} {y}",
    ]
    core_pkgs = ["usbc", "esp32", "ldo", "imu", "conn", "res", "cap", "mcu", "buck", "ant"]
    core_refs = ["j1", "u1", "u2", "u3", "r1", "c1", "l1"]
    for pkg in core_pkgs:
        for ref in core_refs:
            for x in NUMS:
                for y in rng.sample(NUMS, 5):
                    tpl = rng.choice(add_tpl)
                    add(tpl.format(pkg=pkg, ref=ref, x=x, y=y), ["PCB_ADD", pkg, ref, x, y])

    net_tpl = [
        "connect {net} from {a} to {b}",
        "tie {net} between {a} and {b}",
        "net {net} {a} {b}",
        "wire {a} to {b} on {net}",
        "pcb net {net} {a} {b}",
    ]
    for net in NETS:
        for a in core_refs:
            for b in rng.sample(REFS, 3):
                if a == b:
                    continue
                tpl = rng.choice(net_tpl)
                add(tpl.format(net=net, a=a, b=b), ["PCB_NET", net, a, b, none])

    for phrase in [
        "run the pcb flow",
        "finish the board",
        "export gerber",
        "release the pcb",
        "pcb flow",
        "pack gerbers and the bom",
    ]:
        add(phrase, ["PCB_FLOW", none, none, none, none])
    for phrase in ["check drc", "design rule check", "pcb drc", "run drc on the board", "run the design check"]:
        add(phrase, ["PCB_DRC", none, none, none, none])
    for phrase in ["show the board", "pcb status", "list parts", "what is on the pcb"]:
        add(phrase, ["PCB_STATUS", none, none, none, none])

    sketch_tpl = [
        "sketch a plate {l} by {w}",
        "draw a rectangle {l} {w}",
        "cad sketch {l} {w}",
        "make a plate length {l} width {w}",
    ]
    for l in NUMS:
        for w in NUMS:
            if int(w) > int(l):
                continue
            tpl = rng.choice(sketch_tpl)
            add(tpl.format(l=l, w=w), ["CAD_SKETCH", l, w, none, none])
    for t in NUMS[:8]:
        for phrase in [
            f"extrude {t}",
            f"extrude {t} mm",
            f"thicken the plate {t}",
            f"cad extrude {t}",
        ]:
            add(phrase, ["CAD_EXTRUDE", t, none, none, none])
    for d in NUMS[:8]:
        for phrase in [f"drill a {d} mm hole", f"hole diameter {d}", f"bore {d}", f"cad hole {d}"]:
            add(phrase, ["CAD_HOLE", d, none, none, none])
    for r in ["1", "2", "3", "4", "6", "8"]:
        for phrase in [f"fillet {r}", f"fillet radius {r}", f"round the edges {r}", f"cad fillet {r}"]:
            add(phrase, ["CAD_FILLET", r, none, none, none])
    for phrase in ["what is the mass", "cad mass", "how heavy is the part", "weight of the solid"]:
        add(phrase, ["CAD_MASS", none, none, none, none])
    for phrase in ["cad status", "show the solid", "describe the part"]:
        add(phrase, ["CAD_STATUS", none, none, none, none])
    for phrase in ["help", "what can you do", "commands", "how do i start"]:
        add(phrase, ["HELP", none, none, none, none])

    sch_tpl = [
        "add {pkg} symbol {ref}",
        "schematic symbol {pkg} as {ref}",
        "put {pkg} on the schematic {ref}",
    ]
    for pkg in core_pkgs:
        for ref in core_refs[:4]:
            tpl = rng.choice(sch_tpl)
            add(tpl.format(pkg=pkg, ref=ref), ["SCH_ADD", pkg, ref, none, none])
    wire_tpl = [
        "wire {net} from {a} to {b}",
        "schematic net {net} {a} {b}",
        "connect {net} on the schematic from {a} to {b}",
    ]
    for net in NETS:
        for a, b in (("j1", "u1"), ("u1", "u2"), ("u1", "c1"), ("r1", "u1")):
            tpl = rng.choice(wire_tpl)
            add(tpl.format(net=net, a=a, b=b), ["SCH_WIRE", net, a, b, none])
    for phrase in ["run erc", "schematic erc", "electrical rules", "check the schematic"]:
        add(phrase, ["SCH_ERC", none, none, none, none])
    for ref in core_refs:
        for phrase in [f"assign the footprint for {ref}", f"footprint for {ref}", f"set the footprint on {ref}"]:
            add(phrase, ["FP_ASSIGN", ref, none, none, none])
    for phrase in ["run the dc simulation", "dc operating point", "simulate dc", "sim dc"]:
        add(phrase, ["SIM_DC", none, none, none, none])
    for phrase in ["run a transient simulation", "transient sim", "sim tran", "simulate the transient"]:
        add(phrase, ["SIM_TRAN", none, none, none, none])
    for phrase in ["open the 3d viewer", "show the board in 3d", "3d view of the pcb", "view 3d"]:
        add(phrase, ["VIEW_3D", none, none, none, none])
    for phrase in ["pack the fabrication files", "fabrication output", "export gerbers for fabrication", "fab gerber"]:
        add(phrase, ["FAB_PACK", none, none, none, none])
    for phrase in ["show the stackup", "layer stack", "fab stack", "what is the stackup"]:
        add(phrase, ["FAB_STACK", none, none, none, none])
    for phrase in ["export the assembly bom", "assembly bom", "asm bom", "bill of materials"]:
        add(phrase, ["ASM_BOM", none, none, none, none])
    for phrase in ["pick and place file", "centroid file", "asm pos", "placement file for assembly"]:
        add(phrase, ["ASM_POS", none, none, none, none])
    chip_phrases = {
        "pin": ["check chip pins", "check the pinout", "pin check"],
        "decap": ["check decoupling", "decoupling check", "are the caps ok"],
        "power": ["check the power tree", "chip power check", "power check"],
        "io": ["check io voltage", "io levels", "io check"],
        "clock": ["check the clock", "clock discipline", "clock check"],
        "reset": ["check reset", "reset circuit", "reset check"],
        "boot": ["check boot pins", "boot strap", "boot check"],
        "thermal": ["check thermal", "thermal check", "chip thermal"],
        "si": ["check signal integrity", "si check", "signal integrity"],
        "pi": ["check power integrity", "pi check", "power integrity"],
    }
    for kind, phrases in chip_phrases.items():
        for phrase in phrases:
            add(phrase, ["CHIP", kind, none, none, none])
    industry_phrases = {
        "automotive": ["automotive industry", "automatic industry", "car electronics", "this is an automotive board"],
        "aerospace": ["aerospace industry", "aerospace pcb", "flight electronics"],
        "marine": ["marine industry", "marine pcb", "shipboard electronics"],
        "robot": ["robot industry", "robot pcb", "robotics board", "automation industry"],
        "medical": ["medical industry", "medical pcb", "patient electronics", "healthcare industry"],
        "defense": ["defense industry", "defence industry"],
        "space": ["space satellite", "satellite industry"],
        "agri": ["agriculture industry", "agri industry"],
        "audio": ["audio industry", "broadcast industry"],
        "compute": ["computing industry", "data center"],
        "consumer": ["consumer electronics", "consumer industry"],
        "industrial": ["industrial industry", "manufacturing industry"],
        "iot": ["iot industry", "wearable industry"],
        "oil": ["oil industry", "drilling industry"],
        "light": ["lighting industry", "opto industry"],
        "energy": ["energy industry", "power and energy"],
        "quantum": ["quantum industry", "cryogenic industry"],
        "rail": ["railway industry", "transit industry"],
        "instrument": ["scientific industry", "instrument industry"],
        "security": ["security industry"],
        "telecom": ["telecom industry", "telecommunications industry"],
    }
    for kind, phrases in industry_phrases.items():
        for phrase in phrases:
            add(phrase, ["INDUSTRY", kind, none, none, none])
    board_phrases = {
        "tiny": ["tiny circuit", "small module", "tiny pcb"],
        "power": ["power electronics", "power electronics board"],
        "bms": ["battery board class", "set bms class"],
        "motor": ["motor control", "motor control board"],
        "cpu": ["cpu motherboard", "cpu board"],
        "gpu": ["gpu board", "gpu card"],
        "modem": ["network modem", "modem board"],
        "motherboard": ["large motherboard", "big motherboard"],
    }
    for kind, phrases in board_phrases.items():
        for phrase in phrases:
            add(phrase, ["BOARD", kind, none, none, none])
    for phrase in ["check the industry rules", "industry check", "check this board class"]:
        add(phrase, ["CLASS", none, none, none, none])
    add("handle all industries", ["HANDLE", "all", none, none, none])
    add("cover all", ["HANDLE", "all", none, none, none])
    add("covet all", ["HANDLE", "all", none, none, none])
    for kind in INDUSTRIES + BOARDS:
        add(f"handle {kind}", ["HANDLE", kind, none, none, none])
    for length, width in (("80", "40"), ("100", "80"), ("170", "170"), ("244", "200"), ("305", "244")):
        add(f"set the board outline {length} by {width}", ["OUTLINE", length, width, none, none])
        add(f"outline {length} by {width}", ["OUTLINE", length, width, none, none])
    for phrase in ["build from the datasheet", "read the datasheet", "use the datasheet"]:
        add(phrase, ["DATASHEET", none, none, none, none])
    for phrase in ["place the sheet", "place the symbols"]:
        add(phrase, ["PLACE", none, none, none, none])
    for ohms in ("50", "90", "100"):
        add(f"set a {ohms} ohm trace", ["IMPEDANCE", ohms, none, none, none])
        add(f"{ohms} ohm impedance", ["IMPEDANCE", ohms, none, none, none])
    for phrase in ["pour the ground", "copper pour", "ground pour"]:
        add(phrase, ["POUR", none, none, none, none])
    for phrase in ["dfm check", "check annular ring", "fabrication design check"]:
        add(phrase, ["DFM", none, none, none, none])
    for amps in ("1", "2", "5", "10"):
        add(f"size the via for {amps} a", ["VIA", amps, none, none, none])
    for net in ("usb", "gnd", "sw"):
        add(f"differential pair on {net}", ["DIFF", net, none, none, none])
    for radius in ("1", "2", "3"):
        add(f"chamfer {radius}", ["CAD_CHAMFER", radius, none, none, none])
        add(f"shell wall {radius}", ["CAD_SHELL", radius, none, none, none])
    for phrase in ["ipc check", "check ipc", "run the ipc standards", "all ipc"]:
        add(phrase, ["IPC", "all", none, none, none])
    for grade in ("1", "2", "3"):
        add(f"set ipc class {grade}", ["IPC", grade, "class", none, none])
        add(f"ipc class {grade}", ["IPC", grade, "class", none, none])
    for amps in ("1", "2", "3", "5"):
        add(f"trace width for {amps} a", ["GEM", "width", amps, none, none])
    add("rc filter cutoff", ["GEM", "filter", none, none, none])
    add("thermal loss for 3 a", ["GEM", "thermal", "3", none, none])
    add("kicad script", ["GEM", "kicad", none, none, none])
    add("allegro skill", ["GEM", "skill", none, none, none])
    add("altium script", ["GEM", "altium", none, none, none])
    add("drop in replacement", ["GEM", "replace", none, none, none])
    add("creepage at 50 v", ["GEM", "creepage", "50", none, none])
    add("emi layout", ["GEM", "emi", none, none, none])
    add("bom table", ["GEM", "table", none, none, none])
    add("feature audit", ["AUDIT", none, none, none, none])
    add("autoroute the board", ["ROUTE", "all", none, none, none])
    add("route the nets", ["ROUTE", "all", none, none, none])
    add("rip up the routes", ["ROUTE", "rip", none, none, none])
    for net in ("vbus", "gnd", "sw"):
        add(f"route {net}", ["ROUTE", net, none, none, none])
    add("high speed switching circuit", ["CIRCUIT", "switch", none, none, none])
    add("plc circuit", ["CIRCUIT", "plc", none, none, none])
    add("pac circuit", ["CIRCUIT", "pac", none, none, none])
    add("mcu board design", ["CIRCUIT", "mcu", none, none, none])
    add("mcu chip board", ["CIRCUIT", "mcu", none, none, none])
    add("place fet q1 at 12 16", ["PCB_ADD", "fet", "q1", "12", "16"])
    add("place diode d1 at 20 16", ["PCB_ADD", "diode", "d1", "20", "16"])
    add("place led d2 at 28 16", ["PCB_ADD", "led", "d2", "28", "16"])
    add("place inductor l1 at 30 16", ["PCB_ADD", "ind", "l1", "30", "16"])
    add("place transistor q1 at 12 24", ["PCB_ADD", "bjt", "q1", "12", "24"])
    add("design an inverter from transistors", ["CIRCUIT", "inv", none, none, none])
    add("nand cell from transistors", ["CIRCUIT", "nand", none, none, none])
    add("nor cell from transistors", ["CIRCUIT", "nor", none, none, none])
    add("transistor chip cell", ["CIRCUIT", "inv", none, none, none])
    volts = ["10", "12", "16", "20", "24", "30", "40", "50", "60", "80", "90", "100", "150", "170"]
    for volts_n in volts:
        add(f"creepage at {volts_n} v", ["GEM", "creepage", volts_n, none, none])
        add(f"clearance at {volts_n} v", ["GEM", "creepage", volts_n, none, none])
    for amps in ("1", "2", "3", "4", "5", "6", "8", "10"):
        add(f"width for {amps} a trace", ["GEM", "width", amps, none, none])
        add(f"trace current {amps} a", ["GEM", "width", amps, none, none])
    for amps in ("1", "2", "5", "10"):
        add(f"via for {amps} a", ["VIA", amps, none, none, none])
        add(f"size via {amps} amps", ["VIA", amps, none, none, none])
    for length, width in (("80", "50"), ("100", "60"), ("150", "80"), ("170", "100"), ("200", "150"), ("244", "170"), ("305", "200")):
        add(f"board outline {length} by {width}", ["OUTLINE", length, width, none, none])
        add(f"set outline {length} {width}", ["OUTLINE", length, width, none, none])
    for phrase, kind in (
        ("switching fet circuit", "switch"),
        ("fet switch circuit", "switch"),
        ("plc board", "plc"),
        ("pac board", "pac"),
        ("mcu board circuit", "mcu"),
        ("inverter cell", "inv"),
        ("nand from transistors", "nand"),
        ("nor from transistors", "nor"),
        ("transistor cell", "inv"),
    ):
        add(phrase, ["CIRCUIT", kind, none, none, none])
    for phrase in ("autoroute all", "route the board", "route all nets", "rip routes"):
        kind = "rip" if phrase.startswith("rip") else "all"
        add(phrase, ["ROUTE", kind, none, none, none])
    edits = ("r1", "c1", "u1", "q1", "j1", "d1", "l1")
    for ref in edits:
        add(f"delete {ref}", ["DEL", ref, none, none, none])
        add(f"remove {ref}", ["DEL", ref, none, none, none])
        add(f"erase {ref}", ["DEL", ref, none, none, none])
        add(f"move {ref} to 10 12", ["MOVE", ref, "10", "12", none])
        add(f"move {ref} to 20 16", ["MOVE", ref, "20", "16", none])
        add(f"rotate {ref} 90", ["ROT", ref, "90", none, none])
        add(f"rotate {ref} 180", ["ROT", ref, "180", none, none])
        add(f"rotate {ref} 270", ["ROT", ref, "270", none, none])
        add(f"flip {ref}", ["FLIP", ref, none, none, none])
        add(f"mirror {ref}", ["FLIP", ref, none, none, none])
        add(f"find {ref}", ["FIND", ref, none, none, none])
    add("copy r1 to r2", ["COPY", "r1", "r2", none, none])
    add("copy c1 to c2", ["COPY", "c1", "c2", none, none])
    add("copy u1 to u2", ["COPY", "u1", "u2", none, none])
    add("swap r1 and c1", ["SWAP", "r1", "c1", none, none])
    add("swap u1 and u2", ["SWAP", "u1", "u2", none, none])
    add("swap q1 and d1", ["SWAP", "q1", "d1", none, none])
    parts = (
        ("res", "resistor", "r1"),
        ("cap", "capacitor", "c1"),
        ("ind", "inductor", "l1"),
        ("diode", "diode", "d1"),
        ("led", "led", "d2"),
        ("bjt", "transistor", "q1"),
        ("fet", "fet", "q1"),
        ("mcu", "mcu", "u1"),
        ("soic", "soic", "u1"),
        ("qfn", "qfn", "u2"),
        ("tqfp", "tqfp", "u3"),
        ("bga", "bga", "u1"),
        ("dip", "dip", "u2"),
        ("sot", "sot", "q1"),
        ("qfp", "qfp", "u3"),
        ("conn", "connector", "j1"),
        ("crystal", "crystal", "y1"),
    )
    for pkg, word, ref in parts:
        add(f"place a {word} {ref} at 10 12", ["PCB_ADD", pkg, ref, "10", "12"])
        add(f"mount {word} {ref} at 20 16", ["PCB_ADD", pkg, ref, "20", "16"])
    for net in ("vcc", "vdd", "vss", "tx", "rx", "clk", "sda", "scl", "mosi", "miso", "can"):
        add(f"connect {net} from r1 to c1", ["PCB_NET", net, "r1", "c1", none])
        add(f"tie {net} between u1 and r1", ["PCB_NET", net, "u1", "r1", none])
    for phrase in (
        "undo",
        "redo",
        "zoom in",
        "pan the view",
        "lock the parts",
        "align the parts",
        "fanout the bga",
        "add teardrops",
        "stitch the vias",
        "tune the lengths",
        "import an eda file",
    ):
        add(phrase, ["HELP", none, none, none, none])
    add("check the board", ["PCB_DRC", none, none, none, none])
    add("calculate trace width for 2 a", ["GEM", "width", "2", none, none])
    add("rip up the routes", ["ROUTE", "rip", none, none, none])
    add("export the gerbers", ["PCB_FLOW", none, none, none, none])
    add("show me the board", ["PCB_STATUS", none, none, none, none])
    from py.si.computer import ROWS as computer_rows
    from py.si.power import ROWS as power_rows
    from py.si.robot import ROWS as robot_rows
    from py.si.sensor import ROWS as sensor_rows

    catalog = [
        ("POWER", power_rows),
        ("ROBOT", robot_rows),
        ("COMPUTER", computer_rows),
        ("SENSOR", sensor_rows),
    ]
    owners: dict[str, list[tuple[str, object]]] = {}
    for intent, group in catalog:
        for row in group:
            for alias in row.aliases:
                owners.setdefault(alias, []).append((intent, row))
    prefix = {"POWER": "power", "ROBOT": "robot", "COMPUTER": "computer", "SENSOR": "sensor"}
    for intent, group in catalog:
        for row in group:
            alias = row.aliases[0]
            prompt = alias if len(owners.get(alias, [])) == 1 else f"{prefix[intent]} {alias}"
            add(prompt, [intent, row.family, row.id, none, none])
    for phrase in (
        "design the sonar panel booster",
        "design a complete sonar panel booster",
        "design sonar panel booster voltage and current",
        "make a sonar booster",
        "sonar panel booster",
        "design the booster",
        "design a boost converter",
        "i need a boost",
        "design the power stage",
        "build the sonar panel",
        "sonar booster without ratings",
        "design the converter",
        "what booster should i use",
        "size the sonar booster",
        "complete sonar panel booster",
    ):
        add(phrase, ["ASK", "vout", none, none, none])
    return rows


def split_rows(rows: list[tuple[str, list[str]]], rng: random.Random):
    grouped: dict[tuple[str, ...], list[tuple[str, list[str]]]] = {}
    for prompt, target in rows:
        grouped.setdefault(tuple(target), []).append((prompt, target))
    compositional = {"PCB_ADD", "PCB_NET", "CAD_SKETCH", "SCH_ADD", "SCH_WIRE"}
    train: list[tuple[str, list[str]]] = []
    test: list[tuple[str, list[str]]] = []
    for key, items in grouped.items():
        if key[0] in compositional and rng.random() < 0.12:
            test.extend(items)
        elif key[0] in compositional:
            train.extend(items)
        else:
            train.extend(items * 12)
            test.append(items[0])
    return train, test


def to_ids(prompt: str, target: list[str], stoi: dict[str, int]) -> tuple[list[int], int]:
    from py.si.engine import tokenize

    words = tokenize(prompt)[:18]
    ids = [stoi["<bos>"]] + encode_words(words, stoi) + [stoi["<sep>"]]
    sep_at = len(ids) - 1
    ids += [stoi[t] for t in target] + [stoi["<eos>"]]
    return ids[:BLOCK], sep_at


def batchify(pairs, stoi, pad):
    encoded = [to_ids(p, t, stoi) for p, t in pairs]
    width = max(len(ids) for ids, _ in encoded)
    x = torch.full((len(encoded), width), pad, dtype=torch.long)
    y = torch.full((len(encoded), width), -100, dtype=torch.long)
    for i, (ids, sep_at) in enumerate(encoded):
        x[i, : len(ids)] = torch.tensor(ids)
        # predict every token after sep (the program)
        for j in range(sep_at, len(ids) - 1):
            y[i, j] = ids[j + 1]
    return x, y


@torch.no_grad()
def predict(model: GPT, prompt: str, vocab: list[str], stoi: dict[str, int], device, raw: bool = False) -> list[str]:
    from py.si.engine import tokenize
    from py.si.computer import tokens as computer_tokens
    from py.si.power import tokens as power_tokens
    from py.si.robot import tokens as robot_tokens
    from py.si.sensor import tokens as sensor_tokens

    words = tokenize(prompt)[:18]
    ids = [stoi["<bos>"]] + encode_words(words, stoi) + [stoi["<sep>"]]
    intent_ids = [stoi[i] for i in INTENTS]
    slot_words = PKGS + REFS + NETS + NUMS + DISCIPLINES + INDUSTRIES + BOARDS + SLOTS + power_tokens() + robot_tokens() + computer_tokens() + sensor_tokens() + ["<none>"]
    slot_ids = [stoi[t] for t in slot_words if t in stoi]
    for step in range(6):
        window = ids[-BLOCK:]
        idx = torch.tensor([window], device=device)
        logits = model(idx)[0, -1]
        allowed = intent_ids if step == 0 else slot_ids if step < 5 else [stoi["<eos>"]]
        mask = torch.full_like(logits, -1e9)
        mask[allowed] = logits[allowed]
        nxt = int(mask.argmax())
        ids.append(nxt)
        if nxt == stoi["<eos>"]:
            break
    sep = ids.index(stoi["<sep>"])
    out = []
    for i in ids[sep + 1 :]:
        tok = vocab[i]
        if tok == "<eos>":
            break
        out.append(tok)
    while len(out) < 5:
        out.append("<none>")
    if raw:
        return out[:5]
    return bind_slots(words, out[:5])


def _discipline(words: list[str]) -> str | None:
    if "integrity" in words and "signal" in words:
        return "si"
    if "integrity" in words and "power" in words:
        return "pi"
    if "decoupling" in words or "caps" in words or "decap" in words:
        return "decap"
    if "boot" in words:
        return "boot"
    if "reset" in words:
        return "reset"
    if "clock" in words:
        return "clock"
    if "thermal" in words:
        return "thermal"
    if "pinout" in words or "pins" in words or "pin" in words:
        return "pin"
    if "io" in words:
        return "io"
    if "power" in words:
        return "power"
    if "si" in words:
        return "si"
    if "pi" in words:
        return "pi"
    return None


def _industry(words: list[str]) -> str | None:
    if "quantum" in words or "cryogenic" in words:
        return "quantum"
    if "satellite" in words or ("space" in words and "aerospace" not in words):
        return "space"
    if "aerospace" in words or "flight" in words:
        return "aerospace"
    if "defense" in words or "defence" in words:
        return "defense"
    if "railway" in words or "transit" in words:
        return "rail"
    if "oil" in words or "drilling" in words:
        return "oil"
    if "agriculture" in words or "agri" in words or "agrotech" in words:
        return "agri"
    if "audio" in words or "broadcast" in words or "broadcasting" in words:
        return "audio"
    if "computing" in words or "datacenter" in words or ("data" in words and "center" in words):
        return "compute"
    if "consumer" in words:
        return "consumer"
    if "industrial" in words or "manufacturing" in words or "factory" in words:
        return "industrial"
    if "iot" in words or "wearable" in words or "wearables" in words:
        return "iot"
    if "lighting" in words or "opto" in words or "optoelectronics" in words:
        return "light"
    if "solar" in words or "photovoltaic" in words or "energy" in words:
        return "energy"
    if "instrument" in words or "instrumentation" in words or "scientific" in words:
        return "instrument"
    if "security" in words or ("access" in words and "control" in words):
        return "security"
    if "telecom" in words or "telecommunication" in words or "telecommunications" in words or ("rf" in words and "modem" not in words):
        return "telecom"
    if "marine" in words or "shipboard" in words or "ship" in words:
        return "marine"
    if "medical" in words or "patient" in words or "healthcare" in words:
        return "medical"
    if "robot" in words or "robotics" in words or "automation" in words:
        return "robot"
    if "automotive" in words or "automatic" in words or "car" in words or "vehicle" in words:
        return "automotive"
    return None


def _board(words: list[str]) -> str | None:
    if "energy" in words:
        return None
    if "bms" in words or "battery" in words:
        return "bms"
    if "motor" in words:
        return "motor"
    if "gpu" in words:
        return "gpu"
    if "modem" in words or "network" in words:
        return "modem"
    if "tiny" in words or "module" in words:
        return "tiny"
    if "cpu" in words:
        return "cpu"
    if "motherboard" in words:
        return "motherboard"
    if "power" in words:
        return "power"
    return None


def board_program(words: list[str]) -> list[str] | None:
    """Longest catalog name wins. A tie is left to the model."""
    from py.si.computer import find as find_computer
    from py.si.power import find as find_power
    from py.si.robot import find as find_robot
    from py.si.sensor import find as find_sensor

    text = " ".join(words)
    padded = f" {text} "
    hits = []
    for intent, finder in (
        ("POWER", find_power),
        ("ROBOT", find_robot),
        ("COMPUTER", find_computer),
        ("SENSOR", find_sensor),
    ):
        row = finder(text)
        if row is None:
            continue
        span = max((len(alias) for alias in row.aliases if f" {alias} " in padded), default=0)
        hits.append((span, intent, row))
    if not hits:
        return None
    best = max(item[0] for item in hits)
    top = [item for item in hits if item[0] == best]
    if len(top) != 1:
        return None
    _, intent, row = top[0]
    return [intent, row.family, row.id, "<none>", "<none>"]


def bind_slots(words: list[str], prog: list[str]) -> list[str]:
    """Keep the model's intent. Fill arguments from names and numbers actually said."""
    intent = prog[0]
    pkgs = []
    for word in words:
        if word in PKGS and word not in pkgs:
            pkgs.append(word)
        mapped = {
            "transistor": "bjt",
            "mosfet": "fet",
            "inductor": "ind",
            "coil": "ind",
            "resistor": "res",
            "capacitor": "cap",
            "connector": "conn",
            "crystal": "crystal",
            "soic": "soic",
            "qfp": "qfp",
            "qfn": "qfn",
            "tqfp": "tqfp",
            "bga": "bga",
            "dip": "dip",
            "sip": "sip",
            "sop": "sop",
            "ssop": "ssop",
            "tsop": "tsop",
            "dfn": "dfn",
            "lga": "lga",
            "wlcsp": "wlcsp",
            "pga": "pga",
            "sot": "sot",
        }.get(word)
        if mapped and mapped not in pkgs:
            pkgs.append(mapped)
    refs = [w for w in words if w in REFS]
    net_word = {
        "ground": "gnd",
        "vcc": "vcc",
        "vdd": "vdd",
        "vss": "vss",
        "tx": "tx",
        "rx": "rx",
        "clk": "clk",
        "sda": "sda",
        "scl": "scl",
        "mosi": "mosi",
        "miso": "miso",
        "sck": "sck",
        "cs": "cs",
        "can": "can",
        "5v": "5v",
    }
    nets = []
    for word in words:
        name = net_word.get(word, word if word in NETS else None)
        if name and name not in nets:
            nets.append(name)
    nums = [w for w in words if w in set(NUMS)]
    none = "<none>"
    industry = _industry(words)
    board = _board(words)
    if "datasheet" in words:
        return ["DATASHEET", none, none, none, none]
    if any(word in words for word in ("undo", "redo", "zoom", "pan", "lock", "unlock", "align", "fanout", "teardrop", "teardrops", "stitch", "tune")):
        return ["HELP", none, none, none, none]
    if "import" in words and "eda" in words:
        return ["HELP", none, none, none, none]
    if any(word in words for word in ("delete", "erase")) or ("remove" in words and "mask" not in words):
        return ["DEL", refs[0] if refs else "r1", none, none, none]
    if "rotate" in words:
        spoken = [word for word in words if word in {"0", "45", "90", "180", "270"}]
        return ["ROT", refs[0] if refs else "u1", spoken[0] if spoken else "90", none, none]
    if "move" in words and refs:
        spoken = [word for word in words if word.isdigit()]
        return ["MOVE", refs[0], spoken[0] if spoken else "10", spoken[1] if len(spoken) > 1 else "12", none]
    if "copy" in words and len(refs) >= 2:
        return ["COPY", refs[0], refs[1], none, none]
    if "swap" in words and len(refs) >= 2:
        return ["SWAP", refs[0], refs[1], none, none]
    if "flip" in words or "mirror" in words:
        return ["FLIP", refs[0] if refs else "u1", none, none, none]
    if "find" in words and refs:
        return ["FIND", refs[0], none, none, none]
    boarded = board_program(words)
    if boarded:
        return boarded
    if "rip" in words:
        return ["ROUTE", "rip", none, none, none]
    if "autoroute" in words or ("route" in words and ("board" in words or "nets" in words or "all" in words)):
        return ["ROUTE", "all", none, none, none]
    if "route" in words and nets:
        return ["ROUTE", nets[0], none, none, none]
    if "place" not in words and len(nums) < 2:
        if "nand" in words:
            return ["CIRCUIT", "nand", none, none, none]
        if "nor" in words:
            return ["CIRCUIT", "nor", none, none, none]
        if "inverter" in words or ("transistor" in words and ("cell" in words or "chip" in words)):
            return ["CIRCUIT", "inv", none, none, none]
    if "plc" in words:
        return ["CIRCUIT", "plc", none, none, none]
    if "pac" in words:
        return ["CIRCUIT", "pac", none, none, none]
    if "switching" in words or ("switch" in words and ("fet" in words or "speed" in words or "circuit" in words)):
        return ["CIRCUIT", "switch", none, none, none]
    if "mcu" in words and ("board" in words or "chip" in words) and "place" not in words and len(nums) < 2:
        return ["CIRCUIT", "mcu", none, none, none]
    if "trace" in words and ("width" in words or "current" in words):
        spoken = [w for w in words if w.isdigit()]
        return ["GEM", "width", spoken[0] if spoken else "1", none, none]
    if "filter" in words or "cutoff" in words:
        return ["GEM", "filter", none, none, none]
    if "thermal" in words and ("loss" in words or "dissipation" in words):
        spoken = [w for w in words if w.isdigit()]
        return ["GEM", "thermal", spoken[0] if spoken else "1", none, none]
    if "kicad" in words:
        return ["GEM", "kicad", none, none, none]
    if "allegro" in words or ("skill" in words and "ipc" not in words):
        return ["GEM", "skill", none, none, none]
    if "altium" in words:
        return ["GEM", "altium", none, none, none]
    if "replacement" in words or ("drop" in words and "in" in words):
        return ["GEM", "replace", none, none, none]
    if "creepage" in words or ("clearance" in words and "minimum" not in words):
        spoken = [w for w in words if w.isdigit()]
        return ["GEM", "creepage", spoken[0] if spoken else "50", none, none]
    if "emi" in words or "emc" in words:
        return ["GEM", "emi", none, none, none]
    if "bom" in words and "table" in words:
        return ["GEM", "table", none, none, none]
    if "feature" in words and ("audit" in words or "list" in words):
        return ["AUDIT", none, none, none, none]
    if "stripline" in words:
        spoken = [w for w in words if w in {"50", "90", "100"}]
        return ["GEM", "strip", spoken[0] if spoken else "50", none, none]
    if "jlcpcb" in words or ("fab" in words and any(w.startswith("limit") for w in words)) or ("capability" in words and "sheet" in words):
        return ["GEM", "fab", none, none, none]
    if "annular" in words or ("via" in words and "pad" in words):
        spoken = [w for w in words if w.isdigit()]
        return ["GEM", "ring", spoken[0] if spoken else none, none, none]
    if "layers" in words:
        spoken = [w for w in words if w.isdigit()]
        return ["GEM", "layers", spoken[0] if spoken else none, none, none]
    if "copper" in words and "pour" not in words and ("oz" in words or "weight" in words or "half" in words or any(w.isdigit() for w in words)):
        if "half" in words:
            return ["GEM", "copper", "half", none, none]
        spoken = [w for w in words if w.isdigit()]
        return ["GEM", "copper", spoken[0] if spoken else "1", none, none]
    if "thickness" in words and "shell" not in words:
        if "standard" in words:
            return ["GEM", "thick", "standard", none, none]
        spoken = [w for w in words if w.isdigit()]
        return ["GEM", "thick", spoken[0] if spoken else "standard", none, none]
    if ("design" in words and "rules" in words) or "profile" in words:
        return ["GEM", "rules", none, none, none]
    if "ipc" in words or "jstd" in words or "std" in words:
        docs = [w for w in words if w.isdigit() and len(w) >= 3]
        grade = next((w for w in words if w in {"1", "2", "3"}), none)
        if "class" in words and grade != none:
            return ["IPC", grade, "class", none, none]
        if docs:
            return ["IPC", docs[0], "doc", none, none]
        return ["IPC", "all", none, none, none]
    if "ohm" in words or "impedance" in words:
        spoken = [w for w in words if w in {"50", "90", "100"}]
        return ["IMPEDANCE", spoken[0] if spoken else "50", none, none, none]
    if "pour" in words:
        return ["POUR", none, none, none, none]
    if "dfm" in words or "annular" in words:
        return ["DFM", none, none, none, none]
    if "via" in words:
        target = next((n for n in nums if n in {"1", "2", "5", "10"}), "1")
        return ["VIA", target, none, none, none]
    if "differential" in words or ("diff" in words and "pair" in words):
        return ["DIFF", nets[0] if nets else prog[1], none, none, none]
    if "chamfer" in words:
        return ["CAD_CHAMFER", nums[0] if nums else prog[1], none, none, none]
    if "shell" in words or ("wall" in words and "shell" not in words and "cad" in words):
        return ["CAD_SHELL", nums[0] if nums else prog[1], none, none, none]
    if "handle" in words or "cover" in words or "covet" in words:
        kind = _industry(words) or _board(words)
        if kind and "all" not in words:
            return ["HANDLE", kind, none, none, none]
        return ["HANDLE", "all", none, none, none]
    if "outline" in words:
        raw = [w for w in words if w.isdigit()]
        return ["OUTLINE", raw[0] if raw else prog[1], raw[1] if len(raw) > 1 else prog[2], none, none]
    if "stackup" in words or "stack" in words:
        return ["FAB_STACK", none, none, none, none]
    if "schematic" in words and pkgs and refs and not nets:
        return ["SCH_ADD", pkgs[0], refs[0], none, none]
    if ("wire" in words and "from" in words) or ("schematic" in words and nets):
        return ["SCH_WIRE", nets[0] if nets else prog[1], refs[0] if refs else prog[2], refs[1] if len(refs) > 1 else prog[3], none]
    if "3d" in words or "viewer" in words:
        return ["VIEW_3D", none, none, none, none]
    if "industry" in words and ("rules" in words or "class" in words or "check" in words):
        return ["CLASS", none, none, none, none]
    if "class" in words and "check" in words and "ipc" not in words:
        return ["CLASS", none, none, none, none]
    if "design" in words and "check" in words:
        return ["PCB_DRC", none, none, none, none]
    if board and "check" not in words:
        return ["BOARD", board, none, none, none]
    if industry and not board and "check" not in words:
        return ["INDUSTRY", industry, none, none, none]
    if "footprint" in words or "assign" in words:
        return ["FP_ASSIGN", refs[0] if refs else prog[1], none, none, none]
    if "erc" in words or "electrical" in words or ("check" in words and "schematic" in words):
        return ["SCH_ERC", none, none, none, none]
    if "drc" in words or ("check" in words and "board" in words and "class" not in words) or ("rule" in words and "check" in words and "design" not in words and "industry" not in words):
        return ["PCB_DRC", none, none, none, none]
    if "pick" in words or "centroid" in words or ("asm" in words and "pos" in words):
        return ["ASM_POS", none, none, none, none]
    if "bom" in words or "bill" in words:
        return ["ASM_BOM", none, none, none, none]
    if "fabrication" in words or ("fab" in words and "gerber" in words):
        return ["FAB_PACK", none, none, none, none]
    if "flow" in words or "finish" in words or "gerber" in words or "gerbers" in words or ("release" in words and "pcb" in words):
        return ["PCB_FLOW", none, none, none, none]
    if "transient" in words or ("sim" in words and "tran" in words):
        return ["SIM_TRAN", none, none, none, none]
    if "dc" in words or "operating" in words:
        return ["SIM_DC", none, none, none, none]
    if "extrude" in words or "thicken" in words:
        return ["CAD_EXTRUDE", nums[0] if nums else prog[1], none, none, none]
    if "fillet" in words or ("round" in words and "edges" in words):
        return ["CAD_FILLET", nums[0] if nums else prog[1], none, none, none]
    if "drill" in words or "hole" in words or "bore" in words:
        return ["CAD_HOLE", nums[0] if nums else prog[1], none, none, none]
    if "sketch" in words or "plate" in words or "rectangle" in words:
        return ["CAD_SKETCH", nums[0] if nums else prog[1], nums[1] if len(nums) > 1 else prog[2], none, none]
    if "mass" in words or "heavy" in words or "weight" in words:
        return ["CAD_MASS", none, none, none, none]
    if ("cad" in words and "status" in words) or "solid" in words or ("describe" in words and "part" in words):
        return ["CAD_STATUS", none, none, none, none]
    if "status" in words or ("show" in words and "board" in words) or ("list" in words and "parts" in words) or ("what" in words and "pcb" in words):
        return ["PCB_STATUS", none, none, none, none]
    if "help" in words or "commands" in words or ("how" in words and "start" in words) or ("what" in words and "can" in words):
        return ["HELP", none, none, none, none]
    if "symbol" in words and pkgs:
        return ["SCH_ADD", pkgs[0], refs[0] if refs else prog[2], none, none]
    if "place" in words and ("sheet" in words or "symbols" in words) and len(nums) < 2:
        return ["PLACE", none, none, none, none]
    if "connect" in words and "schematic" not in words and (nets or refs):
        return ["PCB_NET", nets[0] if nets else prog[1], refs[0] if refs else prog[2], refs[1] if len(refs) > 1 else prog[3], none]
    if ("wire" in words and "on" in words) or "tie" in words or ("net" in words and "schematic" not in words and (nets or refs)):
        return ["PCB_NET", nets[0] if nets else prog[1], refs[0] if refs else prog[2], refs[1] if len(refs) > 1 else prog[3], none]
    if len(nums) >= 2 and pkgs and refs and "schematic" not in words:
        return ["PCB_ADD", pkgs[0], refs[0], nums[0], nums[1]]
    kind = _discipline(words)
    if kind and ("check" in words or "caps" in words or "integrity" in words or "strap" in words or "levels" in words or "discipline" in words):
        return ["CHIP", kind, none, none, none]
    if intent == "PCB_ADD":
        return [
            intent,
            pkgs[0] if pkgs else prog[1],
            refs[0] if refs else prog[2],
            nums[0] if nums else prog[3],
            nums[1] if len(nums) > 1 else prog[4],
        ]
    if intent == "PCB_NET":
        return [
            intent,
            nets[0] if nets else prog[1],
            refs[0] if refs else prog[2],
            refs[1] if len(refs) > 1 else prog[3],
            none,
        ]
    if intent == "CAD_SKETCH":
        return [intent, nums[0] if nums else prog[1], nums[1] if len(nums) > 1 else prog[2], none, none]
    if intent in {"CAD_EXTRUDE", "CAD_HOLE", "CAD_FILLET", "CAD_CHAMFER", "CAD_SHELL"}:
        return [intent, nums[0] if nums else prog[1], none, none, none]
    if intent == "IMPEDANCE":
        spoken = [w for w in words if w in {"50", "90", "100"}]
        target = spoken[0] if spoken else (prog[1] if prog[1] in {"50", "90", "100"} else "50")
        return [intent, target, none, none, none]
    if intent == "VIA":
        target = next((n for n in nums if n in {"1", "2", "5", "10"}), prog[1] if prog[1] in {"1", "2", "5", "10"} else "1")
        return [intent, target, none, none, none]
    if intent == "DIFF":
        return [intent, nets[0] if nets else prog[1], none, none, none]
    if intent == "SCH_ADD":
        return [intent, pkgs[0] if pkgs else prog[1], refs[0] if refs else prog[2], none, none]
    if intent == "SCH_WIRE":
        return [intent, nets[0] if nets else prog[1], refs[0] if refs else prog[2], refs[1] if len(refs) > 1 else prog[3], none]
    if intent == "FP_ASSIGN":
        return [intent, refs[0] if refs else prog[1], none, none, none]
    if intent == "CHIP":
        kind = _discipline(words) or (prog[1] if prog[1] in DISCIPLINES else "pin")
        return [intent, kind, none, none, none]
    if intent == "INDUSTRY":
        kind = _industry(words) or (prog[1] if prog[1] in INDUSTRIES else "automotive")
        return [intent, kind, none, none, none]
    if intent == "BOARD":
        kind = _board(words) or (prog[1] if prog[1] in BOARDS else "tiny")
        return [intent, kind, none, none, none]
    return [intent, none, none, none, none]


def program_to_action(prog: list[str]) -> dict:
    intent = prog[0] if prog else "HELP"
    if intent == "ASK":
        return {"op": "ask_spec"}
    a = prog[1] if len(prog) > 1 else "<none>"
    b = prog[2] if len(prog) > 2 else "<none>"
    c = prog[3] if len(prog) > 3 else "<none>"
    d = prog[4] if len(prog) > 4 else "<none>"

    def num(tok: str):
        try:
            return float(tok)
        except ValueError:
            return None

    if intent == "PCB_ADD" and a != "<none>" and b != "<none>" and num(c) is not None and num(d) is not None:
        return {"op": "pcb_add", "pkg": a, "ref": b, "x": num(c), "y": num(d)}
    if intent == "PCB_NET" and a != "<none>":
        return {"op": "pcb_net", "name": a, "a": b, "b": c}
    if intent == "PCB_FLOW":
        return {"op": "pcb_flow"}
    if intent == "PCB_DRC":
        return {"op": "pcb_drc"}
    if intent == "PCB_STATUS":
        return {"op": "pcb_status"}
    if intent == "CAD_SKETCH" and num(a) is not None and num(b) is not None:
        return {"op": "cad_sketch", "length": num(a), "width": num(b)}
    if intent == "CAD_EXTRUDE" and num(a) is not None:
        return {"op": "cad_extrude", "thickness": num(a)}
    if intent == "CAD_HOLE" and num(a) is not None:
        return {"op": "cad_hole", "diameter": num(a)}
    if intent == "CAD_FILLET" and num(a) is not None:
        return {"op": "cad_fillet", "radius": num(a)}
    if intent == "CAD_MASS":
        return {"op": "cad_mass"}
    if intent == "CAD_STATUS":
        return {"op": "cad_status"}
    if intent == "SCH_ADD" and a != "<none>" and b != "<none>":
        return {"op": "sch_add", "pkg": a, "ref": b}
    if intent == "SCH_WIRE" and a != "<none>":
        return {"op": "sch_wire", "name": a, "a": b, "b": c}
    if intent == "SCH_ERC":
        return {"op": "sch_erc"}
    if intent == "FP_ASSIGN" and a != "<none>":
        return {"op": "fp_assign", "ref": a}
    if intent == "SIM_DC":
        return {"op": "sim_dc"}
    if intent == "SIM_TRAN":
        return {"op": "sim_tran"}
    if intent == "VIEW_3D":
        return {"op": "view_3d"}
    if intent == "FAB_PACK":
        return {"op": "fab_gerber"}
    if intent == "FAB_STACK":
        return {"op": "fab_stack"}
    if intent == "ASM_BOM":
        return {"op": "asm_bom"}
    if intent == "ASM_POS":
        return {"op": "asm_pos"}
    if intent == "CHIP":
        return {"op": "chip_check", "kind": a if a != "<none>" else "pin"}
    if intent == "INDUSTRY":
        return {"op": "set_industry", "kind": a if a != "<none>" else "automotive"}
    if intent == "BOARD":
        return {"op": "set_board", "kind": a if a != "<none>" else "tiny"}
    if intent == "CLASS":
        return {"op": "industry_check"}
    if intent == "DATASHEET":
        return {"op": "datasheet_rebuild"}
    if intent == "PLACE":
        return {"op": "place_sheet"}
    if intent == "IMPEDANCE":
        return {"op": "impedance", "ohms": num(a) or 50}
    if intent == "POUR":
        return {"op": "pour"}
    if intent == "DFM":
        return {"op": "dfm"}
    if intent == "VIA":
        return {"op": "via", "amps": num(a) or 1}
    if intent == "DIFF":
        return {"op": "diff", "name": a if a != "<none>" else "usb"}
    if intent == "CAD_CHAMFER" and num(a) is not None:
        return {"op": "cad_chamfer", "size": num(a)}
    if intent == "CAD_SHELL" and num(a) is not None:
        return {"op": "cad_shell", "wall": num(a)}
    if intent == "IPC":
        if b == "class" and a in {"1", "2", "3"}:
            return {"op": "set_ipc", "kind": a}
        if a.isdigit() and a not in {"1", "2", "3"}:
            return {"op": "ipc_check", "doc": a}
        return {"op": "ipc_check"}
    if intent == "GEM":
        return {"op": "desk", "kind": a if a != "<none>" else "", "value": num(b), "name": b if b != "<none>" else ""}
    if intent == "AUDIT":
        return {"op": "feature_audit"}
    if intent == "ROUTE":
        return {"op": "autoroute", "which": a if a != "<none>" else "all"}
    if intent == "CIRCUIT":
        if a in {"inv", "nand", "nor"}:
            return {"op": "design_cell", "kind": a}
        return {"op": "build_circuit", "kind": a if a != "<none>" else "mcu"}
    if intent == "FIND" and a != "<none>":
        return {"op": "pcb_find", "ref": a}
    if intent == "DEL" and a != "<none>":
        return {"op": "pcb_delete", "ref": a}
    if intent == "MOVE" and a != "<none>" and num(b) is not None and num(c) is not None:
        return {"op": "pcb_move", "ref": a, "x": num(b), "y": num(c)}
    if intent == "ROT" and a != "<none>":
        return {"op": "pcb_rotate", "ref": a, "angle": num(b) if num(b) is not None else 90}
    if intent == "COPY" and a != "<none>" and b != "<none>":
        return {"op": "pcb_copy", "ref": a, "to": b}
    if intent == "SWAP" and a != "<none>" and b != "<none>":
        return {"op": "pcb_swap", "a": a, "b": b}
    if intent == "FLIP" and a != "<none>":
        return {"op": "pcb_flip", "ref": a}
    if intent == "POWER":
        return {"op": "power_select", "kind": b if b != "<none>" else a}
    if intent == "ROBOT":
        return {"op": "robot_select", "kind": b if b != "<none>" else a}
    if intent == "COMPUTER":
        return {"op": "computer_select", "kind": b if b != "<none>" else a}
    if intent == "SENSOR":
        return {"op": "sensor_select", "kind": b if b != "<none>" else a}
    if intent == "HANDLE":
        if a in INDUSTRIES:
            return {"op": "handle_industry", "kind": a}
        if a in BOARDS:
            return {"op": "handle_board", "kind": a}
        return {"op": "handle_all"}
    if intent == "OUTLINE" and num(a) is not None and num(b) is not None:
        return {"op": "set_outline", "length": num(a), "width": num(b)}
    return {"op": "help"}


def train() -> dict:
    rng = random.Random(7)
    vocab = build_vocab()
    stoi = stoi_of(vocab)
    rows = samples(rng)
    train_rows, test_rows = split_rows(rows, rng)
    rng.shuffle(test_rows)
    device = torch.device("cpu")
    torch.set_num_threads(4)
    model = GPT(len(vocab)).to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=0.01)
    pad = stoi["<pad>"]
    best = {"acc": 0.0, "boards": 0.0, "epoch": 0}
    model.train()
    board_rows = [row for row in test_rows if row[1][0] in {"POWER", "ROBOT", "COMPUTER", "SENSOR"}]
    for epoch in range(1, 5):
        rng.shuffle(train_rows)
        total = 0.0
        seen = 0
        for i in range(0, len(train_rows), 48):
            chunk = train_rows[i : i + 48]
            x, y = batchify(chunk, stoi, pad)
            x, y = x.to(device), y.to(device)
            logits = model(x)
            loss = F.cross_entropy(logits.view(-1, logits.size(-1)), y.view(-1), ignore_index=-100)
            opt.zero_grad()
            loss.backward()
            opt.step()
            total += float(loss.detach()) * len(chunk)
            seen += len(chunk)
        acc = eval_acc(model, test_rows, vocab, stoi, device, raw=True, limit=10_000)
        boards = eval_acc(model, board_rows, vocab, stoi, device, raw=True, limit=10_000)
        loss_now = total / max(1, seen)
        print(f"epoch {epoch} loss {loss_now:.3f} heldout {acc:.3f} boards {boards:.3f}", flush=True)
        if (boards, acc) >= (best["boards"], best["acc"]):
            best = {"acc": acc, "boards": boards, "epoch": epoch, "loss": loss_now}
            ROOT.mkdir(parents=True, exist_ok=True)
            tmp = WEIGHTS.with_suffix(".tmp")
            torch.save({"model": model.state_dict(), "vocab": vocab}, tmp)
            tmp.replace(WEIGHTS)
        if boards >= 0.99 and epoch >= 2:
            break
    model.load_state_dict(torch.load(WEIGHTS, map_location="cpu", weights_only=False)["model"])
    raw_acc = eval_acc(model, test_rows, vocab, stoi, device, raw=True, limit=10_000)
    bound_acc = eval_acc(model, test_rows, vocab, stoi, device, raw=False, limit=10_000)
    payload = {
        "heldout_exact": raw_acc,
        "heldout_bound": bound_acc,
        "epoch": best["epoch"],
        "boards": best.get("boards"),
        "train_rows": len(train_rows),
        "test_rows": len(test_rows),
        "params": sum(p.numel() for p in model.parameters()),
        "vocab": len(vocab),
        "width": N_EMBD,
        "layers": N_LAYER,
        "dropout": DROP,
    }
    META.write_text(json.dumps(payload, indent=2))
    print(json.dumps(payload), flush=True)
    return payload


@torch.no_grad()
def eval_acc(model, rows, vocab, stoi, device, limit: int = 240, raw: bool = True) -> float:
    model.eval()
    pick = rows if len(rows) <= limit else rows[:limit]
    ok = 0
    for prompt, target in pick:
        pred = predict(model, prompt, vocab, stoi, device, raw=raw)
        if pred[:5] == target:
            ok += 1
    model.train()
    return ok / max(1, len(pick))


def load():
    blob = torch.load(WEIGHTS, map_location="cpu", weights_only=False)
    vocab = blob["vocab"]
    model = GPT(len(vocab))
    model.load_state_dict(blob["model"])
    model.eval()
    meta = json.loads(META.read_text()) if META.exists() else {}
    return model, vocab, stoi_of(vocab), meta


def finetune() -> dict:
    """Add the ASK intent to the saved checkpoint without throwing away the trained weights."""
    rng = random.Random(7)
    vocab = build_vocab()
    stoi = stoi_of(vocab)
    blob = torch.load(WEIGHTS, map_location="cpu", weights_only=False)
    old_vocab = list(blob["vocab"])
    old = GPT(len(old_vocab))
    old.load_state_dict(blob["model"])
    model = GPT(len(vocab))
    with torch.no_grad():
        old_at = {tok: i for i, tok in enumerate(old_vocab)}
        for i, tok in enumerate(vocab):
            j = old_at.get(tok)
            if j is None:
                continue
            model.tok.weight[i].copy_(old.tok.weight[j])
            model.head.weight[i].copy_(old.head.weight[j])
        model.pos.load_state_dict(old.pos.state_dict())
        model.blocks.load_state_dict(old.blocks.state_dict())
        model.ln_f.load_state_dict(old.ln_f.state_dict())
    rows = samples(rng)
    train_rows, test_rows = split_rows(rows, rng)
    ask_rows = [row for row in train_rows if row[1][0] == "ASK"]
    # Keep the old skill, and show the new question rows much more often.
    train_rows = train_rows + ask_rows * 40
    device = torch.device("cpu")
    torch.set_num_threads(4)
    model = model.to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=2e-4, weight_decay=0.01)
    pad = stoi["<pad>"]
    board_rows = [row for row in test_rows if row[1][0] in {"POWER", "ROBOT", "COMPUTER", "SENSOR"}]
    ask_test = [row for row in test_rows if row[1][0] == "ASK"]
    best_boards = 0.0
    for epoch in range(1, 3):
        rng.shuffle(train_rows)
        model.train()
        total = 0.0
        seen = 0
        for i in range(0, len(train_rows), 48):
            chunk = train_rows[i : i + 48]
            x, y = batchify(chunk, stoi, pad)
            logits = model(x.to(device))
            loss = F.cross_entropy(logits.view(-1, logits.size(-1)), y.view(-1).to(device), ignore_index=-100)
            opt.zero_grad()
            loss.backward()
            opt.step()
            total += float(loss.detach()) * len(chunk)
            seen += len(chunk)
        boards = eval_acc(model, board_rows, vocab, stoi, device, raw=True, limit=10_000)
        asks = eval_acc(model, ask_test, vocab, stoi, device, raw=True, limit=10_000)
        print(f"finetune {epoch} loss {total / max(1, seen):.3f} boards {boards:.3f} ask {asks:.3f}", flush=True)
        if boards >= best_boards:
            best_boards = boards
            tmp = WEIGHTS.with_suffix(".tmp")
            torch.save({"model": model.state_dict(), "vocab": vocab}, tmp)
            tmp.replace(WEIGHTS)
    model.load_state_dict(torch.load(WEIGHTS, map_location="cpu", weights_only=False)["model"])
    raw_acc = eval_acc(model, test_rows, vocab, stoi, device, raw=True, limit=10_000)
    payload = {
        "heldout_exact": raw_acc,
        "heldout_bound": eval_acc(model, test_rows, vocab, stoi, device, raw=False, limit=10_000),
        "epoch": 3,
        "boards": best_boards,
        "train_rows": len(train_rows),
        "test_rows": len(test_rows),
        "params": sum(p.numel() for p in model.parameters()),
        "vocab": len(vocab),
        "width": N_EMBD,
        "layers": N_LAYER,
        "dropout": DROP,
        "ask": eval_acc(model, ask_test, vocab, stoi, device, raw=True, limit=10_000),
    }
    META.write_text(json.dumps(payload, indent=2))
    print(json.dumps(payload), flush=True)
    return payload


if __name__ == "__main__":
    train()
