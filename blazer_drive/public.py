"""Split between what is published (English only) and what stays local (game text).

The repository never contains Japanese text from the game:

* ``translations/strings_en.csv`` holds only IDs, offsets and the English lines. Custom
  font glyphs (icons, Roman numerals, see docs/FORMATS.md) are written as ``{g:XXXX}``
  tokens (their Shift-JIS code) instead of the kanji code points they occupy.
* ``translations/overrides_en.json`` may use ``{script:NNN:i}``: the i-th kana string
  found in ``script_NNN.bin`` of the user's own ROM (password answers).
* The full catalogue with the Japanese original is generated locally from the user's
  ROM (``workspace/catalog/``, git-ignored).
"""
import csv
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_EN = ROOT / "translations/strings_en.csv"
OVERRIDES = ROOT / "translations/overrides_en.json"
LOCAL_DIR = ROOT / "workspace/catalog"
LOCAL_CSV = LOCAL_DIR / "strings.csv"
LOCAL_XLSX = LOCAL_DIR / "strings.xlsx"

# Shift-JIS codes of the custom glyphs drawn by font01.NFTR (icons + Roman numerals)
GLYPH_CODES = list(range(0x98E4, 0x98FD)) + list(range(0x9940, 0x9950))
_CODE_TO_CHAR = {c: bytes([c >> 8, c & 0xFF]).decode("cp932") for c in GLYPH_CODES}
_CHAR_TO_CODE = {ch: c for c, ch in _CODE_TO_CHAR.items()}
CUSTOM_GLYPHS = set(_CHAR_TO_CODE)
_TOKEN_RE = re.compile(r"\{g:([0-9A-Fa-f]{4})\}")
_SCRIPT_RE = re.compile(r"\{script:(\d+):(\d+)\}")
_KANA_RUN = re.compile(rb"(?:\x83[\x40-\x96]|\x81\x5b){3,}")

PUBLIC_COLUMNS = ["ID", "File", "Offset_Hex", "English", "Status", "Notes"]


def glyphs_to_tokens(text: str) -> str:
    return "".join(f"{{g:{_CHAR_TO_CODE[ch]:04X}}}" if ch in _CHAR_TO_CODE else ch for ch in text)


def tokens_to_glyphs(text: str) -> str:
    return _TOKEN_RE.sub(lambda m: _CODE_TO_CHAR[int(m.group(1), 16)], text)


def export_public(catalog, path: Path = PUBLIC_EN) -> int:
    """Writes the English-only file from a full catalogue. Returns the row count."""
    path.parent.mkdir(parents=True, exist_ok=True)
    import json as _json

    overridden = set(_json.loads(OVERRIDES.read_text(encoding="utf-8"))) if OVERRIDES.exists() else set()
    n = 0
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(PUBLIC_COLUMNS)
        for e in catalog.entries:
            if not e.translation_en or e.entry_id in overridden:
                continue  # overrides live in overrides_en.json (with {script:..} placeholders)
            w.writerow([e.entry_id, e.file_path, f"0x{e.offset:08X}", glyphs_to_tokens(e.translation_en),
                        e.status, e.notes])
            n += 1
    return n


def load_public(path: Path = PUBLIC_EN) -> dict[tuple[str, int], tuple[str, str, str]]:
    """(file, offset) -> (English with real glyphs, status, notes)."""
    if not path.exists():
        return {}
    out = {}
    with path.open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            out[(r["File"], int(r["Offset_Hex"], 16))] = (tokens_to_glyphs(r["English"]), r["Status"], r["Notes"])
    return out


def script_kana(pristine: dict[str, bytes], script: str) -> list[str]:
    data = pristine.get(f"cpk_extracted/field/script_{script}.bin", b"")
    return [m.group().decode("cp932") for m in _KANA_RUN.finditer(data)]


def load_overrides(pristine: dict[str, bytes]) -> dict[str, str]:
    """Overrides with {script:NNN:i} resolved against the user's ROM."""
    if not OVERRIDES.exists():
        return {}
    raw = json.loads(OVERRIDES.read_text(encoding="utf-8"))
    cache: dict[str, list[str]] = {}

    def resolve(m: re.Match) -> str:
        kana = cache.setdefault(m.group(1), script_kana(pristine, m.group(1)))
        return kana[int(m.group(2))]

    return {k: tokens_to_glyphs(_SCRIPT_RE.sub(resolve, v)) for k, v in raw.items() if not k.startswith("_")}
