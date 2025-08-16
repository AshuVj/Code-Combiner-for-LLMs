# src/ui/main_window.py

import customtkinter as ctk
from tkinter import ttk
import tkinter as tk
from queue import Queue, Empty
from threading import Thread, Event
import time
import os
import sys
import re
import subprocess

from src.config import (
    WINDOW_TITLE, WINDOW_SIZE, EXCLUDED_FOLDER_NAMES_DEFAULT,
)
from src.ui.exclusion_manager import ExclusionManager
from src.ui.file_preview import FilePreview
from src.core.file_scanner import FileScanner
from src.core.file_processor import FileProcessor
from src.core.settings_manager import SettingsManager
from src.core.tree_exporter import TreeExporter
from src.utils.logger import logger
from src.utils.prefs import load_prefs, save_prefs
from tkinter import filedialog, messagebox


def resource_path(rel_path: str) -> str:
    try:
        base_path = sys._MEIPASS  # type: ignore[attr-defined]
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, rel_path)


class MainWindow:
    def __init__(self, root: ctk.CTk):
        self.root = root
        self.root.title(WINDOW_TITLE)
        self.root.geometry(WINDOW_SIZE)
        self.root.state('zoomed') 
        self.root.minsize(900, 600)  # sensible minimum
        # Defer icon set to avoid initial paint hiccup
        self.root.after(0, self._safe_set_icon)

        # Services
        self.scanner: FileScanner | None = None
        self.processor: FileProcessor | None = None
        self.settings_manager: SettingsManager | None = None

        # State
        self.selected_folder = ""
        self.queue: Queue = Queue()
        self.excluded_files: set[str] = set()
        self.stop_scan = False
        self.cancel_process_event: Event | None = None

        # Current UI scaling (persisted)
        self._ui_scaling = 1.0

        # UI init — try restore last folder & scaling from prefs
        self._init_from_prefs_or_initial()

        # Queue pump
        self.root.after(100, self.process_queue)

        # Save window geometry on exit
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ---------------- Helpers: icon & redraw ----------------

    def _safe_set_icon(self):
        try:
            self.root.iconbitmap(resource_path("resources/app_icon.ico"))
        except Exception:
            pass

    def _force_redraw(self):
        """Force repaint without touching geometry (avoid un-maximizing)."""
        try:
            # Use update() so late WM changes are flushed, but don't set geometry here.
            self.root.update()
        except Exception:
            pass
        try:
            # Harmless topmost pulse to bring the window forward
            self.root.attributes("-topmost", True)
            self.root.after(60, lambda: self.root.attributes("-topmost", False))
        except Exception:
            pass

    # ---------------- Window state helpers ----------------

    def _set_maximized(self, flag: bool = True):
        """Best-effort cross-platform maximize."""
        try:
            self.root.state("zoomed" if flag else "normal")
            return
        except Exception:
            pass
        try:
            self.root.attributes("-zoomed", bool(flag))  # some Linux Tks
            return
        except Exception:
            pass
        if flag:
            # Fallback: fill screen
            try:
                sw = self.root.winfo_screenwidth()
                sh = self.root.winfo_screenheight()
                self.root.geometry(f"{sw}x{sh}+0+0")
            except Exception:
                pass

    def _get_window_state(self) -> str:
        try:
            st = self.root.state()
            if st in ("normal", "zoomed", "iconic"):
                return st
        except Exception:
            pass
        # Try attribute-based zoomed flag
        try:
            if bool(self.root.attributes("-zoomed")):
                return "zoomed"
        except Exception:
            pass
        return "normal"

    # ---------------- Prefs / bootstrap ----------------

    @staticmethod
    def _clamp_scale(v: float) -> float:
        return max(0.8, min(1.4, float(v)))

    @staticmethod
    def _scale_label_from_float(v: float) -> str:
        pct = int(round(v * 100))
        pct = max(80, min(140, int(round(pct / 10.0) * 10)))  # snap to nearest 10%
        return f"{pct}%"

    @staticmethod
    def _scale_float_from_label(label: str) -> float:
        try:
            pct = int(label.strip().rstrip("%"))
            return MainWindow._clamp_scale(pct / 100.0)
        except Exception:
            return 1.0

    def _win_force_maximize(self):
        """Maximize reliably on Windows; fallback to Tk zoomed elsewhere."""
        if sys.platform.startswith("win"):
            try:
                import ctypes
                hwnd = self.root.winfo_id()
                # 9 = SW_RESTORE, 3 = SW_MAXIMIZE
                ctypes.windll.user32.ShowWindow(hwnd, 9)
                self.root.update_idletasks()
                ctypes.windll.user32.ShowWindow(hwnd, 3)
                # bring to foreground (harmless if it fails)
                try:
                    ctypes.windll.user32.SetForegroundWindow(hwnd)
                except Exception:
                    pass
                return
            except Exception:
                pass
        # Fallback (non-Windows)
        try:
            self.root.state("zoomed")
        except Exception:
            pass

    def _ensure_zoomed(self, retries: int = 6, fallback_fullscreen: bool = True):
        """Retry maximize; if stubborn, briefly go fullscreen then back."""
        def step(i=retries):
            try:
                self.root.update_idletasks()
                # Prefer the generic maximize wrapper
                self._set_maximized(True)
                # Bail if zoomed
                if self._get_window_state() == "zoomed":
                    return
            except Exception:
                pass

            if i > 0:
                self.root.after(150, step, i - 1)
            elif fallback_fullscreen:
                # Stubborn WM: force fullscreen, then exit and re-maximize
                try:
                    self.root.attributes("-fullscreen", True)
                    self.root.after(250, lambda: (
                        self.root.attributes("-fullscreen", False),
                        self._set_maximized(True)
                    ))
                except Exception:
                    pass

        step()

    def _apply_scaling(self, f: float):
        f = self._clamp_scale(f)
        self._ui_scaling = f
        try:
            # Only widget scaling to avoid feedback/jitter with some WMs
            ctk.set_widget_scaling(f)
        except Exception:
            pass
        prefs = load_prefs()
        prefs["ui_scaling"] = f
        save_prefs(prefs)

    def _init_from_prefs_or_initial(self):
        prefs = load_prefs()
        scaling = self._clamp_scale(prefs.get("ui_scaling", 1.0) or 1.0)
        self._apply_scaling(scaling)

        last_folder = prefs.get("last_folder")
        if last_folder and os.path.isdir(last_folder):
            self.selected_folder = os.path.abspath(last_folder)
            self.scanner = FileScanner(self.selected_folder)
            self.processor = FileProcessor(self.selected_folder)
            self.settings_manager = SettingsManager(self.selected_folder)
            self.create_main_ui()
            self.load_settings()
        else:
            self.create_initial_screen()

        # Restore geometry/state if available; otherwise maximize on first run
        geom = prefs.get("window_geometry")
        state = prefs.get("window_state")

        if geom and state != "zoomed":
            try:
                self.root.geometry(geom)
            except Exception:
                pass

        # Kick off maximize attempts; UI methods also call this after layout
        self.root.after_idle(self._ensure_zoomed)
        self.root.after(300, self._ensure_zoomed)

        self._force_redraw()

    # ---------------- Initial Screen ----------------

    def create_initial_screen(self):
        self.initial_frame = ctk.CTkFrame(self.root)
        self.initial_frame.pack(fill="both", expand=True, padx=20, pady=20)

        label = ctk.CTkLabel(self.initial_frame, text="Select a folder to start:", font=("Segoe UI", 16))
        label.pack(pady=50)

        ctk.CTkButton(
            self.initial_frame, text="Browse Folder", command=self.select_folder,
            font=("Segoe UI", 14), width=200, height=40
        ).pack(pady=20)

        # Ensure initial window draws correctly and attempt maximize after layout
        self._force_redraw()
        self.root.after_idle(self._ensure_zoomed)
        self.root.after(400, self._ensure_zoomed)

    # ---------------- Folder selection ----------------

    def select_folder(self):
        folder = filedialog.askdirectory(title="Select Folder")
        if not folder:
            return

        self.selected_folder = os.path.abspath(folder)
        logger.info(f"Selected folder: {self.selected_folder}")

        prefs = load_prefs()
        prefs["last_folder"] = self.selected_folder
        save_prefs(prefs)

        self.scanner = FileScanner(self.selected_folder)
        self.processor = FileProcessor(self.selected_folder)
        self.settings_manager = SettingsManager(self.selected_folder)

        if hasattr(self, 'initial_frame') and self.initial_frame.winfo_exists():
            self.initial_frame.destroy()
            self.create_main_ui()
        else:
            self.reset_main_ui()

        self.load_settings()
        self._force_redraw()

    def reset_main_ui(self):
        if hasattr(self, 'main_frame') and self.main_frame.winfo_exists():
            self.main_frame.destroy()
        self.excluded_files = set()
        self.stop_scan = False
        self.cancel_process_event = None
        self.create_main_ui()
        self._force_redraw()

    # ---------------- Main UI ----------------

    def create_main_ui(self):
        self.main_frame = ctk.CTkFrame(self.root)
        self.main_frame.pack(fill="both", expand=True, padx=0, pady=0)

        # Exclusions + Preview
        self.exclusion_manager = ExclusionManager(self)
        self.file_preview = FilePreview(self)

        # Top bar: Theme & Scaling
        top_bar = ctk.CTkFrame(self.main_frame)
        top_bar.pack(fill="x", padx=0, pady=(0, 6))

        ctk.CTkLabel(top_bar, text="Appearance:", font=("Segoe UI", 12)).pack(side=tk.LEFT, padx=(10, 6))
        self.theme_option = ctk.CTkOptionMenu(top_bar, values=["System", "Light", "Dark"], command=self.change_theme, width=100)
        self.theme_option.set(ctk.get_appearance_mode())
        self.theme_option.pack(side=tk.LEFT)

        ctk.CTkLabel(top_bar, text="UI scaling:", font=("Segoe UI", 12)).pack(side=tk.LEFT, padx=(12, 6))
        self.scale_option = ctk.CTkOptionMenu(
            top_bar,
            values=["80%", "90%", "100%", "110%", "120%", "130%", "140%"],
            command=self._on_scale_select,
            width=90
        )
        self.scale_option.set(self._scale_label_from_float(self._ui_scaling))
        self.scale_option.pack(side=tk.LEFT, padx=(0, 10))

        # Paned: files + preview
        files_paned = ttk.PanedWindow(self.main_frame, orient=tk.HORIZONTAL)
        files_paned.pack(fill=tk.BOTH, expand=True, padx=0, pady=0)

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
        self.file_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=0, pady=0)

        tree_scroll = ttk.Scrollbar(file_list_frame, orient="vertical", command=self.file_tree.yview)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.file_tree.configure(yscrollcommand=tree_scroll.set)
        self.file_tree.bind("<<TreeviewSelect>>", self.preview_file)

        # Context menu
        self._init_context_menu()
        self.file_tree.bind("<Button-3>", self._open_context_menu)  # right-click
        self.file_tree.bind("<Control-a>", lambda e: (self.select_all_files(), "break"))

        # Right: preview
        self.file_preview.setup_ui(files_paned)

        # Action buttons + options
        action_frame = ctk.CTkFrame(self.main_frame)
        action_frame.pack(fill="x", padx=0, pady=6)

        ctk.CTkButton(action_frame, text="Exclude Selected", command=self.exclude_selected_files,
                      font=("Segoe UI", 12), width=150, height=40).pack(side=tk.LEFT, padx=5)

        ctk.CTkButton(action_frame, text="Select All", command=self.select_all_files,
                      font=("Segoe UI", 12), width=120, height=40).pack(side=tk.LEFT, padx=5)

        ctk.CTkButton(action_frame, text="Deselect All", command=self.deselect_all_files,
                      font=("Segoe UI", 12), width=130, height=40).pack(side=tk.LEFT, padx=5)

        # Generate buttons
        ctk.CTkButton(action_frame, text="Generate Selected Output", command=self.generate_selected_output,
                      font=("Segoe UI", 12), width=220, height=40).pack(side=tk.RIGHT, padx=5)

        ctk.CTkButton(action_frame, text="Generate Combined Output", command=self.generate_combined_output,
                      font=("Segoe UI", 12), width=220, height=40).pack(side=tk.RIGHT, padx=5)

        # Refresh / Change folder
        ctk.CTkButton(action_frame, text="Refresh Files", command=self.update_file_list,
                      font=("Segoe UI", 12), width=150, height=40).pack(side=tk.RIGHT, padx=5)
        ctk.CTkButton(action_frame, text="Change Folder", command=self.select_folder,
                      font=("Segoe UI", 12), width=150, height=40).pack(side=tk.RIGHT, padx=5)

        # Cancel buttons
        ctk.CTkButton(action_frame, text="Cancel Scan", command=self.cancel_scan,
                      font=("Segoe UI", 12), width=130, height=40).pack(side=tk.LEFT, padx=5)
        ctk.CTkButton(action_frame, text="Cancel Process", command=self.cancel_process,
                      font=("Segoe UI", 12), width=140, height=40).pack(side=tk.LEFT, padx=5)

        # Export File Tree + options
        ctk.CTkButton(action_frame, text="Export File Tree", command=self.export_file_tree,
                      font=("Segoe UI", 12), width=160, height=40).pack(side=tk.LEFT, padx=5)

        options = ctk.CTkFrame(self.main_frame)
        options.pack(fill="x", padx=0, pady=(0, 6))
        self.opt_markdown = tk.BooleanVar(value=False)
        self.opt_ascii = tk.BooleanVar(value=False)
        self.opt_sizes = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(options, text="Markdown tree", variable=self.opt_markdown).pack(side=tk.LEFT, padx=(4, 10))
        ctk.CTkCheckBox(options, text="ASCII tree", variable=self.opt_ascii).pack(side=tk.LEFT, padx=(4, 10))
        ctk.CTkCheckBox(options, text="Include sizes", variable=self.opt_sizes).pack(side=tk.LEFT, padx=(4, 10))

        # Progress & Status
        self.progress_bar = ctk.CTkProgressBar(self.main_frame)
        self.progress_bar.pack(fill="x", padx=0, pady=6)
        self.progress_bar.set(0)

        self.status_var = tk.StringVar(value="Ready")
        ctk.CTkLabel(
            self.main_frame, textvariable=self.status_var, anchor=tk.W, font=("Segoe UI", 12)
        ).pack(fill="x", padx=0, pady=(0, 6))

        # Shortcuts
        self._bind_shortcuts()

        # Scan
        self.start_scanning()

        # Force a clean paint after constructing the full layout
        self._force_redraw()
        # Try maximize post-layout as well
        self.root.after_idle(self._ensure_zoomed)
        self.root.after(400, self._ensure_zoomed)

    # ---------------- Context menu ----------------

    def _init_context_menu(self):
        self.ctx = tk.Menu(self.root, tearoff=0)
        self.ctx.add_command(label="Open", command=self._ctx_open)
        self.ctx.add_command(label="Reveal in Explorer/Finder", command=self._ctx_reveal)
        self.ctx.add_separator()
        self.ctx.add_command(label="Copy full path", command=self._ctx_copy_full)
        self.ctx.add_command(label="Copy relative path", command=self._ctx_copy_rel)
        self.ctx.add_separator()
        self.ctx.add_command(label="Exclude", command=self.exclude_selected_files)

    def _open_context_menu(self, event):
        try:
            self.ctx.tk_popup(event.x_root, event.y_root)
        finally:
            self.ctx.grab_release()

    def _get_first_selected_path(self):
        sel = self.file_tree.selection()
        if not sel:
            return None, None
        vals = self.file_tree.item(sel[0]).get('values') or []
        if len(vals) < 2:
            return None, None
        filename, rel_path = vals[0], vals[1]
        full = os.path.join(self.selected_folder, rel_path)
        return full, rel_path

    def _ctx_open(self):
        full, _ = self._get_first_selected_path()
        if not full:
            return
        try:
            if sys.platform.startswith("win"):
                os.startfile(full)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.run(["open", full])
            else:
                subprocess.run(["xdg-open", full])
        except Exception as e:
            messagebox.showerror("Open failed", str(e))

    def _ctx_reveal(self):
        full, _ = self._get_first_selected_path()
        if not full:
            return
        try:
            if sys.platform.startswith("win"):
                subprocess.run(["explorer", "/select,", full])
            elif sys.platform == "darwin":
                subprocess.run(["open", "-R", full])
            else:
                subprocess.run(["xdg-open", os.path.dirname(full)])
        except Exception as e:
            messagebox.showerror("Reveal failed", str(e))

    def _ctx_copy_full(self):
        full, _ = self._get_first_selected_path()
        if not full:
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(full)

    def _ctx_copy_rel(self):
        _, rel = self._get_first_selected_path()
        if not rel:
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(rel)

    # ---------------- Scaling & theme ----------------

    def _on_scale_select(self, label: str):
        f = self._scale_float_from_label(label)
        self._apply_scaling(f)
        # Redraw after scale change to avoid any delayed paints
        self._force_redraw()

    def change_theme(self, selected_mode):
        ctk.set_appearance_mode(selected_mode)
        logger.info(f"Appearance mode changed to {selected_mode}")

    # ---------------- Shortcuts ----------------

    def _bind_shortcuts(self):
        self.root.bind("<Control-f>", lambda e: self._focus_search())
        self.root.bind("<F5>", lambda e: self.update_file_list())
        self.root.bind("<Delete>", lambda e: self.exclude_selected_files())
        self.root.bind("<Control-g>", lambda e: self.generate_combined_output())
        self.root.bind("<Control-p>", lambda e: self.export_file_tree())
        self.root.bind("<Control-a>", lambda e: (self.select_all_files(), "break"))
        self.root.bind("<Control-d>", lambda e: self.deselect_all_files())
        # Quick maximize toggle (useful if WM ignores saved state)
        self.root.bind("<F11>", lambda e: self._set_maximized(True))
        # Hard fallback: brief fullscreen pulse then maximize
        self.root.bind("<Shift-F11>", lambda e: (
            self.root.attributes("-fullscreen", True),
            self.root.after(250, lambda: (self.root.attributes("-fullscreen", False), self._set_maximized(True)))
        ))

    def _focus_search(self):
        pass

    # ---------------- Dynamic names ----------------

    def _default_output_filename(self) -> str:
        base = os.path.basename(self.selected_folder.rstrip("\\/")) or "combined_output"
        name = re.sub(r"\s+", "_", base)
        name = re.sub(r"[^\w.\-]+", "_", name)
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

    # ---------------- Scanning ----------------

    def cancel_scan(self):
        self.stop_scan = True
        self.status_var.set("Cancelling scan...")

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
        try:
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

            gen = self.scanner.yield_files()
            chunk, processed = [], 0
            chunk_size = 100

            for file_tuple in gen:
                if self.stop_scan:
                    self.queue.put(("status", "Scan cancelled by user."))
                    break
                chunk.append(file_tuple)
                processed += 1
                if len(chunk) >= chunk_size:
                    self.queue.put(("add_files_bulk", chunk.copy()))
                    chunk.clear()
                    progress = (processed / max(1, total_estimate)) * 100
                    self.queue.put(("progress", progress))
                    self.queue.put(("status", f"Scanning... {processed}/{total_estimate}"))
                    time.sleep(0.01)

            if not self.stop_scan and chunk:
                self.queue.put(("add_files_bulk", chunk.copy()))
                chunk.clear()

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

    # ---------------- Combine / Cancel Process ----------------

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
        # Auto-exclude our own output so it doesn't reappear on next scan
        self.excluded_files.add(os.path.abspath(output_path))
        self.save_settings()

        self.status_var.set("Generating combined output...")
        self.progress_bar.set(0)
        self.disable_buttons()
        self.cancel_process_event = Event()

        def runner():
            try:
                def progress_callback(proc, total):
                    progress = (proc / total) * 100 if total > 0 else 100
                    self.queue.put(("progress", progress))
                    self.queue.put(("status", f"Processing file {proc}/{total}"))

                # Call without cancel_event for compatibility with current processor
                ok = self.processor.process_files(  # type: ignore
                    files_to_process, output_path, progress_callback, self.cancel_process_event
                )
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
                self.cancel_process_event = None

        Thread(target=runner, daemon=True).start()

    def cancel_process(self):
        if self.cancel_process_event and not self.cancel_process_event.is_set():
            self.cancel_process_event.set()
            self.status_var.set("Cancelling process...")

    # ---------------- Export File Tree ----------------

    def export_file_tree(self):
        if not self.selected_folder:
            messagebox.showwarning("No Folder", "Please select a folder first.")
            return

        # Dynamic default name: "<root>_tree.txt"
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

        # Exclude our tree file from future scans
        self.excluded_files.add(os.path.abspath(out_path))
        self.save_settings()

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

        style = "ascii" if self.opt_ascii.get() else "unicode"
        md = bool(self.opt_markdown.get())
        sizes = bool(self.opt_sizes.get())

        def runner():
            try:
                total = exporter.count_nodes()

                def progress(done, tot):
                    pct = (done / max(1, tot)) * 100
                    self.queue.put(("progress", pct))
                    self.queue.put(("status", f"Generating tree {done}/{tot}"))

                ok = exporter.export(out_path, style=style, progress=progress, include_sizes=sizes, markdown=md)
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
        ok = self.settings_manager.save_settings(settings)
        if ok:
            logger.info("Settings saved successfully.")
        else:
            messagebox.showerror("Error", "Failed to save settings.")

        # Save window geometry & last folder to global prefs
        prefs = load_prefs()
        prefs["window_geometry"] = self.root.winfo_geometry()
        prefs["last_folder"] = self.selected_folder
        prefs["ui_scaling"] = float(self._ui_scaling)
        prefs["window_state"] = self._get_window_state()
        save_prefs(prefs)

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

            # Ensure repaint after a potentially long layout/scan start
            self.root.after(0, self._force_redraw)

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

    # ---------------- Close ----------------

    def _on_close(self):
        try:
            self.save_settings()
        finally:
            self.root.destroy()
