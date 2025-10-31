# src/ui_qt/workers/scan_worker.py
from __future__ import annotations
from typing import List, Tuple
from PySide6.QtCore import QThread, Signal
import time

from src.core.file_scanner import FileScanner
from src.config import EXCLUDED_FOLDER_NAMES_DEFAULT

class ScanWorker(QThread):
    batch = Signal(list)                 # List[Tuple[str, str, str]]
    progress = Signal(int, int)          # processed, total
    status = Signal(str)
    finishedOk = Signal()

    def __init__(self, state):
        super().__init__()
        self.state = state
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        st = self.state
        if not st.scanner:
            self.status.emit("Scanner not initialized.")
            self.finishedOk.emit()
            return

        st.scanner.excluded_folders = set(st.excluded_folders)
        st.scanner.excluded_file_patterns = set(st.excluded_file_patterns)
        st.scanner.excluded_files = set(st.excluded_files_abs)
        st.scanner.apply_gitignore = bool(st.apply_gitignore)
        st.scanner.excluded_folder_names = set(EXCLUDED_FOLDER_NAMES_DEFAULT) if st.use_default_folder_names else set()

        processed = 0
        batch: List[Tuple[str, str, str]] = []
        chunk_size = 180

        for item in st.scanner.yield_files():
            if self._stop:
                self.status.emit("Scan cancelled.")
                break
            batch.append(item)
            processed += 1
            if len(batch) >= chunk_size:
                self.batch.emit(batch.copy())
                batch.clear()
                # Indeterminate progress during single-pass scan (total=0)
                self.progress.emit(processed, 0)
                self.status.emit(f"Scanning… {processed} files")
                time.sleep(0.003)

        if not self._stop:
            if batch:
                self.batch.emit(batch.copy())
            if processed == 0:
                self.status.emit("No files found.")
            else:
                self.status.emit(f"Scan complete. Found {processed} files.")

        self.finishedOk.emit()
