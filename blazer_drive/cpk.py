import struct
from dataclasses import dataclass
from pathlib import Path


def _get_next_bits(input_data: bytes, state: list[int], bit_count: int) -> int:
    out_bits = 0
    num_bits_produced = 0
    while num_bits_produced < bit_count:
        if state[2] == 0:
            state[1] = input_data[state[0]]
            state[2] = 8
            state[0] -= 1
        if state[2] > (bit_count - num_bits_produced):
            bits_this_round = bit_count - num_bits_produced
        else:
            bits_this_round = state[2]
        out_bits <<= bits_this_round
        out_bits |= (state[1] >> (state[2] - bits_this_round)) & ((1 << bits_this_round) - 1)
        state[2] -= bits_this_round
        num_bits_produced += bits_this_round
    return out_bits


def decompress_crilayla(input_data: bytes, uncompressed_size: int) -> bytes:
    if len(input_data) < 16:
        return input_data

    uncompressed_header_offset = struct.unpack("<I", input_data[12:16])[0]
    result = bytearray(uncompressed_size + 0x100)

    copy_start = uncompressed_header_offset + 0x10
    copy_end = copy_start + 0x100
    if copy_end <= len(input_data):
        result[0:0x100] = input_data[copy_start:copy_end]

    input_offset = len(input_data) - 0x100 - 1
    output_end = 0x100 + uncompressed_size - 1
    bytes_output = 0
    vle_lens = [2, 3, 5, 8]
    state = [input_offset, 0, 0]

    while bytes_output < uncompressed_size and state[0] >= 0:
        if _get_next_bits(input_data, state, 1) > 0:
            backref_offset = output_end - bytes_output + _get_next_bits(input_data, state, 13) + 3
            backref_length = 3
            for vle in vle_lens:
                this_level = _get_next_bits(input_data, state, vle)
                backref_length += this_level
                if this_level != ((1 << vle) - 1):
                    break
            else:
                while True:
                    this_level = _get_next_bits(input_data, state, 8)
                    backref_length += this_level
                    if this_level != 255:
                        break

            for _ in range(backref_length):
                if 0 <= backref_offset < len(result) and 0 <= (output_end - bytes_output) < len(result):
                    result[output_end - bytes_output] = result[backref_offset]
                backref_offset -= 1
                bytes_output += 1
                if bytes_output >= uncompressed_size:
                    break
        else:
            if 0 <= (output_end - bytes_output) < len(result):
                result[output_end - bytes_output] = _get_next_bits(input_data, state, 8)
            bytes_output += 1

    return bytes(result)


_TYPE_SIZES = {0: 1, 1: 1, 2: 2, 3: 2, 4: 4, 5: 4, 6: 8, 7: 8, 8: 4, 0xA: 4, 0xB: 8}
_INT_FMT = {1: ">B", 2: ">H", 4: ">I", 8: ">Q"}


def _utf_xor(buf: bytes) -> bytes:
    """Standard XOR encryption/decryption of CRIWARE @UTF tables (symmetric)."""
    m = 0x655F
    out = bytearray(buf)
    for i in range(len(out)):
        out[i] ^= m & 0xFF
        m = (m * 0x4115) & 0xFFFFFFFF
    return bytes(out)


@dataclass
class CpkEntry:
    name: str
    data: bytes  # already decompressed contents
    compressed: bool
    row_index: int


class CpkManager:
    """Safe reading and repacking of CRIWARE CPK containers.

    Repacking does NOT use CriPakTools: that tool writes the modified data
    over the TOC table (which it does not relocate) and corrupts the file.
    Here modified files are appended to the end of the CPK and only the
    TOC's FileOffset/FileSize/ExtractSize fields are patched in place,
    without changing the size of any table.
    """

    @staticmethod
    def _chunk_utf(data: bytes, chunk_off: int) -> tuple[bytes, bool]:
        """Returns (bytes with the chunk's @UTF table decrypted, was_encrypted)."""
        if data[chunk_off + 0x10 : chunk_off + 0x14] == b"@UTF":
            return data, False
        size = struct.unpack("<I", data[chunk_off + 8 : chunk_off + 12])[0]
        buf = bytearray(data)
        buf[chunk_off + 0x10 : chunk_off + 0x10 + size] = _utf_xor(
            data[chunk_off + 0x10 : chunk_off + 0x10 + size]
        )
        return bytes(buf), True

    @staticmethod
    def utf_layout(data: bytes, offset: int) -> tuple[list[dict], list[dict]]:
        """Parses a @UTF table. Returns (rows, positions), where
        positions[r][field] = (absolute_offset, size) of the per-row fields."""
        if data[offset : offset + 4] != b"@UTF":
            return [], []
        (_, rows_off, strings_off, data_off, _, num_fields, row_len, num_rows) = struct.unpack(
            ">IIIIIHHI", data[offset + 4 : offset + 32]
        )
        strings_base = offset + 8 + strings_off
        data_base = offset + 8 + data_off

        def cstr(pos: int) -> str:
            end = data.index(b"\x00", pos)
            return data[pos:end].decode("ascii", errors="replace")

        def read(ft: int, pos: int):
            if ft == 0xA:
                return cstr(strings_base + struct.unpack(">I", data[pos : pos + 4])[0])
            if ft == 0xB:
                boff, bsz = struct.unpack(">II", data[pos : pos + 8])
                return data[data_base + boff : data_base + boff + bsz]
            if ft == 8:
                return struct.unpack(">f", data[pos : pos + 4])[0]
            size = _TYPE_SIZES[ft]
            return struct.unpack(_INT_FMT[size], data[pos : pos + size])[0]

        p = offset + 32
        fields = []
        for _ in range(num_fields):
            flags = data[p]
            name = cstr(strings_base + struct.unpack(">I", data[p + 1 : p + 5])[0])
            p += 5
            storage, ft = flags & 0xF0, flags & 0x0F
            const = None
            if storage == 0x30:
                const = read(ft, p)
                p += _TYPE_SIZES[ft]
            fields.append((name, storage, ft, const))

        rows, positions = [], []
        for r in range(num_rows):
            rp = offset + 8 + rows_off + r * row_len
            row, pos = {}, {}
            for name, storage, ft, const in fields:
                if storage == 0x30:
                    row[name] = const
                elif storage == 0x50:
                    row[name] = read(ft, rp)
                    pos[name] = (rp, _TYPE_SIZES[ft])
                    rp += _TYPE_SIZES[ft]
                else:
                    row[name] = None
            rows.append(row)
            positions.append(pos)
        return rows, positions

    @classmethod
    def parse_utf_table(cls, data: bytes, offset: int = 0) -> list[dict]:
        return cls.utf_layout(data, offset)[0]

    @classmethod
    def _header_and_toc(cls, data: bytes):
        plain, _ = cls._chunk_utf(data, 0)
        hdr_rows = cls.parse_utf_table(plain, 0x10)
        if not hdr_rows:
            raise ValueError("Invalid CPK header")
        hdr = hdr_rows[0]
        toc = hdr.get("TocOffset") or 0
        if not toc:
            raise ValueError("CPK without TOC (ITOC-only is not supported)")
        plain, toc_enc = cls._chunk_utf(plain, toc)
        rows, positions = cls.utf_layout(plain, toc + 0x10)
        content = hdr.get("ContentOffset") or 0x800
        base = min(toc, content)  # CRI rule: offsets are relative to the smaller of the two
        return plain, hdr, toc, toc_enc, rows, positions, base

    @classmethod
    def read_entries(cls, data: bytes) -> list[CpkEntry]:
        _, _, _, _, rows, _, base = cls._header_and_toc(data)
        out = []
        for i, r in enumerate(rows):
            fsize = r["FileSize"]
            esize = r.get("ExtractSize") or fsize
            raw = bytes(data[base + r["FileOffset"] : base + r["FileOffset"] + fsize])
            comp = esize > fsize
            body = decompress_crilayla(raw, esize - 0x100)[:esize] if comp else raw
            out.append(CpkEntry(r["FileName"], bytes(body), comp, i))
        return out

    @classmethod
    def extract_cpk(cls, cpk_path: Path, out_dir: Path) -> int:
        out_dir.mkdir(parents=True, exist_ok=True)
        try:
            entries = cls.read_entries(cpk_path.read_bytes())
        except (ValueError, KeyError):
            return 0
        for e in entries:
            (out_dir / e.name).write_bytes(e.data)
        return len(entries)

    @classmethod
    def patch_cpk(cls, data: bytes, replacements: dict[str, bytes]) -> bytes:
        """New CPK with `replacements` (uncompressed) appended at the end and the TOC
        patched in place. All other files stay byte-for-byte intact."""
        plain, hdr, toc, toc_enc, rows, positions, base = cls._header_and_toc(data)
        align = hdr.get("Align") or 0x800
        toc_size = struct.unpack("<I", data[toc + 8 : toc + 12])[0]
        toc_plain = bytearray(plain[toc + 0x10 : toc + 0x10 + toc_size])
        names = {r["FileName"]: i for i, r in enumerate(rows)}
        missing = set(replacements) - set(names)
        if missing:
            raise KeyError(f"Not present in the CPK: {sorted(missing)}")

        out = bytearray(data)

        def put(field_pos: tuple[int, int], value: int) -> None:
            pos, size = field_pos
            rel = pos - (toc + 0x10)
            toc_plain[rel : rel + size] = struct.pack(_INT_FMT[size], value)

        for name, body in replacements.items():
            i = names[name]
            pos = positions[i]
            for f in ("FileOffset", "FileSize"):
                if f not in pos:
                    raise ValueError(f"Field {f} is not editable per row in {name}")
            out += b"\x00" * ((-len(out)) % align)
            put(pos["FileOffset"], len(out) - base)
            put(pos["FileSize"], len(body))
            if "ExtractSize" in pos:
                put(pos["ExtractSize"], len(body))
            out += body
        out += b"\x00" * ((-len(out)) % align)
        blob = _utf_xor(bytes(toc_plain)) if toc_enc else bytes(toc_plain)
        out[toc + 0x10 : toc + 0x10 + len(blob)] = blob
        return bytes(out)
