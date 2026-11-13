# Blazer Drive file formats (NDS, `CVZJ`)

Everything below was verified against the ROM and in the emulator. Each format is
implemented in `blazer_drive/` and covered by `tests/`.

## CPK archives (CRIWARE) — `blazer_drive/cpk.py`

* 87 `.cpk` archives in the NDS filesystem.
* The header and TOC are `@UTF` tables. They may be encrypted with the standard CRI XOR
  (seed `0x655F`, multiplier `0x4115`).
* File offsets are relative to `min(TocOffset, ContentOffset)`. Compression is CRILAYLA.
* **Repacking:** modified files are appended to the end of the archive. Only
  `FileOffset/FileSize/ExtractSize` are patched in place in the TOC. CriPakTools **must
  not be used**: it writes data over the TOC (it corrupted 339 bytes of
  `battle_msg.bmsg`).

## Message files `.bmsg` (magic `MPCT`) — `blazer_drive/bmsg.py`

```
0x00  'MPCT', u32 1, 0x18 zero bytes
0x20  u32 2, u32 N, u32 9, u32 0, u32 1, 0xFF padding up to 0x4C
0x4C  N x u32 id   |   N x u32 index   |   u32 0, u32 3
PT    N x (u32 id, u32 offset relative to PT)
...   strings: u32 length + Shift-JIS + 00, 4-byte aligned
...   'EOFC' footer (0x20 bytes)
```

* 136 files and 19,826 strings. The parser rebuilds them byte for byte.
* There are no global size fields, so strings can grow freely.
* Control codes: `$Nc … $c` (colour), `%s`, `%d`, `%02d`; `#` is a page break in the
  message box.

## Font `font01.NFTR` — `blazer_drive/font.py`, `blazer_drive/font_patch.py`

* 9×9 cells at 1 bpp. The engine adds 1 px after single-byte characters, so the
  original ASCII advances 6 px and kana/kanji 12 px. A 180 px dialogue box fits 15
  Japanese characters or 30 ASCII characters.
* **VWF:** `font_patch` sets each ASCII glyph's advance to its real width and redraws
  `M W m w` at 5 px. This fits 25–30 % more English text per line.
* Shift-JIS `0x98E4–0x994F` are **custom glyphs**: icons (arrows, card suits, `!!`, `!?`)
  and Roman numerals (`0x9943`–`0x994F` = Ⅰ–ⅩⅢ). Copy them verbatim; the published files
  store them as `{g:XXXX}` tokens. `0x9950–0x9957` replace kanji that are missing from the
  font (one of them means "trap"); translate those as normal text.

## Textures `.sbd` (magic `DCSD`) — `blazer_drive/sbd.py`, `blazer_drive/gfx_text.py`

Menus are drawn with DS 3D textures. Internal offsets are relative to the start of each
block + 0x10.

| Block | Contents |
|---|---|
| `DTXL` | n × (u8 format, u8, u8 log2(w/8), u8 log2(h/8), u16, u16, u32 offset, u32 size) |
| `DPAL` | n × (u32 format, u32 offset, u32 size, u32 size); BGR555 colours |
| `DTEX` | n × (u32 id, u16 texture, u16 palette) |

Texture formats: 1 = A3I5, 2 = 4 colours, 3 = 16, 4 = 256, 6 = A5I3, 7 = direct.
`gfx_text.redraw` clears a box and writes the English text using the gradient, outline
and shadow sampled from the texture itself. It only uses colours already in the
palette. The game has 867 `.sbd` files and 540 `.5bg` backgrounds.

## Event passwords

`script_336/563/575.bin` compare the player's input against fixed kana strings stored in
the script. The English clues must show those exact characters, so
`translations/overrides_en.json` uses `{script:NNN:i}` placeholders that are filled from
the user's ROM at build time (no game text is stored in the repository). Event 350 uses a
choice menu whose options live in the `.bmsg`, so it is translated normally.

## Left untouched

* `arm9.bin`: the old heuristic scanner mistook ARM code for Shift-JIS text. Injecting
  there stopped the game from booting.
* Script `.bin` files, and `.trd/.ord` textures that are not on the graphics patch list.
