# src/core/file_scanner.py

import os
import fnmatch
from typing import Generator, Tuple
from src.utils.logger import logger
from src.config import PREDEFINED_EXCLUDED_FILES

class FileScanner:
    def __init__(self, base_folder: str):
        self.base_folder = base_folder
        self.excluded_folders = set()      # Relative paths
        self.excluded_folder_names = {}  # Default set, can be updated externally
        self.excluded_file_patterns = set()
        self.excluded_files = set()        # Absolute paths

    def is_within_excluded_folder(self, path: str) -> bool:
        """Check if a path is within an excluded folder."""
        path = os.path.normpath(path)

        # If path matches or is inside an explicitly excluded folder
        for excluded_folder in self.excluded_folders:
            excluded_folder = os.path.normpath(excluded_folder)
            if path == excluded_folder or path.startswith(excluded_folder + os.sep):
                logger.debug(f"Excluding folder path: {path}")
                return True

        # If path segment matches a known excluded folder name
        path_parts = path.split(os.sep)
        for part in path_parts:
            if part in self.excluded_folder_names:
                logger.debug(f"Excluding folder due to name: {part}")
                return True

        return False

    def is_file_excluded(self, filename: str, rel_path: str) -> bool:
        """Check if a file should be excluded based on patterns or predefined exclusions."""
        # Predefined exclusions (e.g., combined_output.txt, README.md, etc.)
        if filename in PREDEFINED_EXCLUDED_FILES:
            logger.debug(f"Excluding file due to predefined exclusion: {filename}")
            return True

        # Check file patterns (e.g., *.txt)
        for pattern in self.excluded_file_patterns:
            if fnmatch.fnmatch(filename, pattern):
                logger.debug(f"Excluding file '{filename}' due to pattern '{pattern}'")
                return True

        # Check absolute path list
        absolute_path = os.path.abspath(os.path.join(self.base_folder, rel_path))
        if absolute_path in self.excluded_files:
            logger.debug(f"Excluding file '{absolute_path}' as it's in excluded_files list.")
            return True

        return False

    def yield_files(self) -> Generator[Tuple[str, str], None, None]:
        """
        Generator that yields (filename, relative_path) for each file 
        that is NOT excluded. This avoids building a massive list in memory.
        """
        try:
            for root_dir, dirs, files in os.walk(self.base_folder):
                rel_dir = os.path.relpath(root_dir, self.base_folder)
                rel_dir = "" if rel_dir == "." else os.path.normpath(rel_dir)

                # Skip if folder is excluded
                if self.is_within_excluded_folder(rel_dir):
                    dirs[:] = []
                    logger.debug(f"Skipping excluded folder: {rel_dir}")
                    continue

                # Filter out subdirectories that are within excluded folders
                dirs[:] = [
                    d for d in dirs
                    if not self.is_within_excluded_folder(os.path.normpath(os.path.join(rel_dir, d)))
                ]

                # Yield non-excluded files
                for file in files:
                    rel_path = os.path.normpath(os.path.join(rel_dir, file))
                    if not self.is_file_excluded(file, rel_path):
                        logger.debug(f"Including file: {rel_path}")
                        yield (file, rel_path)
                    else:
                        logger.debug(f"Excluded file: {rel_path}")

        except Exception as e:
            logger.error(f"Error scanning files: {str(e)}")
            # In case of error, we just stop yielding
            return
