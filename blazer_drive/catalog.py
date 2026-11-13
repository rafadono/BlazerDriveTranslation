import csv
import re
from dataclasses import dataclass
from pathlib import Path

from blazer_drive.font import FontEngine


CONTROL_CODE_RE = re.compile(r"\$\d*c")


@dataclass
class TranslationEntry:
    entry_id: str
    file_path: str
    offset: int
    max_bytes: int
    original_jp: str
    translation_en: str = ""
    translation_es: str = ""
    status: str = "Pending"
    width_px: int = 0
    max_px: int = 224
    max_lines: int = 3
    lines: int = 1
    overflow_alert: str = "OK"
    notes: str = ""


class TranslationCatalog:
    HEADERS = [
        ("entry_id", "ID", 18),
        ("file_path", "File", 40),
        ("offset", "Offset_Hex", 14),
        ("max_bytes", "MaxBytes", 12),
        ("original_jp", "Original_JP", 45),
        ("translation_en", "English", 45),
        ("translation_es", "Spanish", 45),
        ("status", "Status", 12),
        ("width_px", "Width_PX", 12),
        ("max_px", "MaxBox_PX", 12),
        ("max_lines", "MaxLines", 9),
        ("lines", "Lines", 8),
        ("overflow_alert", "OverflowAlert", 18),
        ("notes", "Notes", 25),
    ]

    def __init__(self, font_engine: FontEngine | None = None) -> None:
        self.entries: list[TranslationEntry] = []
        self.font = font_engine or FontEngine()

    def add_entry(
        self,
        entry_id: str,
        file_path: str,
        offset: int,
        max_bytes: int,
        original_jp: str,
        translation_en: str = "",
        translation_es: str = "",
        notes: str = "",
    ) -> TranslationEntry:
        entry = TranslationEntry(
            entry_id=entry_id,
            file_path=file_path,
            offset=offset,
            max_bytes=max_bytes,
            original_jp=original_jp,
            translation_en=translation_en,
            translation_es=translation_es,
            notes=notes,
        )
        self.audit_entry(entry)
        self.entries.append(entry)
        return entry

    def audit_entry(self, entry: TranslationEntry, target_lang: str = "en") -> None:
        target_text = entry.translation_en if target_lang == "en" else entry.translation_es
        if not target_text:
            entry.width_px = 0
            entry.lines = 1
            entry.overflow_alert = "EMPTY"
            return

        visible = CONTROL_CODE_RE.sub("", target_text)
        w, lines = self.font.measure_text_box(visible)
        entry.width_px = w
        entry.lines = lines

        alerts: list[str] = []
        byte_len = len(target_text.encode("cp932", errors="replace"))
        # .bmsg files are rebuilt (blazer_drive/bmsg.py) and can grow: the byte limit does not apply.
        if not entry.file_path.endswith(".bmsg") and byte_len > entry.max_bytes:
            alerts.append(f"BYTE_OVERFLOW(+{byte_len - entry.max_bytes})")
        if w > entry.max_px:
            alerts.append(f"WIDTH_OVERFLOW({w}px>{entry.max_px}px)")
        if lines > entry.max_lines:
            alerts.append(f"LINE_OVERFLOW({lines}>{entry.max_lines})")
        try:
            target_text.encode("cp932")
        except UnicodeEncodeError:
            alerts.append("ENCODING")

        entry.overflow_alert = "; ".join(alerts) if alerts else "OK"

    def audit_all(self, target_lang: str = "en") -> dict[str, int]:
        summary = {"total": len(self.entries), "ok": 0, "overflow": 0, "empty": 0}
        for entry in self.entries:
            self.audit_entry(entry, target_lang)
            if entry.overflow_alert == "OK":
                summary["ok"] += 1
            elif entry.overflow_alert == "EMPTY":
                summary["empty"] += 1
            else:
                summary["overflow"] += 1
        return summary

    def export_excel(self, out_path: Path) -> None:
        import openpyxl
        from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
        from openpyxl.utils import get_column_letter

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Translations"

        header_font = Font(name="Segoe UI", size=10, bold=True, color="FFFFFF")
        header_fill = PatternFill(start_color="1F497D", end_color="1F497D", fill_type="solid")
        border_thin = Border(
            left=Side(style="thin", color="E0E0E0"),
            right=Side(style="thin", color="E0E0E0"),
            top=Side(style="thin", color="E0E0E0"),
            bottom=Side(style="thin", color="E0E0E0"),
        )
        warn_fill = PatternFill(start_color="FCE4D6", end_color="FCE4D6", fill_type="solid")
        ok_fill = PatternFill(start_color="E2EFDA", end_color="E2EFDA", fill_type="solid")
        data_font = Font(name="Segoe UI", size=9)

        header_titles = [h[1] for h in self.HEADERS]
        ws.append(header_titles)

        for col_idx in range(1, len(header_titles) + 1):
            cell = ws.cell(row=1, column=col_idx)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal="center", vertical="center")

        ws.freeze_panes = "A2"

        for row_idx, entry in enumerate(self.entries, start=2):
            row_data = [
                entry.entry_id,
                entry.file_path,
                f"0x{entry.offset:08X}",
                entry.max_bytes,
                entry.original_jp,
                entry.translation_en,
                entry.translation_es,
                entry.status,
                entry.width_px,
                entry.max_px,
                entry.max_lines,
                entry.lines,
                entry.overflow_alert,
                entry.notes,
            ]
            ws.append(row_data)

            if entry.overflow_alert != "EMPTY":
                alert_cell = ws.cell(row=row_idx, column=13)
                if entry.overflow_alert == "OK":
                    alert_cell.fill = ok_fill
                elif "OVERFLOW" in entry.overflow_alert:
                    alert_cell.fill = warn_fill

        for col_idx, (_, _, width) in enumerate(self.HEADERS, start=1):
            col_letter = get_column_letter(col_idx)
            ws.column_dimensions[col_letter].width = width

        ws.auto_filter.ref = ws.dimensions
        out_path.parent.mkdir(parents=True, exist_ok=True)
        wb.save(str(out_path))

    def export_csv(self, out_path: Path) -> None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([h[1] for h in self.HEADERS])
            for entry in self.entries:
                writer.writerow(
                    [
                        entry.entry_id,
                        entry.file_path,
                        f"0x{entry.offset:08X}",
                        entry.max_bytes,
                        entry.original_jp,
                        entry.translation_en,
                        entry.translation_es,
                        entry.status,
                        entry.width_px,
                        entry.max_px,
                        entry.max_lines,
                        entry.lines,
                        entry.overflow_alert,
                        entry.notes,
                    ]
                )

    def load_from_excel(self, in_path: Path) -> int:
        import openpyxl

        wb = openpyxl.load_workbook(str(in_path), data_only=True)
        ws = wb.active
        self.entries.clear()

        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            return 0

        header_row = [str(c or "").strip() for c in rows[0]]
        col_map = {name: idx for idx, name in enumerate(header_row)}

        count = 0
        for r in rows[1:]:
            if not r or not any(r):
                continue
            e_id = str(r[col_map.get("ID", 0)] or "")
            f_path = str(r[col_map.get("File", 1)] or "")
            off_str = str(r[col_map.get("Offset_Hex", 2)] or "0")
            offset = int(off_str, 16) if off_str.startswith("0x") else int(off_str or 0)
            max_b = int(r[col_map.get("MaxBytes", 3)] or 0)
            orig_jp = str(r[col_map.get("Original_JP", 4)] or "")
            en = str(r[col_map.get("English", 5)] or "")
            es = str(r[col_map.get("Spanish", 6)] or "")
            status = str(r[col_map.get("Status", 7)] or "Pending")
            notes = str(r[col_map.get("Notes", 12)] or "")
            max_px = int(r[col_map["MaxBox_PX"]] or 224) if "MaxBox_PX" in col_map else 224
            max_lines = int(r[col_map["MaxLines"]] or 3) if "MaxLines" in col_map else 3

            entry = TranslationEntry(
                entry_id=e_id,
                file_path=f_path,
                offset=offset,
                max_bytes=max_b,
                original_jp=orig_jp,
                translation_en=en,
                translation_es=es,
                status=status,
                notes=notes,
                max_px=max_px,
                max_lines=max_lines,
            )
            self.audit_entry(entry)
            self.entries.append(entry)
            count += 1

        return count

    def load_from_csv(self, in_path: Path) -> int:
        self.entries.clear()
        with in_path.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.reader(f)
            header = next(reader, None)
            if not header:
                return 0
            col_map = {name.strip(): idx for idx, name in enumerate(header)}
            count = 0
            for r in reader:
                if not r or not any(r):
                    continue
                e_id = r[col_map.get("ID", 0)]
                f_path = r[col_map.get("File", 1)]
                off_str = r[col_map.get("Offset_Hex", 2)]
                offset = int(off_str, 16) if off_str.startswith("0x") else int(off_str or 0)
                max_b = int(r[col_map.get("MaxBytes", 3)] or 0)
                orig_jp = r[col_map.get("Original_JP", 4)]
                en = r[col_map.get("English", 5)]
                es = r[col_map.get("Spanish", 6)]
                status = r[col_map.get("Status", 7)]
                notes = r[col_map.get("Notes", 12)] if "Notes" in col_map else ""
                max_px = int(r[col_map["MaxBox_PX"]] or 224) if "MaxBox_PX" in col_map else 224
                max_lines = int(r[col_map["MaxLines"]] or 3) if "MaxLines" in col_map else 3

                entry = TranslationEntry(
                    entry_id=e_id,
                    file_path=f_path,
                    offset=offset,
                    max_bytes=max_b,
                    original_jp=orig_jp,
                    translation_en=en,
                    translation_es=es,
                    status=status,
                    notes=notes,
                    max_px=max_px,
                    max_lines=max_lines,
                )
                self.audit_entry(entry)
                self.entries.append(entry)
                count += 1
        return count
