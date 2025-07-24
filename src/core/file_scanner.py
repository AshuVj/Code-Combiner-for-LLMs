# src/core/file_scanner.py

import os
import fnmatch
from typing import Generator, Tuple, Literal
from src.utils.logger import logger
from src.config import PREDEFINED_EXCLUDED_FILES, BINARY_FILE_EXTENSIONS, EXCLUDED_FOLDER_NAMES_DEFAULT

FileType = Literal['text', 'binary']

class FileScanner:
    def __init__(self, base_folder: str):
        self.base_folder = base_folder
        self.excluded_folders = set()      # Relative paths from user settings
        self.excluded_folder_names = EXCLUDED_FOLDER_NAMES_DEFAULT  # Default set, can be updated
        self.excluded_file_patterns = set()
        self.excluded_files = set()        # Absolute paths from user settings

    def is_within_excluded_folder(self, path: str) -> bool:
        """Check if a path is within an excluded folder (by name or by full path)."""
        path = os.path.normpath(path)
        path_parts = path.split(os.sep)

        # Check against default and user-defined folder names
        if self.excluded_folder_names.intersection(path_parts):
            logger.debug(f"Excluding folder due to name match: {path}")
            return True
        
        # Check against user-defined full folder paths
        for excluded_folder in self.excluded_folders:
            excluded_folder = os.path.normpath(excluded_folder)
            if path == excluded_folder or path.startswith(excluded_folder + os.sep):
                logger.debug(f"Excluding folder path due to full path match: {path}")
                return True
        return False

    def is_file_excluded(self, filename: str, rel_path: str) -> bool:
        """Check if a file should be completely hidden from the list."""
        # Predefined exclusions (e.g., combined_output.txt)
        if filename in PREDEFINED_EXCLUDED_FILES:
            return True

        # User-defined patterns
        for pattern in self.excluded_file_patterns:
            if fnmatch.fnmatch(filename, pattern):
                logger.debug(f"Excluding file '{filename}' due to pattern '{pattern}'")
                return True

        # User-excluded specific files (by absolute path)
        absolute_path = os.path.abspath(os.path.join(self.base_folder, rel_path))
        if absolute_path in self.excluded_files:
            return True

        return False

    def get_file_type(self, filename: str) -> FileType:
        """Determine if a file is likely text or binary based on its extension."""
        _, ext = os.path.splitext(filename)
        if ext.lower() in BINARY_FILE_EXTENSIONS:
            return 'binary'
        return 'text'

    def yield_files(self) -> Generator[Tuple[str, str, FileType], None, None]:
        """
        Generator that yields (filename, relative_path, file_type) for each file.
        This no longer hides binary files, it identifies them.
        """
        try:
            for root_dir, dirs, files in os.walk(self.base_folder, topdown=True):
                # Filter out excluded subdirectories in-place
                dirs[:] = [d for d in dirs if not self.is_within_excluded_folder(
                    os.path.normpath(os.path.join(os.path.relpath(root_dir, self.base_folder), d))
                )]
                
                # Process files in the current directory
                for file in files:
                    rel_path = os.path.normpath(os.path.join(os.path.relpath(root_dir, self.base_folder), file))
                    
                    # Exclude if it matches user-defined rules
                    if self.is_file_excluded(file, rel_path):
                        logger.debug(f"Completely excluding file: {rel_path}")
                        continue
                    
                    # Identify file type and yield
                    file_type = self.get_file_type(file)
                    logger.debug(f"Including file: {rel_path} (Type: {file_type})")
                    yield (file, rel_path, file_type)

        except Exception as e:
            logger.error(f"Error scanning files: {str(e)}")
            return