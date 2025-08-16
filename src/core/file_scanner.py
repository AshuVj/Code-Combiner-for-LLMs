# src/core/file_scanner.py

import os
import fnmatch
from typing import Generator, Tuple, Literal
from src.utils.logger import logger
from src.config import PREDEFINED_EXCLUDED_FILES, BINARY_FILE_EXTENSIONS, EXCLUDED_FOLDER_NAMES_DEFAULT

# NEW: honor .gitignore
from pathspec import PathSpec

FileType = Literal['text', 'binary']

class FileScanner:
    def __init__(self, base_folder: str):
        self.base_folder = base_folder
        self.excluded_folders = set()      # Relative paths from user settings
        self.excluded_folder_names = EXCLUDED_FOLDER_NAMES_DEFAULT  # Default set, can be updated
        self.excluded_file_patterns = set()
        self.excluded_files = set()        # Absolute paths from user settings

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
        if not self._gitignore_spec:
            return False
        try:
            return self._gitignore_spec.match_file(rel_path)
        except Exception:
            return False

    def is_within_excluded_folder(self, path: str) -> bool:
        """Check if a path is within an excluded folder (by name or by full path)."""
        path = os.path.normpath(path)
        path_parts = path.split(os.sep)

        # name-based exclusions
        if self.excluded_folder_names.intersection(path_parts):
            logger.debug(f"Excluding folder due to name match: {path}")
            return True

        # .gitignore
        if self._ignored_by_git(path):
            logger.debug(f"Excluding folder due to .gitignore: {path}")
            return True

        # user-defined full paths
        for excluded_folder in self.excluded_folders:
            excluded_folder = os.path.normpath(excluded_folder)
            if path == excluded_folder or path.startswith(excluded_folder + os.sep):
                logger.debug(f"Excluding folder path due to full path match: {path}")
                return True
        return False

    def is_file_excluded(self, filename: str, rel_path: str) -> bool:
        """Check if a file should be completely hidden from the list."""
        if filename in PREDEFINED_EXCLUDED_FILES:
            return True

        # .gitignore
        if self._ignored_by_git(rel_path):
            return True

        # patterns
        for pattern in self.excluded_file_patterns:
            if fnmatch.fnmatch(filename, pattern):
                logger.debug(f"Excluding file '{filename}' due to pattern '{pattern}'")
                return True

        # user-defined absolute path
        absolute_path = os.path.abspath(os.path.join(self.base_folder, rel_path))
        if absolute_path in self.excluded_files:
            return True

        return False

    def get_file_type(self, filename: str) -> FileType:
        _, ext = os.path.splitext(filename)
        if ext.lower() in BINARY_FILE_EXTENSIONS:
            return 'binary'
        return 'text'

    def yield_files(self) -> Generator[Tuple[str, str, FileType], None, None]:
        """
        Generator that yields (filename, relative_path, file_type) for each file.
        Deterministically sorted; identifies binary vs text.
        """
        try:
            for root_dir, dirs, files in os.walk(self.base_folder, topdown=True):
                rel_root = os.path.normpath(os.path.relpath(root_dir, self.base_folder))
                if rel_root == ".":
                    rel_root = ""

                # filter dirs in-place (name/fullpath/.gitignore) and sort
                dirs[:] = [d for d in dirs if not self.is_within_excluded_folder(
                    os.path.normpath(os.path.join(rel_root, d)) if rel_root else d
                )]
                dirs.sort(key=str.lower)

                # sort files deterministically
                files = sorted(files, key=str.lower)

                for file in files:
                    rel_path = os.path.normpath(os.path.join(rel_root, file)) if rel_root else file

                    if self.is_file_excluded(file, rel_path):
                        logger.debug(f"Completely excluding file: {rel_path}")
                        continue

                    file_type = self.get_file_type(file)
                    logger.debug(f"Including file: {rel_path} (Type: {file_type})")
                    yield (file, rel_path, file_type)

        except Exception as e:
            logger.error(f"Error scanning files: {str(e)}")
            return
