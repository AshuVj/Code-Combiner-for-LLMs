# src/core/file_processor.py

import os
from typing import List, Tuple, Callable
from src.utils.encoding_detector import detect_file_encoding
from src.utils.logger import logger

class FileProcessor:
    def __init__(self, base_folder: str):
        self.base_folder = base_folder

    def process_files(self,
                     files: List[Tuple[str, str, str]], # Expects a 3-item tuple now
                     output_path: str,
                     progress_callback: Callable[[int, int], None] = None) -> bool:
        """Process and combine files, handling text and binary types."""
        try:
            with open(output_path, "w", encoding="utf-8") as outfile:
                total_files = len(files)
                for i, (filename, rel_path, file_type) in enumerate(files):
                    file_path = os.path.join(self.base_folder, rel_path)
                    
                    outfile.write(f"\n{'=' * 80}\n")
                    outfile.write(f"File: {filename}\n")
                    outfile.write(f"Path: {rel_path}\n")
                    outfile.write(f"{'=' * 80}\n\n")

                    if file_type == 'text':
                        try:
                            encoding = detect_file_encoding(file_path)
                            with open(file_path, "r", encoding=encoding) as infile:
                                outfile.write(infile.read())
                        except Exception as e:
                            logger.error(f"Error reading text file {file_path}: {str(e)}")
                            outfile.write(f"[Error reading file: {str(e)}]\n")
                    
                    elif file_type == 'binary':
                        outfile.write("[Binary file - content not included]\n")

                    outfile.write("\n\n")
                    if progress_callback:
                        progress_callback(i + 1, total_files)
            
            logger.info(f"Output generated successfully at {output_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to generate output: {str(e)}")
            return False