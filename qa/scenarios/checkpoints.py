"""Regenerates the test save states for the current ROM (they must be redone after every build:
the game caches the CPK file tables in RAM, and a state from another build reads
wrong offsets).

    python qa/scenarios/checkpoints.py [--rom ROM]

  <rom>__cp01_title_newgame.dst   "Start a new game in this game file?" prompt (from boot)
  <rom>__cp02_prologue_dialog.dst first prologue dialog, after the cutscenes (from cp01)
"""
import argparse
import hashlib
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "qa/harness"))
from dsm import Movie  # noqa: E402
from emu import DeSmuME  # noqa: E402
from run import run  # noqa: E402

ROM = ROOT / "rom/blazer_drive_translated.nds"  # can be changed with --rom
STATES = ROOT / "qa/states"
OUT = ROOT / "qa/out/checkpoints"


def rom_id() -> str:
    return hashlib.sha1(ROM.read_bytes()).hexdigest()[:12]


def make(name: str, movie: Movie, slot: int, from_state: Path | None, max_s: int, frameskip: int) -> Path:
    name = f"{ROM.stem}__{name}"
    OUT.mkdir(parents=True, exist_ok=True)
    mv = OUT / f"{name}.dsm"
    movie.save(mv, ROM.name, from_state=from_state)
    run(ROM, mv, OUT / name, every=10, max_seconds=max_s, save_slot=slot, frameskip=frameskip)
    src = DeSmuME.__new__(DeSmuME)
    src.rom = ROM
    dst = STATES / f"{name}.dst"
    shutil.copyfile(src.slot_file(slot), dst)
    (STATES / f"{name}.rom_sha1").write_text(rom_id())
    print("checkpoint:", dst)
    return dst


def state(name: str, rom: Path | None = None) -> Path:
    return STATES / f"{(rom or ROM).stem}__{name}.dst"


def main() -> None:
    global ROM
    ap = argparse.ArgumentParser()
    ap.add_argument("--rom", default=str(ROM))
    ROM = Path(ap.parse_args().rom).resolve()
    STATES.mkdir(parents=True, exist_ok=True)
    m = Movie().wait(5900)                       # full intro
    for _ in range(8):
        m.touch(128, 96, hold=10, release=50)    # TOUCH TO START
    m.wait(400)
    cp1 = make("cp01_title_newgame", m, 1, None, 600, 2)

    m = Movie().wait(20)
    m.touch(77, 160, hold=10, release=120)       # YES
    m.wait(6400)                                 # prologue cutscenes
    m.press("a", hold=6, release=200)
    make("cp02_prologue_dialog", m, 2, cp1, 900, 2)


if __name__ == "__main__":
    main()
