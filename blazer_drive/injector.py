"""Safe injection of translations.

Rules (derived from the emulator audit, see tests/README_QA.md):
  * Always start from the PRISTINE files of the original ROM (never from the workspace,
    which may contain previous injections).
  * Only .bmsg files are injected, and only at offsets the exact parser recognizes as
    a string start (structural proof that it is real text). The .bin / arm9.bin files
    contain code and binary data misdetected as text: injecting there
    breaks the game's boot.
  * The original text at the offset must match Original_JP byte for byte.
  * printf specifiers (%s, %d, %02d...) must match in order, and the
    $Nc color codes must be kept in the same quantity.
  * Never truncate: the .bmsg is rebuilt (blazer_drive/bmsg.py) and the string grows; the
    text is re-wrapped to MaxBox_PX/MaxLines and whatever does not fit is reported.
"""
import csv
import re
import struct
from collections import Counter, defaultdict
from pathlib import Path

from blazer_drive.font import FontEngine
from blazer_drive.catalog import TranslationCatalog

PRINTF_RE = re.compile(rb"%[-+#0]*\d*(?:\.\d+)?(?:ll|l|h)?[sdcuxXf]")
COLOR_RE = re.compile(rb"\$\d*c")
INJECTABLE_SUFFIXES = {".bmsg"}


def _norm(s: str) -> str:
    return s.replace("\r\n", "\n")


def check_entry(pristine: bytes, offset: int, max_bytes: int, original: str, encoded: bytes) -> str:
    """Returns 'OK' or the rejection reason."""
    if offset < 4 or offset + max_bytes >= len(pristine):
        return "BAD_OFFSET"
    if struct.unpack("<I", pristine[offset - 4 : offset])[0] != max_bytes:
        return "NOT_LENGTH_PREFIXED"
    raw = pristine[offset : offset + max_bytes]
    if pristine[offset + max_bytes] != 0:
        return "NO_TERMINATOR"
    if raw.decode("cp932", errors="replace").strip() != _norm(original).strip():
        return "ORIGINAL_MISMATCH"
    if PRINTF_RE.findall(raw) != PRINTF_RE.findall(encoded):
        return "PRINTF_MISMATCH"
    if len(COLOR_RE.findall(raw)) != len(COLOR_RE.findall(encoded)):
        return "COLOR_CODE_MISMATCH"
    if len(encoded) > max_bytes:
        return "BYTE_OVERFLOW"
    return "OK"


def fit_layout(font: FontEngine, text: str, max_px: int, max_lines: int, paginate: bool = False) -> tuple[str, bool]:
    """Re-wraps lines to the box width. Keeps paragraphs (blank lines) and the translator's
    line breaks when they fit; otherwise reflows the text. Returns (text, overflows)."""
    from blazer_drive.catalog import CONTROL_CODE_RE

    def width(line: str) -> int:
        return font.measure_line_width(CONTROL_CODE_RE.sub("", line))

    def wrap(par: str) -> list[str]:
        out, cur = [], ""
        for word in par.split(" "):
            cand = f"{cur} {word}" if cur else word
            if width(cand) <= max_px or not cur:
                cur = cand
            else:
                out.append(cur)
                cur = word
        return out + ([cur] if cur else [])

    def fit_page(page: str) -> list[str]:
        lines = [l.strip() for l in page.split("\n")]
        if all(width(l) <= max_px for l in lines) and len(lines) <= max_lines:
            return lines
        paragraphs = "\n".join(lines).split("\n\n")
        blocks = [wrap(" ".join(x for x in par.split("\n") if x)) for par in paragraphs]
        return "\n\n".join("\n".join(b) for b in blocks).split("\n")

    # '#' = message box page break (used by the game in tutorials and events)
    pages_out: list[list[str]] = []
    for page in text.split("#"):
        page = page.lstrip("\n")
        lines = fit_page(page)
        if paginate and len(lines) > max_lines:
            for i in range(0, len(lines), max_lines):
                pages_out.append(lines[i : i + max_lines])
        else:
            pages_out.append(lines)
    result = "#\n".join("\n".join(p) for p in pages_out)
    overflow = any(len(p) > max_lines for p in pages_out) or any(
        width(l) > max_px for p in pages_out for l in p
    )
    return result, overflow


PAGINATED_FILES = ("event_msg_", "battle_msg", "sys_msg")


def _paginates(rel_file: str) -> bool:
    """Message boxes that accept '#' as a page break (verified in the emulator)."""
    return Path(rel_file).name.startswith(PAGINATED_FILES)


class TextInjector:
    def __init__(self, font_engine: FontEngine | None = None) -> None:
        self.font = font_engine or FontEngine()

    def inject_catalog(
        self,
        catalog: TranslationCatalog,
        pristine_files: dict[str, bytes],
        out_dir: Path,
        target_lang: str = "en",
        auto_wrap: bool = True,
        max_box_width: int = 224,
        report_path: Path | None = None,
    ) -> dict[str, int]:
        """.bmsg files are rebuilt with blazer_drive/bmsg.py: strings can grow."""
        from blazer_drive.bmsg import Bmsg

        stats: Counter = Counter(total_entries=len(catalog.entries))
        by_file = defaultdict(list)
        for entry in catalog.entries:
            if entry.status.lower() in ("ignored", "ignore"):
                stats["skipped_ignored"] += 1
                continue
            by_file[entry.file_path].append(entry)

        report_rows = []
        modified: dict[str, bytes] = {}
        for rel_file, entries in by_file.items():
            if Path(rel_file).suffix.lower() not in INJECTABLE_SUFFIXES:
                stats["rejected_not_injectable_file"] += len(entries)
                continue
            pristine = pristine_files.get(rel_file)
            if pristine is None:
                stats["rejected_missing_file"] += len(entries)
                continue
            bm = Bmsg(pristine)
            index = bm.by_text_offset()
            repl: dict[int, bytes] = {}
            for entry in entries:
                text = _norm((entry.translation_en if target_lang == "en" else entry.translation_es) or "").strip()
                if not text:
                    stats["skipped_empty"] += 1
                    continue
                if text == _norm(entry.original_jp).strip():
                    stats["skipped_identical"] += 1
                    continue
                st = index.get(entry.offset)
                verdict = "OK"
                if st is None:
                    verdict = "NOT_A_STRING_START"
                elif st.raw.decode("cp932", errors="replace").strip() != _norm(entry.original_jp).strip():
                    verdict = "ORIGINAL_MISMATCH"
                overflow = False
                if verdict == "OK" and auto_wrap:
                    text, overflow = fit_layout(self.font, text, entry.max_px, entry.max_lines,
                                               paginate=_paginates(rel_file))
                encoded = b""
                if verdict == "OK":
                    try:
                        encoded = text.encode("cp932")
                    except UnicodeEncodeError:
                        verdict = "ENCODING_ERROR"
                if verdict == "OK":
                    if PRINTF_RE.findall(st.raw) != PRINTF_RE.findall(encoded):
                        verdict = "PRINTF_MISMATCH"
                    elif len(COLOR_RE.findall(st.raw)) != len(COLOR_RE.findall(encoded)):
                        verdict = "COLOR_CODE_MISMATCH"
                if verdict != "OK":
                    stats["rejected_" + verdict.lower()] += 1
                    report_rows.append((entry.entry_id, rel_file, hex(entry.offset), verdict, entry.original_jp, text))
                    continue
                if overflow:
                    stats["injected_layout_overflow"] += 1
                    report_rows.append((entry.entry_id, rel_file, hex(entry.offset), "LAYOUT_OVERFLOW", entry.original_jp, text))
                repl[entry.offset] = encoded
                stats["injected"] += 1
            if repl:
                modified[rel_file] = bm.rebuild(repl)
                stats["bytes_growth"] += len(modified[rel_file]) - len(pristine)

        for rel_file, body in modified.items():
            target = out_dir / rel_file
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(body)
        stats["files_modified"] = len(modified)

        if report_path:
            report_path.parent.mkdir(parents=True, exist_ok=True)
            with report_path.open("w", encoding="utf-8-sig", newline="") as f:
                w = csv.writer(f)
                w.writerow(["ID", "File", "Offset", "Reason", "Original_JP", "Translation"])
                w.writerows(report_rows)
        return dict(stats)
