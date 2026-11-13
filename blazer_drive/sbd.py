"""Reader/writer for textures in Blazer Drive's .sbd (DCSD) containers.

Relevant blocks (internal offsets relative to block_start + 0x10):
  DTEX  u32 n, u32 table -> n x (u32 id, u16 texture, u16 palette)
  DTXL  u32 n, u32 table, u32 data, ... -> n x (u8 fmt, u8 ?, u8 log2(w/8), u8 log2(h/8),
        u16 0xFFFF, u16 0, u32 offset, u32 size)
  DPAL  u32 n, u32 table, u32 data -> n x (u32 fmt, u32 offset, u32 size, u32 size)
DS texture formats: 1=A3I5, 2=4 colors, 3=16 colors, 4=256 colors, 6=A5I3, 7=direct.
"""
import struct
from dataclasses import dataclass

from PIL import Image


@dataclass
class Texture:
    index: int
    fmt: int
    width: int
    height: int
    data_pos: int   # absolute offset in the file
    size: int


@dataclass
class Palette:
    index: int
    pos: int
    size: int


def _chunks(data: bytes) -> dict[bytes, int]:
    out = {}
    for magic in (b"DTEX", b"DTXL", b"DPAL"):
        p = data.find(magic)
        if p >= 0:
            out[magic] = p
    return out


class Sbd:
    def __init__(self, data: bytes) -> None:
        if data[:4] != b"DCSD":
            raise ValueError("Not a DCSD file")
        self.data = bytearray(data)
        c = _chunks(data)
        self.textures: list[Texture] = []
        self.palettes: list[Palette] = []
        self.links: list[tuple[int, int, int]] = []
        if b"DTXL" in c:
            b = c[b"DTXL"] + 0x10
            n, tab, dat = struct.unpack_from("<III", data, b)
            for i in range(n):
                fmt, _, wl, hl, _, _, off, size = struct.unpack_from("<BBBBHHII", data, b + tab + 16 * i)
                self.textures.append(Texture(i, fmt, 8 << wl, 8 << hl, b + dat + off, size))
        if b"DPAL" in c:
            b = c[b"DPAL"] + 0x10
            n, tab, dat = struct.unpack_from("<III", data, b)
            for i in range(n):
                _, off, size, _ = struct.unpack_from("<IIII", data, b + tab + 16 * i)
                self.palettes.append(Palette(i, b + dat + off, size))
        if b"DTEX" in c:
            b = c[b"DTEX"] + 0x10
            n, tab = struct.unpack_from("<II", data, b)
            for i in range(n):
                self.links.append(struct.unpack_from("<IHH", self.data, b + tab + 8 * i))

    def palette_colors(self, pal: Palette) -> list[tuple[int, int, int]]:
        cols = []
        for i in range(pal.size // 2):
            v = struct.unpack_from("<H", self.data, pal.pos + 2 * i)[0]
            cols.append(((v & 31) * 255 // 31, ((v >> 5) & 31) * 255 // 31, ((v >> 10) & 31) * 255 // 31))
        return cols

    def palette_for(self, tex: Texture) -> Palette | None:
        for _, t, p in self.links:
            if t == tex.index and p < len(self.palettes):
                return self.palettes[p]
        return None

    def decode(self, tex: Texture) -> Image.Image:
        pal = self.palette_for(tex)
        cols = self.palette_colors(pal) if pal else [(i, i, i) for i in range(256)]
        raw = self.data[tex.data_pos : tex.data_pos + tex.size]
        w, h = tex.width, tex.height
        img = Image.new("RGBA", (w, h))
        px = img.load()
        for y in range(h):
            for x in range(w):
                i = y * w + x
                if tex.fmt == 4:
                    c, a = raw[i], 255 if raw[i] else 0
                elif tex.fmt == 3:
                    c = (raw[i >> 1] >> ((i & 1) * 4)) & 15
                    a = 255 if c else 0
                elif tex.fmt == 2:
                    c = (raw[i >> 2] >> ((i & 3) * 2)) & 3
                    a = 255 if c else 0
                elif tex.fmt == 1:
                    c, a = raw[i] & 31, (raw[i] >> 5) * 255 // 7
                elif tex.fmt == 6:
                    c, a = raw[i] & 7, (raw[i] >> 3) * 255 // 31
                elif tex.fmt == 7:
                    v = struct.unpack_from("<H", raw, 2 * i)[0]
                    px[x, y] = ((v & 31) * 8, ((v >> 5) & 31) * 8, ((v >> 10) & 31) * 8, 255 if v & 0x8000 else 0)
                    continue
                else:
                    continue
                r, g, b = cols[c] if c < len(cols) else (255, 0, 255)
                px[x, y] = (r, g, b, a)
        return img
