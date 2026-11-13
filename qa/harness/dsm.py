"""Generator of .dsm input movies for DeSmuME (--play-movie).

Per-frame format:  |0|RLDUTSBAYXWEG XXX YYY T|
  R=Right L=Left D=Down U=Up T=Start S=Select B A Y X W=R-shoulder E=L-shoulder G=debug
  XXX YYY = stylus on the bottom screen (0-255, 0-191), T = 1 if touching.
"""
from pathlib import Path

ORDER = "RLDUTSBAYXWEG"
ALIAS = {"right": "R", "left": "L", "down": "D", "up": "U", "start": "T", "select": "S",
         "b": "B", "a": "A", "y": "Y", "x": "X", "r": "W", "l": "E"}


class Movie:
    def __init__(self) -> None:
        self.frames: list[tuple[set, tuple | None]] = []

    def wait(self, n: int) -> "Movie":
        self.frames += [(set(), None)] * n
        return self

    def press(self, buttons: str, hold: int = 6, release: int = 14) -> "Movie":
        keys = {ALIAS[b.strip().lower()] for b in buttons.split("+")}
        self.frames += [(keys, None)] * hold
        return self.wait(release)

    def touch(self, x: int, y: int, hold: int = 6, release: int = 14) -> "Movie":
        self.frames += [(set(), (x, y))] * hold
        return self.wait(release)

    def mash(self, buttons: str, times: int, every: int = 30) -> "Movie":
        for _ in range(times):
            self.press(buttons, hold=6, release=every - 6)
        return self

    def __len__(self) -> int:
        return len(self.frames)

    def save(self, path: Path, rom_name: str = "rom.nds", from_state: Path | None = None) -> Path:
        """from_state: save state (.dsN/.dst) the movie starts from (copied as <movie>.dst)."""
        lines = ["version 1", "emuVersion 91300", "rerecordCount 0", f"romFilename {rom_name}",
                 "romChecksum 00000000", "romSerial NTR-YBDJ-JPN", "guid 00000000-0000-0000-0000-000000000000",
                 "useExtBios 0", "advancedTiming 1", "useExtFirmware 0", "firmNickname qa", "firmLanguage 1"]
        if from_state:
            import shutil
            shutil.copyfile(from_state, Path(path).with_suffix(".dst"))
            lines.append("savestate 1")
        # DeSmuME 0.9.13 consumes one extra line per record when parsing: each frame is
        # written twice so the duration matches (verified with the frame counter).
        for keys, tch in [f for f in self.frames for _ in (0, 1)]:
            pad = "".join(c if c in keys else "." for c in ORDER)
            x, y, t = (tch[0], tch[1], 1) if tch else (0, 0, 0)
            lines.append(f"|0|{pad}{x:03d} {y:03d} {t}|")
        path.write_bytes(("\n".join(lines) + "\n").encode("ascii"))  # LF only: CRLF desyncs the parser
        return path
