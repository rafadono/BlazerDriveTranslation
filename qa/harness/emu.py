"""Real control of DeSmuME 0.9.13 (Windows) from Python: launch it, capture the window,
send menu commands (save/load state, pause) and detect the end of a movie.

Nothing is simulated: it is the real emulator; screenshots come from the window via PrintWindow.
"""
import ctypes
import ctypes.wintypes as wt
import shutil
import subprocess
import time
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
EXE = ROOT / "tools/emulators/desmume/DeSmuME_0.9.13_x64.exe"
STATE_DIR = EXE.parent / "StateSlots"

user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32")

WM_COMMAND, WM_CLOSE = 0x0111, 0x0010
MENU_PAUSE = 113
MENU_SAVE_SLOT = {1: 140, 2: 141, 3: 142, 4: 143, 5: 144, 6: 145, 7: 146, 8: 147, 9: 148, 0: 139}
MENU_LOAD_SLOT = {1: 150, 2: 151, 3: 152, 4: 153, 5: 154, 6: 155, 7: 156, 8: 157, 9: 158, 0: 149}

EnumWindowsProc = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wt.DWORD), ("biWidth", wt.LONG), ("biHeight", wt.LONG), ("biPlanes", wt.WORD),
                ("biBitCount", wt.WORD), ("biCompression", wt.DWORD), ("biSizeImage", wt.DWORD),
                ("biXPelsPerMeter", wt.LONG), ("biYPelsPerMeter", wt.LONG), ("biClrUsed", wt.DWORD),
                ("biClrImportant", wt.DWORD)]


def _windows_of(pid: int) -> list[int]:
    found = []

    def cb(hwnd, _):
        p = wt.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(p))
        if p.value == pid and user32.IsWindowVisible(hwnd):
            found.append(hwnd)
        return True

    user32.EnumWindows(EnumWindowsProc(cb), 0)
    return found


def _click_ok(dialog: int) -> None:
    """Clicks the message box button (BM_CLICK on its child button)."""
    buttons = []

    def cb(h, _):
        if _class(h) == "Button":
            buttons.append(h)
        return True

    user32.EnumChildWindows(dialog, EnumWindowsProc(cb), 0)
    for b in buttons[:1]:
        user32.SendMessageW(b, 0x00F5, 0, 0)  # BM_CLICK


def _class(hwnd: int) -> str:
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf, 256)
    return buf.value


def _title(hwnd: int) -> str:
    buf = ctypes.create_unicode_buffer(512)
    user32.GetWindowTextW(hwnd, buf, 512)
    return buf.value


def set_frame_counter(on: bool) -> None:
    """Shows/hides the OSD frame counter (needed to detect the end of a movie)."""
    import re

    ini = EXE.parent / "desmume.ini"
    txt = ini.read_text(encoding="utf-8", errors="ignore") if ini.exists() else ""
    if re.search(r"FrameCounter=\d", txt):
        txt = re.sub(r"FrameCounter=\d", f"FrameCounter={int(on)}", txt)
    else:
        txt += f"\n[Display]\nFrameCounter={int(on)}\n"
    ini.write_text(txt, encoding="utf-8")


class DeSmuME:
    def __init__(self, rom: Path, movie: Path | None = None, no_limiter: bool = True, frameskip: int = 0,
                 frame_counter: bool = True):
        set_frame_counter(frame_counter)
        args = [str(EXE), "--disable-sound"]
        if no_limiter:
            args.append("--disable-limiter")
        if frameskip:
            args += ["--frameskip", str(frameskip)]
        if movie:
            args += ["--play-movie", str(Path(movie).resolve())]
        args.append(str(Path(rom).resolve()))
        self.rom = Path(rom).resolve()
        self.proc = subprocess.Popen(args, cwd=str(EXE.parent))
        self.hwnd = 0
        for _ in range(80):
            time.sleep(0.25)
            for h in _windows_of(self.proc.pid):
                if _class(h) == "DeSmuME":  # the modal warning has the same title
                    self.hwnd = h
                elif _class(h) == "#32770":  # save state warning from another build: accept it
                    _click_ok(h)
            if self.hwnd:
                break
        if not self.hwnd:
            self.kill()
            raise RuntimeError("The DeSmuME window did not appear")

    # --- control -----------------------------------------------------------------
    def menu(self, cmd_id: int) -> None:
        user32.PostMessageW(self.hwnd, WM_COMMAND, cmd_id, 0)

    def extra_windows(self) -> list[str]:
        return [_title(h) for h in _windows_of(self.proc.pid) if h != self.hwnd]

    def dismiss_dialogs(self) -> list[str]:
        """Accepts modal warnings (e.g. 'savestate does not match the ROM'): sends IDOK."""
        texts = []
        for h in _windows_of(self.proc.pid):
            if h == self.hwnd:
                continue
            buf = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(h, buf, 256)
            if buf.value == "#32770" and _title(h).startswith("DeSmuME"):
                texts.append(_title(h))
                _click_ok(h)
        return texts

    def alive(self) -> bool:
        return self.proc.poll() is None

    def kill(self) -> None:
        if self.proc.poll() is None:
            self.proc.kill()
            self.proc.wait(10)

    def slot_file(self, slot: int) -> Path:
        return STATE_DIR / f"{self.rom.stem}.ds{slot}"

    def save_slot(self, slot: int, timeout: float = 10) -> Path:
        f = self.slot_file(slot)
        before = f.stat().st_mtime if f.exists() else 0
        self.menu(MENU_SAVE_SLOT[slot])
        t0 = time.time()
        while time.time() - t0 < timeout:
            time.sleep(0.25)
            if f.exists() and f.stat().st_mtime != before and f.stat().st_size > 0:
                time.sleep(0.5)
                return f
        raise RuntimeError(f"Save state {f} was not written")

    # --- capture -----------------------------------------------------------------
    def capture(self) -> Image.Image:
        rect = wt.RECT()
        user32.GetWindowRect(self.hwnd, ctypes.byref(rect))
        w, h = rect.right - rect.left, rect.bottom - rect.top
        hdc_win = user32.GetWindowDC(self.hwnd)
        hdc = gdi32.CreateCompatibleDC(hdc_win)
        bmp = gdi32.CreateCompatibleBitmap(hdc_win, w, h)
        gdi32.SelectObject(hdc, bmp)
        user32.PrintWindow(self.hwnd, hdc, 2)
        bi = BITMAPINFOHEADER(ctypes.sizeof(BITMAPINFOHEADER), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
        buf = ctypes.create_string_buffer(w * h * 4)
        gdi32.GetDIBits(hdc, bmp, 0, h, buf, ctypes.byref(bi), 0)
        gdi32.DeleteObject(bmp)
        gdi32.DeleteDC(hdc)
        user32.ReleaseDC(self.hwnd, hdc_win)
        return Image.frombuffer("RGB", (w, h), buf, "raw", "BGRX", 0, 1)


def screens(window_img: Image.Image) -> Image.Image:
    """Crops the window to the two DS screens (256x384, scaled)."""
    w, h = window_img.size
    return window_img.crop((8, h - 8 - int((w - 16) * 1.5), w - 8, h - 8))


FINISHED_TEMPLATE = Path(__file__).with_name("finished_template.txt")


def _text_mask(img: Image.Image, x0: int = 0, x1: int = 404) -> list[list[bool]]:
    """OSD text mask: white pixel with a nearby black outline (frame counter band)."""
    band = img.convert("RGB").crop((x0, 30, x1, 60))
    px = band.load()
    w, h = band.size
    near = ((2, 0), (-2, 0), (0, 2), (0, -2), (1, 1), (-1, -1), (1, -1), (-1, 1))
    return [[min(px[x, y]) > 200 and any(0 <= x + dx < w and 0 <= y + dy < h and max(px[x + dx, y + dy]) < 70
                                          for dx, dy in near) for x in range(w)] for y in range(h)]


def build_finished_template(sample: Path, x0: int, x1: int) -> None:
    """Crops the word '(finished)' from a real screenshot in which it appears."""
    m = _text_mask(Image.open(sample), x0, x1)
    FINISHED_TEMPLATE.write_text("\n".join("".join("#" if v else "." for v in row) for row in m), encoding="utf-8")


def movie_finished(screen_img: Image.Image) -> bool:
    """True if the OSD shows '(finished)': searches for the template by sliding it horizontally."""
    tpl = [[c == "#" for c in row] for row in FINISHED_TEMPLATE.read_text(encoding="utf-8").split("\n")]
    th, tw = len(tpl), len(tpl[0])
    ones = [(y, x) for y in range(th) for x in range(tw) if tpl[y][x]]
    m = _text_mask(screen_img)
    h, w = len(m), len(m[0])
    best = 0.0
    for ox in range(0, w - tw):
        hit = sum(1 for y, x in ones if m[y][x + ox])
        extra = sum(1 for y in range(th) for x in range(ox, ox + tw) if m[y][x]) - hit
        score = (hit - extra) / len(ones)
        best = max(best, score)
    return best > 0.7


def make_state_movie(base_state: Path, movie: Path) -> None:
    """Copies the save state next to the movie (.dst) so DeSmuME starts it from there."""
    shutil.copyfile(base_state, movie.with_suffix(".dst"))
