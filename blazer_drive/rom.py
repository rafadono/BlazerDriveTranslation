import json
from pathlib import Path
import ndspy.fnt
import ndspy.rom


class RomHandler:
    @staticmethod
    def find_default_rom() -> Path | None:
        candidates = [
            Path("rom/blazer_drive_jp.nds"),
            Path("rom/blazer_drive.nds"),
            Path("roms/blazer_drive.nds"),
        ]
        for c in candidates:
            if c.exists():
                return c

        for search_dir in (Path("rom"), Path("roms"), Path(".")):
            if search_dir.exists():
                for f in search_dir.glob("*.nds"):
                    if "translated" not in f.name.lower() and "_es" not in f.name.lower():
                        return f
        return None

    @staticmethod
    def unpack(rom_path: Path, out_dir: Path) -> dict[str, int]:
        if not rom_path.exists():
            raise FileNotFoundError(f"ROM not found at: {rom_path}")

        rom = ndspy.rom.NintendoDSRom.fromFile(str(rom_path))
        out_dir.mkdir(parents=True, exist_ok=True)
        data_dir = out_dir / "data"
        sys_dir = out_dir / "system"
        data_dir.mkdir(parents=True, exist_ok=True)
        sys_dir.mkdir(parents=True, exist_ok=True)

        (sys_dir / "arm9.bin").write_bytes(rom.arm9)
        (sys_dir / "arm7.bin").write_bytes(rom.arm7)
        (sys_dir / "banner.bin").write_bytes(rom.iconBanner)

        meta = {
            "name": rom.name.decode("ascii", errors="ignore").rstrip("\x00"),
            "idCode": rom.idCode.decode("ascii", errors="ignore"),
            "developerCode": rom.developerCode.decode("ascii", errors="ignore"),
            "arm9RamAddress": hex(rom.arm9RamAddress),
            "arm9EntryAddress": hex(rom.arm9EntryAddress),
            "arm7RamAddress": hex(rom.arm7RamAddress),
            "arm7EntryAddress": hex(rom.arm7EntryAddress),
        }
        (sys_dir / "header_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

        extracted_files = 0

        def _dump_folder(folder: ndspy.fnt.Folder, current_path: Path) -> None:
            nonlocal extracted_files
            current_path.mkdir(parents=True, exist_ok=True)
            for i, filename in enumerate(folder.files):
                file_id = folder.firstID + i
                (current_path / filename).write_bytes(rom.files[file_id])
                extracted_files += 1
            for sub_name, sub_folder in folder.folders:
                _dump_folder(sub_folder, current_path / sub_name)

        _dump_folder(rom.filenames, data_dir)
        return {"extracted_files": extracted_files}

    @staticmethod
    def pristine_files(rom_path: Path) -> dict[str, bytes]:
        """ORIGINAL ROM files, keyed by the same relative paths as the catalog:
        'data/<path>' for the NDS file system and
        'cpk_extracted/<cpk without extension>/<file>' for the contents of each CPK."""
        from blazer_drive.cpk import CpkManager

        rom = ndspy.rom.NintendoDSRom.fromFile(str(rom_path))
        out: dict[str, bytes] = {"system/arm9.bin": bytes(rom.arm9)}
        for fid, body in enumerate(rom.files):
            name = rom.filenames.filenameOf(fid)
            if not name:
                continue
            out[f"data/{name}"] = bytes(body)
            if name.lower().endswith(".cpk"):
                try:
                    for e in CpkManager.read_entries(body):
                        out[f"cpk_extracted/{name[:-4]}/{e.name}"] = e.data
                except (ValueError, KeyError):
                    pass
        return out

    @staticmethod
    def rebuild(base_rom_path: Path, patched_dir: Path, out_rom_path: Path, allow_arm9: bool = False) -> dict[str, int]:
        """Builds the final ROM from the ORIGINAL ROM + the files in `patched_dir`.

        * cpk_extracted/<cpk>/<file> -> repacked into data/<cpk>.cpk with
          CpkManager.patch_cpk (safe append, no CriPakTools).
        * data/<path> -> replaces the NDS file directly.
        * system/arm9.bin -> only if allow_arm9=True (the original is kept by default).
        """
        from blazer_drive.cpk import CpkManager

        if not base_rom_path.exists():
            raise FileNotFoundError(f"The original ROM is required at: {base_rom_path}")
        rom = ndspy.rom.NintendoDSRom.fromFile(str(base_rom_path))
        stats = {"replaced_files": 0, "cpk_patched": 0, "cpk_inner_files": 0, "arm9_patched": 0}

        arm9_path = patched_dir / "system" / "arm9.bin"
        if allow_arm9 and arm9_path.exists() and arm9_path.read_bytes() != rom.arm9:
            rom.arm9 = arm9_path.read_bytes()
            stats["arm9_patched"] = 1

        cpk_root = patched_dir / "cpk_extracted"
        groups: dict[str, dict[str, bytes]] = {}
        if cpk_root.exists():
            for f in sorted(cpk_root.rglob("*")):
                if f.is_file():
                    rel = f.relative_to(cpk_root)
                    cpk_name = "/".join(rel.parts[:-1]) + ".cpk"
                    groups.setdefault(cpk_name, {})[rel.parts[-1]] = f.read_bytes()
        for cpk_name, repl in groups.items():
            fid = rom.filenames.idOf(cpk_name)
            if fid is None:
                raise FileNotFoundError(f"CPK not found in the ROM: {cpk_name}")
            rom.files[fid] = CpkManager.patch_cpk(rom.files[fid], repl)
            stats["cpk_patched"] += 1
            stats["cpk_inner_files"] += len(repl)

        data_root = patched_dir / "data"
        if data_root.exists():
            for f in sorted(data_root.rglob("*")):
                if f.is_file():
                    fid = rom.filenames.idOf(f.relative_to(data_root).as_posix())
                    if fid is not None and rom.files[fid] != f.read_bytes():
                        rom.files[fid] = f.read_bytes()
                        stats["replaced_files"] += 1

        out_rom_path.parent.mkdir(parents=True, exist_ok=True)
        rom.saveToFile(str(out_rom_path))
        return stats
