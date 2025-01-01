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
            
            ctk.set_widget_scaling(0.9)
            ctk.set_window_scaling(0.9)

            self.root = ctk.CTk()
            self.main_window = MainWindow(self.root)
            
            # Set up close handler
            self.root.protocol("WM_DELETE_WINDOW", self.on_close)
            
            # Start the application
            self.root.mainloop()
        except Exception as e:
            logger.error(f"Application error: {str(e)}")
            raise

    def on_close(self):
        """Handle application closing."""
        try:
            if self.main_window:
                # Save settings before closing
                self.main_window.save_settings()
            self.root.destroy()
        except Exception as e:
            logger.error(f"Error during shutdown: {str(e)}")
