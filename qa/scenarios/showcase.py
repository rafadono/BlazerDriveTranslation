"""Japanese / English comparison images for the README (real DeSmuME screenshots).

Both ROMs are played from their checkpoints with the same input movie; dialogue lines are
60 fps (limiter on), so the screenshots land on the same frames.
Requires checkpoints for both ROMs (qa/scenarios/checkpoints.py --rom ...).

    python qa/scenarios/showcase.py
"""
import sys
import time
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "qa/harness"))
sys.path.insert(0, str(ROOT / "qa/scenarios"))
import checkpoints  # noqa: E402
from dsm import Movie  # noqa: E402
from emu import DeSmuME, screens  # noqa: E402

JP = ROOT / "rom/blazer_drive_jp.nds"
EN = ROOT / "rom/blazer_drive_translated.nds"
OUT = ROOT / "docs/images"
WORK = ROOT / "qa/out/showcase"


def is_blank(img: Image.Image) -> bool:
    """PrintWindow sometimes returns an empty light-grey frame instead of the game."""
    small = img.convert("RGB").resize((64, 96))
    grey = sum(1 for r, g, b in small.getdata() if abs(r - 240) < 8 and abs(g - 240) < 8 and abs(b - 240) < 8)
    return grey > 0.85 * 64 * 96


def burst(rom: Path, state: str, movie: Movie, seconds: float, period: float = 0.25) -> list[Image.Image]:
    """Plays `movie` from the checkpoint at real speed and captures every `period` s."""
    WORK.mkdir(parents=True, exist_ok=True)
    mv = WORK / f"{rom.stem}_{state}.dsm"
    movie.save(mv, rom.name, from_state=checkpoints.state(state, rom))
    emu = DeSmuME(rom, mv, no_limiter=True, frame_counter=False)
    t0, shots = time.time(), []
    try:
        while time.time() - t0 < seconds:
            time.sleep(period)
            emu.dismiss_dialogs()
            img = screens(emu.capture()).resize((256, 384), Image.LANCZOS)
            if not is_blank(img):
                shots.append(img)
    finally:
        emu.kill()
    return shots


TEXT_BOX = (60, 347, 246, 374)  # text lines inside the dialogue box (256x384 coordinates)


def text_amount(img: Image.Image) -> int:
    return sum(1 for p in img.crop(TEXT_BOX).convert("L").getdata() if p > 200)


def split_dialogs(shots: list[Image.Image], min_text: int = 20) -> list[Image.Image]:
    """One image per dialogue line: a new line starts when the text amount drops sharply
    (the box is cleared and the next line is typed); keeps the most complete frame."""
    best: list[Image.Image] = []
    cur, cur_score = None, 0
    for img in shots:
        score = text_amount(img)
        if cur is not None and score < cur_score * 0.4:
            if cur_score >= min_text:
                best.append(cur)
            cur, cur_score = None, 0
        if score >= cur_score:
            cur, cur_score = img, score
    if cur is not None and cur_score >= min_text:
        best.append(cur)
    return best


def pair(jp: Image.Image, en: Image.Image, crop: tuple[int, int, int, int] | None = None, z: int = 2) -> Image.Image:
    if crop:
        jp, en = jp.crop(crop), en.crop(crop)
    w, h = jp.size
    canvas = Image.new("RGB", (w * 2 * z + 24, h * z + 30), (18, 20, 28))
    d = ImageDraw.Draw(canvas)
    for i, (im, label) in enumerate(((jp, "Original (JP)"), (en, "Blazer Drive - English"))):
        x = 8 + i * (w * z + 8)
        canvas.paste(im.resize((w * z, h * z), Image.NEAREST), (x, 24))
        d.text((x, 6), label, fill=(255, 210, 90))
    return canvas


def stack(rows: list[Image.Image]) -> Image.Image:
    sheet = Image.new("RGB", (rows[0].width, sum(r.height for r in rows)), (18, 20, 28))
    y = 0
    for r in rows:
        sheet.paste(r, (0, y))
        y += r.height
    return sheet


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--pairs", default="", help="JP:EN line indices to compose, e.g. 0:0,1:2")
    args = ap.parse_args()
    args.pairs = [tuple(map(int, x.split(":"))) for x in args.pairs.split(",") if x]
    OUT.mkdir(parents=True, exist_ok=True)
    # 1) File-select panel (checkpoint 1): last clean frame of a short burst
    panel = Movie().wait(600)
    p_jp = burst(JP, "cp01_title_newgame", panel, 5)[-1]
    p_en = burst(EN, "cp01_title_newgame", panel, 5)[-1]
    pair(p_jp, p_en, (0, 192, 256, 384)).save(WORK / "compare_file_select.png")  # local only (JP)
    p_en.crop((0, 192, 256, 384)).resize((512, 384), Image.NEAREST).save(OUT / "screenshot_file_select_en.png")

    # 2) Prologue dialogue (checkpoint 2): same inputs on both ROMs, paired by line order
    m = Movie().wait(100)
    for _ in range(10):
        m.press("a", hold=6, release=174)
    d_jp = [d for d in split_dialogs(burst(JP, "cp02_prologue_dialog", m, 34)) if not is_blank(d)]
    d_en = [d for d in split_dialogs(burst(EN, "cp02_prologue_dialog", m, 34)) if not is_blank(d)]
    for tag, lines in (("jp", d_jp), ("en", d_en)):
        for k, img in enumerate(lines):
            img.save(WORK / f"line_{tag}_{k:02d}.png")
    print(f"dialogue lines: JP={len(d_jp)} EN={len(d_en)} -> {WORK}/line_*.png")
    if args.pairs:
        rows = [pair(d_jp[a], d_en[b], (0, 320, 256, 384)) for a, b in args.pairs]
        stack(rows).save(WORK / "compare_dialogs.png")  # local only (JP)
    print("images in", OUT, "and", WORK)


if __name__ == "__main__":
    main()
