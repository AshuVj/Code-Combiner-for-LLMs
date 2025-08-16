# src/app.py

import customtkinter as ctk
from src.ui.main_window import MainWindow
from src.utils.logger import logger

class FileCombinerApp:
    def __init__(self):
        self.root = None
        self.main_window = None

    def run(self):
        """Initialize and run the application."""
        try:
            ctk.set_appearance_mode("System")
            ctk.set_default_color_theme("blue")

            self.root = ctk.CTk()
            self.main_window = MainWindow(self.root)

            self.root.mainloop()
        except Exception as e:
            logger.error(f"Application error: {str(e)}")
            raise

    def on_close(self):
        """Handled by MainWindow now."""
        pass
