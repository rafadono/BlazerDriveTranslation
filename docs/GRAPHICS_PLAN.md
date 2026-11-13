# Plan: translating the remaining graphics

All game text stored as *text* (19,826 strings) is already translated. What remains is
text drawn **inside images**. This plan comes from a full inventory of the original ROM:
`python tools/gfx_inventory.py` decodes every texture of the 867 `.sbd` containers
(6,508 textures) into labelled contact sheets under `workspace/gfx_inventory/`
(git-ignored), and each sheet was reviewed by hand.

## Inventory summary

| Area (CPK folder) | Textures | Japanese text found | Priority |
|---|---:|---|---|
| `system` (title, file select, keyboard) | 49 | file panel **done**; keyboard screen (`swkb.sbd`: delete/space/all, confirm, Back) | P1 |
| `menu` (main menu `menu_top`, `msin`) | 49 | menu labels (Storage equip, Policy equip, Drive Skill equip, Data, Save, Mission, Back), ward badges `Ward Ⅰ…Ⅹ` | P1 |
| `mssl` (mission select) | 39 | chapter titles and mode labels (same art as the file panel), Back | P1 |
| "Back" button (`↪ モドル`) | ~15 copies | the same button in system, menu, mssl, strg, dtbs, shop, policy_board, skrd, battle | P1 (one design, many files) |
| `strg` (storage / deck edit) | 129 | sort, clear, name, edit/set/copy/delete, Back | P2 |
| `policy_board` (AI tactics) | 44 | tactic tags: Attack, Defense, Over-DF, Technique, Extra, HP Up, Support, Partner | P2 |
| `shop` | 86 | shop title, buy/sort/repair, "MYSTICKER Pack", Back | P2 |
| `dtbs` (database / collection) | 91 | info pack, character/base/data tabs, sort, clear, shop, "Guardian / S-Me" tags | P2 |
| `battle/result`, `battle/select_player`, `battle/main` | ~80 | revenge/retire, result lists (vs COM, tag start, normal/custom rule), Back | P2 |
| `battle/avant` (ARMS cut-ins) | 220 | ~22 ARMS names: kanji epithet + katakana name (the English name already appears on the left) | P3 |
| `skrd`, `msen`, `message`, `common`, `ending`, `battle_mode` | ~110 | a few labels each (to confirm per screen) | P3 |
| `network` (Wi-Fi) | 440 | lobby/ranking labels; Nintendo WFC is offline, so low value | P4 |
| `battle/*` effects and sprites | ~5,000 | almost all art or already English (B-DRIVE, OVER DEFENSE, YOU WIN!!) | — |

Not yet decoded (need reverse engineering first):

| Format | Count | Likely content |
|---|---:|---|
| `.5bg` backgrounds | 540 | title/top screens, logos, menu backgrounds; some may contain Japanese text |
| `.trd` / `.ord` (`DRRL`) standalone textures | 3,697 files | card art, buttons, area-name banners shown when entering a zone |

## Phases

### Phase 0 — tooling (prerequisite for everything else)

1. **Read the exact piece rectangles from `DCSD`.** Today the boxes in
   `blazer_drive/gfx_patches.py` are measured by hand from a zoomed texture. Decoding the
   cell/UV tables removes guesswork (no damaged neighbours) and shows where a label can be
   widened.
2. **Text styles.** Add presets to `gfx_text.redraw` for the 4–5 styles that repeat
   (yellow menu labels, orange chapter titles, white button text, red tactic tags), plus
   a small pixel font for 8 px labels, where TrueType rendering is too blurry.
3. **Decoders for `.5bg` and `DRRL` (`.trd/.ord`).** Same approach as `.sbd`: identify the
   palette, tiles and map, round-trip byte for byte, then reuse `redraw`.
4. **Screen-level QA.** One checkpoint per screen (main menu, storage, shop, tactics,
   battle result) in `qa/scenarios/`. This allows before/after captures of each patched
   screen.

### Phase 1 — screens seen in every session (P1)

* Main menu (`menu_top`, `msin`): menu labels and ward badges.
* Mission select (`mssl`): reuses the chapter and mode titles already drawn for `load.sbd`.
* "Back" button: draw once, apply to every copy (same texture layout).
* Keyboard / naming screen (`swkb.sbd`).
* Exit criterion: captures of each screen in English, with no damaged pieces.

### Phase 2 — gameplay UI (P2)

Storage edit, tactics board, shop, database and battle result screens. Most labels are
short (1–3 words). Tactic tags are fixed-size badges, so use abbreviations from the style
guide where needed ("Over-DF").

### Phase 3 — flavour (P3)

ARMS cut-in names (`battle/avant`), area-name banners (after the `DRRL` decoder), and the
remaining small screens (`skrd`, `msen`, `ending`…).

### Phase 4 — optional

Wi-Fi screens (`network`) and decorative backgrounds, only if the `.5bg` decoder shows
readable Japanese text.

## Rules

* Use only colours from the original palette. Keep the texture size; never move a piece
  outside its rectangle.
* English labels follow `translations/STYLE_GUIDE.md` (canonical names, Title Case).
* Graphics are generated from the user's ROM at build time (`python -m blazer_drive gfx`).
  The repository stores only the patch list (file, texture, box, English text), never
  the images.
