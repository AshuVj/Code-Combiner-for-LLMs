# src/ui/main_window.py

import customtkinter as ctk
from tkinter import ttk
import tkinter as tk
from queue import Queue, Empty
from threading import Thread
import time
import os
import sys
import re

from src.config import WINDOW_TITLE, WINDOW_SIZE, EXCLUDED_FOLDER_NAMES_DEFAULT
from src.ui.exclusion_manager import ExclusionManager
from src.ui.file_preview import FilePreview
from src.core.file_scanner import FileScanner
from src.core.file_processor import FileProcessor
from src.core.settings_manager import SettingsManager
from src.core.tree_exporter import TreeExporter
from src.utils.logger import logger
from tkinter import filedialog, messagebox


def resource_path(rel_path: str) -> str:
    """Resolve resources in dev & PyInstaller."""
    try:
        base_path = sys._MEIPASS  # type: ignore[attr-defined]
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, rel_path)


class MainWindow:
    def __init__(self, root: ctk.CTk):
        self.root = root
        self.root.title(WINDOW_TITLE)
        try:
            self.root.iconbitmap(resource_path("resources/app_icon.ico"))
        except Exception:
            pass
        self.root.geometry(WINDOW_SIZE)

        # Core components
        self.scanner: FileScanner | None = None
        self.processor: FileProcessor | None = None
        self.settings_manager: SettingsManager | None = None

        # State
        self.selected_folder = ""
        self.queue: Queue = Queue()
        self.excluded_files: set[str] = set()
        self.stop_scan = False  # for "Cancel Scan"

        # UI init
        self.create_initial_screen()

        # Queue pump
        self.root.after(100, self.process_queue)

    # ---------------- Initial Screen ----------------

    def create_initial_screen(self):
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

    # ---------------- Folder selection ----------------

    def select_folder(self):
        folder = filedialog.askdirectory(title="Select Folder")
        if not folder:
            return

        self.selected_folder = os.path.abspath(folder)
        logger.info(f"Selected folder: {self.selected_folder}")

        # Init services
        self.scanner = FileScanner(self.selected_folder)
        # Optionally auto-skip heavy dirs by NAME here:
        self.scanner.excluded_folder_names.update([])

        self.processor = FileProcessor(self.selected_folder)
        self.settings_manager = SettingsManager(self.selected_folder)

        if hasattr(self, 'initial_frame') and self.initial_frame.winfo_exists():
            self.initial_frame.destroy()
            self.create_main_ui()
        else:
            self.reset_main_ui()

        # Load settings AFTER UI exists
        self.load_settings()

    def reset_main_ui(self):
        if hasattr(self, 'main_frame') and self.main_frame.winfo_exists():
            self.main_frame.destroy()
        self.excluded_files = set()
        self.stop_scan = False
        self.create_main_ui()

    # ---------------- Main UI ----------------

    def create_main_ui(self):
        self.main_frame = ctk.CTkFrame(self.root)
        self.main_frame.pack(fill="both", expand=True, padx=10, pady=10)

        # Exclusions + Preview
        self.exclusion_manager = ExclusionManager(self)
        self.file_preview = FilePreview(self)

        # Theme switch
        theme_frame = ctk.CTkFrame(self.main_frame)
        theme_frame.pack(anchor='ne', pady=(0, 10))

        ctk.CTkLabel(theme_frame, text="Appearance Mode:", font=("Segoe UI", 12)).pack(side=tk.LEFT, padx=(0, 10))
        self.theme_option = ctk.CTkOptionMenu(
            theme_frame, values=["System", "Light", "Dark"], command=self.change_theme, width=100
        )
        self.theme_option.set(ctk.get_appearance_mode())
        self.theme_option.pack(side=tk.LEFT)

        # Paned: files + preview
        files_paned = ttk.PanedWindow(self.main_frame, orient=tk.HORIZONTAL)
        files_paned.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Left: file list
        file_list_frame = ctk.CTkFrame(files_paned)
        files_paned.add(file_list_frame, weight=3)

        ctk.CTkLabel(file_list_frame, text="Files to Process", font=("Segoe UI", 14)).pack(anchor="w", pady=(0, 5), padx=10)

        # Search
        search_frame = ctk.CTkFrame(file_list_frame)
        search_frame.pack(fill="x", padx=10, pady=(0, 5))

        ctk.CTkLabel(search_frame, text="Search:", font=("Segoe UI", 12)).pack(side=tk.LEFT, padx=(0, 10))
        self.search_var = tk.StringVar()
        search_entry = ctk.CTkEntry(search_frame, textvariable=self.search_var, width=200)
        search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        search_entry.bind("<KeyRelease>", self.perform_search)

        # Treeview (Filename, Path, Type)
        self.file_tree = ttk.Treeview(
            file_list_frame,
            columns=("Filename", "Path", "Type"),
            show="headings",
            selectmode="extended"
        )
        self.file_tree.heading("Filename", text="Filename")
        self.file_tree.heading("Path", text="Path")
        self.file_tree.heading("Type", text="Type")
        self.file_tree.column("Filename", width=220, anchor='w')
        self.file_tree.column("Path", width=460, anchor='w')
        self.file_tree.column("Type", width=80, anchor='w')
        self.file_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(10, 0), pady=5)

        tree_scroll = ttk.Scrollbar(file_list_frame, orient="vertical", command=self.file_tree.yview)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.file_tree.configure(yscrollcommand=tree_scroll.set)
        self.file_tree.bind("<<TreeviewSelect>>", self.preview_file)

        # Right: preview
        self.file_preview.setup_ui(files_paned)

        # Actions
        action_frame = ctk.CTkFrame(self.main_frame)
        action_frame.pack(fill="x", padx=10, pady=10)

        ctk.CTkButton(action_frame, text="Exclude Selected", command=self.exclude_selected_files,
                      font=("Segoe UI", 12), width=150, height=40).pack(side=tk.LEFT, padx=5)

        ctk.CTkButton(action_frame, text="Select All", command=self.select_all_files,
                      font=("Segoe UI", 12), width=120, height=40).pack(side=tk.LEFT, padx=5)

        ctk.CTkButton(action_frame, text="Deselect All", command=self.deselect_all_files,
                      font=("Segoe UI", 12), width=130, height=40).pack(side=tk.LEFT, padx=5)

        # NEW: Generate Selected Output (uses same dynamic filename)
        ctk.CTkButton(action_frame, text="Generate Selected Output", command=self.generate_selected_output,
                      font=("Segoe UI", 12), width=220, height=40).pack(side=tk.RIGHT, padx=5)

        ctk.CTkButton(action_frame, text="Generate Combined Output", command=self.generate_combined_output,
                      font=("Segoe UI", 12), width=220, height=40).pack(side=tk.RIGHT, padx=5)

        ctk.CTkButton(action_frame, text="Refresh Files", command=self.update_file_list,
                      font=("Segoe UI", 12), width=150, height=40).pack(side=tk.RIGHT, padx=5)

        ctk.CTkButton(action_frame, text="Change Folder", command=self.select_folder,
                      font=("Segoe UI", 12), width=150, height=40).pack(side=tk.RIGHT, padx=5)

        ctk.CTkButton(action_frame, text="Cancel Scan", command=self.cancel_scan,
                      font=("Segoe UI", 12), width=130, height=40).pack(side=tk.LEFT, padx=5)

        # NEW: Export File Tree
        ctk.CTkButton(action_frame, text="Export File Tree", command=self.export_file_tree,
                      font=("Segoe UI", 12), width=160, height=40).pack(side=tk.LEFT, padx=5)

        # Progress & Status
        self.progress_bar = ctk.CTkProgressBar(self.main_frame)
        self.progress_bar.pack(fill="x", padx=10, pady=10)
        self.progress_bar.set(0)

        self.status_var = tk.StringVar(value="Ready")
        ctk.CTkLabel(self.main_frame, textvariable=self.status_var, anchor=tk.W,
                     font=("Segoe UI", 12)).pack(fill="x", padx=10, pady=(0, 10))

        # Scan
        self.start_scanning()

    # ---------------- Helpers ----------------

    def _default_output_filename(self) -> str:
        """
        Build default name from the selected folder:
        'E:\\Projects\\Output Files' -> 'Output_Files.txt'
        """
        base = os.path.basename(self.selected_folder.rstrip("\\/")) or "combined_output"
        name = re.sub(r"\s+", "_", base)              # spaces -> _
        name = re.sub(r"[^\w.\-]+", "_", name)        # anything weird -> _
        name = name.strip("._-") or "combined_output"
        if not name.lower().endswith(".txt"):
            name += ".txt"
        return name

    def _ask_output_path(self) -> str:
        return filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
            initialfile=self._default_output_filename(),
            title="Save Combined Output As",
            initialdir=self.selected_folder or os.path.expanduser("~"),
        )

    # ---------------- Controls ----------------

    def cancel_scan(self):
        self.stop_scan = True
        self.status_var.set("Cancelling scan...")

    def change_theme(self, selected_mode):
        ctk.set_appearance_mode(selected_mode)
        logger.info(f"Appearance mode changed to {selected_mode}")

    # ---------------- Scanning ----------------

    def start_scanning(self):
        if not self.scanner:
            logger.error("FileScanner is not initialized.")
            return
        self.status_var.set("Scanning files...")
        self.progress_bar.set(0)
        self.disable_buttons()
        self.stop_scan = False
        Thread(target=self.scan_files_thread, daemon=True).start()

    def scan_files_thread(self):
        """Two-pass scan with progress + cancel."""
        try:
            # Pass 1: estimate
            total_estimate = 0
            for _ in self.scanner.yield_files():
                if self.stop_scan:
                    self.queue.put(("status", "Scan cancelled by user."))
                    self.queue.put(("scan_complete", None))
                    return
                total_estimate += 1

            if total_estimate == 0:
                self.queue.put(("status", "No files found."))
                self.queue.put(("scan_complete", None))
                return

            # Pass 2: actual
            file_generator = self.scanner.yield_files()
            chunk_size = 100
            batch = []
            processed = 0

            for file_tuple in file_generator:
                if self.stop_scan:
                    self.queue.put(("status", "Scan cancelled by user."))
                    break

                batch.append(file_tuple)
                processed += 1

                if len(batch) >= chunk_size:
                    self.queue.put(("add_files_bulk", batch.copy()))
                    batch.clear()

                    progress = (processed / max(1, total_estimate)) * 100
                    self.queue.put(("progress", progress))
                    self.queue.put(("status", f"Scanning... {processed}/{total_estimate}"))
                    time.sleep(0.01)

            if not self.stop_scan and batch:
                self.queue.put(("add_files_bulk", batch.copy()))
                batch.clear()

            if not self.stop_scan:
                self.queue.put(("progress", 100))
                self.queue.put(("status", f"Scan complete. Found {processed} files."))
                logger.info("File scan complete.")

        except Exception as e:
            self.queue.put(("error", f"Failed to scan files: {str(e)}"))
            logger.error(f"Failed to scan files: {str(e)}")
        finally:
            self.queue.put(("scan_complete", None))

    def process_queue(self):
        try:
            while True:
                msg_type, data = self.queue.get_nowait()

                if msg_type == "add_files_bulk":
                    for (file, rel_path, file_type) in data:
                        self.file_tree.insert("", "end", values=(file, rel_path, file_type.capitalize()))

                elif msg_type == "progress":
                    self.progress_bar.set(float(data) / 100.0)

                elif msg_type == "status":
                    self.status_var.set(data)

                elif msg_type == "error":
                    self.status_var.set("Error occurred")
                    messagebox.showerror("Error", data)
                    self.enable_buttons()

                elif msg_type == "scan_complete":
                    self.enable_buttons()

                elif msg_type == "process_complete":
                    self.enable_buttons()

                elif msg_type == "message":
                    messagebox.showinfo("Info", data)

        except Empty:
            pass

        self.root.after(100, self.process_queue)

    # ---------------- Preview ----------------

    def preview_file(self, _event):
        selected_items = self.file_tree.selection()
        if not selected_items:
            return
        item = selected_items[0]
        vals = self.file_tree.item(item).get('values') or []
        if len(vals) < 3:
            return
        _, rel_path, file_type = vals

        if str(file_type).lower() == 'binary':
            self.file_preview.display_preview(None, is_binary=True)
        else:
            file_path = os.path.join(self.selected_folder, rel_path)
            self.file_preview.display_preview(file_path, is_binary=False)

    # ---------------- Exclusions ----------------

    def exclude_selected_files(self):
        selected_items = self.file_tree.selection()
        if not selected_items:
            messagebox.showwarning("No Selection", "Please select file(s) to exclude.")
            return

        excluded_count = 0
        for item in selected_items:
            vals = self.file_tree.item(item).get('values') or []
            if len(vals) < 2:
                continue
            _, rel_path, _ = vals
            absolute_path = os.path.abspath(os.path.join(self.selected_folder, rel_path))
            self.excluded_files.add(absolute_path)
            self.file_tree.delete(item)
            excluded_count += 1
            logger.info(f"Excluded file: {absolute_path}")

        self.exclusion_manager.update_excluded_files(self.excluded_files)
        if self.scanner:
            self.scanner.excluded_files = self.excluded_files
            self.scanner.excluded_folders = set(
                os.path.normpath(folder) for folder in self.exclusion_manager.excluded_folders
            )
            self.scanner.excluded_file_patterns = self.exclusion_manager.excluded_file_patterns

        self.save_settings()
        self.status_var.set(f"Excluded {excluded_count} file(s)")
        messagebox.showinfo("Excluded", f"Excluded {excluded_count} file(s) from processing.")
        self.update_file_list()

    # ---------------- Selection helpers ----------------

    def select_all_files(self):
        for item in self.file_tree.get_children():
            self.file_tree.selection_add(item)

    def deselect_all_files(self):
        for item in self.file_tree.selection():
            self.file_tree.selection_remove(item)

    # ---------------- Combine ----------------

    def _collect_tree_files(self, selected_only: bool) -> list[tuple[str, str, str]]:
        items = self.file_tree.selection() if selected_only else self.file_tree.get_children()
        files_to_process: list[tuple[str, str, str]] = []
        for item in items:
            vals = self.file_tree.item(item).get('values') or []
            if len(vals) < 3:
                continue
            filename, rel_path, file_type = vals
            files_to_process.append((filename, rel_path, str(file_type).lower()))
        return files_to_process

    def generate_selected_output(self):
        if not self.file_tree.selection():
            messagebox.showwarning("No Selection", "Select some files first.")
            return
        out_path = self._ask_output_path()
        if not out_path:
            return
        files_to_process = self._collect_tree_files(selected_only=True)
        self._start_process(files_to_process, out_path)

    def generate_combined_output(self):
        if not self.file_tree.get_children():
            messagebox.showwarning("No Files", "There are no files to process.")
            return
        out_path = self._ask_output_path()
        if not out_path:
            return
        files_to_process = self._collect_tree_files(selected_only=False)
        self._start_process(files_to_process, out_path)

    def _start_process(self, files_to_process, output_path):
        self.status_var.set("Generating combined output...")
        self.progress_bar.set(0)
        self.disable_buttons()

        def runner():
            try:
                def progress_callback(proc, total):
                    progress = (proc / total) * 100 if total > 0 else 100
                    self.queue.put(("progress", progress))
                    self.queue.put(("status", f"Processing file {proc}/{total}"))

                ok = self.processor.process_files(files_to_process, output_path, progress_callback)  # type: ignore
                if ok:
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

        Thread(target=runner, daemon=True).start()

    # ---------------- Export File Tree ----------------

    def export_file_tree(self):
        if not self.selected_folder:
            messagebox.showwarning("No Folder", "Please select a folder first.")
            return

        tree_name = os.path.splitext(self._default_output_filename())[0] + "_tree.txt"
        out_path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
            initialfile=tree_name,
            title="Save File Tree As",
            initialdir=self.selected_folder or os.path.expanduser("~"),
        )
        if not out_path:
            return

        folder_names = set(EXCLUDED_FOLDER_NAMES_DEFAULT)
        if hasattr(self.exclusion_manager, "excluded_folder_names"):
            folder_names |= set(self.exclusion_manager.excluded_folder_names)

        excluded_folders = set(self.exclusion_manager.excluded_folders)
        excluded_patterns = set(self.exclusion_manager.excluded_file_patterns)
        excluded_files_abs = set(self.excluded_files)

        exporter = TreeExporter(
            self.selected_folder,
            excluded_folder_names=folder_names,
            excluded_folders=excluded_folders,
            excluded_file_patterns=excluded_patterns,
            excluded_files=excluded_files_abs,
        )

        self.status_var.set("Building file tree...")
        self.progress_bar.set(0)
        self.disable_buttons()

        def runner():
            try:
                total = exporter.count_nodes()

                def progress(done, tot):
                    pct = (done / max(1, tot)) * 100
                    self.queue.put(("progress", pct))
                    self.queue.put(("status", f"Generating tree {done}/{tot}"))

                ok = exporter.export(out_path, style="unicode", progress=progress)
                if ok:
                    self.queue.put(("progress", 100))
                    self.queue.put(("status", "File tree exported"))
                    self.queue.put(("message", f"File tree saved to:\n{out_path}"))
                    logger.info(f"File tree saved to {out_path}")
                else:
                    self.queue.put(("error", "Failed to export file tree."))
            except Exception as e:
                self.queue.put(("error", f"Failed to export file tree: {e}"))
                logger.exception("Tree export failed")
            finally:
                self.queue.put(("process_complete", None))

        Thread(target=runner, daemon=True).start()

    # ---------------- Refresh & Settings ----------------

    def update_file_list(self):
        if not self.scanner:
            logger.error("FileScanner is not initialized.")
            return

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

        self.file_tree.delete(*self.file_tree.get_children())
        self.start_scanning()

    def disable_buttons(self):
        def walk(widget):
            if isinstance(widget, ctk.CTkButton):
                widget.configure(state="disabled")
            for child in widget.winfo_children():
                walk(child)
        if hasattr(self, "main_frame"):
            walk(self.main_frame)
        logger.debug("Buttons disabled.")

    def enable_buttons(self):
        def walk(widget):
            if isinstance(widget, ctk.CTkButton):
                widget.configure(state="normal")
            for child in widget.winfo_children():
                walk(child)
        if hasattr(self, "main_frame"):
            walk(self.main_frame)
        logger.debug("Buttons enabled.")

    def save_settings(self):
        if not self.settings_manager:
            logger.error("SettingsManager is not initialized.")
            return

        settings = {
            "selected_folder": self.selected_folder,
            "excluded_folders": list(self.exclusion_manager.excluded_folders),
            "excluded_folder_names": list(getattr(self.exclusion_manager, "excluded_folder_names", set())),
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
        if not self.settings_manager:
            logger.error("SettingsManager is not initialized.")
            return

        settings = self.settings_manager.load_settings()
        if settings:
            self.selected_folder = settings.get("selected_folder", self.selected_folder)
            self.exclusion_manager.excluded_folders = set(settings.get("excluded_folders", []))
            self.exclusion_manager.excluded_folder_names = set(settings.get("excluded_folder_names", {"venv"}))
            self.exclusion_manager.excluded_file_patterns = set(settings.get("excluded_file_patterns", []))
            self.excluded_files = set(
                os.path.abspath(os.path.join(self.selected_folder, path))
                for path in settings.get("excluded_files", [])
            )

            self.exclusion_manager.update_ui()
            self.update_file_list()

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

    # ---------------- Search ----------------

    def perform_search(self, _event):
        query = (self.search_var.get() or "").lower()
        if not query:
            for item in self.file_tree.get_children():
                self.file_tree.item(item, tags=())
        else:
            for item in self.file_tree.get_children():
                vals = self.file_tree.item(item).get('values') or []
                if len(vals) < 2:
                    continue
                filename, rel_path = vals[0], vals[1]
                if query in str(filename).lower() or query in str(rel_path).lower():
                    self.file_tree.item(item, tags=('match',))
                else:
                    self.file_tree.item(item, tags=())
        try:
            self.file_tree.tag_configure('match', background='lightblue')
        except Exception:
            pass
