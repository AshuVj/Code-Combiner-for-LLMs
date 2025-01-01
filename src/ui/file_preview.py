# src/ui/file_preview.py

import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox
from src.utils.encoding_detector import detect_file_encoding
from src.utils.logger import logger
from src.config import PREVIEW_CHUNK_SIZE
import os

class FilePreview:
    def __init__(self, main_window):
        self.main_window = main_window
        self.preview_text = None
        
    def setup_ui(self, parent_paned):
        """Setup the file preview UI components."""
        preview_frame = ctk.CTkFrame(parent_paned)
        parent_paned.add(preview_frame, weight=2)
        
        preview_label = ctk.CTkLabel(preview_frame, text="File Preview", font=("Segoe UI", 14))
        preview_label.pack(anchor="w", pady=(0, 5), padx=10)
        
        # Text widget for preview
        self.preview_text = ctk.CTkTextbox(preview_frame, wrap=tk.WORD, state=tk.DISABLED, font=("Segoe UI", 12))
        self.preview_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # Scrollbar for Text widget
        preview_scroll = tk.Scrollbar(preview_frame, orient="vertical", command=self.preview_text.yview)
        preview_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.preview_text.configure(yscrollcommand=preview_scroll.set)
        
    def display_preview(self, file_path):
        """Display a preview of the selected file with line numbers."""
        self.preview_text.configure(state="normal")
        self.preview_text.delete("1.0", tk.END)
        try:
            encoding = detect_file_encoding(file_path) or 'utf-8'
            with open(file_path, "r", encoding=encoding) as f:
                content = f.read(PREVIEW_CHUNK_SIZE)
                lines = content.split('\n')
                numbered_content = ""
                for idx, line in enumerate(lines, 1):
                    numbered_content += f"{idx}: {line}\n"
                if len(content) == PREVIEW_CHUNK_SIZE:
                    numbered_content += "\n... (file content truncated for preview)"
                self.preview_text.insert(tk.END, numbered_content)
        except UnicodeDecodeError:
            self.preview_text.insert(tk.END, "Cannot preview binary or non-text file.")
            logger.warning(f"UnicodeDecodeError for file {file_path}")
        except Exception as e:
            self.preview_text.insert(tk.END, f"Error reading file:\n{str(e)}")
            logger.error(f"Error reading file {file_path}: {str(e)}")
        finally:
            self.preview_text.configure(state="disabled")
