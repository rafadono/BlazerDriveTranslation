"""Contact sheets with the screenshots of a run (visual evidence).

    python qa/harness/sheets.py DIR            # overview sheet (sheet.png)
    python qa/harness/sheets.py DIR --dialogs  # only distinct dialog boxes (dialogs.png)
"""
import argparse
from pathlib import Path

from PIL import Image, ImageDraw

PATTERN = "[0-9]*_t*.png"


def overview(d: Path, cols: int = 8, step: int = 1) -> Path:
    ps = sorted(d.glob(PATTERN))[::step]
    ims = [Image.open(p) for p in ps]
    w, h = ims[0].size
    rows = (len(ims) + cols - 1) // cols
    s = Image.new("RGB", (w * cols, rows * (h + 14)), (20, 20, 20))
    dr = ImageDraw.Draw(s)
    for i, (p, im) in enumerate(zip(ps, ims)):
        x, y = (i % cols) * w, (i // cols) * (h + 14)
        s.paste(im, (x, y + 14))
        dr.text((x + 2, y + 1), p.stem, fill=(255, 255, 0))
    out = d / "sheet.png"
    s.save(out)
    return out


def dialogs(d: Path, top: float = 0.84, scale: int = 2, limit: int = 40) -> Path:
    """Bottom band (dialog box) of each screenshot, skipping repeated identical boxes."""
    crops, last = [], None
    for p in sorted(d.glob(PATTERN)):
        im = Image.open(p)
        w, h = im.size
        c = im.crop((0, int(h * top), w, h))
        sig = c.resize((48, 8)).tobytes()
        if sig != last:
            crops.append((p.stem, c))
            last = sig
    crops = crops[:limit]
    W, H = crops[0][1].size
    out = Image.new("RGB", (W * scale * 2, (H * scale + 12) * ((len(crops) + 1) // 2)), (20, 20, 20))
    dr = ImageDraw.Draw(out)
    for i, (n, c) in enumerate(crops):
        x, y = (i % 2) * W * scale, (i // 2) * (H * scale + 12)
        out.paste(c.resize((W * scale, H * scale), Image.NEAREST), (x, y + 12))
        dr.text((x + 2, y), n, fill=(255, 255, 0))
    f = d / "dialogs.png"
    out.save(f)
    return f


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("dir")
    ap.add_argument("--dialogs", action="store_true")
    ap.add_argument("--step", type=int, default=1)
    a = ap.parse_args()
    print(dialogs(Path(a.dir)) if a.dialogs else overview(Path(a.dir), step=a.step))
