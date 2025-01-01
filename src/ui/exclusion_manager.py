# src/ui/exclusion_manager.py

import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog
from src.utils.logger import logger
import os

class ExclusionManager:
    def __init__(self, main_window):
        self.main_window = main_window
        self.excluded_folders = set()  # Relative paths
        self.excluded_folder_names = {}  # Default excluded folder names
        self.excluded_file_patterns = set()
        self.excluded_files = set()  # Absolute paths
        
        # Predefined exclusions
        self.predefined_excluded_files = {"combined_output.txt", "README.md"}
        
        # Initialize UI components
        self.setup_ui()
        
    def setup_ui(self):
        """Setup the exclusion management UI components."""
        exclusion_frame = ctk.CTkFrame(self.main_window.main_frame)
        exclusion_frame.pack(fill="x", padx=10, pady=5)
        
        exclusion_label = ctk.CTkLabel(
            exclusion_frame,
            text="Exclusion Settings",
            font=("Segoe UI", 14)
        )
        exclusion_label.pack(anchor="w", pady=(0, 10))
        
        # Notebook for exclusion tabs
        exclusion_notebook = ctk.CTkTabview(exclusion_frame, width=400)
        exclusion_notebook.pack(fill="both", expand=True)
        
        # Excluded Folders Tab
        exclusion_notebook.add("Excluded Folders")
        folders_tab = exclusion_notebook.tab("Excluded Folders")
        
        # Listbox for Excluded Folders
        self.folder_listbox = tk.Listbox(
            folders_tab,
            height=5,
            font=("Segoe UI", 12),
            selectmode=tk.EXTENDED
        )
        self.folder_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(10, 0), pady=5)
        self.add_scrollbar(self.folder_listbox, folders_tab)
        
        # Buttons Frame
        folders_btn_frame = ctk.CTkFrame(folders_tab)
        folders_btn_frame.pack(side=tk.LEFT, fill=tk.Y, padx=10, pady=5)
        
        add_folder_btn = ctk.CTkButton(
            folders_btn_frame,
            text="Add Folder(s)",
            command=self.add_excluded_folders,
            font=("Segoe UI", 12),
            width=120,
            height=30
        )
        add_folder_btn.pack(pady=(0, 10))
        
        remove_folder_btn = ctk.CTkButton(
            folders_btn_frame,
            text="Remove Selected",
            command=self.remove_excluded_folders,
            font=("Segoe UI", 12),
            width=120,
            height=30
        )
        remove_folder_btn.pack()
        
        # Excluded Patterns Tab
        exclusion_notebook.add("Excluded Patterns")
        patterns_tab = exclusion_notebook.tab("Excluded Patterns")
        
        # Listbox for Excluded Patterns
        self.pattern_listbox = tk.Listbox(
            patterns_tab,
            height=5,
            font=("Segoe UI", 12),
            selectmode=tk.EXTENDED
        )
        self.pattern_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(10, 0), pady=5)
        self.add_scrollbar(self.pattern_listbox, patterns_tab)
        
        # Buttons Frame
        patterns_btn_frame = ctk.CTkFrame(patterns_tab)
        patterns_btn_frame.pack(side=tk.LEFT, fill=tk.Y, padx=10, pady=5)
        
        add_pattern_btn = ctk.CTkButton(
            patterns_btn_frame,
            text="Add Pattern",
            command=self.add_excluded_pattern,
            font=("Segoe UI", 12),
            width=120,
            height=30
        )
        add_pattern_btn.pack(pady=(0, 10))
        
        remove_pattern_btn = ctk.CTkButton(
            patterns_btn_frame,
            text="Remove Selected",
            command=self.remove_excluded_patterns,
            font=("Segoe UI", 12),
            width=120,
            height=30
        )
        remove_pattern_btn.pack()
        
        # Excluded Files Tab
        exclusion_notebook.add("Excluded Files")
        files_tab = exclusion_notebook.tab("Excluded Files")
        
        # Listbox for Excluded Files
        self.excluded_files_listbox = tk.Listbox(
            files_tab,
            height=5,
            font=("Segoe UI", 12),
            selectmode=tk.EXTENDED
        )
        self.excluded_files_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(10, 0), pady=5)
        self.add_scrollbar(self.excluded_files_listbox, files_tab)
        
        # Buttons Frame
        files_btn_frame = ctk.CTkFrame(files_tab)
        files_btn_frame.pack(side=tk.LEFT, fill=tk.Y, padx=10, pady=5)
        
        reinclude_btn = ctk.CTkButton(
            files_btn_frame,
            text="Re-include Selected",
            command=self.reinclude_selected_files,
            font=("Segoe UI", 12),
            width=150,
            height=30
        )
        reinclude_btn.pack()
        
    def add_scrollbar(self, listbox, parent):
        """Add a vertical scrollbar to a given listbox."""
        scrollbar = tk.Scrollbar(parent, orient=tk.VERTICAL, command=listbox.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        listbox.configure(yscrollcommand=scrollbar.set)
        
    def add_excluded_folders(self):
        """Add folders to the exclusion list."""
        while True:
            folder_path = filedialog.askdirectory(mustexist=True, title="Select Folder to Exclude")
            if not folder_path:
                break
            absolute_path = os.path.abspath(folder_path)
            rel_path = os.path.relpath(absolute_path, self.main_window.selected_folder)
            rel_path = os.path.normpath(rel_path)  # Ensure consistent path format
            if rel_path not in self.excluded_folders:
                self.excluded_folders.add(rel_path)
                self.folder_listbox.insert(tk.END, rel_path)
                logger.info(f"Added excluded folder: {absolute_path}")
                self.main_window.update_file_list()
                self.main_window.save_settings()
            else:
                messagebox.showwarning("Already Excluded", f"The folder '{rel_path}' is already excluded.")
            
            # Ask if the user wants to add another folder
            add_more = messagebox.askyesno("Add Another", "Do you want to add another folder to exclude?")
            if not add_more:
                break
            
    def remove_excluded_folders(self):
        """Remove selected folders from the exclusion list."""
        selected_indices = self.folder_listbox.curselection()
        if not selected_indices:
            messagebox.showwarning("No Selection", "Please select folder(s) to remove.")
            return
        
        removed = 0
        for index in reversed(selected_indices):
            rel_path = self.folder_listbox.get(index)
            self.excluded_folders.discard(rel_path)
            self.folder_listbox.delete(index)
            removed += 1
            absolute_path = os.path.abspath(os.path.join(self.main_window.selected_folder, rel_path))
            logger.info(f"Removed excluded folder: {absolute_path}")
        
        self.main_window.update_file_list()
        self.main_window.save_settings()
        messagebox.showinfo("Removed", f"Removed {removed} folder(s) from exclusion list.")
        
    def add_excluded_pattern(self):
        """Add a file pattern to the exclusion list."""
        pattern = simpledialog.askstring("Add Excluded Pattern", "Enter file pattern to exclude (e.g., *.txt):", parent=self.main_window.root)
        if pattern:
            pattern = pattern.strip()
            if pattern and pattern not in self.excluded_file_patterns and pattern not in self.predefined_excluded_files:
                self.excluded_file_patterns.add(pattern)
                self.pattern_listbox.insert(tk.END, pattern)
                logger.info(f"Added excluded pattern: {pattern}")
                self.main_window.update_file_list()
                self.main_window.save_settings()
                messagebox.showinfo("Success", f"Added excluded pattern: {pattern}")
            elif pattern in self.predefined_excluded_files:
                messagebox.showwarning("Predefined Exclusion", "This pattern is already a predefined exclusion.")
            else:
                messagebox.showwarning("Duplicate Pattern", "This pattern is already in the exclusion list.")
                
    def remove_excluded_patterns(self):
        """Remove selected patterns from the exclusion list."""
        selected_indices = self.pattern_listbox.curselection()
        if not selected_indices:
            messagebox.showwarning("No Selection", "Please select pattern(s) to remove.")
            return
        
        removed = 0
        for index in reversed(selected_indices):
            pattern = self.pattern_listbox.get(index)
            if pattern not in self.predefined_excluded_files:
                self.excluded_file_patterns.discard(pattern)
                self.pattern_listbox.delete(index)
                removed += 1
                logger.info(f"Removed excluded pattern: {pattern}")
        
        self.main_window.update_file_list()
        self.main_window.save_settings()
        messagebox.showinfo("Removed", f"Removed {removed} pattern(s) from exclusion list.")
        
    def reinclude_selected_files(self):
        """Re-include selected excluded files back into processing."""
        selected_indices = self.excluded_files_listbox.curselection()
        if not selected_indices:
            messagebox.showwarning("No Selection", "Please select file(s) to re-include.")
            return
        
        reincluded = 0
        for index in reversed(selected_indices):
            rel_path = self.excluded_files_listbox.get(index)
            absolute_path = os.path.abspath(os.path.join(self.main_window.selected_folder, rel_path))
            if absolute_path in self.main_window.excluded_files:
                self.main_window.excluded_files.discard(absolute_path)
                self.excluded_files_listbox.delete(index)
                reincluded += 1
                logger.info(f"Re-included file: {absolute_path}")
        
        self.main_window.update_file_list()
        self.main_window.save_settings()
        messagebox.showinfo("Re-included", f"Re-included {reincluded} file(s) into processing.")
        
    def update_excluded_files(self, excluded_files):
        """Update the excluded files listbox."""
        self.excluded_files = excluded_files
        self.excluded_files_listbox.delete(0, tk.END)
        for file in sorted(self.excluded_files):
            rel_path = os.path.relpath(file, self.main_window.selected_folder)
            self.excluded_files_listbox.insert(tk.END, rel_path)
        
    def update_ui(self):
        """Update the exclusion manager UI based on current exclusions."""
        # Update Excluded Folders
        self.folder_listbox.delete(0, tk.END)
        for folder in sorted(self.excluded_folders):
            self.folder_listbox.insert(tk.END, folder)
        
        # Update Excluded Patterns
        self.pattern_listbox.delete(0, tk.END)
        for pattern in sorted(self.excluded_file_patterns):
            self.pattern_listbox.insert(tk.END, pattern)
        for pattern in sorted(self.predefined_excluded_files):
            if pattern not in self.pattern_listbox.get(0, tk.END):
                self.pattern_listbox.insert(tk.END, pattern)
        
        # Update Excluded Files
        self.update_excluded_files(self.main_window.excluded_files)
