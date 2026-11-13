import struct
from pathlib import Path


class FontEngine:
    DEFAULT_CHAR_WIDTH = 6
    DEFAULT_JP_WIDTH = 12
    DEFAULT_SPACE_WIDTH = 4

    def __init__(self, nftr_path: Path | None = None) -> None:
        self.char_widths: dict[int, int] = {}
        self.default_width = self.DEFAULT_CHAR_WIDTH
        self.default_height = 12
        if nftr_path and nftr_path.exists():
            self._load_nftr(nftr_path)

    def _load_nftr(self, path: Path) -> None:
        data = path.read_bytes()
        if len(data) < 16 or data[:4] != b"RTFN":
            return

        glyph_widths: dict[int, int] = {}
        ptr = 16
        cmap_blocks: list[tuple[int, int, int, int]] = []

        while ptr + 8 <= len(data):
            magic = bytes(data[ptr : ptr + 4])
            size = struct.unpack("<I", data[ptr + 4 : ptr + 8])[0]
            if size <= 0 or ptr + size > len(data):
                break

            if magic == b"HDWC":
                if size >= 16:
                    first, last = struct.unpack("<HH", data[ptr + 8 : ptr + 12])
                    entries = last - first + 1
                    base = ptr + 16
                    for g in range(entries):
                        ep = base + g * 3
                        if ep + 3 <= ptr + size:
                            _, _, char_w = struct.unpack("3b", data[ep : ep + 3])
                            glyph_widths[first + g] = max(1, char_w)

            elif magic == b"PAMC":
                if size >= 20:
                    c_first, c_last, c_type = struct.unpack("<HHI", data[ptr + 8 : ptr + 16])
                    cmap_blocks.append((c_first, c_last, c_type, ptr))

            ptr += size

        for c_first, c_last, c_type, blk_ptr in cmap_blocks:
            if c_type == 0:
                base_glyph = struct.unpack("<H", data[blk_ptr + 20 : blk_ptr + 22])[0]
                for code in range(c_first, c_last + 1):
                    gid = base_glyph + (code - c_first)
                    if gid in glyph_widths:
                        self.char_widths[code] = glyph_widths[gid]
            elif c_type == 1:
                total = c_last - c_first + 1
                base = blk_ptr + 20
                for idx in range(total):
                    ep = base + idx * 2
                    if ep + 2 <= len(data):
                        gid = struct.unpack("<H", data[ep : ep + 2])[0]
                        if gid != 0xFFFF and gid in glyph_widths:
                            self.char_widths[c_first + idx] = glyph_widths[gid]

    # Measured in the emulator (tests/out/s01/zoom_*.png): the game draws 1-byte (ASCII)
    # characters with 1 px of extra spacing -> real advance of 6 px; 2-byte characters
    # (kana/kanji) advance 12 px. A 180 px dialog box fits 15 Japanese characters
    # or 30 ASCII ones.
    ASCII_LETTER_SPACING = 1

    def get_char_width(self, char: str) -> int:
        if not char:
            return 0
        if char == " ":
            return self.char_widths.get(0x0020, self.DEFAULT_SPACE_WIDTH) + self.ASCII_LETTER_SPACING
        code = ord(char)
        if code in self.char_widths:
            return self.char_widths[code] + (self.ASCII_LETTER_SPACING if code < 0x80 else 0)
        if code > 0x7E:
            return self.DEFAULT_JP_WIDTH
        return self.DEFAULT_CHAR_WIDTH

    def measure_line_width(self, line: str) -> int:
        total = 0
        for ch in line:
            if ch == "\n":
                break
            total += self.get_char_width(ch)
        return total

    def measure_text_box(self, text: str) -> tuple[int, int]:
        lines = text.split("\n")
        max_w = max((self.measure_line_width(l) for l in lines), default=0)
        return max_w, len(lines)

    def wrap_text(self, text: str, max_pixels: int = 224, max_lines: int = 3) -> tuple[str, bool]:
        if "\n" in text:
            paragraphs = text.split("\n")
            wrapped_paras: list[str] = []
            exceeded = False
            for p in paragraphs:
                wp, exc = self.wrap_text(p, max_pixels, max_lines)
                wrapped_paras.append(wp)
                if exc:
                    exceeded = True
            joined = "\n".join(wrapped_paras)
            total_lines = joined.count("\n") + 1
            return joined, exceeded or (total_lines > max_lines)

        words = text.split(" ")
        lines: list[str] = []
        current_line = ""

        for word in words:
            candidate = f"{current_line} {word}".strip() if current_line else word
            if self.measure_line_width(candidate) <= max_pixels:
                current_line = candidate
            else:
                if current_line:
                    lines.append(current_line)
                    current_line = word
                else:
                    lines.append(word)
                    current_line = ""

        if current_line:
            lines.append(current_line)

        is_overflow = len(lines) > max_lines
        return "\n".join(lines), is_overflow

