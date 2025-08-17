# src/ui_qt/workers/tree_worker.py
from __future__ import annotations
import os
from PySide6.QtCore import QThread, Signal
from pathspec import PathSpec

from src.core.tree_exporter import TreeExporter
from src.config import EXCLUDED_FOLDER_NAMES_DEFAULT

def hr_size(n: int) -> str:
    units = ["B","KB","MB","GB","TB"]
    i = 0
    f = float(n)
    while f >= 1024 and i < len(units)-1:
        f /= 1024.0
        i += 1
    return f"{f:.1f} {units[i]}"

class TreeWorker(QThread):
    progress = Signal(int, int)
    status = Signal(str)
    done = Signal(bool, str, str)  # ok, out_path, err

    def __init__(self, state, out_path: str, style: str, markdown: bool, sizes: bool):
        super().__init__()
        self.state = state
        self.out_path = out_path
        self.style = style
        self.markdown = markdown
        self.sizes = sizes

        self._git_spec = None
        gi = os.path.join(self.state.selected_folder or "", ".gitignore")
        if self.state.apply_gitignore and gi and os.path.isfile(gi):
            try:
                with open(gi, "r", encoding="utf-8", errors="ignore") as f:
                    self._git_spec = PathSpec.from_lines("gitwildmatch", f)
            except Exception:
                self._git_spec = None

    def _ignored_by_git(self, rel_path: str) -> bool:
        if not self.state.apply_gitignore or not self._git_spec:
            return False
        try:
            return self._git_spec.match_file(rel_path)
        except Exception:
            return False

    def _filtered_walk(self, root: str):
        st = self.state
        base = os.path.abspath(root)
        for curr, dirs, files in os.walk(base):
            rel_dir = os.path.relpath(curr, base)
            if rel_dir == ".":
                rel_dir = ""

            dirs[:] = [
                d for d in dirs
                if not (
                    (st.use_default_folder_names and d in EXCLUDED_FOLDER_NAMES_DEFAULT) or
                    ((os.path.normpath(os.path.join(rel_dir, d)) if rel_dir else d) in st.excluded_folders) or
                    self._ignored_by_git(os.path.normpath(os.path.join(rel_dir, d)) if rel_dir else d)
                )
            ]

            keep_files = []
            for f in files:
                rel_file = os.path.normpath(os.path.join(rel_dir, f)) if rel_dir else f
                abs_f = os.path.join(curr, f)

                if self._ignored_by_git(rel_file):
                    continue
                if abs_f in st.excluded_files_abs:
                    continue

                skip = False
                for pat in st.excluded_file_patterns:
                    ln = f.lower()
                    if pat.startswith("*.") and ln.endswith(pat[1:].lower()):
                        skip = True; break
                    if pat.endswith("*") and ln.startswith(pat[:-1].lower()):
                        skip = True; break
                    if pat.startswith("*") and ln.endswith(pat[1:].lower()):
                        skip = True; break
                    if pat == f or pat == rel_file:
                        skip = True; break
                if not skip:
                    keep_files.append(f)
            yield curr, dirs, keep_files

    def _prefix(self, depth: int) -> str:
        if self.style == "ascii":
            return "|   " * (depth - 1) + ("|-- " if depth > 0 else "")
        else:
            return "│   " * (depth - 1) + ("├── " if depth > 0 else "")

    def run(self):
        st = self.state
        try:
            used_fallback = False
            try:
                exporter = TreeExporter(
                    st.selected_folder,
                    excluded_folder_names=(EXCLUDED_FOLDER_NAMES_DEFAULT if st.use_default_folder_names else set()),
                    excluded_folders=st.excluded_folders,
                    excluded_file_patterns=st.excluded_file_patterns,
                    excluded_files=st.excluded_files_abs
                )
                total = max(1, exporter.count_nodes())

                def cb(done, tot):
                    self.progress.emit(done, max(1, tot))
                    self.status.emit(f"Generating tree {done}/{tot}")

                ok = False
                try:
                    # newer signature
                    ok = exporter.export(
                        self.out_path, style=self.style, progress=cb,
                        include_sizes=self.sizes, markdown=self.markdown,  # respect_exclusions handled internally
                    )
                except TypeError:
                    ok = exporter.export(
                        self.out_path, style=self.style, progress=cb,
                        include_sizes=self.sizes, markdown=self.markdown
                    )
                if not ok:
                    used_fallback = True
            except Exception:
                used_fallback = True

            if used_fallback:
                base = os.path.abspath(st.selected_folder)
                total = 0
                for _, _, files in self._filtered_walk(base):
                    total += 1 + len(files)
                total = max(1, total)

                done = 0
                with open(self.out_path, "w", encoding="utf-8", errors="replace") as w:
                    if self.markdown:
                        w.write("```text\n")

                    w.write(os.path.basename(base) + "/\n")
                    done += 1; self.progress.emit(done, total)

                    for curr, dirs, files in self._filtered_walk(base):
                        if curr != base:
                            depth = len(os.path.relpath(curr, base).split(os.sep))
                            w.write(self._prefix(depth) + os.path.basename(curr) + "/\n")
                            done += 1; self.progress.emit(done, total)

                        for f in sorted(files, key=str.lower):
                            p = os.path.join(curr, f)
                            depth = (len(os.path.relpath(curr, base).split(os.sep)) if curr != base else 0) + 1
                            if self.sizes:
                                try:
                                    s = os.path.getsize(p)
                                    line = f"{self._prefix(depth)}{f} ({hr_size(s)})\n"
                                except Exception:
                                    line = f"{self._prefix(depth)}{f}\n"
                            else:
                                line = f"{self._prefix(depth)}{f}\n"
                            w.write(line)
                            done += 1; self.progress.emit(done, total)

                    if self.markdown:
                        w.write("```\n")

            self.done.emit(True, self.out_path, "")
        except Exception as e:
            self.done.emit(False, self.out_path, str(e))
