# English style guide

Rules for every English line in `strings_en.csv` and `overrides_en.json`. The full
source-term glossary (Japanese → English) is generated locally next to the catalogue
(`workspace/catalog/`) and is never committed.

## Technical rules (the game shows garbage or breaks otherwise)

1. **Control codes are copied verbatim**, with the same count and order:
   colour `$1c … $c` (`$3c`, `$4c`, `$6c`, `$8c`, `$9c`…), a lone `$`, and printf
   arguments `%s %d %02d %03d %04d %c`. `#` is a page break inside a message box.
2. **Custom glyphs** are written as `{g:XXXX}` tokens (their Shift-JIS code). The font
   draws icons there: `{g:9943}`–`{g:994F}` are the Roman numerals Ⅰ–ⅩⅢ (wards are
   written `Ward {g:9945}` → "Ward Ⅲ"), `{g:98EF}`→ `{g:98F2}` are arrows, `{g:98E7}`
   `!`, `{g:98FB}` `!!`. Keep every token the source line has.
3. **ASCII only**: `...` not `…`, `-` not `—`, `~` not `～`, straight quotes.
4. **Width:** a dialogue box holds about 36 characters per line and 2 lines (the font is
   variable-width). Longer text is paginated automatically, but prefer short lines.
5. Never leave a line empty. Interjections and ellipses are translated too.
6. Password puzzles keep the in-game answer through `{script:NNN:i}` placeholders in
   `overrides_en.json` (see `docs/FORMATS.md`).

## Canonical names

**Characters:** Shirou (nickname "Shiro" from Tamaki), Tamaki ("Tama" from Shirou),
Pettan (sounds: Peta, Petata, Pepe), Kuroki, Shunya, Jonathan ("old man" to Shirou),
Albert, Kouta ("Master Kouta" to his gang), Daichi, Tsurugi (archaic speech), Yaiba
(speaks English lines), Shiihara (the Governor), Meg, Karen, Misora, Apple (talks about
herself in the third person), Akkun ("Fugo"), Holly, Yuma, Erina Garland, Shinpo.

**Terms:** MYSTICKER (always caps), Blazer, rogue Blazer, Guardian, Team Fenrir, Mission
(Mission Clear!), Blaze Out!!, Drive / Drive Skill, ARMS, LEGEND, Storage, arm / right arm
/ left arm, Judge, Tension / Tension Drum / Tension Level, Combination, Friend, Grunt Deck,
Grannark, NEXT, Pinpara Weekly, Gate / First Gate / Second Gate, the Other Side, Heaven
MYSTICKER, Link Battle, elements Fire / Ice / Wind / Electric / Dark / Neutral.

**Places and groups:** Ward {g:9945} (and other wards), City Hall, Monorail Line,
Frozen Park, Temple of the Sun, Scorching Desert, Central Falls, Volganic Road, Wing of the
Earth, Pink Paradise, Team Ozora, Top Dogs, Desstickers, the Blue Snake Gang, the Poison
Scorpions, the Marmots gang, Guardian Weekly, Coeurl / Frigid Coeurl, Valiant,
Thunder King, Soul Eater.

## Style

* Natural, casual English for a shonen action game (ages 10+). Shirou is brash; Tamaki is
  cheerful; robot and keypad voices are in ALL CAPS.
* Keep jokes and tone rather than word order. Mission titles and menu labels use Title
  Case and stay short (`Order: ...` for mission orders).
* The same source line always gets the same English line.
