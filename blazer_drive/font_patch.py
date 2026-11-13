"""Turns the ASCII part of font01.NFTR into a variable-width font (VWF).

The original font draws ASCII in ~4 px but with a fixed advance of 5 (+1 px added
by the game engine = 6 px per letter). Here each ASCII glyph gets left=0 and
advance = actual drawn width, so English text takes up less space.
Japanese glyphs are left untouched.
"""
import struct
from pathlib import Path

SPACE_ADVANCE = 2  # + 1 px from the engine = 3 px per space


def _section(data: bytes, magic: bytes) -> int:
    ptr = 16
    while ptr + 8 <= len(data):
        if data[ptr : ptr + 4] == magic:
            return ptr
        size = struct.unpack_from("<I", data, ptr + 4)[0]
        if size <= 0:
            break
        ptr += size
    raise ValueError(f"Section {magic!r} not found")


def ascii_glyph_ids(data: bytes) -> dict[int, int]:
    """Map ASCII code -> glyph index (direct CMAP block 0x20-0x7E)."""
    ptr = 16
    out = {}
    while ptr + 8 <= len(data):
        magic = data[ptr : ptr + 4]
        size = struct.unpack_from("<I", data, ptr + 4)[0]
        if magic == b"PAMC":
            first, last, kind = struct.unpack_from("<HHI", data, ptr + 8)
            if kind == 0 and first <= 0x7E and last >= 0x20:
                base = struct.unpack_from("<H", data, ptr + 20)[0]
                for code in range(max(first, 0x20), min(last, 0x7E) + 1):
                    out[code] = base + code - first
        if size <= 0:
            break
        ptr += size
    return out


# Glyphs redrawn at 5 px: at 4 px 'm' looks like 'n' and 'W' like 'H'
# (verified in emulator screenshots: "I cone" instead of "I come").
WIDE_GLYPHS = {
    "M": ["#...#", "##.##", "#.#.#", "#.#.#", "#...#", "#...#", "#...#", "#...#", "#...#"],
    "W": ["#...#", "#...#", "#...#", "#...#", "#.#.#", "#.#.#", "#.#.#", "##.##", "#...#"],
    "m": [".....", ".....", "####.", "#.#.#", "#.#.#", "#.#.#", "#.#.#", "#.#.#", "#.#.#"],
    "w": [".....", ".....", "#...#", "#...#", "#.#.#", "#.#.#", "#.#.#", "#.#.#", ".#.#."],
}


def _set_glyph(out: bytearray, data: bytes, gid: int, rows: list[str]) -> None:
    cg = _section(data, b"PLGC")
    cell_w, cell_h = data[cg + 8], data[cg + 9]
    size = struct.unpack_from("<H", data, cg + 10)[0]
    bits = "".join((r + "." * cell_w)[:cell_w] for r in rows[:cell_h]).replace("#", "1").replace(".", "0")
    bits = bits.ljust(size * 8, "0")
    pos = cg + 16 + gid * size
    out[pos : pos + size] = int(bits, 2).to_bytes(size, "big")


def make_vwf(data: bytes) -> bytes:
    out = bytearray(data)
    gids = ascii_glyph_ids(data)
    for ch, rows in WIDE_GLYPHS.items():
        _set_glyph(out, data, gids[ord(ch)], rows)
    cw = _section(data, b"HDWC")
    first = struct.unpack_from("<H", data, cw + 8)[0]
    for ch, rows in WIDE_GLYPHS.items():
        e = cw + 16 + 3 * (gids[ord(ch)] - first)
        out[e + 1] = max(len(r.rstrip(".")) for r in rows)
    data = bytes(out)
    first = struct.unpack_from("<H", data, cw + 8)[0]
    for code, gid in ascii_glyph_ids(data).items():
        e = cw + 16 + 3 * (gid - first)
        left, width, adv = data[e], data[e + 1], data[e + 2]
        if code == 0x20:
            out[e : e + 3] = bytes([0, 0, SPACE_ADVANCE])
        else:
            out[e : e + 3] = bytes([0, width, max(1, width)])
    return bytes(out)


def write_vwf(src: Path, dst: Path) -> Path:
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(make_vwf(src.read_bytes()))
    return dst
