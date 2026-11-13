"""Unit tests for the pipeline (python -m unittest discover -s tests).

Tests that need the original ROM (rom/*.nds, not versioned) are skipped if it is missing.
"""
import struct
import unittest
from pathlib import Path

from blazer_drive.batches import validate
from blazer_drive.bmsg import Bmsg
from blazer_drive.font import FontEngine
from blazer_drive.injector import fit_layout
from blazer_drive.rom import RomHandler

ROOT = Path(__file__).resolve().parents[1]

# Test characters are built from Shift-JIS codes so no game text is stored in the repository.
KANA = bytes([0x82, 0xA0])      # a hiragana character (2 bytes)
K = KANA.decode("cp932")
WARD_III = bytes([0x99, 0x45]).decode("cp932")  # custom glyph drawn as the Roman numeral III
FONT = ROOT / "workspace/unpacked/data/font01.NFTR"
ROM = RomHandler.find_default_rom()


def make_bmsg(texts: list[bytes]) -> bytes:
    """Builds a synthetic .bmsg with the same structure as the game's."""
    n = len(texts)
    head = bytearray(b"MPCT" + struct.pack("<I", 1) + b"\0" * 0x18)
    head += struct.pack("<5I", 2, n, 9, 0, 1) + b"\xff" * (0x4C - 0x34)
    head += b"".join(struct.pack("<I", 0x1000 + i) for i in range(n))      # ids
    head += b"".join(struct.pack("<I", i) for i in range(n))               # indices
    head += struct.pack("<II", 0, 3)
    pt = len(head)
    body, offs = bytearray(), []
    for t in texts:
        offs.append(8 * n + len(body))
        body += struct.pack("<I", len(t)) + t + b"\0"
        body += b"\0" * ((-len(body)) % 4)
    table = b"".join(struct.pack("<II", 0x1000 + i, o) for i, o in enumerate(offs))
    return bytes(head + table + body + b"EOFC" + b"\0" * 0x1C)


class TestBmsg(unittest.TestCase):
    def test_roundtrip_is_identical(self):
        data = make_bmsg([KANA * 5, b"%s$1cAT$c", b"OK"])
        self.assertEqual(Bmsg(data).rebuild({}), data)

    def test_string_grows_and_others_are_kept(self):
        data = make_bmsg([b"AB", b"CD", b"EF"])
        b = Bmsg(data)
        first = b.strings[0]
        nb = Bmsg(b.rebuild({first.text_offset: b"A much longer string"}))
        self.assertEqual([s.raw for s in nb.strings], [b"A much longer string", b"CD", b"EF"])


class TestValidation(unittest.TestCase):
    def test_control_codes(self):
        self.assertEqual(validate(f"%s{K}$3c{K}{K}$c", "%s's $3cattack$c"), [])
        self.assertIn("printf", validate(f"%s{K}{K}", "Got it"))
        self.assertIn("color", validate(f"$1c{K}$c", "red"))

    def test_custom_glyph_required(self):
        self.assertEqual(validate(f"{WARD_III}{K}", f"Ward {WARD_III}"), [])
        self.assertIn("glyph", validate(f"{WARD_III}{K}", "Ward III"))

    def test_percent_is_not_printf(self):
        self.assertEqual(validate(f"50%{K}{K}", "50% chance"), [])


class TestPublicFiles(unittest.TestCase):
    def test_glyph_tokens_roundtrip(self):
        from blazer_drive.public import glyphs_to_tokens, tokens_to_glyphs

        text = f"Ward {WARD_III}!"
        self.assertEqual(glyphs_to_tokens(text), "Ward {g:9945}!")
        self.assertEqual(tokens_to_glyphs("Ward {g:9945}!"), text)

    def test_published_files_have_no_japanese(self):
        import re

        jp = re.compile(r"[\u3040-\u30ff\u3400-\u9fff\uff61-\uff9f]")
        for f in ("translations/strings_en.csv", "translations/overrides_en.json", "translations/STYLE_GUIDE.md"):
            path = ROOT / f
            if path.exists():
                self.assertIsNone(jp.search(path.read_text(encoding="utf-8")), f)


@unittest.skipUnless(FONT.exists(), "requires workspace/unpacked (make unpack)")
class TestLayout(unittest.TestCase):
    def setUp(self):
        self.font = FontEngine(FONT)

    def test_ascii_6px_and_kana_12px(self):
        self.assertEqual(self.font.get_char_width("A"), 6)
        self.assertEqual(self.font.get_char_width(K), 12)

    def test_paginates_when_too_long(self):
        text = "This sentence is far too long to fit inside a two line dialogue box of the game."
        out, overflow = fit_layout(self.font, text, 180, 2, paginate=True)
        self.assertFalse(overflow)
        for page in out.split("#"):
            lines = page.strip("\n").split("\n")
            self.assertLessEqual(len(lines), 2)
            self.assertTrue(all(self.font.measure_line_width(l) <= 180 for l in lines))


@unittest.skipUnless(ROM and ROM.exists(), "requires the original ROM in rom/")
class TestRom(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.files = RomHandler.pristine_files(ROM)

    def test_all_bmsg_roundtrip(self):
        bm = {k: v for k, v in self.files.items() if k.endswith(".bmsg")}
        self.assertEqual(len(bm), 136)
        for k, v in bm.items():
            self.assertEqual(Bmsg(v).rebuild({}), v, k)

    def test_cpk_patch_keeps_other_files(self):
        from blazer_drive.cpk import CpkManager
        import ndspy.rom

        data = ndspy.rom.NintendoDSRom.fromFile(str(ROM)).getFileByName("common.cpk")
        entries = CpkManager.read_entries(data)
        patched = CpkManager.read_entries(CpkManager.patch_cpk(data, {entries[0].name: entries[0].data + b"X"}))
        self.assertEqual(patched[0].data, entries[0].data + b"X")
        self.assertEqual([e.data for e in patched[1:]], [e.data for e in entries[1:]])


if __name__ == "__main__":
    unittest.main()
