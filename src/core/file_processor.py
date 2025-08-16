# src/core/file_processor.py

from __future__ import annotations

import os
import shutil
import tempfile
from typing import List, Tuple, Callable, Optional

# For Python <3.8, Protocol is in typing_extensions; this keeps Pylance happy too.
try:
    from typing import Protocol
except Exception:  # pragma: no cover
    from typing_extensions import Protocol  # type: ignore

from src.utils.encoding_detector import detect_file_encoding
from src.utils.logger import logger
from src.config import PROCESS_MAX_BYTES


class CancelEventLike(Protocol):
    """Duck-typed cancel event (e.g., threading.Event)."""
    def is_set(self) -> bool: ...


class FileProcessor:
    def __init__(self, base_folder: str):
        self.base_folder = base_folder

    def process_files(
        self,
        files: List[Tuple[str, str, str]],  # (filename, rel_path, file_type)
        output_path: str,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        cancel_event: Optional[CancelEventLike] = None,  # duck-typed: has is_set()
    ) -> bool:
        """
        Process and combine files, handling text and binary types.
        Writes atomically (tmp -> replace) and tolerates encoding issues.
        Skips very large text files with a note.
        """
        tmp_dir = os.path.dirname(output_path) or "."
        total_files = len(files)
        done = 0

        try:
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=tmp_dir) as tmp:
                tmp_path = tmp.name

                for (filename, rel_path, file_type) in files:
                    if cancel_event and getattr(cancel_event, "is_set", None) and cancel_event.is_set():
                        tmp.write("\n[Operation cancelled by user]\n")
                        logger.info("Processing cancelled by user.")
                        break

                    file_path = os.path.join(self.base_folder, rel_path)

                    tmp.write(f"\n{'=' * 80}\n")
                    tmp.write(f"File: {filename}\n")
                    tmp.write(f"Path: {rel_path}\n")
                    tmp.write(f"{'=' * 80}\n\n")

                    if file_type == "text":
                        try:
                            # Skip huge files (write a note instead)
                            try:
                                sz = os.path.getsize(file_path)
                            except OSError:
                                sz = None
                            if sz is not None and sz > PROCESS_MAX_BYTES:
                                mb = PROCESS_MAX_BYTES / (1024 * 1024)
                                tmp.write(f"[Skipped: file exceeds size limit ({mb:.1f} MB)]\n")
                            else:
                                encoding = detect_file_encoding(file_path)
                                with open(file_path, "r", encoding=encoding, errors="replace") as infile:
                                    shutil.copyfileobj(infile, tmp, length=1024 * 1024)  # 1MB chunks
                        except Exception as e:
                            logger.error(f"Error reading text file {file_path}: {str(e)}")
                            tmp.write(f"[Error reading file: {str(e)}]\n")

                    elif file_type == "binary":
                        tmp.write("[Binary file - content not included]\n")

                    tmp.write("\n\n")

                    done += 1
                    if progress_callback:
                        progress_callback(done, total_files)

            # Atomic replace
            os.replace(tmp_path, output_path)
            logger.info(f"Output generated successfully at {output_path}")
            return True

        except Exception as e:
            logger.error(f"Failed to generate output: {str(e)}")
            return False
