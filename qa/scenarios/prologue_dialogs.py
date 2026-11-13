"""Steps through the prologue dialogs from checkpoint 2 and generates the dialog box sheet.

    python qa/scenarios/prologue_dialogs.py [--rom ROM] [--presses 45]
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "qa/harness"))
sys.path.insert(0, str(ROOT / "qa/scenarios"))
import checkpoints  # noqa: E402
from dsm import Movie  # noqa: E402
from run import run  # noqa: E402
from sheets import dialogs  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rom", default=str(checkpoints.ROM))
    ap.add_argument("--presses", type=int, default=45)
    a = ap.parse_args()
    rom = Path(a.rom).resolve()
    out = ROOT / "qa/out/prologue_dialogs" / rom.stem
    out.mkdir(parents=True, exist_ok=True)
    m = Movie().wait(60)
    for _ in range(a.presses):
        m.press("a", hold=6, release=114)
    mv = out / "dialogs.dsm"
    m.save(mv, rom.name, from_state=checkpoints.state("cp02_prologue_dialog", rom))
    run(rom, mv, out, every=1.0, max_seconds=300, frameskip=0)
    print(dialogs(out))


if __name__ == "__main__":
    main()
