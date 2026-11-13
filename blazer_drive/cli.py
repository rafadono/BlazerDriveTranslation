import argparse
import shutil
import sys
from pathlib import Path
from rich.console import Console
from rich.table import Table

from blazer_drive.cpk import CpkManager
from blazer_drive.font import FontEngine
from blazer_drive.rom import RomHandler
from blazer_drive.injector import TextInjector
from blazer_drive.catalog import TranslationCatalog, TranslationEntry

console = Console()

def cmd_unpack(args: argparse.Namespace) -> None:
    rom_path = Path(args.rom) if args.rom else RomHandler.find_default_rom()
    if not rom_path or not rom_path.exists():
        console.print("[red]Error:[/red] Blazer Drive ROM not found. Specify --rom.")
        sys.exit(1)

    out_dir = Path(args.out_dir)
    console.print(f"[bold cyan]Unpacking ROM:[/bold cyan] {rom_path}")
    rom_res = RomHandler.unpack(rom_path, out_dir)
    console.print(f"[green]Base NDS files extracted:[/green] {rom_res['extracted_files']}")

    data_dir = out_dir / "data"
    cpk_out_root = out_dir / "cpk_extracted"
    cpk_files = sorted(data_dir.rglob("*.cpk"))
    console.print(f"[bold cyan]CPK containers found:[/bold cyan] {len(cpk_files)}")

    for cpk_file in cpk_files:
        rel = cpk_file.relative_to(data_dir).with_suffix("")
        target_dir = cpk_out_root / rel
        extracted = CpkManager.extract_cpk(cpk_file, target_dir)
        console.print(f"  - {cpk_file.name}: {extracted} files extracted to {target_dir.name}")


LAYOUT_MULTILINE_GROUPS = {"event_msg", "sys_msg.bmsg", "battle_msg.bmsg", "system_msg.bmsg"}


def _bmsg_group(rel: str) -> str:
    name = rel.split("/")[-1]
    return "event_msg" if name.startswith("event_msg") else name


def cmd_extract(args: argparse.Namespace) -> None:
    """Extracts ALL real strings from the .bmsg files (exact parser, blazer_drive/bmsg.py) from the
    original ROM and merges the existing translations from the previous catalog."""
    import re as _re
    from collections import defaultdict

    from blazer_drive.bmsg import Bmsg
    from blazer_drive.catalog import CONTROL_CODE_RE

    rom_path = Path(args.rom) if args.rom else RomHandler.find_default_rom()
    if not rom_path or not rom_path.exists():
        console.print("[red]Error:[/red] The original ROM is required.")
        sys.exit(1)
    font_path = Path(args.unpacked_dir) / "data" / "font01.NFTR"
    font = FontEngine(font_path if font_path.exists() else None)

    from blazer_drive import public

    previous: dict[tuple[str, int], TranslationEntry] = {}
    out_xlsx, out_csv = Path(args.out_xlsx), Path(args.out_csv)
    if out_csv.exists():
        old = TranslationCatalog(font)
        old.load_from_csv(out_csv)
        previous = {(e.file_path, e.offset): e for e in old.entries}

    pristine = RomHandler.pristine_files(rom_path)
    files = sorted(k for k in pristine if k.endswith(".bmsg"))
    parsed = {k: Bmsg(pristine[k]) for k in files}

    # Per-group layout limits: width = 95th percentile of the original lines.
    widths = defaultdict(list)
    for k, b in parsed.items():
        for st in b.strings:
            for line in CONTROL_CODE_RE.sub("", st.raw.decode("cp932", "replace")).split("\n"):
                widths[_bmsg_group(k)].append(font.measure_line_width(line))
    group_w = {g: sorted(v)[int(len(v) * 0.95)] for g, v in widths.items()}

    catalog = TranslationCatalog(font)
    reused = from_public = 0
    public_en = public.load_public()           # English lines published in the repository
    overrides = public.load_overrides(pristine)  # password clues resolved against this ROM
    for k, b in parsed.items():
        stem = Path(k).stem.upper()
        g = _bmsg_group(k)
        for st in b.strings:
            jp = st.raw.decode("cp932", "replace")
            vis = CONTROL_CODE_RE.sub("", jp).split("\n")
            orig_w = max(font.measure_line_width(x) for x in vis)
            orig_lines = len(vis)
            e = catalog.add_entry(
                entry_id=f"{stem}_{st.index:04d}",
                file_path=k,
                offset=st.text_offset,
                max_bytes=len(st.raw),
                original_jp=jp,
            )
            e.max_px = max(orig_w, group_w[g])
            e.max_lines = max(orig_lines, 2) if g in LAYOUT_MULTILINE_GROUPS else orig_lines
            prev = previous.get((k, st.text_offset))
            if prev and prev.original_jp.strip() == jp.strip():
                e.translation_en, e.translation_es, e.notes = prev.translation_en, prev.translation_es, prev.notes
                if prev.status.lower() == "approved" and "human" not in (prev.notes or "").lower():
                    e.status = "Draft"  # approved by an MT script, not by a person
                else:
                    e.status = prev.status if prev.status.lower() != "ignored" else "Pending"
                if e.translation_en.strip() == jp.strip():
                    e.translation_en, e.status = "", "Pending"
                reused += 1 if e.translation_en else 0
            if not e.translation_en and (k, st.text_offset) in public_en:
                e.translation_en, e.status, e.notes = public_en[(k, st.text_offset)]
                from_public += 1
            if e.entry_id in overrides:
                e.translation_en, e.status, e.notes = overrides[e.entry_id], "Approved", "override (puzzle)"
            if not _re.search(r"[\u3040-\u30ff\u4e00-\u9fff\uff01-\uff5e]", jp) and not e.translation_en:
                e.status = "Ignored"  # no Japanese (numbers, symbols, codes)
            catalog.audit_entry(e)

    out_xlsx.parent.mkdir(parents=True, exist_ok=True)
    catalog.export_excel(out_xlsx)
    catalog.export_csv(out_csv)
    console.print(
        f"[bold green]Catalog regenerated:[/bold green] {len(catalog.entries)} strings in {len(files)} .bmsg; "
        f"translations reused: {reused}\n  Excel: {out_xlsx}\n  CSV: {out_csv}"
    )


def cmd_audit(args: argparse.Namespace) -> None:
    table_path = Path(args.table)
    if not table_path.exists():
        console.print(f"[red]Error:[/red] Translation table not found at {table_path}")
        sys.exit(1)

    unpacked_dir = Path(args.unpacked_dir)
    font_path = unpacked_dir / "data" / "font01.NFTR"
    font = FontEngine(font_path if font_path.exists() else None)
    catalog = TranslationCatalog(font)

    if table_path.suffix.lower() == ".xlsx":
        loaded = catalog.load_from_excel(table_path)
    else:
        loaded = catalog.load_from_csv(table_path)

    summary = catalog.audit_all(target_lang=args.lang)

    table = Table(title="Translation and Screen Limits Audit", show_header=True)
    table.add_column("Metric", style="bold cyan")
    table.add_column("Count", style="bold white")

    table.add_row("Total Entries", str(summary["total"]))
    table.add_row("Untranslated (Empty)", str(summary["empty"]))
    table.add_row("OK (Within limits)", f"[green]{summary['ok']}[/green]")
    table.add_row("Overflow Alerts", f"[red]{summary['overflow']}[/red]")

    console.print(table)

    if table_path.suffix.lower() == ".xlsx":
        catalog.export_excel(table_path)
    else:
        catalog.export_csv(table_path)
    console.print(f"[green]Statuses and alerts updated in {table_path}[/green]")


def cmd_inject(args: argparse.Namespace) -> None:
    table_path = Path(args.table)
    if not table_path.exists():
        console.print(f"[red]Error:[/red] Translation table not found at {table_path}")
        sys.exit(1)
    rom_path = Path(args.rom) if args.rom else RomHandler.find_default_rom()
    if not rom_path or not rom_path.exists():
        console.print("[red]Error:[/red] The original ROM is required (pristine source).")
        sys.exit(1)

    unpacked_dir = Path(args.unpacked_dir)
    font_path = unpacked_dir / "data" / "font01.NFTR"
    # Measure with the variable-width font that gets installed in the ROM (blazer_drive/gfx_patches.py)
    from blazer_drive.font_patch import make_vwf
    import tempfile
    vwf_path = Path(tempfile.gettempdir()) / "blazer_font01_vwf.NFTR"
    vwf_path.write_bytes(make_vwf(font_path.read_bytes()))
    font = FontEngine(vwf_path)
    catalog = TranslationCatalog(font)
    if table_path.suffix.lower() == ".xlsx":
        catalog.load_from_excel(table_path)
    else:
        catalog.load_from_csv(table_path)

    out_dir = Path(args.patched_dir)
    if out_dir.exists():
        shutil.rmtree(out_dir)
    console.print(f"[cyan]Reading pristine files from:[/cyan] {rom_path}")
    pristine = RomHandler.pristine_files(rom_path)

    report = Path(args.report)
    stats = TextInjector(font).inject_catalog(
        catalog=catalog,
        pristine_files=pristine,
        out_dir=out_dir,
        target_lang=args.lang,
        auto_wrap=not args.no_wrap,
        max_box_width=args.max_width,
        report_path=report,
    )
    table = Table(title="Injection result")
    table.add_column("Metric", style="bold cyan")
    table.add_column("Count", justify="right")
    for k in sorted(stats):
        table.add_row(k, str(stats[k]))
    console.print(table)
    console.print(f"[green]Patched files in:[/green] {out_dir}   [green]Rejections:[/green] {report}")


def cmd_build(args: argparse.Namespace) -> None:
    rom_base = Path(args.rom) if args.rom else RomHandler.find_default_rom()
    if not rom_base or not rom_base.exists():
        console.print("[red]Error:[/red] The original ROM is required as a base.")
        sys.exit(1)

    out_rom = Path(args.out_rom)

    console.print(f"[bold cyan]Rebuilding NDS ROM to:[/bold cyan] {out_rom}")
    res = RomHandler.rebuild(rom_base, Path(args.patched_dir), out_rom, allow_arm9=args.allow_arm9)
    console.print(f"[bold green]ROM built successfully:[/bold green] {out_rom} {res}")


def cmd_gfx(args: argparse.Namespace) -> None:
    from blazer_drive.gfx_patches import apply

    rom = Path(args.rom) if args.rom else RomHandler.find_default_rom()
    apply(rom, Path(args.patched_dir), Path(args.preview) if args.preview else None)


def cmd_batches(args: argparse.Namespace) -> None:
    from blazer_drive import batches

    if args.action == "export":
        batches.cmd_export(args.size)
    else:
        batches.cmd_import()


def cmd_all(args: argparse.Namespace) -> None:
    """Full pipeline: inject -> gfx -> build."""
    cmd_inject(args)
    cmd_gfx(args)
    cmd_build(args)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Translation, Excel audit and build orchestrator for Blazer Drive (NDS)."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    p_unpack = subparsers.add_parser("unpack", help="Unpack the ROM and its CPK containers.")
    p_unpack.add_argument("--rom", help="Path to the original ROM (.nds).")
    p_unpack.add_argument("--out-dir", default="workspace/unpacked", help="Destination directory.")
    p_unpack.set_defaults(func=cmd_unpack)

    p_extract = subparsers.add_parser("extract", help="Extract text to Excel and CSV for translation.")
    p_extract.add_argument("--unpacked-dir", default="workspace/unpacked", help="Unpacked directory (source).")
    p_extract.add_argument("--rom", help="Original ROM.")
    p_extract.add_argument("--out-xlsx", default="workspace/catalog/strings.xlsx", help="Excel output (local, contains the Japanese original).")
    p_extract.add_argument("--out-csv", default="workspace/catalog/strings.csv", help="CSV output (local, contains the Japanese original).")
    p_extract.set_defaults(func=cmd_extract)

    p_audit = subparsers.add_parser("audit", help="Audit byte lengths, line breaks and pixel width.")
    p_audit.add_argument("--table", default="workspace/catalog/strings.csv", help="Path to the local CSV (or .xlsx) catalog.")
    p_audit.add_argument("--unpacked-dir", default="workspace/unpacked", help="Unpacked directory.")
    p_audit.add_argument("--lang", default="en", choices=["en", "es"], help="Language to audit (en/es).")
    p_audit.set_defaults(func=cmd_audit)

    p_inject = subparsers.add_parser("inject", help="Inject the translated text with limit checks.")
    p_inject.add_argument("--table", default="workspace/catalog/strings.csv", help="Path to the local CSV (or .xlsx) catalog.")
    p_inject.add_argument("--unpacked-dir", default="workspace/unpacked", help="Unpacked directory.")
    p_inject.add_argument("--lang", default="en", choices=["en", "es"], help="Target language (en/es).")
    p_inject.add_argument("--no-wrap", action="store_true", help="Disable automatic line wrapping.")
    p_inject.add_argument("--max-width", type=int, default=224, help="Maximum text box width in pixels.")
    p_inject.add_argument("--rom", help="Original ROM (pristine source of the files).")
    p_inject.add_argument("--patched-dir", default="workspace/patched", help="Output for patched files.")
    p_inject.add_argument("--report", default="workspace/reports/inject_rejections.csv", help="CSV of rejected entries.")
    p_inject.set_defaults(func=cmd_inject)

    p_build = subparsers.add_parser("build", help="Rebuild the final NDS ROM.")
    p_build.add_argument("--rom", help="Path to the original base ROM.")
    p_build.add_argument("--patched-dir", default="workspace/patched", help="Files patched by 'inject'.")
    p_build.add_argument("--allow-arm9", action="store_true", help="Apply the patched system/arm9.bin (dangerous).")
    p_build.add_argument("--out-rom", default="rom/blazer_drive_translated.nds", help="Output ROM path.")
    p_build.set_defaults(func=cmd_build)

    p_gfx = subparsers.add_parser("gfx", help="Redraw texture text in English and generate the VWF font.")
    p_gfx.add_argument("--rom", help="Original ROM.")
    p_gfx.add_argument("--patched-dir", default="workspace/patched")
    p_gfx.add_argument("--preview", help="Directory for before/after previews.")
    p_gfx.set_defaults(func=cmd_gfx)

    p_bat = subparsers.add_parser("batches", help="JSON translation batches (export) and validated re-import (import).")
    p_bat.add_argument("action", choices=["export", "import"])
    p_bat.add_argument("--size", type=int, default=650, help="Unique phrases per batch (export).")
    p_bat.set_defaults(func=cmd_batches)

    p_all = subparsers.add_parser("all", help="inject + gfx + build in one step.")
    for a in p_inject._actions[1:]:
        p_all._add_action(a)
    p_all.add_argument("--preview", default=None)
    p_all.add_argument("--allow-arm9", action="store_true")
    p_all.add_argument("--out-rom", default="rom/blazer_drive_translated.nds")
    p_all.set_defaults(func=cmd_all)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
