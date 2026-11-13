"""Exact reader/writer for Blazer Drive's .bmsg message format (magic 'MPCT').

Layout (verified on all 136 .bmsg files in the ROM):

    0x00  'MPCT', u32 version=1, 0x18 zero bytes
    0x20  u32 2, u32 N (message count), u32 9, u32 0, u32 1, 0xFF padding up to 0x4C
    0x4C  N x u32  message identifiers (hash)
          N x u32  indices
          u32 0, u32 3
    PT    N x (u32 id, u32 offset)   <- offset relative to PT, points at the length prefix
    PT+8N strings: u32 length (excluding the trailing 0) + Shift-JIS text + 0x00, 4-byte aligned
    ...   'EOFC' footer (0x20 bytes)

There are no global size fields, so strings can grow: rewriting the string block
and the offset table is enough.
"""
import struct
from dataclasses import dataclass


@dataclass
class BmsgString:
    index: int          # physical order within the string block
    rel_offset: int     # original offset relative to PT (points at the length prefix)
    text_offset: int    # absolute offset of the first text byte (what the catalog uses)
    raw: bytes          # Shift-JIS bytes without the trailing 0


class Bmsg:
    def __init__(self, data: bytes) -> None:
        if data[:4] != b"MPCT":
            raise ValueError("Not an MPCT/.bmsg file")
        self.data = data
        u = lambda o: struct.unpack_from("<I", data, o)[0]
        self.count = u(0x24)
        self.pt = 0x4C + 8 * self.count + 8
        self.pairs = [(u(self.pt + i * 8), u(self.pt + i * 8 + 4)) for i in range(self.count)]
        offs = sorted(set(o for _, o in self.pairs))
        self.strings: list[BmsgString] = []
        end = self.pt + 8 * self.count
        for i, o in enumerate(offs):
            p = self.pt + o
            length = u(p)
            raw = data[p + 4 : p + 4 + length]
            if data[p + 4 + length] != 0:
                raise ValueError(f"Unterminated string at 0x{p:X}")
            self.strings.append(BmsgString(i, o, p + 4, raw))
            end = max(end, p + 4 + length + 1)
        self.strings_start = self.pt + 8 * self.count
        if offs and self.pt + offs[0] != self.strings_start:
            raise ValueError("Unexpected gap before the string block")
        end += (-end) % 4
        self.footer = data[end:]
        if not self.footer.startswith(b"EOFC"):
            raise ValueError("EOFC footer not found after the strings")

    def by_text_offset(self) -> dict[int, BmsgString]:
        return {s.text_offset: s for s in self.strings}

    def rebuild(self, replacements: dict[int, bytes]) -> bytes:
        """replacements: {original text_offset -> new Shift-JIS bytes (without trailing 0)}."""
        out = bytearray(self.data[: self.strings_start])
        new_rel: dict[int, int] = {}
        for s in self.strings:
            body = replacements.get(s.text_offset, s.raw)
            if b"\x00" in body:
                raise ValueError("Text cannot contain 0x00")
            new_rel[s.rel_offset] = len(out) - self.pt
            out += struct.pack("<I", len(body)) + body + b"\x00"
            out += b"\x00" * ((-len(out)) % 4)
        out += self.footer
        for i, (mid, off) in enumerate(self.pairs):
            struct.pack_into("<II", out, self.pt + i * 8, mid, new_rel[off])
        return bytes(out)
