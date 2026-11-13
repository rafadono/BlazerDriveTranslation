# QA with a real emulator (DeSmuME 0.9.13)

The QA runs the real emulator on the built ROM. Screenshots are taken from its window
with Win32 `PrintWindow`; nothing is simulated.

## Components (`qa/`)

| File | Purpose |
|---|---|
| `harness/emu.py` | Launches DeSmuME, captures the window, sends menu commands (pause, save/load slot), accepts warning dialogs and detects the end of a movie (`(finished)` in the frame counter). |
| `harness/dsm.py` | Input movies (`.dsm`): buttons and touch screen per frame, optionally starting from a save state. |
| `harness/run.py` | Plays a movie and captures every N seconds. When the movie ends it pauses and can save a state. |
| `harness/sheets.py` | Contact sheets: an overview, or dialogue boxes only. |
| `scenarios/checkpoints.py` | Creates save states for the current build: `cp01` (the new-game prompt) and `cp02` (the first prologue dialogue). |
| `scenarios/prologue_dialogs.py` | Steps through the prologue dialogue starting from `cp02`. |
| `scenarios/showcase.py` | JP/EN comparison images for `docs/images`. Both ROMs replay the same inputs from their checkpoints. Each detected dialogue line is saved to `qa/out/showcase/line_{jp,en}_NN.png`, and `--pairs 0:1,2:3` composes the comparison in `qa/out/showcase/` from matching lines. Only English-only images go to `docs/images`. |

## Usage

```bash
make emulators        # once: DeSmuME into tools/emulators/
make all              # build the translated ROM
make qa-checkpoints   # ~5 min: save states for THIS build
make qa-dialogs       # ~2 min: prologue dialogue -> qa/out/prologue_dialogs/*/dialogs.png
make showcase         # JP/EN comparison images (needs checkpoints for both ROMs)
```

## Things to know

* **Save states are tied to one build.** The game caches the CPK file tables in RAM, so
  a state from another build reads wrong offsets (black screen). Regenerate the
  checkpoints after every `make all`. Each state is named after its ROM, and a
  `.rom_sha1` file next to it records the ROM's SHA-1.
* **Movies** use LF line endings, and each frame is written twice: DeSmuME 0.9.13
  consumes an extra line per record. The `savestate 1` header makes a movie start from
  `<movie>.dst`.
* On the first boot without a save, the full intro plays (~5,900 frames). The title
  screen is passed by **touching** the screen; A and Start do nothing.
* Screenshots are taken every 10 s while creating checkpoints (cutscenes) and every 5 s
  by default.
* The harness sets `FrameCounter=1` in `desmume.ini`, because end-of-movie detection
  relies on it.
* DeSmuME does not ship `lua51.dll`, so Lua scripting is not used.

## Verified findings

| # | Finding |
|---|---|
| 1 | The original translated ROM did not boot because `arm9.bin` was corrupted. Isolated by building cross-combined ROMs (original arm9 + new CPKs boots; patched arm9 + original CPKs does not). |
| 2 | CriPakTools corrupted the CPK TOC. |
| 3 | ASCII advances 6 px, not 5, so lines overflowed. Fixed with the real measurement, then with the VWF. |
| 4 | With the VWF and `#` pagination, no line overflows its box. |
| 5 | The file-select screen is in English (NEW GAME, MISSIONS, BACK…): `images/screenshot_en.png`. |

Screenshots that show the Japanese original are written only to `qa/out/` (git-ignored).
