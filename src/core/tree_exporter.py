# src/core/tree_exporter.py

import os
import fnmatch
from typing import Callable, Iterable, List, Tuple, Set
from src.config import PREDEFINED_EXCLUDED_FILES


class TreeExporter:
    """
    Builds an ASCII/Unicode file tree for a folder, honoring exclusions:
      - excluded_folder_names: set of folder names to skip anywhere
      - excluded_folders: set of relative folder paths (from base) to skip recursively
      - excluded_file_patterns: fnmatch patterns for filenames
      - excluded_files: absolute file paths to skip
    """

    def __init__(
        self,
        base_folder: str,
        *,
        excluded_folder_names: Set[str] | None = None,
        excluded_folders: Set[str] | None = None,
        excluded_file_patterns: Set[str] | None = None,
        excluded_files: Set[str] | None = None,
    ):
        self.base = os.path.abspath(base_folder)
        self.excluded_folder_names = set(excluded_folder_names or set())
        self.excluded_folders = {os.path.normpath(p) for p in (excluded_folders or set())}
        self.excluded_file_patterns = set(excluded_file_patterns or set())
        self.excluded_files_abs = {os.path.abspath(p) for p in (excluded_files or set())}

    # ---------- public API ----------

    def count_nodes(self) -> int:
        """Rough count of included dirs+files for progress."""
        total = 1  # root line
        for rel_dir, dirs, files in self._iter_lists():
            total += len(dirs) + len(files)
        return total

    def export(
        self,
        dest_path: str,
        *,
        style: str = "unicode",
        progress: Callable[[int, int], None] | None = None,
    ) -> bool:
        """
        Write the tree to dest_path.
        style: 'unicode' (├─, │, └─) or 'ascii' (|--, |, `--).
        progress: callback(done, total)
        """
        lines = self.build_lines(style=style, progress=progress)
        try:
            with open(dest_path, "w", encoding="utf-8") as f:
                for line in lines:
                    f.write(line)
                    if not line.endswith("\n"):
                        f.write("\n")
            return True
        except Exception:
            return False

    def build_lines(
        self,
        *,
        style: str = "unicode",
        progress: Callable[[int, int], None] | None = None,
    ) -> List[str]:
        """Return the tree lines."""
        chars = self._style_chars(style)
        root_name = os.path.basename(self.base) or self.base

        total = self.count_nodes()
        done = 0

        lines: List[str] = [root_name]
        done += 1
        if progress:
            progress(done, total)

        def list_dir(rel_dir: str) -> Tuple[List[str], List[str]]:
            full = os.path.join(self.base, rel_dir) if rel_dir else self.base
            try:
                entries = list(os.scandir(full))
            except (FileNotFoundError, PermissionError):
                return [], []

            dirs: List[str] = []
            files: List[str] = []

            for e in entries:
                name = e.name
                # Skip '.' and '..'
                if name in (".", ".."):
                    continue

                # Build rel paths
                child_rel = os.path.normpath(os.path.join(rel_dir, name)) if rel_dir else name

                if e.is_dir(follow_symlinks=False):
                    if self._is_dir_excluded(child_rel, name):
                        continue
                    dirs.append(name)
                else:
                    if self._is_file_excluded(child_rel, name):
                        continue
                    files.append(name)

            # sort case-insensitively
            key = lambda s: s.lower()
            dirs.sort(key=key)
            files.sort(key=key)
            return dirs, files

        def walk(rel_dir: str, prefix: str):
            nonlocal done
            dirs, files = list_dir(rel_dir)
            children = [(d, True) for d in dirs] + [(f, False) for f in files]

            for idx, (name, is_dir) in enumerate(children):
                is_last = (idx == len(children) - 1)
                connector = chars["L"] if is_last else chars["T"]
                line = f"{prefix}{connector} {name}"
                lines.append(line)
                done += 1
                if progress:
                    progress(done, total)

                if is_dir:
                    child_rel = os.path.normpath(os.path.join(rel_dir, name)) if rel_dir else name
                    # Next prefix keeps vertical line if not last
                    next_prefix = prefix + (chars["V"] + "   " if not is_last else "    ")
                    walk(child_rel, next_prefix)

        walk("", "")
        return lines

    # ---------- internals ----------

    def _style_chars(self, style: str) -> dict:
        style = (style or "").lower()
        if style == "ascii":
            return {
                "T": "|--",  # tee
                "L": "`--",  # last
                "V": "|",    # vertical
            }
        # default unicode
        return {
            "T": "├──",
            "L": "└──",
            "V": "│",
        }

    def _iter_lists(self):
        """Yield (rel_dir, dirs, files) for all dirs, filtered."""
        for root_dir, dirs, files in os.walk(self.base, topdown=True):
            rel_root = os.path.normpath(os.path.relpath(root_dir, self.base))
            if rel_root == ".":
                rel_root = ""

            # dir filtering in-place
            keep_dirs = []
            for d in list(dirs):
                child_rel = os.path.normpath(os.path.join(rel_root, d)) if rel_root else d
                if not self._is_dir_excluded(child_rel, d):
                    keep_dirs.append(d)
            dirs[:] = keep_dirs

            # files filtered snapshot
            keep_files = []
            for f in files:
                child_rel = os.path.normpath(os.path.join(rel_root, f)) if rel_root else f
                if not self._is_file_excluded(child_rel, f):
                    keep_files.append(f)

            yield rel_root, keep_dirs, keep_files

    def _is_dir_excluded(self, rel_path: str, name: str) -> bool:
        # name-based exclusion anywhere in path
        if name in self.excluded_folder_names:
            return True

        # user excluded full relative paths (dir or subdir)
        rel_norm = os.path.normpath(rel_path)
        for ex in self.excluded_folders:
            ex_norm = os.path.normpath(ex)
            if rel_norm == ex_norm or rel_norm.startswith(ex_norm + os.sep):
                return True
        return False

    def _is_file_excluded(self, rel_path: str, filename: str) -> bool:
        if filename in PREDEFINED_EXCLUDED_FILES:
            return True

        for pattern in self.excluded_file_patterns:
            if fnmatch.fnmatch(filename, pattern):
                return True

        abs_path = os.path.abspath(os.path.join(self.base, rel_path))
        if abs_path in self.excluded_files_abs:
            return True

        return False
