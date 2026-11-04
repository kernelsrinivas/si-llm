"""Causal transformer that turns a PCB/CAD sentence into a command."""

from __future__ import annotations

import json
import random
from pathlib import Path

import torch
import torch.nn as nn
import torch.nn.functional as F

ROOT = Path("/workspace/model")
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
    "CAD_SKETCH",
    "CAD_EXTRUDE",
    "CAD_HOLE",
    "CAD_FILLET",
    "CAD_MASS",
    "CAD_STATUS",
    "HELP",
]
PKGS = ["usbc", "esp32", "ldo", "imu", "conn", "res", "cap", "mcu", "buck", "ant"]
REFS = ["j1", "u1", "u2", "u3", "r1", "c1", "l1"]
NETS = ["vbus", "gnd", "i2c", "sw", "usb", "3v3"]
NUMS = ["1", "2", "3", "4", "5", "6", "8", "10", "12", "16", "20", "24", "28", "30", "40", "50", "60", "80", "90"]
DISCIPLINES = ["pin", "decap", "power", "io", "clock", "reset", "boot", "thermal", "si", "pi"]
INDUSTRIES = ["automotive", "aerospace", "marine", "robot", "medical"]
BOARDS = ["tiny", "power", "bms", "motor", "cpu", "gpu", "modem", "motherboard"]
SPECIAL = ["<pad>", "<bos>", "<eos>", "<sep>", "<unk>", "<none>"]

BLOCK = 28
N_EMBD = 384
N_HEAD = 8
N_LAYER = 8


def build_vocab() -> list[str]:
    words = set(SPECIAL) | set(INTENTS) | set(PKGS) | set(REFS) | set(NETS) | set(NUMS) | set(DISCIPLINES) | set(INDUSTRIES) | set(BOARDS) | {"80", "100", "150", "170", "200", "244", "305", "all"}
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
        x = x + self.proj(y)
        h = self.ln2(x)
        x = x + self.fc2(F.gelu(self.fc1(h)))
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
    for pkg in PKGS:
        for ref in REFS:
            for x in NUMS:
                for y in rng.sample(NUMS, 3):
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
        for a in REFS:
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
    for pkg in PKGS:
        for ref in REFS[:4]:
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
    for ref in REFS:
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
        "robot": ["robot industry", "robot pcb", "robotics board"],
        "medical": ["medical industry", "medical pcb", "patient electronics"],
    }
    for kind, phrases in industry_phrases.items():
        for phrase in phrases:
            add(phrase, ["INDUSTRY", kind, none, none, none])
    board_phrases = {
        "tiny": ["tiny circuit", "small module", "tiny pcb"],
        "power": ["power electronics", "power electronics board"],
        "bms": ["bms board", "battery management"],
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

    words = tokenize(prompt)[:18]
    ids = [stoi["<bos>"]] + encode_words(words, stoi) + [stoi["<sep>"]]
    intent_ids = [stoi[i] for i in INTENTS]
    slot_ids = [stoi[t] for t in PKGS + REFS + NETS + NUMS + DISCIPLINES + INDUSTRIES + BOARDS + ["all", "100", "150", "170", "200", "244", "305", "<none>"] if t in stoi]
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
    if "aerospace" in words or "flight" in words:
        return "aerospace"
    if "marine" in words or "shipboard" in words or "ship" in words:
        return "marine"
    if "medical" in words or "patient" in words:
        return "medical"
    if "robot" in words or "robotics" in words:
        return "robot"
    if "automotive" in words or "automatic" in words or "car" in words or "vehicle" in words:
        return "automotive"
    return None


def _board(words: list[str]) -> str | None:
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


def bind_slots(words: list[str], prog: list[str]) -> list[str]:
    """Keep the model's intent. Fill arguments from names and numbers actually said."""
    intent = prog[0]
    pkgs = [w for w in words if w in PKGS]
    refs = [w for w in words if w in REFS]
    nets = [w for w in words if w in NETS]
    nums = [w for w in words if w in set(NUMS)]
    none = "<none>"
    industry = _industry(words)
    board = _board(words)
    if "datasheet" in words:
        return ["DATASHEET", none, none, none, none]
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
    if "drc" in words or ("rule" in words and "check" in words):
        return ["PCB_DRC", none, none, none, none]
    if "pick" in words or "centroid" in words or ("asm" in words and "pos" in words):
        return ["ASM_POS", none, none, none, none]
    if "bom" in words or "bill" in words:
        return ["ASM_BOM", none, none, none, none]
    if "fabrication" in words or ("fab" in words and "gerber" in words):
        return ["FAB_PACK", none, none, none, none]
    if "flow" in words or "finish" in words or "gerber" in words or ("release" in words and "pcb" in words):
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
    best = {"acc": 0.0, "epoch": 0}
    model.train()
    for epoch in range(1, 9):
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
        acc = eval_acc(model, test_rows, vocab, stoi, device, raw=True)
        print(f"epoch {epoch} loss {total / max(1, seen):.3f} heldout {acc:.3f}", flush=True)
        if acc >= best["acc"]:
            best = {"acc": acc, "epoch": epoch, "loss": total / max(1, seen)}
            ROOT.mkdir(parents=True, exist_ok=True)
            torch.save({"model": model.state_dict(), "vocab": vocab}, WEIGHTS)
        if acc >= 0.99:
            break
    model.load_state_dict(torch.load(WEIGHTS, map_location="cpu", weights_only=False)["model"])
    raw_acc = eval_acc(model, test_rows, vocab, stoi, device, raw=True, limit=10_000)
    bound_acc = eval_acc(model, test_rows, vocab, stoi, device, raw=False, limit=10_000)
    payload = {
        "heldout_exact": raw_acc,
        "heldout_bound": bound_acc,
        "epoch": best["epoch"],
        "train_rows": len(train_rows),
        "test_rows": len(test_rows),
        "params": sum(p.numel() for p in model.parameters()),
        "vocab": len(vocab),
        "width": N_EMBD,
        "layers": N_LAYER,
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


if __name__ == "__main__":
    train()
