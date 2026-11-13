"""Inventory of texture graphics: decodes every texture inside the .sbd containers of the
original ROM and writes labelled contact sheets per folder (workspace/gfx_inventory/,
git-ignored because it contains game graphics).

    python tools/gfx_inventory.py [--folders system menu shop ...]

Each thumbnail is labelled ``<file>:<texture index>``, the same identifiers used by
``blazer_drive/gfx_patches.py``.
"""
import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PIL import Image, ImageDraw  # noqa: E402

from blazer_drive.rom import RomHandler  # noqa: E402
from blazer_drive.sbd import Sbd  # noqa: E402

OUT = ROOT / "workspace/gfx_inventory"
THUMB = 128


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--folders", nargs="*", help="CPK folders to include (default: all)")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    pristine = RomHandler.pristine_files(RomHandler.find_default_rom())
    by_folder: dict[str, list[tuple[str, int, Image.Image]]] = defaultdict(list)
    rows = []
    for name, data in sorted(pristine.items()):
        if not name.endswith(".sbd") or not name.startswith("cpk_extracted/"):
            continue
        folder = name.split("/")[1]
        if a.folders and folder not in a.folders:
            continue
        try:
            s = Sbd(data)
        except ValueError:
            continue
        for t in s.textures:
            if t.fmt not in (1, 2, 3, 4, 6, 7):
                continue
            img = s.decode(t)
            by_folder[folder].append((name.split("/", 2)[2], t.index, img))
            rows.append((name, t.index, t.fmt, t.width, t.height))
    with (OUT / "textures.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["file", "texture", "format", "width", "height"])
        w.writerows(rows)
    for folder, items in by_folder.items():
        cols = 10
        for page in range(0, len(items), 100):
            chunk = items[page : page + 100]
            rows_n = (len(chunk) + cols - 1) // cols
            sheet = Image.new("RGB", (cols * (THUMB + 4), rows_n * (THUMB + 16)), (40, 40, 60))
            d = ImageDraw.Draw(sheet)
            for i, (fname, idx, img) in enumerate(chunk):
                im = img.copy()
                im.thumbnail((THUMB, THUMB), Image.NEAREST)
                x, y = (i % cols) * (THUMB + 4), (i // cols) * (THUMB + 16)
                sheet.paste(im, (x, y + 14), im)
                d.text((x + 1, y + 1), f"{fname}:{idx}"[-24:], fill=(255, 255, 0))
            sheet.save(OUT / f"{folder}_{page // 100:02d}.png")
        print(f"{folder}: {len(items)} textures")
    print("inventory:", OUT)


if __name__ == "__main__":
    main()
