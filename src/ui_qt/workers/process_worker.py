# src/ui_qt/workers/process_worker.py
from __future__ import annotations
from typing import List, Tuple
from PySide6.QtCore import QThread, Signal

from src.core.file_processor import FileProcessor
from src.ui_qt.workers.common import QtCancelEvent

class ProcessWorker(QThread):
    progress = Signal(int, int)
    status = Signal(str)
    done = Signal(bool, str, str)    # ok, out_path, err

    def __init__(self, state, files: List[Tuple[str, str, str]], out_path: str, *, include_toc: bool = False):
        super().__init__()
        self.state = state
        self.files = files
        self.out_path = out_path
        self.cancel_event = QtCancelEvent()
        self.include_toc = include_toc

    def cancel(self):
        self.cancel_event.set()

    def run(self):
        st = self.state
        if not st.processor:
            self.done.emit(False, self.out_path, "Processor not initialized.")
            return

        def cb(proc, total):
            self.progress.emit(proc, max(1, total))
            self.status.emit(f"Processing file {proc}/{total}")

        try:
            ok = st.processor.process_files(self.files, self.out_path, cb, self.cancel_event, include_toc=self.include_toc)
            if ok:
                self.done.emit(True, self.out_path, "")
            else:
                self.done.emit(False, self.out_path, "Failed to generate combined output.")
        except Exception as e:
            self.done.emit(False, self.out_path, str(e))
