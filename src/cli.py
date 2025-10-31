from __future__ import annotations

import os
import sys
import argparse
from typing import List, Tuple

from src.core.file_scanner import FileScanner
from src.core.file_processor import FileProcessor
from src.config import EXCLUDED_FOLDER_NAMES_DEFAULT


def _default_output_filename(base_folder: str) -> str:
    import re
    base = os.path.basename((base_folder or "").rstrip("\\/")) or "combined_output"
    name = re.sub(r"\s+", "_", base)
    name = re.sub(r"[^\w.\-]+", "_", name)
    name = name.strip("._-") or "combined_output"
    if not name.lower().endswith(".txt"):
        name += ".txt"
    return name


def _progress(proc: int, total: int) -> None:
    total = max(1, total)
    pct = int(proc * 100 / total)
    print(f"Processing {proc}/{total} ({pct}%)", file=sys.stderr)


def main(argv: List[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Combine text files respecting exclusions")
    p.add_argument("root", help="Root folder to scan")
    p.add_argument("--out", "-o", help="Output file path (default: <root name>.txt)")
    p.add_argument("--no-gitignore", action="store_true", help="Do not honor .gitignore")
    p.add_argument("--use-default-folder-names", action="store_true", help="Exclude common junk folder names (node_modules, venv, …)")
    p.add_argument("--exclude-folder", action="append", default=[], help="Relative folder path to exclude (repeatable)")
    p.add_argument("--exclude-file-pattern", action="append", default=[], help="Filename pattern to exclude, e.g., *.log (repeatable)")
    p.add_argument("--exclude-file", action="append", default=[], help="Absolute file path to exclude (repeatable)")

    args = p.parse_args(argv)
    root = os.path.abspath(args.root)
    if not os.path.isdir(root):
        print(f"Root folder does not exist: {root}", file=sys.stderr)
        return 2

    out_path = args.out
    if not out_path:
        out_path = os.path.join(root, _default_output_filename(root))

    scanner = FileScanner(root)
    scanner.apply_gitignore = not args.no_gitignore
    scanner.excluded_folder_names = set(EXCLUDED_FOLDER_NAMES_DEFAULT) if args.use_default_folder_names else set()
    scanner.excluded_folders = {os.path.normpath(s) for s in (args.exclude_folder or [])}
    scanner.excluded_file_patterns = set(args.exclude_file_pattern or [])
    scanner.excluded_files = {os.path.abspath(s) for s in (args.exclude_file or [])}

    files: List[Tuple[str, str, str]] = list(scanner.yield_files())
    if not files:
        print("No files found to process.", file=sys.stderr)
        return 1

    proc = FileProcessor(root)
    ok = proc.process_files(files, out_path, progress_callback=_progress)
    if not ok:
        print("Failed to generate output.", file=sys.stderr)
        return 1

    print(out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
