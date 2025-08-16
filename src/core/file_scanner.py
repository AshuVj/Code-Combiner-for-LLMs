# src/core/file_scanner.py

import os
import fnmatch
from typing import Generator, Tuple, Literal
from src.utils.logger import logger
from src.config import PREDEFINED_EXCLUDED_FILES, BINARY_FILE_EXTENSIONS, EXCLUDED_FOLDER_NAMES_DEFAULT

# honor .gitignore (toggleable)
from pathspec import PathSpec

FileType = Literal['text', 'binary']

class FileScanner:
    def __init__(self, base_folder: str):
        self.base_folder = base_folder

        # User-configurable (set by the UI)
        self.excluded_folders = set()                 # relative paths
        self.excluded_folder_names = EXCLUDED_FOLDER_NAMES_DEFAULT.copy()
        self.excluded_file_patterns = set()
        self.excluded_files = set()                   # absolute paths

        # NEW: switches (UI checkboxes)
        self.apply_gitignore = True
        self.use_predefined_excluded_files = True

        # Load .gitignore if present
        self._gitignore_spec = None
        gi = os.path.join(self.base_folder, ".gitignore")
        if os.path.exists(gi):
            try:
                with open(gi, "r", encoding="utf-8", errors="ignore") as f:
                    self._gitignore_spec = PathSpec.from_lines("gitwildmatch", f)
            except Exception as e:
                logger.warning(f"Failed to parse .gitignore: {e}")

    def _ignored_by_git(self, rel_path: str) -> bool:
        if not self.apply_gitignore:
            return False
        if not self._gitignore_spec:
            return False
        try:
            return self._gitignore_spec.match_file(rel_path)
        except Exception:
            return False

    def is_within_excluded_folder(self, path: str) -> bool:
        """Check if a rel path sits inside an excluded folder (by name or full rel path)."""
        path = os.path.normpath(path)
        path_parts = path.split(os.sep)

        # name-based (toggle-controlled)
        if self.excluded_folder_names.intersection(path_parts):
            return True

        # .gitignore
        if self._ignored_by_git(path):
            return True

        # user-defined full rel paths
        for ex in self.excluded_folders:
            ex = os.path.normpath(ex)
            if path == ex or path.startswith(ex + os.sep):
                return True
        return False

    def is_file_excluded(self, filename: str, rel_path: str) -> bool:
        # predefs (toggle-controlled)
        if self.use_predefined_excluded_files and filename in PREDEFINED_EXCLUDED_FILES:
            return True

        # .gitignore
        if self._ignored_by_git(rel_path):
            return True

        # pattern rules
        for pattern in self.excluded_file_patterns:
            if fnmatch.fnmatch(filename, pattern):
                return True

        # explicit absolute-path exclusions
        absolute = os.path.abspath(os.path.join(self.base_folder, rel_path))
        if absolute in self.excluded_files:
            return True

        return False

    def get_file_type(self, filename: str) -> FileType:
        _, ext = os.path.splitext(filename)
        if ext.lower() in BINARY_FILE_EXTENSIONS:
            return 'binary'
        return 'text'

    def yield_files(self) -> Generator[Tuple[str, str, FileType], None, None]:
        """Yield (filename, relative_path, file_type), deterministically sorted."""
        try:
            for root_dir, dirs, files in os.walk(self.base_folder, topdown=True):
                rel_root = os.path.normpath(os.path.relpath(root_dir, self.base_folder))
                if rel_root == ".":
                    rel_root = ""

                # filter dirs in-place (names, explicit rel paths, .gitignore)
                dirs[:] = [
                    d for d in dirs
                    if not self.is_within_excluded_folder(
                        os.path.normpath(os.path.join(rel_root, d)) if rel_root else d
                    )
                ]
                dirs.sort(key=str.lower)

                for file in sorted(files, key=str.lower):
                    rel_path = os.path.normpath(os.path.join(rel_root, file)) if rel_root else file
                    if self.is_file_excluded(file, rel_path):
                        continue
                    yield (file, rel_path, self.get_file_type(file))
        except Exception as e:
            logger.error(f"Error scanning files: {e}")
            return
