# src/ui_qt/workers/common.py
class QtCancelEvent:
    def __init__(self):
        self._flag = False
    def is_set(self) -> bool:
        return self._flag
    def set(self):
        self._flag = True
