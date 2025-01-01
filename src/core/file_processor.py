# src/core/file_processor.py

import os
from typing import List, Tuple, Callable
from src.utils.encoding_detector import detect_file_encoding
from src.utils.logger import logger

class FileProcessor:
    def __init__(self, base_folder: str):
        self.base_folder = base_folder

    def process_files(self, 
                     files: List[Tuple[str, str]], 
                     output_path: str,
                     progress_callback: Callable[[int, int], None] = None) -> bool:
        """
        Process and combine files into a single output file.
        
        Args:
            files: List of (filename, relative_path) tuples
            output_path: Path for the combined output file
            progress_callback: Optional callback for progress updates
            
        Returns:
            bool: True if processing is successful, False otherwise
        """
        try:
            total_files = len(files)
            processed = 0

            with open(output_path, "w", encoding="utf-8") as outfile:
                for filename, rel_path in files:
                    file_path = os.path.join(self.base_folder, rel_path)
                    try:
                        encoding = detect_file_encoding(file_path)
                        with open(file_path, "r", encoding=encoding) as infile:
                            outfile.write(f"\n{'=' * 80}\n")
                            outfile.write(f"File: {filename}\n")
                            outfile.write(f"Path: {rel_path}\n")
                            outfile.write(f"{'=' * 80}\n\n")
                            content = infile.read()
                            outfile.write(content)
                            outfile.write("\n\n")
                    except Exception as e:
                        logger.error(f"Error processing file {file_path}: {str(e)}")
                        outfile.write(f"Error reading file {filename}: {str(e)}\n")

                    processed += 1
                    if progress_callback:
                        progress_callback(processed, total_files)

            logger.info(f"Output generated successfully at {output_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to generate output: {str(e)}")
            return False
