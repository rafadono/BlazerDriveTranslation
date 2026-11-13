"""Runs an input movie in the real DeSmuME, captures screenshots and optionally
saves a save state when it ends.

    python qa/harness/run.py ROM MOVIE OUTDIR [--every 5] [--max 600] [--save-slot N]
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from emu import MENU_PAUSE, DeSmuME, movie_finished, screens  # noqa: E402
from PIL import ImageChops


def _stable(a, b) -> bool:
    """Screens are equal, ignoring the frame counter band (top)."""
    a, b = a.crop((0, 70, a.width, a.height)), b.crop((0, 70, b.width, b.height))
    return ImageChops.difference(a, b).getbbox() is None


def run(rom, movie, outdir, every=5.0, max_seconds=600, save_slot=None, frameskip=2, keep_window=False,
        movie_frames=0):
    """Runs the movie without the speed limiter; when 'N/M (finished)' is detected in the OSD it
    pauses the emulator and, if requested, saves the state to the given slot."""
    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    emu = DeSmuME(Path(rom), Path(movie) if movie else None, no_limiter=True, frameskip=frameskip)
    min_t = movie_frames / 60.0 + 3
    prev = None
    t0, n, finished_hits, state = time.time(), 0, 0, None
    try:
        while time.time() - t0 < max_seconds:
            time.sleep(every)
            if not emu.alive():
                print("EMULATOR CLOSED"); break
            if emu.dismiss_dialogs():
                print("warning accepted (save state from another build of the ROM)")
                time.sleep(0.5)
            img = emu.capture()
            n += 1
            cur = screens(img)
            cur.save(out / f"{n:04d}_t{int(time.time() - t0):04d}s.png")
            extra = emu.extra_windows()
            if extra:
                print("EXTRA WINDOW:", extra)
            finished_hits = finished_hits + 1 if movie and movie_finished(cur) else 0
            prev = cur
            if finished_hits >= 1:
                emu.menu(MENU_PAUSE)
                time.sleep(1)
                print(f"movie finished after {int(time.time() - t0)} s")
                if save_slot is not None:
                    state = emu.save_slot(save_slot)
                    cur.save(out / "state_saved.png")
                    print("save state:", state)
                break
    finally:
        if not keep_window:
            emu.kill()
    print(f"screenshots: {n}")
    return state


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("rom"); ap.add_argument("movie"); ap.add_argument("outdir")
    ap.add_argument("--every", type=float, default=5.0)
    ap.add_argument("--max", type=int, default=600)
    ap.add_argument("--save-slot", type=int)
    ap.add_argument("--frameskip", type=int, default=2)
    ap.add_argument("--frames", type=int, default=0, help="movie length in frames (for --save-slot)")
    a = ap.parse_args()
    run(a.rom, a.movie if a.movie != "-" else None, a.outdir, a.every, a.max, a.save_slot, a.frameskip, movie_frames=a.frames)
