"""Graphics patches: redraws the Japanese text in .sbd textures in English and generates the
variable-width font. Writes the modified files to workspace/patched (picked up by `build`).

    python -m blazer_drive gfx [--preview DIR]

Each patch: file (catalog path), texture index, box (x, y, w, h) and text.
The boxes were taken from the original texture, enlarged with a grid (workspace/textures/).
"""
from pathlib import Path

from PIL import Image, ImageDraw

from blazer_drive.font_patch import write_vwf
from blazer_drive.gfx_text import redraw
from blazer_drive.rom import RomHandler
from blazer_drive.sbd import Sbd

ROOT = Path(__file__).resolve().parents[1]

PATCHES: dict[str, list[tuple[int, tuple[int, int, int, int], str]]] = {
    # Save/game select screen (verified in the emulator)
    "cpk_extracted/system/load.sbd": [
        # texture 1: label atlas for the file panel
        (1, (0, 10, 37, 11), "MISSIONS"),     # "mission" label (the game leaves a gap before the "clear" piece)
        (1, (36, 21, 28, 10), ""),            # "clear" piece, emptied (x<36 is the edge of the Y in PLAY)
        (1, (37, 10, 27, 11), "ACK"),         # "-doru" piece ("mo" + "doru" = "Back")
        (1, (0, 53, 11, 11), "B"),            # "mo" piece
        (1, (0, 31, 52, 11), "DELETE"),       # "data clear" label
        # texture 6: "Back" button (arrow + label)
        (6, (19, 1, 30, 12), "BACK"),
        # texture 11: modes
        (11, (0, 0, 128, 16), "EXTRA MISSION"),
        (11, (0, 16, 128, 16), "TUTORIAL"),
        (11, (0, 32, 128, 16), "FREE MISSION"),
        (11, (0, 48, 128, 16), "NEW GAME"),
        # texture 12: chapter titles
        (12, (0, 0, 128, 16), "GUARDIAN"),
        (12, (0, 16, 128, 16), "RIVAL"),
        (12, (0, 32, 128, 16), "FRIENDSHIP"),
        (12, (0, 48, 128, 16), "A NEW STEP"),
        (12, (0, 64, 128, 16), "HEAVEN STIRS"),
        (12, (0, 80, 128, 16), "BLAZER"),
        (12, (0, 96, 128, 16), "EACH ONE'S POWER"),
    ],
}


def preview(name: str, before: Sbd, after: Sbd, out_dir: Path) -> Path:
    idxs = sorted({p[0] for p in PATCHES[name]})
    tiles = []
    for i in idxs:
        a, b = before.decode(before.textures[i]), after.decode(after.textures[i])
        tile = Image.new("RGBA", (a.width * 2 + 8, a.height), (50, 50, 80, 255))
        tile.alpha_composite(a, (0, 0))
        tile.alpha_composite(b, (a.width + 8, 0))
        tiles.append(tile)
    W, H = max(t.width for t in tiles), sum(t.height + 4 for t in tiles)
    sheet = Image.new("RGBA", (W, H), (20, 20, 20, 255))
    y = 0
    for t in tiles:
        sheet.alpha_composite(t, (0, y))
        y += t.height + 4
    out = out_dir / (Path(name).stem + "_preview.png")
    sheet.resize((W * 3, H * 3), Image.NEAREST).save(out)
    return out


def apply(rom: Path, patched_dir: Path, preview_dir: Path | None = None) -> None:
    pristine = RomHandler.pristine_files(rom)
    for name, patches in PATCHES.items():
        before = Sbd(pristine[name])
        s = Sbd(pristine[name])
        for tex, box, text in patches:
            redraw(s, tex, box, text)
        target = patched_dir / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(bytes(s.data))
        print(f"{name}: {len(patches)} texts redrawn")
        if preview_dir:
            preview_dir.mkdir(parents=True, exist_ok=True)
            print("  preview:", preview(name, before, s, preview_dir))
    font = write_vwf(ROOT / "workspace/unpacked/data/font01.NFTR", patched_dir / "data/font01.NFTR")
    print("VWF font:", font)
