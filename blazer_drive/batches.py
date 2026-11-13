"""Exports the catalog to JSON batches for translation and re-imports/validates the results.

  python -m blazer_drive batches export [--size 650]
      -> workspace/batches/in/batch_NN.json   (unique phrases, in file order)
  python -m blazer_drive batches import
      -> reads workspace/batches/out/batch_NN*.json, validates and fills the English column
         of the local catalogue (Status=Draft, Notes='batch v2') and refreshes translations/strings_en.csv.

Expected output format: JSON list of {"k": "<key>", "en": "<text>"}.
"""
import argparse
import hashlib
import json
import re
from collections import Counter, OrderedDict
from pathlib import Path

from blazer_drive.font import FontEngine
from blazer_drive.catalog import TranslationCatalog
from blazer_drive.public import CUSTOM_GLYPHS, LOCAL_CSV, LOCAL_XLSX, export_public, load_overrides

ROOT = Path(__file__).resolve().parents[1]

CSV = LOCAL_CSV
XLSX = LOCAL_XLSX
BATCH_DIR = ROOT / "workspace/batches"
# Icons / Roman numerals (Shift-JIS 0x98E4-0x994F): must be preserved as-is.
# 0x9950-0x9957: substitutes for kanji missing from the font (e.g. the one meaning "trap"):
# they are translated as normal text.
PRINTF_RE = re.compile(r"%[-+#0]*\d*(?:\.\d+)?(?:ll|l|h)?[sdcuxXf]")
COLOR_RE = re.compile(r"\$\d*c")
JP_RE = re.compile(r"[\u3040-\u30ff\u4e00-\u9fff\uff01-\uff5e]")


def key_of(jp: str) -> str:
    return hashlib.sha1(jp.encode("utf-8")).hexdigest()[:10]


def load() -> TranslationCatalog:
    font = FontEngine(ROOT / "workspace/unpacked/data/font01.NFTR")
    cat = TranslationCatalog(font)
    cat.load_from_csv(CSV)
    return cat


def validate(jp: str, en: str) -> list[str]:
    errs = []
    if not en.strip():
        errs.append("empty")
    if PRINTF_RE.findall(jp) != PRINTF_RE.findall(en):
        errs.append("printf")
    if COLOR_RE.findall(jp) != COLOR_RE.findall(en):
        errs.append("color")
    if Counter(c for c in jp if c in CUSTOM_GLYPHS) != Counter(c for c in en if c in CUSTOM_GLYPHS):
        errs.append("glyph")
    try:
        en.encode("cp932")
    except UnicodeEncodeError as ex:
        errs.append(f"encoding:{en[ex.start:ex.end]!r}")
    leftover = [c for c in en if JP_RE.match(c) and c not in CUSTOM_GLYPHS]
    if leftover:
        errs.append("japanese_left:" + "".join(leftover[:5]))
    return errs


def cmd_export(size: int) -> None:
    cat = load()
    uniq: "OrderedDict[str, dict]" = OrderedDict()
    for e in cat.entries:
        if e.status.lower() == "ignored":
            continue
        if e.original_jp not in uniq:
            uniq[e.original_jp] = {
                "k": key_of(e.original_jp),
                "file": Path(e.file_path).stem,
                "max_chars": max(8, e.max_px // 5),
                "max_lines": e.max_lines,
                "jp": e.original_jp,
            }
    items = list(uniq.values())
    out = BATCH_DIR / "in"
    out.mkdir(parents=True, exist_ok=True)
    for f in out.glob("*.json"):
        f.unlink()
    # split at file boundaries when possible to preserve context
    batches, cur = [], []
    for it in items:
        if len(cur) >= size and (it["file"] != cur[-1]["file"] or len(cur) >= size * 1.3):
            batches.append(cur)
            cur = []
        cur.append(it)
    if cur:
        batches.append(cur)
    for i, b in enumerate(batches, start=1):
        (out / f"batch_{i:02d}.json").write_text(json.dumps(b, ensure_ascii=False, indent=0), encoding="utf-8")
    print(f"{len(items)} unique phrases in {len(batches)} batches -> {out}")


def cmd_import() -> None:
    cat = load()
    results: dict[str, str] = {}
    for f in sorted((BATCH_DIR / "out").glob("batch_*.json")):
        for it in json.loads(f.read_text(encoding="utf-8")):
            results[it["k"]] = it["en"].replace("\r\n", "\n")
    stats, bad = Counter(), []
    for e in cat.entries:
        if e.status.lower() == "ignored":
            continue
        en = results.get(key_of(e.original_jp))
        if en is None:
            stats["missing"] += 1
            continue
        errs = validate(e.original_jp, en)
        if errs:
            stats["invalid"] += 1
            bad.append({"id": e.entry_id, "k": key_of(e.original_jp), "jp": e.original_jp, "en": en, "errors": errs})
            continue
        e.translation_en = en
        e.status = "Draft"
        e.notes = "batch v2"
        cat.audit_entry(e)
        stats["applied"] += 1
    # Manual overrides (password puzzles whose kana answers are read from the user's ROM)
    from blazer_drive.rom import RomHandler

    overrides = load_overrides(RomHandler.pristine_files(RomHandler.find_default_rom()))
    for e in cat.entries:
        en = overrides.get(e.entry_id)
        if en is None:
            continue
        errs = [x for x in validate(e.original_jp, en) if not x.startswith("japanese_left")]
        if errs:
            bad.append({"id": e.entry_id, "override": True, "errors": errs})
            continue
        e.translation_en, e.status, e.notes = en, "Approved", "override (puzzle)"
        cat.audit_entry(e)
        stats["overrides"] += 1
    cat.export_csv(CSV)
    cat.export_excel(XLSX)
    stats["public_rows"] = export_public(cat)
    (BATCH_DIR / "import_errors.json").write_text(json.dumps(bad, ensure_ascii=False, indent=1), encoding="utf-8")
    print(dict(stats), "errors ->", BATCH_DIR / "import_errors.json")
