"""
Contains the code for a feature-rich graphical user interface (GUI).

This GUI supports batch processing of files and directories, asynchronous
metadata parsing, and conversion, ensuring the UI remains responsive.
"""
import dataclasses
import importlib.resources as res
import logging
import traceback
import threading
import queue
import re
from pathlib import Path

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
except ImportError:
    TkinterDnD = None # Flag that it's not available

from .utils.config import ConversionConfig
from .core.batch_processor import BatchProcessor
from .core.fb2_book import FB2Book
from .utils.logger import setup_main_logger

log = logging.getLogger("fb2_converter")


class SettingsDialog(tk.Toplevel):
    """A dialog for configuring conversion settings."""
    def __init__(self, parent, config: ConversionConfig):
        super().__init__(parent)
        self.transient(parent)
        self.title("Conversion Settings")
        self.config: ConversionConfig = config
        self.result: ConversionConfig | None = None

        self.toc_depth_var = tk.IntVar(value=self.config.toc_depth)
        self.split_level_var = tk.IntVar(value=self.config.split_level)
        self.split_size_var = tk.IntVar(value=self.config.split_size_kb)
        self.stylesheet_var = tk.StringVar(value=str(self.config.custom_stylesheet or ""))
        self.threads_var = tk.IntVar(value=self.config.num_threads)
        self.typography_var = tk.BooleanVar(value=self.config.improve_typography)

        body = ttk.Frame(self, padding="10")
        body.pack(padx=5, pady=5, fill=tk.BOTH, expand=True)

        # Create fields
        self._create_widgets(body)

        self.grab_set()  # Modal
        self.protocol("WM_DELETE_WINDOW", self.on_cancel)
        
        self.resizable(False, False)
        self.wait_window(self)

    def _create_widgets(self, parent):
        frame = ttk.Frame(parent)
        frame.pack(fill=tk.X, expand=True)

        # TOC Depth
        ttk.Label(frame, text="TOC Depth (1-6):").grid(row=0, column=0, sticky=tk.W, pady=2)
        ttk.Spinbox(frame, from_=1, to=6, textvariable=self.toc_depth_var, width=5).grid(row=0, column=1, sticky=tk.W, pady=2)

        # Split Level
        ttk.Label(frame, text="Split Level (1-6):").grid(row=1, column=0, sticky=tk.W, pady=2)
        ttk.Spinbox(frame, from_=1, to=6, textvariable=self.split_level_var, width=5).grid(row=1, column=1, sticky=tk.W, pady=2)

        # Split Size
        ttk.Label(frame, text="Split Size (KB, 0=off):").grid(row=2, column=0, sticky=tk.W, pady=2)
        ttk.Entry(frame, textvariable=self.split_size_var, width=7).grid(row=2, column=1, sticky=tk.W, pady=2)
        
        # Threads
        ttk.Label(frame, text="Threads (0=auto):").grid(row=3, column=0, sticky=tk.W, pady=2)
        ttk.Entry(frame, textvariable=self.threads_var, width=7).grid(row=3, column=1, sticky=tk.W, pady=2)

        # Typography
        ttk.Checkbutton(frame, text="Improve Typography", variable=self.typography_var).grid(row=4, column=0, columnspan=2, sticky=tk.W, pady=5)

        # Stylesheet
        ttk.Label(frame, text="Custom CSS File:").grid(row=5, column=0, sticky=tk.W, pady=2)
        stylesheet_frame = ttk.Frame(frame)
        stylesheet_frame.grid(row=6, column=0, columnspan=2, sticky=tk.EW, pady=2)
        ttk.Entry(stylesheet_frame, textvariable=self.stylesheet_var, width=40).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(stylesheet_frame, text="...", command=self.on_browse_css, width=3).pack(side=tk.LEFT, padx=(5, 0))

        # OK/Cancel Buttons
        button_frame = ttk.Frame(parent)
        button_frame.pack(fill=tk.X, pady=(10, 0))
        ttk.Button(button_frame, text="OK", command=self.on_ok).pack(side=tk.RIGHT, padx=5)
        ttk.Button(button_frame, text="Cancel", command=self.on_cancel).pack(side=tk.RIGHT)

    def on_browse_css(self):
        file = filedialog.askopenfilename(
            title="Select Stylesheet",
            filetypes=[("CSS Files", "*.css"), ("All Files", "*.*")]
        )
        if file:
            self.stylesheet_var.set(file)

    def on_ok(self):
        try:
            css_path = self.stylesheet_var.get()
            
            self.result = dataclasses.replace(self.config,
                toc_depth=self.toc_depth_var.get(),
                split_level=self.split_level_var.get(),
                split_size_kb=self.split_size_var.get(),
                custom_stylesheet=Path(css_path) if css_path else None,
                num_threads=self.threads_var.get(),
                improve_typography=self.typography_var.get()
            )
            self.on_cancel()
        except ValueError:
            messagebox.showerror("Invalid Input", "Please enter valid numbers for fields.")

    def on_cancel(self):
        self.grab_release()
        self.destroy()


def load_icon(name: str) -> tk.PhotoImage:
    """Loads an icon image from the package resources."""
    with res.open_binary('fictionpub.resources.icons', name) as img_file:
        return tk.PhotoImage(data=img_file.read())


class ConverterApp:
    """The main application class for the GUI."""
    def __init__(self, root):
        self.root = root
        self.root.title("FB2 to EPUB Converter")
        self.root.geometry("700x500")

        # Set up the main logger for the GUI
        setup_main_logger(logging.INFO)

        self.conversion_config = ConversionConfig()
        self.queue = queue.Queue()
        self.conversion_thread: threading.Thread | None = None
        self.file_map = {}  # Maps file path str to tree item_id

        self.pending_img = load_icon("mark_pending.png")
        self.success_img = load_icon("mark_success.png")
        self.failure_img = load_icon("mark_error.png")

        self._create_widgets()
        self._setup_layout()
        self._update_button_states()
        self._process_queue()

    def _create_widgets(self):
        """Creates all the widgets for the application."""
        self.main_frame = ttk.Frame(self.root, padding="5")

        # --- Settings Frame ---
        self.settings_frame = ttk.Frame(self.main_frame)
        self.add_files_btn = ttk.Button(self.settings_frame, text="Add Files", command=self.on_add_files_click)
        self.add_folder_btn = ttk.Button(self.settings_frame, text="Add Folder", command=self.on_add_folder_click)
        self.clear_btn = ttk.Button(self.settings_frame, text="Clear List", command=self.on_clear_list_click)
        self.settings_btn = ttk.Button(self.settings_frame, text="Settings", command=self.on_settings_click)
        
        # --- File List Frame ---
        self.tree_frame = ttk.Frame(self.main_frame)
        self._create_treeview(self.tree_frame)

        # --- Convert Frame ---
        self.convert_frame = ttk.Frame(self.main_frame)
        self.convert_btn = ttk.Button(self.convert_frame, text="Convert", command=self.on_convert_click)
        
        # --- Status Frame ---
        self.status_frame = ttk.Frame(self.main_frame, relief=tk.SUNKEN, padding="2")
        self.status_label = ttk.Label(self.status_frame, text="Ready", anchor=tk.W)

    def _create_treeview(self, parent):
        """Creates the Treeview for file listing."""
        self.tree = ttk.Treeview(
            parent,
            columns=("state", "title", "author", "path"),
            show="headings"
        )
        self.tree_scroll_y = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=self.tree_scroll_y.set)

        self.tree.heading("state", text="", anchor=tk.W)
        self.tree.heading("title", text="Title")
        self.tree.heading("author", text="Author")
        self.tree.heading("path", text="File Path")

        self.tree.column("state", width=30, stretch=tk.NO, anchor=tk.CENTER)
        self.tree.column("title", width=250)
        self.tree.column("author", width=150)
        self.tree.column("path", width=200)

        # Register drag-and-drop
        if TkinterDnD:
            self.tree.drop_target_register(DND_FILES)
            self.tree.dnd_bind('<<Drop>>', self.on_drop)
        else:
            log.warning("tkinterdnd2 not found. Drag-and-drop will be disabled.")

    def _setup_layout(self):
        """Packs all widgets into the root window."""
        self.main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Settings
        self.settings_frame.pack(fill=tk.X, pady=5)
        self.add_files_btn.pack(side=tk.LEFT, padx=2)
        self.add_folder_btn.pack(side=tk.LEFT, padx=2)
        self.clear_btn.pack(side=tk.LEFT, padx=2)
        self.settings_btn.pack(side=tk.RIGHT, padx=2)

        # Treeview
        self.tree_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        self.tree_scroll_y.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Convert
        self.convert_frame.pack(fill=tk.X, pady=5)
        self.convert_btn.pack(side=tk.RIGHT)

        # Status
        self.status_frame.pack(fill=tk.X, side=tk.BOTTOM)
        self.status_label.pack(fill=tk.X)

    def on_add_files_click(self):
        """Opens a file dialog to select .fb2/.fb2.zip files."""
        files = filedialog.askopenfilenames(
            title="Select FB2 Files",
            filetypes=[
                ("FB2 Files", "*.fb2 *.fb2.zip"),
                ("All Files", "*.*")
            ]
        )
        if files:
            self.add_files_to_list(files)

    def add_files_to_list(self, file_paths):
        """
        Adds a list of file paths to the treeview and starts parsing them.
        """
        self.status_label.config(text="Parsing metadata...")
        for file_path in file_paths:
            path = Path(file_path)
            if str(path) in self.file_map:
                continue  # Skip duplicates
            
            item_id = self.tree.insert(
                "", tk.END, text="", 
                image=self.pending_img, # Use pending image
                values=("", "Parsing...", "", str(path))
            )
            self.file_map[str(path)] = item_id
            
            # Start a background thread to parse this file's metadata
            parse_thread = threading.Thread(
                target=self._parse_metadata_thread, 
                args=(item_id, path),
                daemon=True
            )
            parse_thread.start()

    def on_add_folder_click(self):
        """Opens a dialog to select a folder to scan."""
        folder = filedialog.askdirectory()
        if folder:
            self.add_folder_to_list(Path(folder))

    def add_folder_to_list(self, folder_path: Path):
        """Scans a folder and adds all found files to the list."""
        self.status_label.config(text=f"Scanning {folder_path}...")
        self.root.update_idletasks()  # Force status update
        
        files_to_add = []
        for ext in ("**/*.fb2", "**/*.fb2.zip"):
            files_to_add.extend(folder_path.rglob(ext))
        
        self.add_files_to_list(files_to_add)
        self.status_label.config(text=f"Added {len(files_to_add)} files from {folder_path}.")

    def on_drop(self, event):
        """Handles files dropped onto the treeview."""
        raw_paths = event.data.strip()
        if not raw_paths:
            return
        
        paths_str = []
        try:
            # Find all content within braces or non-spaced content
            # Handles "{C:/path/file one.fb2} {C:/path/file two.fb2}"
            paths_str = re.findall(r'\{([^}]+)\}|([^{\s}]+)', raw_paths)
            # re.findall returns tuples if groups are used: [('path1', ''), ('', 'path2')]
            paths_str = [p[0] or p[1] for p in paths_str]
        except Exception as e:
            log.error(f"Error parsing dropped paths: {e}")
            paths_str = [raw_paths] # Fallback

        if not paths_str:
            return

        log.info(f"Parsing dropped paths: {paths_str}")
        
        paths_to_add = [Path(p) for p in paths_str]
        
        files_to_process = []
        folders_to_scan = []
        
        for path in paths_to_add:
            if not path.exists():
                log.warning(f"Dropped path does not exist: {path}")
                continue
            if path.is_dir():
                folders_to_scan.append(path)
            elif path.is_file() and path.suffix in ['.fb2', '.zip']:
                filename = str(path)
                if filename.endswith('.fb2') or filename.endswith('.fb2.zip'):
                    files_to_process.append(path)
        
        # Add individual files
        if files_to_process:
            self.add_files_to_list(files_to_process)
        
        # Add folders
        if folders_to_scan:
            for folder_path in folders_to_scan:
                self.add_folder_to_list(folder_path)

    def on_clear_list_click(self):
        """Clears all items from the file list."""
        if self.conversion_thread and self.conversion_thread.is_alive():
            messagebox.showwarning("Busy", "Cannot clear list while conversion is in progress.")
            return
        for item_id in self.tree.get_children():
            self.tree.delete(item_id)
        self.file_map.clear()
        self.status_label.config(text="Ready")

    def on_settings_click(self):
        """Opens the settings dialog."""
        dialog = SettingsDialog(self.root, self.conversion_config)
        if dialog.result:
            self.conversion_config = dialog.result
            self.status_label.config(text="Settings updated.")

    def on_convert_click(self):
        """Starts the batch conversion process."""
        if not self.file_map:
            messagebox.showinfo("No Files", "Please add files to the list first.")
            return

        output_dir = filedialog.askdirectory(title="Select Output Folder (Cancel to save alongside originals)")

        self.conversion_config = dataclasses.replace(self.conversion_config,
            output_path=Path(output_dir) if output_dir else None
        )
        
        self._start_conversion_thread()

    def _update_button_states(self, converting=False):
        """Enables or disables buttons based on application state."""
        state = tk.DISABLED if converting else tk.NORMAL
        self.add_files_btn.config(state=state)
        self.add_folder_btn.config(state=state)
        self.clear_btn.config(state=state)
        self.settings_btn.config(state=state)
        self.convert_btn.config(state=state)

    def _parse_metadata_thread(self, item_id: str, path: Path):
        """Worker thread to parse FB2 metadata."""
        try:
            metadata = FB2Book.get_quick_metadata(path)
            title = metadata.get("title", "Unknown Title")
            author = metadata.get("author", "Unknown Author")
            self.queue.put(("parse_ok", item_id, (title, author)))
        except Exception as e:
            log.warning(f"Failed to parse metadata for {path.name}: {e}")
            self.queue.put(("parse_fail", item_id, str(e)))

    def _start_conversion_thread(self):
        """Gathers files and starts the batch processor in a new thread."""
        files_to_convert = [Path(p) for p in self.file_map.keys()]
        if not files_to_convert:
            return

        self._update_button_states(converting=True)
        self.status_label.config(text=f"Starting conversion of {len(files_to_convert)} files...")

        # Reset all icons to pending
        for item_id in self.file_map.values():
            self.tree.item(item_id, image=self.pending_img, tags=())

        def conversion_task():
            try:
                processor = BatchProcessor(self.conversion_config)
                processor.run(files_to_convert, self._conversion_progress_callback)
                self.queue.put(("conversion_done", None, "Batch conversion finished."))
            except Exception as e:
                log.error("Fatal error in conversion thread", exc_info=True)
                self.queue.put(("fatal_error", None, str(e)))

        self.conversion_thread = threading.Thread(target=conversion_task, daemon=True)
        self.conversion_thread.start()

    def _conversion_progress_callback(self, path: Path, result: Path | None, exc: Exception | None):
        """
        Callback for the BatchProcessor.
        This runs in the conversion thread and puts results in the queue.
        """
        item_id = self.file_map.get(str(path))
        if not item_id:
            return 
        
        if exc:
            self.queue.put(("convert_fail", item_id, str(exc)))
        else:
            self.queue.put(("convert_ok", item_id, None))

    def _process_queue(self):
        """
        Processes messages from the worker threads in the main UI thread.
        This is the *only* place UI elements should be updated.
        """
        try:
            while True:
                task_type, item_id, data = self.queue.get_nowait()

                if item_id and not self.tree.exists(item_id):
                    # Item was cleared from list, ignore update
                    continue

                match task_type:
                    case "parse_ok":
                        title, author = data
                        self.tree.item(item_id, values=("", title, author, self.tree.item(item_id, "values")[-1]))
                    case "parse_fail":
                        self.tree.item(item_id, values=("", "Failed to parse", f"Error: {data}", self.tree.item(item_id, "values")[-1]))
                    case "status":
                        self.status_label.config(text=data)
                    case "convert_ok":
                        self.tree.item(item_id, tags=('success',), image=self.success_img)
                        self.tree.tag_configure('success', foreground='green')
                    case "convert_fail":
                        self.tree.item(item_id, tags=('failure',), image=self.failure_img)
                        self.tree.tag_configure('failure', foreground='red')
                        log.error(f"Failed to convert item {item_id}: {data}")
                    case "conversion_done":
                        self.status_label.config(text=data)
                        self._update_button_states(converting=False)
                        messagebox.showinfo("Complete", "Batch conversion process has finished.")
                    case "fatal_error":
                        self.status_label.config(text="A fatal error stopped the conversion.")
                        messagebox.showerror("Fatal Error", str(data))
                        self._update_button_states(converting=False)
                    case _:
                        log.error(f"Unknown task type: {task_type}")
        
        except queue.Empty:
            # No more tasks, schedule next check
            self.root.after(100, self._process_queue)


def run_gui():
    """Launches the GUI application."""
    if TkinterDnD:
        root = TkinterDnD.Tk()
    else:
        root = tk.Tk()
        
    app = ConverterApp(root)
    root.mainloop()