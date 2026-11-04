"""Read a part datasheet and return only the packages it actually dimensions."""

from __future__ import annotations

import re
import zlib

_PKG = re.compile(
    r"\b(SOIC|SOP|SSOP|TSSOP|QFN|QFP|DFN|DIP)-(\d{1,3})\b|\b(SOT)-(23-5|23-6|223|89|23)\b|\b(0402|0603|0805|1206)\b",
    re.I,
)
_DIMS = re.compile(r"(\d+(?:\.\d+)?)\s*[x×]\s*(\d+(?:\.\d+)?)\s*[x×]\s*(\d+(?:\.\d+)?)", re.I)
_PITCH = re.compile(r"pitch\s*[:=]?\s*(\d+(?:\.\d+)?)", re.I)
_MPN = re.compile(r"part\s*(?:number|no\.?)\s*[:#]?\s*([A-Za-z0-9][A-Za-z0-9.\-]{2,})", re.I)
_PIN = re.compile(r"^\s*(\d{1,3})\s+([A-Za-z][A-Za-z0-9+\-]{0,15})\s*$")
_SOT_PINS = {"23": 3, "23-5": 5, "23-6": 6, "223": 4, "89": 3}
_CHIP_PINS = {"0402": 2, "0603": 2, "0805": 2, "1206": 2}


def pdf_text(data: bytes) -> str:
    """Pull a text layer out of a simple PDF. Scanned pages return nothing."""
    if not data.startswith(b"%PDF"):
        return ""
    pieces: list[str] = []
    for match in re.finditer(rb"stream\r?\n(.*?)endstream", data, re.S):
        raw = match.group(1).strip(b"\r\n")
        window = data[max(0, match.start() - 240) : match.start()]
        if b"FlateDecode" in window:
            try:
                raw = zlib.decompress(raw)
            except zlib.error:
                continue
        pieces.extend(_strings(raw))
    text = "\n".join(piece for piece in pieces if piece.strip())
    return text if len(text) >= 40 else ""


def _strings(raw: bytes) -> list[str]:
    found: list[str] = []
    for match in re.finditer(rb"\((?:\\.|[^\\)])*\)", raw):
        found.append(_unescape(match.group(0)))
    return found


def _unescape(token: bytes) -> str:
    body = token[1:-1]
    out = bytearray()
    i = 0
    while i < len(body):
        if body[i] == 0x5C and i + 1 < len(body):
            nxt = body[i + 1]
            if nxt in b"nrt":
                out.append({ord("n"): 10, ord("r"): 13, ord("t"): 9}[nxt])
            else:
                out.append(nxt)
            i += 2
            continue
        out.append(body[i])
        i += 1
    return out.decode("latin1", errors="ignore")


def _package(match: re.Match[str]) -> tuple[str, str, int] | None:
    if match.group(1):
        family = match.group(1).lower()
        pins = int(match.group(2))
        if pins < 2 or pins > 256 or pins % 2 and family != "sot":
            return None
        return family, f"{match.group(1).upper()}-{pins}", pins
    if match.group(3):
        code = match.group(4)
        pins = _SOT_PINS.get(code)
        if not pins:
            return None
        return "sot", f"SOT-{code}", pins
    code = match.group(5)
    return "chip", code, _CHIP_PINS[code]


def parse(text: str) -> tuple[list[dict], list[str]]:
    mpn_match = _MPN.search(text)
    mpn = mpn_match.group(1) if mpn_match else ""
    pins: dict[int, str] = {}
    for line in text.splitlines():
        hit = _PIN.match(line.strip())
        if hit:
            pins[int(hit.group(1))] = hit.group(2).upper()
    variants: list[dict] = []
    gaps: list[str] = []
    seen: set[str] = set()
    for line in text.splitlines():
        for match in _PKG.finditer(line):
            parsed = _package(match)
            if parsed is None:
                continue
            family, package, count = parsed
            if package in seen:
                continue
            seen.add(package)
            dims = _DIMS.search(line)
            pitch = _PITCH.search(line)
            missing = []
            if not dims:
                missing.append("body length, width, and height")
            if not pitch and family != "chip":
                missing.append("pitch")
            if missing:
                gaps.append(f"{package} was named but its line has no {' or '.join(missing)}.")
                continue
            length, width, height = (float(dims.group(i)) for i in (1, 2, 3)) if dims else (0.0, 0.0, 0.0)
            pitch_mm = float(pitch.group(1)) if pitch else 0.0
            named = {num: name for num, name in pins.items() if num <= count} if len(pins) == count else {}
            variants.append(
                {
                    "mpn": mpn,
                    "family": family,
                    "package": package,
                    "pins": count,
                    "pitch": pitch_mm,
                    "length": length,
                    "width": width,
                    "height": height,
                    "pin_names": named,
                }
            )
    if not variants and not gaps:
        gaps.append("No package with a body size was found. Put each package on its own line with length x width x height and pitch.")
    return variants, gaps


def lands(spec: dict) -> list[dict]:
    """Pad centers in millimetres. Pin 1 is the top of the left side. Land is calculated, not copied from a drawing."""
    count = int(spec["pins"])
    pitch = float(spec["pitch"] or 0)
    body_w = float(spec["width"])
    body_l = float(spec["length"])
    names = {int(k): v for k, v in (spec.get("pin_names") or {}).items()}
    family = spec["family"]
    pad_h = min(1.2, max(0.25, pitch * 0.55)) if pitch else 0.6
    pad_w = 1.5 if pitch >= 0.8 else 0.7

    def pad(num: int, x: float, y: float, w: float, h: float, kind: str = "smd") -> dict:
        return {
            "num": num,
            "name": names.get(num, f"P{num}"),
            "x": round(x, 3),
            "y": round(y, 3),
            "w": round(w, 3),
            "h": round(h, 3),
            "kind": kind,
        }

    if family == "chip":
        span = body_l / 2 + 0.35
        return [pad(1, -span, 0, 0.6, body_w * 0.8), pad(2, span, 0, 0.6, body_w * 0.8)]
    if family == "sot" and spec["package"] == "SOT-223":
        return [
            pad(1, -2.3, body_w / 2 + 0.9, 1.2, 1.5),
            pad(2, 0, body_w / 2 + 0.9, 1.2, 1.5),
            pad(3, 2.3, body_w / 2 + 0.9, 1.2, 1.5),
            pad(4, 0, -(body_w / 2 + 0.9), 3.5, 2.0),
        ]
    if family in {"qfn", "qfp", "dfn"} and count % 4 == 0:
        per = count // 4
        span = (per - 1) * pitch
        row = max(body_l, body_w) / 2 + 0.6
        pads = []
        num = 1
        for i in range(per):
            pads.append(pad(num, -row, span / 2 - i * pitch, pad_w, pad_h))
            num += 1
        for i in range(per):
            pads.append(pad(num, -span / 2 + i * pitch, -row, pad_h, pad_w))
            num += 1
        for i in range(per):
            pads.append(pad(num, row, -span / 2 + i * pitch, pad_w, pad_h))
            num += 1
        for i in range(per):
            pads.append(pad(num, span / 2 - i * pitch, row, pad_h, pad_w))
            num += 1
        return pads
    per = count // 2
    span = (per - 1) * pitch
    row = body_w / 2 + 1.0
    kind = "th" if family == "dip" else "smd"
    size = 1.0 if kind == "th" else pad_w
    pads = []
    for i in range(per):
        pads.append(pad(i + 1, -row, span / 2 - i * pitch, size, 1.0 if kind == "th" else pad_h, kind))
    for i in range(per):
        pads.append(pad(per + 1 + i, row, -span / 2 + i * pitch, size, 1.0 if kind == "th" else pad_h, kind))
    return pads

