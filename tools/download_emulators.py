import io
import urllib.request
import zipfile
from pathlib import Path

EMU_DIR = Path("tools/emulators")
EMU_DIR.mkdir(parents=True, exist_ok=True)

DESMUME_URL = "https://github.com/TASEmulators/desmume/releases/download/release_0_9_13/desmume-0.9.13-win64.zip"
MELONDS_URL = "https://github.com/melonDS-emu/melonDS/releases/download/1.1/melonDS-1.1-windows-x86_64.zip"

headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

def download_and_extract(url: str, dest_folder: Path) -> None:
    dest_folder.mkdir(parents=True, exist_ok=True)
    print(f"Downloading {url}...")
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        content = resp.read()
    print(f"Downloaded ({len(content)} bytes). Extracting to {dest_folder}...")
    with zipfile.ZipFile(io.BytesIO(content)) as z:
        z.extractall(dest_folder)
    print("Extraction completed successfully.")

desmume_dir = EMU_DIR / "desmume"
if not (desmume_dir / "DeSmuME_0.9.13_x64.exe").exists():
    download_and_extract(DESMUME_URL, desmume_dir)
else:
    print("DeSmuME already exists.")

melonds_dir = EMU_DIR / "melonds"
if not (melonds_dir / "melonDS.exe").exists():
    download_and_extract(MELONDS_URL, melonds_dir)
else:
    print("melonDS already exists.")

