# src/ui/main_window.py

import customtkinter as ctk
from tkinter import ttk
import tkinter as tk
from queue import Queue, Empty
from threading import Thread
import time
import os

from src.config import WINDOW_TITLE, WINDOW_SIZE
from src.ui.exclusion_manager import ExclusionManager
from src.ui.file_preview import FilePreview
from src.core.file_scanner import FileScanner
from src.core.file_processor import FileProcessor
from src.core.settings_manager import SettingsManager
from src.utils.logger import logger
from tkinter import filedialog, messagebox

class MainWindow:
    def __init__(self, root: ctk.CTk):


        self.root = root
        self.root.title(WINDOW_TITLE)
        self.root.geometry(WINDOW_SIZE)

        # Core components
        self.scanner = None
        self.processor = None
        self.settings_manager = None

        # State variables
        self.selected_folder = ""
        self.queue = Queue()
        self.excluded_files = set()
        self.stop_scan = False  # <-- for optional "Cancel Scan"

        # UI initialization
        self.create_initial_screen()

        # Process the queue periodically
        self.root.after(100, self.process_queue)

    def create_initial_screen(self):
        """Create the initial screen prompting the user to select a folder."""
        self.initial_frame = ctk.CTkFrame(self.root)
        self.initial_frame.pack(fill="both", expand=True, padx=20, pady=20)

        label = ctk.CTkLabel(
            self.initial_frame,
            text="Select a folder to start:",
            font=("Segoe UI", 16)
        )
        label.pack(pady=50)

        browse_button = ctk.CTkButton(
            self.initial_frame,
            text="Browse Folder",
            command=self.select_folder,
            font=("Segoe UI", 14),
            width=200,
            height=40
        )
        browse_button.pack(pady=20)

    def select_folder(self):
        """Handle folder selection and transition to the main UI."""
        folder = filedialog.askdirectory(title="Select Folder")
        if folder:
            self.selected_folder = os.path.abspath(folder)
            logger.info(f"Selected folder: {self.selected_folder}")

            # Initialize Scanner, Processor, and Settings
            self.scanner = FileScanner(self.selected_folder)

            # 1) Auto-exclude known huge folders so we skip them
            heavy_folders = []
            self.scanner.excluded_folder_names.update(heavy_folders)

            self.processor = FileProcessor(self.selected_folder)
            self.settings_manager = SettingsManager(self.selected_folder)

            if hasattr(self, 'initial_frame') and self.initial_frame.winfo_exists():
                # First-time selection: destroy initial frame, create main UI
                self.initial_frame.destroy()
                self.create_main_ui()
            else:
                # Changing folder from main UI
                self.reset_main_ui()

            # Load settings after main_ui is ready
            self.load_settings()

    def reset_main_ui(self):
        """Reset the main UI components for a new folder."""
        if hasattr(self, 'main_frame') and self.main_frame.winfo_exists():
            self.main_frame.destroy()
        self.excluded_files = set()
        self.stop_scan = False
        self.create_main_ui()

    def create_main_ui(self):
        """Create the main user interface."""
        self.main_frame = ctk.CTkFrame(self.root)
        self.main_frame.pack(fill="both", expand=True, padx=10, pady=10)

        # Exclusion Manager & File Preview
        self.exclusion_manager = ExclusionManager(self)
        self.file_preview = FilePreview(self)

        # Appearance/Theme Toggle
        theme_frame = ctk.CTkFrame(self.main_frame)
        theme_frame.pack(anchor='ne', pady=(0, 10))

        theme_label = ctk.CTkLabel(theme_frame, text="Appearance Mode:", font=("Segoe UI", 12))
        theme_label.pack(side=tk.LEFT, padx=(0, 10))

        self.theme_option = ctk.CTkOptionMenu(
            theme_frame,
            values=["System", "Light", "Dark"],
            command=self.change_theme,
            width=100
        )
        self.theme_option.set(ctk.get_appearance_mode())
        self.theme_option.pack(side=tk.LEFT)

        # Paned window for file list + preview
        files_paned = ttk.PanedWindow(self.main_frame, orient=tk.HORIZONTAL)
        files_paned.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # File List Frame
        file_list_frame = ctk.CTkFrame(files_paned)
        files_paned.add(file_list_frame, weight=3)

        file_list_label = ctk.CTkLabel(
            file_list_frame, text="Files to Process", font=("Segoe UI", 14)
        )
        file_list_label.pack(anchor="w", pady=(0, 5), padx=10)

        # Search Frame
        search_frame = ctk.CTkFrame(file_list_frame)
        search_frame.pack(fill="x", padx=10, pady=(0, 5))

        search_label = ctk.CTkLabel(search_frame, text="Search:", font=("Segoe UI", 12))
        search_label.pack(side=tk.LEFT, padx=(0, 10))

        self.search_var = tk.StringVar()
        search_entry = ctk.CTkEntry(search_frame, textvariable=self.search_var, width=200)
        search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        search_entry.bind("<KeyRelease>", self.perform_search)

        # Treeview for files
        self.file_tree = ttk.Treeview(
            file_list_frame,
            columns=("Filename", "Path"),
            show="headings",
            selectmode="extended"
        )
        self.file_tree.heading("Filename", text="Filename")
        self.file_tree.heading("Path", text="Path")
        self.file_tree.column("Filename", width=200, anchor='w')
        self.file_tree.column("Path", width=400, anchor='w')
        self.file_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(10, 0), pady=5)

        tree_scroll = ttk.Scrollbar(file_list_frame, orient="vertical", command=self.file_tree.yview)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.file_tree.configure(yscrollcommand=tree_scroll.set)

        # Bind selection event for file preview
        self.file_tree.bind("<<TreeviewSelect>>", self.preview_file)

        # File Preview
        self.file_preview.setup_ui(files_paned)

        # Action Buttons Frame
        action_frame = ctk.CTkFrame(self.main_frame)
        action_frame.pack(fill="x", padx=10, pady=10)

        exclude_button = ctk.CTkButton(
            action_frame,
            text="Exclude Selected",
            command=self.exclude_selected_files,
            font=("Segoe UI", 12),
            width=150,
            height=40
        )
        exclude_button.pack(side=tk.LEFT, padx=5)

        select_all_button = ctk.CTkButton(
            action_frame,
            text="Select All",
            command=self.select_all_files,
            font=("Segoe UI", 12),
            width=120,
            height=40
        )
        select_all_button.pack(side=tk.LEFT, padx=5)

        deselect_all_button = ctk.CTkButton(
            action_frame,
            text="Deselect All",
            command=self.deselect_all_files,
            font=("Segoe UI", 12),
            width=130,
            height=40
        )
        deselect_all_button.pack(side=tk.LEFT, padx=5)

        generate_output_button = ctk.CTkButton(
            action_frame,
            text="Generate Combined Output",
            command=self.generate_combined_output,
            font=("Segoe UI", 12),
            width=220,
            height=40
        )
        generate_output_button.pack(side=tk.RIGHT, padx=5)

        #
        # --- START OF CHANGE ---
        #
        refresh_button = ctk.CTkButton(
            action_frame,
            text="Refresh Files",
            command=self.update_file_list,  # Re-uses the existing update method
            font=("Segoe UI", 12),
            width=150,
            height=40
        )
        refresh_button.pack(side=tk.RIGHT, padx=5)
        #
        # --- END OF CHANGE ---
        #

        change_folder_button = ctk.CTkButton(
            action_frame,
            text="Change Folder",
            command=self.select_folder,
            font=("Segoe UI", 12),
            width=150,
            height=40
        )
        change_folder_button.pack(side=tk.RIGHT, padx=5)

        # (Optional) Cancel Scan Button
        cancel_scan_btn = ctk.CTkButton(
            action_frame,
            text="Cancel Scan",
            command=self.cancel_scan,
            font=("Segoe UI", 12),
            width=130,
            height=40
        )
        cancel_scan_btn.pack(side=tk.LEFT, padx=5)

        # Progress Bar
        self.progress_bar = ctk.CTkProgressBar(self.main_frame)
        self.progress_bar.pack(fill="x", padx=10, pady=10)
        self.progress_bar.set(0)

        # Status Bar
        self.status_var = tk.StringVar(value="Ready")
        status_bar = ctk.CTkLabel(
            self.main_frame,
            textvariable=self.status_var,
            anchor=tk.W,
            font=("Segoe UI", 12)
        )
        status_bar.pack(fill="x", padx=10, pady=(0, 10))

        # Finally, start scanning automatically
        self.start_scanning()

    def cancel_scan(self):
        """Stop scanning in progress."""
        self.stop_scan = True
        self.status_var.set("Cancelling scan...")

    def change_theme(self, selected_mode):
        ctk.set_appearance_mode(selected_mode)
        logger.info(f"Appearance mode changed to {selected_mode}")

    def start_scanning(self):
        """Start scanning files in a background thread."""
        if not self.scanner:
            logger.error("FileScanner is not initialized.")
            return
        self.status_var.set("Scanning files...")
        self.progress_bar.set(0)
        self.disable_buttons()
        self.stop_scan = False  # reset before new scan

        scan_thread = Thread(target=self.scan_files_thread, daemon=True)
        scan_thread.start()

    def scan_files_thread(self):
        """Thread target for scanning files in chunks (generator-based)."""
        try:
            # 1) First pass: estimate total file count
            total_estimate = 0
            for _ in self.scanner.yield_files():
                total_estimate += 1

            if total_estimate == 0:
                # If no files found, just send a quick status
                self.queue.put(("progress", 100))
                self.queue.put(("status", "No files found."))
                self.queue.put(("scan_complete", None))
                return

            # 2) Second pass: yield the actual files and chunk them
            file_generator = self.scanner.yield_files()

            chunk_size = 100  # adjust as needed
            batch = []
            processed = 0

            for file_tuple in file_generator:
                if self.stop_scan:
                    self.queue.put(("status", "Scan cancelled by user."))
                    break

                batch.append(file_tuple)
                processed += 1

                # If we have enough files in batch, add them
                if len(batch) >= chunk_size:
                    self.queue.put(("add_files_bulk", batch.copy()))
                    batch.clear()

                    # Throttle progress
                    progress = (processed / total_estimate) * 100
                    self.queue.put(("progress", progress))
                    self.queue.put(("status", f"Scanning... {processed}/{total_estimate}"))

                    # Sleep a bit to keep UI responsive
                    time.sleep(0.01)

            # Push leftover batch if not cancelled
            if not self.stop_scan and batch:
                self.queue.put(("add_files_bulk", batch.copy()))
                batch.clear()

            if not self.stop_scan:
                # Final update if we finished scanning
                self.queue.put(("progress", 100))
                self.queue.put(("status", f"Scan complete. Found ~{processed} files."))
                logger.info("File scan complete.")

        except Exception as e:
            self.queue.put(("error", f"Failed to scan files: {str(e)}"))
            logger.error(f"Failed to scan files: {str(e)}")
        finally:
            self.queue.put(("scan_complete", None))

    def process_queue(self):
        """Process messages from the queue to update the GUI safely."""
        try:
            while True:
                message = self.queue.get_nowait()
                msg_type = message[0]

                if msg_type == "add_files_bulk":
                    files_batch = message[1]
                    for (file, rel_path) in files_batch:
                        self.file_tree.insert("", "end", values=(file, rel_path))

                elif msg_type == "progress":
                    self.progress_bar.set(message[1] / 100)

                elif msg_type == "status":
                    self.status_var.set(message[1])

                elif msg_type == "error":
                    self.status_var.set("Error occurred")
                    messagebox.showerror("Error", message[1])
                    self.enable_buttons()

                elif msg_type == "scan_complete":
                    self.enable_buttons()

                elif msg_type == "process_complete":
                    self.enable_buttons()

                elif msg_type == "message":
                    messagebox.showinfo("Info", message[1])

        except Empty:
            pass

        self.root.after(100, self.process_queue)

    def preview_file(self, event):
        """Preview the selected file's content."""
        selected_items = self.file_tree.selection()
        if selected_items:
            item = selected_items[0]
            filename, rel_path = self.file_tree.item(item)['values']
            file_path = os.path.join(self.selected_folder, rel_path)
            self.file_preview.display_preview(file_path)

    def exclude_selected_files(self):
        """Exclude the selected files from processing."""
        selected_items = self.file_tree.selection()
        if not selected_items:
            messagebox.showwarning("No Selection", "Please select file(s) to exclude.")
            return

        excluded_count = 0
        for item in selected_items:
            filename, rel_path = self.file_tree.item(item)['values']
            absolute_path = os.path.abspath(os.path.join(self.selected_folder, rel_path))
            self.excluded_files.add(absolute_path)
            self.file_tree.delete(item)
            excluded_count += 1
            logger.info(f"Excluded file: {absolute_path}")

        # Update ExclusionManager
        self.exclusion_manager.update_excluded_files(self.excluded_files)

        # Update FileScanner's exclusion lists
        self.scanner.excluded_files = self.excluded_files
        self.scanner.excluded_folders = set(
            os.path.normpath(folder) for folder in self.exclusion_manager.excluded_folders
        )
        self.scanner.excluded_file_patterns = self.exclusion_manager.excluded_file_patterns

        # Save & re-scan
        self.save_settings()
        self.status_var.set(f"Excluded {excluded_count} file(s)")
        messagebox.showinfo("Excluded", f"Excluded {excluded_count} file(s) from processing.")
        self.update_file_list()

    def select_all_files(self):
        """Select all files in the file list."""
        for item in self.file_tree.get_children():
            self.file_tree.selection_add(item)

    def deselect_all_files(self):
        """Deselect all selected files in the file list."""
        for item in self.file_tree.selection():
            self.file_tree.selection_remove(item)

    def generate_combined_output(self):
        """Initiate the output generation process."""
        if not self.file_tree.get_children():
            messagebox.showwarning("No Files", "There are no files to process.")
            return

        output_path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
            initialfile="combined_output.txt",
            title="Save Combined Output As"
        )
        if not output_path:
            return  # user cancelled

        self.status_var.set("Generating combined output...")
        self.progress_bar.set(0)
        self.disable_buttons()

        # Gather files from TreeView
        files = []
        for item in self.file_tree.get_children():
            filename, rel_path = self.file_tree.item(item)['values']
            files.append((filename, rel_path))

        # Run in background
        process_thread = Thread(target=self.process_files_thread, args=(files, output_path), daemon=True)
        process_thread.start()

    def process_files_thread(self, files, output_path):
        """Process/combine files in a background thread."""
        try:
            total_files = len(files)
            processed = 0

            def progress_callback(proc, total):
                progress = (proc / total) * 100 if total > 0 else 100
                self.queue.put(("progress", progress))
                self.queue.put(("status", f"Processing file {proc}/{total}"))

            success = self.processor.process_files(files, output_path, progress_callback)
            if success:
                self.queue.put(("progress", 100))
                self.queue.put(("status", "Output generation complete"))
                self.queue.put(("message", f"Combined output saved to:\n{output_path}"))
                logger.info(f"Combined output generated at: {output_path}")
            else:
                self.queue.put(("error", "Failed to generate combined output."))
        except Exception as e:
            self.queue.put(("error", f"Failed to generate output: {str(e)}"))
            logger.error(f"Failed to generate output: {str(e)}")
        finally:
            self.queue.put(("process_complete", None))

    def update_file_list(self):
        """Update the file list based on current exclusions."""
        if not self.scanner:
            logger.error("FileScanner is not initialized.")
            return

        # Update scanner’s exclusions
        self.scanner.excluded_folders = set(
            os.path.normpath(folder) for folder in self.exclusion_manager.excluded_folders
        )
        self.scanner.excluded_file_patterns = self.exclusion_manager.excluded_file_patterns
        self.scanner.excluded_files = self.excluded_files

        logger.debug(
            f"FileScanner Exclusions Set:\n"
            f"Excluded Folders: {self.scanner.excluded_folders}\n"
            f"Excluded Patterns: {self.scanner.excluded_file_patterns}\n"
            f"Excluded Files: {self.scanner.excluded_files}"
        )

        # Clear existing file list
        self.file_tree.delete(*self.file_tree.get_children())

        # Start a fresh scan
        self.start_scanning()

    def disable_buttons(self):
        """Disable all CTkButton widgets to prevent multiple clicks."""
        def disable_recursively(widget):
            if isinstance(widget, ctk.CTkButton):
                widget.configure(state="disabled")
            for child in widget.winfo_children():
                disable_recursively(child)

        disable_recursively(self.main_frame)
        logger.debug("All buttons have been disabled.")

    def enable_buttons(self):
        """Enable all CTkButton widgets after an operation is complete."""
        def enable_recursively(widget):
            if isinstance(widget, ctk.CTkButton):
                widget.configure(state="normal")
            for child in widget.winfo_children():
                enable_recursively(child)

        enable_recursively(self.main_frame)
        logger.debug("All buttons have been enabled.")

    def save_settings(self):
        """Save current exclusion settings."""
        if not self.settings_manager:
            logger.error("SettingsManager is not initialized.")
            return

        settings = {
            "selected_folder": self.selected_folder,
            "excluded_folders": list(self.exclusion_manager.excluded_folders),
            "excluded_folder_names": list(self.exclusion_manager.excluded_folder_names),
            "excluded_file_patterns": list(self.exclusion_manager.excluded_file_patterns),
            "excluded_files": [
                os.path.relpath(path, self.selected_folder) for path in self.excluded_files
            ],
        }

        logger.debug(f"Saving settings: {settings}")
        success = self.settings_manager.save_settings(settings)
        if success:
            logger.info("Settings saved successfully.")
        else:
            messagebox.showerror("Error", "Failed to save settings.")

    def load_settings(self):
        """Load settings from file, then trigger scanning."""
        if not self.settings_manager:
            logger.error("SettingsManager is not initialized.")
            return

        settings = self.settings_manager.load_settings()
        if settings:
            self.selected_folder = settings.get("selected_folder", self.selected_folder)
            self.exclusion_manager.excluded_folders = set(settings.get("excluded_folders", []))
            self.exclusion_manager.excluded_folder_names = set(settings.get("excluded_folder_names", {"venv"}))
            self.exclusion_manager.excluded_file_patterns = set(settings.get("excluded_file_patterns", set()))
            self.excluded_files = set(
                os.path.abspath(os.path.join(self.selected_folder, path))
                for path in settings.get("excluded_files", [])
            )

            self.exclusion_manager.update_ui()
            self.update_file_list()  # re-scan with the loaded exclusions

            logger.debug(
                f"Loaded Settings:\n"
                f"Selected Folder: {self.selected_folder}\n"
                f"Excluded Folders: {self.exclusion_manager.excluded_folders}\n"
                f"Excluded Patterns: {self.exclusion_manager.excluded_file_patterns}\n"
                f"Excluded Files: {self.excluded_files}"
            )
            logger.info("Settings loaded successfully.")
        else:
            logger.info("No settings to load.")

    def perform_search(self, event):
        """Filter the TreeView based on search query."""
        query = self.search_var.get().lower()
        if not query:
            for item in self.file_tree.get_children():
                self.file_tree.item(item, tags=())
        else:
            for item in self.file_tree.get_children():
                filename, rel_path = self.file_tree.item(item)['values']
                if query in filename.lower() or query in rel_path.lower():
                    self.file_tree.item(item, tags=('match',))
                else:
                    self.file_tree.item(item, tags=())
        self.file_tree.tag_configure('match', background='lightblue')