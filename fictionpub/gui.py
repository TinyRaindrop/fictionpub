"""
Contains the code for a feature-rich graphical user interface (GUI).
"""
import logging
import threading
import queue
import re
import dataclasses
import importlib.resources as res
import os
import platform
import subprocess
import concurrent.futures
from pathlib import Path

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
except ImportError:
    TkinterDnD = None

from .utils.config import ConversionConfig
from .core.batch_processor import BatchProcessor
from .core.fb2_book import FB2Book
from .utils.logger import setup_main_logger, LOG_DIR

log = logging.getLogger("fb2_converter")


def load_icon(name: str) -> tk.PhotoImage:
    """Loads an icon image from resources and scales it down if necessary."""
    package = "fictionpub.resources.icons"
    
    try:
        with res.open_binary(package, name) as img_file:
            data = img_file.read()
            img = tk.PhotoImage(data=data)
            if img.width() > 24:
                scale = img.width() // 18 
                if scale > 1:
                    img = img.subsample(scale)
            return img
    
    except Exception as e:
        log.error(f"Failed to load icon {name}: {e}")
        return tk.PhotoImage(width=16, height=16)


def open_path(path: Path):
    """Opens a file or directory in the system's default explorer."""
    try:
        if platform.system() == "Windows":
            os.startfile(path)
        elif platform.system() == "Darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
    except Exception as e:
        log.error(f"Failed to open path {path}: {e}")


class SettingsDialog(tk.Toplevel):
    """A dialog for configuring conversion settings."""
    def __init__(self, parent, config: ConversionConfig):
        super().__init__(parent)
        self.withdraw() # Start hidden
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
        self._create_widgets(body)
        
        # Center without flash
        self._center_window(parent)
        self.deiconify() # Show only after geometry is set

        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self.on_cancel)
        self.resizable(False, False)
        self.wait_window(self)

    def _center_window(self, parent):
        self.update_idletasks()
        width = self.winfo_reqwidth()
        height = self.winfo_reqheight()
        
        parent_x = parent.winfo_rootx()
        parent_y = parent.winfo_rooty()
        parent_width = parent.winfo_width()
        parent_height = parent.winfo_height()
        
        x = parent_x + (parent_width // 2) - (width // 2)
        y = parent_y + (parent_height // 2) - (height // 2)
        self.geometry(f"{width}x{height}+{x}+{y}")

    def _create_widgets(self, parent):
        frame = ttk.Frame(parent)
        frame.pack(fill=tk.X, expand=True)
        
        def add_row(row, label, widget):
            ttk.Label(frame, text=label).grid(row=row, column=0, sticky=tk.W, pady=2)
            widget.grid(row=row, column=1, sticky=tk.W, pady=2, padx=5)

        add_row(0, "TOC Depth (1-6):", ttk.Spinbox(frame, from_=1, to=6, textvariable=self.toc_depth_var, width=5))
        add_row(1, "Split Level (1-6):", ttk.Spinbox(frame, from_=1, to=6, textvariable=self.split_level_var, width=5))
        add_row(2, "Split Size (KB, 0=off):", ttk.Entry(frame, textvariable=self.split_size_var, width=7))
        add_row(3, "Threads (0=auto):", ttk.Entry(frame, textvariable=self.threads_var, width=7))
        ttk.Checkbutton(frame, text="Improve Typography", variable=self.typography_var).grid(row=4, column=0, columnspan=2, sticky=tk.W, pady=5)
        
        ttk.Label(frame, text="Custom CSS:").grid(row=5, column=0, sticky=tk.W, pady=2)
        css_frame = ttk.Frame(frame)
        css_frame.grid(row=6, column=0, columnspan=2, sticky=tk.EW, pady=2)
        ttk.Entry(css_frame, textvariable=self.stylesheet_var, width=40).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(css_frame, text="...", command=self.on_browse_css, width=3).pack(side=tk.LEFT, padx=5)

        btn_frame = ttk.Frame(parent)
        btn_frame.pack(fill=tk.X, pady=(10, 0))
        ttk.Button(btn_frame, text="Cancel", command=self.on_cancel).pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_frame, text="OK", command=self.on_ok).pack(side=tk.RIGHT)

    def on_browse_css(self):
        file = filedialog.askopenfilename(
            filetypes=[("CSS Files", "*.css"), ("All Files", "*.*")]
        )
        if file: self.stylesheet_var.set(file)

    def on_ok(self):
        try:
            css = self.stylesheet_var.get()
            self.result = dataclasses.replace(
                self.config,
                toc_depth=self.toc_depth_var.get(),
                split_level=self.split_level_var.get(),
                split_size_kb=self.split_size_var.get(),
                custom_stylesheet=Path(css) if css else None,
                num_threads=self.threads_var.get(),
                improve_typography=self.typography_var.get()
            )
            self.on_cancel()
        except ValueError:
            messagebox.showerror("Invalid Input", "Please enter valid numbers.")

    def on_cancel(self):
        self.grab_release()
        self.destroy()


class ConverterApp:
    def __init__(self, root):
        self.root = root
        self.root.title("FB2 to EPUB Converter")
        self.root.geometry("950x600")

        setup_main_logger(logging.INFO)

        self.conversion_config = ConversionConfig()
        self.queue = queue.Queue()
        self.conversion_thread: threading.Thread | None = None
        
        # Thread pool for metadata parsing (prevents creating thousands of threads)
        self.meta_executor = concurrent.futures.ThreadPoolExecutor(max_workers=10)
        
        self.file_map = {} 
        self.folder_nodes = {}

        self._load_resources()
        self._create_widgets()
        self._setup_layout()
        self._bind_events()
        self._process_queue()

    def _load_resources(self):
        self.icon_unselected = load_icon("mark_unselected.png")
        self.icon_selected = load_icon("mark_selected.png")
        self.icon_success = load_icon("mark_success.png")
        self.icon_failure = load_icon("mark_error.png")

    def _create_widgets(self):
        self.main_frame = ttk.Frame(self.root, padding="5")

        # Toolbar
        self.toolbar = ttk.Frame(self.main_frame)
        self.add_files_btn = ttk.Button(self.toolbar, text="Add Files", command=self.on_add_files_click)
        self.add_folder_btn = ttk.Button(self.toolbar, text="Add Folder", command=self.on_add_folder_click)
        self.remove_btn = ttk.Button(self.toolbar, text="Remove Selected", command=self.on_remove_click)
        self.remove_all_btn = ttk.Button(self.toolbar, text="Remove All", command=self.on_remove_all_click)
        
        self.right_toolbar = ttk.Frame(self.toolbar)
        self.logs_btn = ttk.Button(self.right_toolbar, text="Logs", command=self.on_logs_click)
        self.settings_btn = ttk.Button(self.right_toolbar, text="Settings", command=self.on_settings_click)

        # Treeview
        self.tree_frame = ttk.Frame(self.main_frame)
        self.tree = ttk.Treeview(
            self.tree_frame,
            columns=("author", "title", "date", "lang"),
            selectmode="extended" 
        )
        self.tree_scroll_y = ttk.Scrollbar(self.tree_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=self.tree_scroll_y.set)

        self.tree.tag_configure('dimmed', foreground='gray')

        # Configure columns
        self.tree.heading("#0", text="Status / Filename", anchor=tk.W, command=self.on_header_click)
        self.tree.column("#0", width=400, anchor=tk.W)
        self.tree.heading("author", text="Author", anchor=tk.W)
        self.tree.column("author", width=150)
        self.tree.heading("title", text="Title", anchor=tk.W)
        self.tree.column("title", width=200)
        
        # Narrow columns that don't stretch
        self.tree.heading("date", text="Date", anchor=tk.W)
        self.tree.column("date", width=60, minwidth=60, stretch=False)
        self.tree.heading("lang", text="Lang", anchor=tk.W)
        self.tree.column("lang", width=50, minwidth=50, stretch=False)

        if TkinterDnD:
            self.tree.drop_target_register(DND_FILES)
            self.tree.dnd_bind('<<Drop>>', self.on_drop)

        self.bottom_panel = ttk.Frame(self.main_frame)
        self.convert_btn = ttk.Button(self.bottom_panel, text="Convert Checked Items", command=self.on_convert_click)
        
        self.status_frame = ttk.Frame(self.main_frame, relief=tk.SUNKEN, padding="2")
        self.status_label = ttk.Label(self.status_frame, text="Ready", anchor=tk.W)

    def _setup_layout(self):
        self.main_frame.pack(fill=tk.BOTH, expand=True)

        self.toolbar.pack(fill=tk.X, pady=(0, 5))
        self.add_files_btn.pack(side=tk.LEFT, padx=2)
        self.add_folder_btn.pack(side=tk.LEFT, padx=2)
        self.remove_btn.pack(side=tk.LEFT, padx=2)
        self.remove_all_btn.pack(side=tk.LEFT, padx=2)
        
        self.right_toolbar.pack(side=tk.RIGHT)
        self.logs_btn.pack(side=tk.LEFT, padx=2)
        self.settings_btn.pack(side=tk.LEFT, padx=2)

        self.tree_frame.pack(fill=tk.BOTH, expand=True)
        self.tree_scroll_y.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.bottom_panel.pack(fill=tk.X, pady=5)
        self.convert_btn.pack(side=tk.RIGHT)

        self.status_frame.pack(fill=tk.X, side=tk.BOTTOM)
        self.status_label.pack(fill=tk.X)

    def _bind_events(self):
        self.tree.bind("<Button-1>", self.on_tree_click)
        self.tree.bind("<Delete>", lambda e: self.on_remove_click())
        self.root.bind("<Control-a>", self.on_select_all)
        self.tree.bind("<space>", self.on_space_toggle)

    # --- Actions ---

    def on_logs_click(self):
        """Opens the logs directory."""
        if LOG_DIR.exists():
            open_path(LOG_DIR)
        else:
            messagebox.showinfo("Logs", "Log directory does not exist yet.")

    def on_settings_click(self):
        dialog = SettingsDialog(self.root, self.conversion_config)
        if dialog.result:
            self.conversion_config = dialog.result
            self.status_label.config(text="Settings saved.")

    # --- Selection Logic ---

    def on_select_all(self, event=None):
        children = self.tree.get_children()
        if not children: return
        selection = []
        for child in children:
            selection.append(child)
            selection.extend(self.tree.get_children(child))
        self.tree.selection_set(selection)

    def _set_item_state(self, item_id, selected: bool):
        """Helper to toggle item visual state between selected and unselected/dimmed."""
        img = self.icon_selected if selected else self.icon_unselected
        tags = () if selected else ('dimmed',)
        self.tree.item(item_id, image=img, tags=tags)
        
        if item_id in self.folder_nodes.values():
            for child in self.tree.get_children(item_id):
                self.tree.item(child, image=img, tags=tags)

    def on_space_toggle(self, event=None):
        selected_items = self.tree.selection()
        if not selected_items: return
        
        first = selected_items[0]
        curr_img = self.tree.item(first, "image")
        target_selected = str(self.icon_unselected) in str(curr_img)
        
        for item_id in selected_items:
            self._set_item_state(item_id, target_selected)

    def on_tree_click(self, event):
        region = self.tree.identify_region(event.x, event.y)
        if region == "tree" or region == "image":
            item_id = self.tree.identify_row(event.y)
            if not item_id: return
            if self.conversion_thread and self.conversion_thread.is_alive(): return

            curr_img = self.tree.item(item_id, "image")
            is_currently_unselected = str(self.icon_unselected) in str(curr_img)
            self._set_item_state(item_id, is_currently_unselected)

    def on_header_click(self):
        if self.conversion_thread and self.conversion_thread.is_alive(): return
        children = self.tree.get_children()
        if not children: return
        
        first_img = self.tree.item(children[0], "image")
        target_selected = str(self.icon_unselected) in str(first_img)
        
        for item in children:
            self._set_item_state(item, target_selected)

    def on_remove_click(self):
        if self.conversion_thread and self.conversion_thread.is_alive(): return
        selected = self.tree.selection()
        if not selected: return
        
        for item_id in selected:
            if item_id in self.folder_nodes.values():
                for child in self.tree.get_children(item_id):
                    self._remove_from_map(child)
                key = next((k for k, v in self.folder_nodes.items() if v == item_id), None)
                if key: del self.folder_nodes[key]
            else:
                self._remove_from_map(item_id)
            self.tree.delete(item_id)
        
        self.status_label.config(text="Items removed.")

    def on_remove_all_click(self):
        if self.conversion_thread and self.conversion_thread.is_alive(): return
        self.tree.delete(*self.tree.get_children())
        self.file_map.clear()
        self.folder_nodes.clear()
        self.status_label.config(text="All items removed.")

    def _remove_from_map(self, item_id):
        path_to_remove = next((k for k, v in self.file_map.items() if v == item_id), None)
        if path_to_remove: del self.file_map[path_to_remove]

    # --- Async File Adding ---

    def _update_ui_state(self, busy):
        state = tk.DISABLED if busy else tk.NORMAL
        self.add_files_btn.config(state=state)
        self.add_folder_btn.config(state=state)
        self.remove_btn.config(state=state)
        self.remove_all_btn.config(state=state)
        self.convert_btn.config(state=state)

    def on_add_files_click(self):
        files = filedialog.askopenfilenames(title="Select FB2 Files", filetypes=[("FB2 Files", "*.fb2 *.fb2.zip"), ("All Files", "*.*")])
        if files: 
            self._start_scanning([Path(f) for f in files])

    def on_add_folder_click(self):
        folder = filedialog.askdirectory()
        if folder: 
            self._start_scanning([Path(folder)])

    def on_drop(self, event):
        data = event.data
        if not data: return
        try:
            paths_list = self.root.tk.splitlist(data)
        except Exception:
            paths_list = re.findall(r'\{([^}]+)\}|([^{\s}]+)', data)
            paths_list = [p[0] or p[1] for p in paths_list]
        
        if paths_list:
            self._start_scanning([Path(p) for p in paths_list])

    def _start_scanning(self, input_paths: list[Path]):
        """Starts a background thread to scan directories and add files."""
        self._update_ui_state(busy=True)
        self.status_label.config(text="Scanning files...")
        
        threading.Thread(target=self._scan_worker, args=(input_paths,), daemon=True).start()

    def _scan_worker(self, input_paths: list[Path]):
        """Background worker to scan for files."""
        found_files = []
        for p in input_paths:
            if p.is_file() and p.suffix in ['.fb2', '.zip']:
                found_files.append(p)
            elif p.is_dir():
                for ext in ("**/*.fb2", "**/*.fb2.zip"):
                    found_files.extend(p.rglob(ext))
        
        # Send result back to main thread
        self.queue.put(("scan_complete", None, found_files))

    def _batch_add_files(self, files: list[Path]):
        """Adds files to treeview and queues metadata parsing. Runs on main thread."""
        added_count = 0
        for path in files:
            s_path = str(path)
            if s_path in self.file_map: continue
            
            parent = path.parent
            s_parent = str(parent)
            
            if s_parent not in self.folder_nodes:
                node = self.tree.insert("", tk.END, text=s_parent, image=self.icon_selected, open=True)
                self.folder_nodes[s_parent] = node
            
            p_node = self.folder_nodes[s_parent]
            item_id = self.tree.insert(p_node, tk.END, text=path.name, image=self.icon_selected, values=("Parsing...", "", "", ""))
            self.file_map[s_path] = item_id
            added_count += 1
            
            # Submit to ThreadPool instead of creating a new thread
            self.meta_executor.submit(self._parse_meta_task, item_id, path)
            
        self.status_label.config(text=f"Added {added_count} new files.")

    def _parse_meta_task(self, item_id, path):
        """Task running in thread pool."""
        try:
            meta = FB2Book.get_quick_metadata(path)
            self.queue.put(("parse_ok", item_id, meta))
        except Exception as e:
            self.queue.put(("parse_fail", item_id, str(e)))

    # --- Conversion ---

    def on_convert_click(self):
        if self.conversion_thread and self.conversion_thread.is_alive(): return

        files_to_convert = []
        for s_path, item_id in self.file_map.items():
            if not self.tree.exists(item_id): continue
            if str(self.icon_selected) in str(self.tree.item(item_id, "image")):
                files_to_convert.append(Path(s_path))
        
        if not files_to_convert:
            messagebox.showinfo("Info", "No files checked for conversion.")
            return

        out_dir = filedialog.askdirectory(title="Output Folder (Cancel for default)")
        
        self.conversion_config = dataclasses.replace(
            self.conversion_config,
            output_path=Path(out_dir) if out_dir else None
        )

        self._start_conversion(files_to_convert)

    def _start_conversion(self, files):
        self._update_ui_state(busy=True)
        self.status_label.config(text=f"Converting {len(files)} files...")
        
        def run_batch():
            try:
                proc = BatchProcessor(self.conversion_config)
                proc.run(files, self._progress_callback)
                self.queue.put(("batch_done", None, None))
            except Exception as e:
                self.queue.put(("fatal_error", None, str(e)))

        self.conversion_thread = threading.Thread(target=run_batch, daemon=True)
        self.conversion_thread.start()

    def _progress_callback(self, path: Path, result: Path | None, exc: Exception | None):
        item_id = self.file_map.get(str(path))
        if item_id:
            if exc:
                self.queue.put(("convert_fail", item_id, str(exc)))
            else:
                self.queue.put(("convert_ok", item_id, None))

    def _process_queue(self):
        try:
            while True:
                task, item_id, data = self.queue.get_nowait()
                
                # Handle non-item tasks
                if task == "scan_complete":
                    self._update_ui_state(busy=False)
                    self._batch_add_files(data)
                    continue
                elif task == "batch_done":
                    self._update_ui_state(busy=False)
                    messagebox.showinfo("Done", "Conversion complete.")
                    continue
                elif task == "fatal_error":
                    self._update_ui_state(busy=False)
                    messagebox.showerror("Error", data)
                    continue

                # Handle item-specific tasks
                if item_id and not self.tree.exists(item_id): continue

                match task:
                    case "parse_ok":
                        self.tree.item(item_id, values=data)
                    case "parse_fail":
                        self.tree.item(item_id, values=("Error", str(data), "", ""))
                    case "convert_ok":
                        self.tree.item(item_id, image=self.icon_success, tags=("success",))
                        self.tree.tag_configure("success", foreground="green")
                    case "convert_fail":
                        self.tree.item(item_id, image=self.icon_failure, tags=("failure",))
                        self.tree.tag_configure("failure", foreground="red")
                        log.error(f"GUI Fail: {data}")

        except queue.Empty:
            pass
        self.root.after(100, self._process_queue)


def run_gui():
    if TkinterDnD:
        root = TkinterDnD.Tk()
    else:
        root = tk.Tk()
    app = ConverterApp(root)
    root.mainloop()