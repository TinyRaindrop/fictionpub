"""
Contains the code for a feature-rich graphical user interface (GUI).

This GUI supports batch processing of files and directories, asynchronous
metadata parsing, and conversion, ensuring the UI remains responsive.
"""
import logging
import traceback
import threading
import queue
from pathlib import Path

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from tkinterdnd2 import DND_FILES, TkinterDND

from .utils.config import ConversionConfig
from .core.batch_processor import BatchProcessor
from .core.fb2_book import FB2Book


log = logging.getLogger("fb2_converter")


class SettingsDialog(tk.Toplevel):
    """A dialog for configuring conversion settings."""
    def __init__(self, parent, config: ConversionConfig):
        super().__init__(parent)
        self.transient(parent)
        self.title("Conversion Settings")
        self.config = config
        self.result: ConversionConfig | None = None

        self.toc_depth_var = tk.IntVar(value=self.config.toc_depth)
        self.split_level_var = tk.IntVar(value=self.config.split_level)
        self.split_size_var = tk.IntVar(value=self.config.split_size_kb)
        self.stylesheet_var = tk.StringVar(value=str(self.config.custom_stylesheet))

        body = ttk.Frame(self, padding="10")
        body.pack(padx=5, pady=5)

        ttk.Label(body, text="Table of Contents depth:").grid(row=0, column=0, sticky="w")
        ttk.Spinbox(body, from_=1, to=6, textvariable=self.toc_depth_var, width=5).grid(row=0, column=1, padx=5)
        ttk.Label(body, text="Split level:").grid(row=1, column=0, sticky="w")
        ttk.Spinbox(body, from_=1, to=6, textvariable=self.split_level_var, width=5).grid(row=1, column=1, padx=5)
        ttk.Label(body, text="Split size (KB):").grid(row=2, column=0, sticky="w")
        ttk.Spinbox(body, from_=0, textvariable=self.split_size_var, width=5).grid(row=2, column=1, padx=5)
        ttk.Label(body, text="Stylesheet").grid(row=3, column=0, sticky="w")
        ttk.Entry(body, textvariable=self.stylesheet_var, width=20).grid(row=3, column=1, padx=5)
        
        button_frame = ttk.Frame(self)
        button_frame.pack(padx=10, pady=(0, 10), fill="x")
        
        ttk.Button(button_frame, text="OK", command=self._on_ok).pack(side="right")
        ttk.Button(button_frame, text="Cancel", command=self._on_cancel).pack(side="right", padx=5)

        self.grab_set()
        self.wait_window(self)

    def _on_ok(self):
        # Update the config object with new values from the dialog
        self.config.toc_depth = self.toc_depth_var.get()
        self.config.split_level = self.split_level_var.get()
        self.config.split_size_kb = self.split_size_var.get()
        self.config.custom_stylesheet = Path(self.stylesheet_var.get())
        self.result = self.config
        self.destroy()

    def _on_cancel(self):
        self.result = None
        self.destroy()


class ConverterApp:
    def __init__(self, root):
        self.root = root
        self.root.title("FB2 to EPUB Batch Converter")
        self.root.geometry("960x600")
        self.root.minsize(600, 400)

        self.conversion_thread = None
        self.file_map = {}
        self.directory_nodes = {}
        self.selection_map = {}
        self.conversion_config = ConversionConfig()
        
        # Base64 encoded tiny images for state
        # TODO: replace with PNG
        # Empty (pending)
        PENDING_B64 = "iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAALUlEQVQ4T2NkoAEwUqAyoGBCUoFhQJqB1IFBcBqRhYHarwMEEwM1IHIx0EAEsQAAYQYB/8UPomEAAAAASUVORK5CYII="
        # Green Check (success)
        SUCCESS_B64 = "iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAACl0lEQVQ4T41TTWtTURD+Vne9N0mTJjGJU5M0qVlTjAup2lZtqV1FhLgSxEUK6kaCi4i4F3EhAhdBrlq1K4i6EJeiXFz5Aa66EKEiXGlT06T5vPcmTZo0adO01M8OPDszOzvzPcN+XFwePj6mP/i/oK+vD8Vi8cbj8V08Ht+Lx+PB4XA0Nzc3LIvVag2NRmN/vV4fA4GAisVisECIEMdxvN1spmKx+B0Mw8fQarX+y31h18wBIIoihBAIAoFAv9+PJpNJc3NzLMsSjUZDlGVJpVIhCAKEw+GAIAgQhiGz2QwjEWOMsWazGWOMsVwuQ5ZlyWQyrNdr0Gg0aDQaGIYBgBDGGOPxeChb02q1kMvlAAohBDs7OxCLxcjlcqRSKYiiiFgsRjAYpG+G5vN5xWKRmEwmxsbGOHDgwB8uXLjAzc2Nm5ubmJub4+HhgaenJ7quf6HRaLDb7RBCgGAYBul0msPhgCAISJIkHo+HeDwOiUAIAYRSqRSHw4EoikilUhBCgCAIkM/ni8VigBAKhcLvVqs1mqaJZrNB0zRhGCabzQJtmmYymSSdTgNhGCYSiQCqYrH4G8MwLBaL+v1+URSxWq1gcRzzAyzLkmq1isViEQqFAABBEACAMQaApmnQNM1utwshRBRFHMdxOBwKjUYDmqaRz+fh+77dbocsy4jH43A4HIhGoxRFwXVdsixjfX0dRVFQLpeRSqWILMs4HA5AkiSEEOVyGWEYgqZpsixjPB4DwDAMBgMRx3EMwxCLxaBarUKr1RJCgGEYYrEYiBDy+RwgCPJ+vweA1+slGo3yfr8PhmE0nU4zDMM4HA5EkiQymQyZTAYZhiGZTAIAy7IkGo2S3W5HFEWaphFCiKLI6XSK4/EYDAZAIoQQCoX8fv/V6/VCoRA+n08VBEH4ff+ryWQSmqbpN5sNkUgEAACNRsNyuQzHcbZt22azeXw+n1ar9Z3neXmNMQDAt23bbrdDkiQ+nw+KoqDVakEITdP8B0Y5/xG1k3FIAAAAAElFTkSuQmCC"
        # Red X (failure)
        FAILURE_B64 = "iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAACaklEQVQ4T6WTTUhUURTHf/emx6yZRh0zdFqD0Ai6UW1oF5FudAm6EBfqErVpoW5SFAVBtGjRQkF0IyKIiKA3kZAWBBU703YxPZ9z7j13bt/MvDcYhGbIgfNx7vN/zrn3A/AfLly4cCIQCPwQCAR+C4VC9oGBAZpMJoPBYFhUVITVam1ra2s2m83A6/WWVqvNsVgsyMfjcXNzczo6Oubl5eW/6ojP5+Pv7x9dXV1zc3PzmJqawuVyAfj4+DgcDsPlcjE3NwdAOBx2Op2WpqamkM/nq1wuBQGfYIhhGNdxHDs7OzRNw/O8R0dHfH19AYiKigIA8Pl8rKyswOv14PF4kE6nAYDX68UwjOd5x3GcFBUV+blcDu/3e2trK4eHh3EcBwBBEABQsVh0u93L5XIAAgaDARqN5o8cTwjDyWQymUwmIRqNfsePHycvLw+xWAxzc3NwOByMj4/T1NQEwHIiJiamvb0dIyMjvL29AQiFQvu+LwCwWCzy+Tz8PhgMQoIgkEgkgiAI+P1+vV5PENQ0zXw+v2q1Gk3TBAKBQEiSpNFoENF1nclkMhqNwuFwBINBkMvl4HkeQRBQUVEBtGmaTCbDbreDz+dDoVAgCALm5+f5/v4G4OjoiNfrxev1gkBQFMVut3t3d5eTkxMAoVDI4XCAIAjBYBBmZmbY3t6G4zgYY5LJJIQQCoUCm82GlZUV+v0+LMsiSRIeDoeHhwdEo1GSpEmlUsiyrKurC13X+Xw+Wq0Wu90OAFmWqdVqGAwGuq6bzWajadrr9RJFkXK5nHg8Hk3TyOfz0+k0m81mgBAApVL5P/0H/gX9G0P8A+e1MQzO1l3gAAAAAElFTkSuQmCC"
        
        self.pending_img = tk.PhotoImage(data=PENDING_B64)
        self.success_img = tk.PhotoImage(data=SUCCESS_B64)
        self.failure_img = tk.PhotoImage(data=FAILURE_B64)

        # GIF data for checkboxes
        self.checked_img = tk.PhotoImage(
            "checked_img",
            data=b'R0lGODlhEAAQALMAAAAAAAD/AAAA//8A/wD/AP//AAAA/wD/AP8A/wD/AP8A/wD/AP8A/wD/AP8A/wD/AAAAACH5BAEAAA8ALAAAAAAQABAAAARa8ElGq5kM4660fCIQ3gL4cWX3Fpx1lJ5oMopZp52rtrQC3/N6I8iQNh5y+A4gTCf2fI4HpdJ5AFnOms3qded5n4YxAYyJd1zG/bl/p1v/A/U3/gcCADs=',
            master=root
        )
        self.unchecked_img = tk.PhotoImage(
            "unchecked_img",
            data=b'R0lGODlhEAAQAIABAAAAAP///yH5BAEKAAEALAAAAAAQABAAAAIOjI+py+0Po5y02otnAQA7',
            master=root
        )

        self._setup_widgets()
        self.worker_queue = queue.Queue()

    def _setup_widgets(self):
        top_frame = ttk.Frame(self.root, padding="10 10 10 5")
        top_frame.pack(side="top", fill="x")
        middle_frame = ttk.Frame(self.root, padding="10 0 10 10")
        middle_frame.pack(side="top", fill="both", expand=True)
        bottom_frame = ttk.Frame(self.root, padding="10 5 10 10")
        bottom_frame.pack(side="bottom", fill="x")

        # Top Frame
        ttk.Button(top_frame, text="Add Files...", command=self._add_files).pack(side="left", padx=(0, 5))
        ttk.Button(top_frame, text="Add Directory...", command=self._add_directory).pack(side="left", padx=5)
        ttk.Button(top_frame, text="Settings...", command=self._open_settings).pack(side="left", padx=5)
        ttk.Button(top_frame, text="Clear List", command=self._clear_list).pack(side="right")

        self.tree = ttk.Treeview(middle_frame, columns=("size", "author", "title"), show="tree headings")
        self.tree.pack(side="left", fill="both", expand=True)

        self.tree.heading("#0", text="File / Directory Path", image=self.checked_img, anchor="w", command=self._toggle_all_selection)
        self.tree.heading("size", text="Size")
        self.tree.heading("author", text="Author")
        self.tree.heading("title", text="Book Title")
        self.tree.column("#0", width=300, stretch=tk.YES)
        self.tree.column("size", width=100, anchor="e")
        self.tree.column("author", width=150)
        self.tree.column("title", width=250)

        scrollbar = ttk.Scrollbar(middle_frame, orient="vertical", command=self.tree.yview)
        scrollbar.pack(side="right", fill="y")
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.bind("<Button-1>", self._on_tree_click)
        self.all_selected_state = True

        self.status_label = ttk.Label(bottom_frame, text="Select files or directories to begin.")
        self.status_label.pack(side="left", fill="x", expand=True)
        self.parse_button = ttk.Button(bottom_frame, text="Parse Metadata", command=self._start_metadata_parsing, state="disabled")
        self.parse_button.pack(side="left", padx=10)
        self.convert_button = ttk.Button(bottom_frame, text="Convert Selected", command=self._start_conversion, state="disabled")
        self.convert_button.pack(side="left")

    def _open_settings(self):
        dialog = SettingsDialog(self.root, self.conversion_config)
        if dialog.result is not None:
            self.conversion_config = dialog.result
            messagebox.showinfo("Settings Updated", "Conversion settings have been updated.")

    def _start_conversion(self):
        files_to_convert = [path for item_id, path in self.file_map.items() if self.selection_map.get(item_id, False)]
        if not files_to_convert:
            messagebox.showwarning("No Files Selected", "Please select at least one file to convert.")
            return

        self.status_label.config(text=f"Starting parallel conversion for {len(files_to_convert)} file(s)...")
        self.parse_button.config(state="disabled")
        self.convert_button.config(state="disabled")

        threading.Thread(target=self._conversion_worker, args=(files_to_convert,), daemon=True).start()
        self.root.after(100, self._process_queue)

    def _conversion_worker(self, files_to_convert: list[Path]):
        """Worker thread that uses the BatchProcessor."""
        total = len(files_to_convert)
        completed_count = 0
        path_to_id = {path: item_id for item_id, path in self.file_map.items()}

        def progress_callback(path: Path, result: Path | None, exc: Exception | None):
            nonlocal completed_count
            completed_count += 1
            item_id = path_to_id.get('path')
            if not item_id:
                return
            
            self.worker_queue.put(("status", None, f"Converting ({completed_count}/{total}): {path.name}"))
            if exc:
                # For the GUI, we show a simple error message in the UI,
                # but we log the full, detailed traceback to the console for debugging.
                # traceback.format_exc() gets the full traceback string.
                full_traceback = traceback.format_exc()
                log.error(f"Error converting {path.name}:\n{full_traceback}")
                self.worker_queue.put(("convert_fail", item_id, f"✗ Error: {exc}"))
            else:
                self.worker_queue.put(("convert_ok", item_id, "✓ Converted"))         

        try:
            processor = BatchProcessor(self.conversion_config)
            processor.run(files_to_convert, progress_callback)
        except Exception as e:
            self.worker_queue.put(("fatal_error", None, f"A fatal error occurred: {e}"))
        
        self.worker_queue.put(("conversion_done", None, "All selected conversions finished."))
    
    def _on_tree_click(self, event):
        """Handles clicks on the treeview to toggle checkboxes."""
        region = self.tree.identify_region(event.x, event.y)
        if region != "tree":
            return # Click was not on the checkbox area
        
        item_id = self.tree.identify_row(event.y)
        if item_id:
            self._toggle_item_selection(item_id)

    def _toggle_item_selection(self, item_id):
        """Toggles the selection state of a single item and its children if it's a directory."""
        current_state = self.selection_map.get(item_id, False)
        new_state = not current_state
        
        # Toggle the item itself
        self.selection_map[item_id] = new_state
        self.tree.item(item_id, image=self.checked_img if new_state else self.unchecked_img)

        # If it's a directory, toggle all its children
        if item_id in self.directory_nodes.values():
            for child_id in self.tree.get_children(item_id):
                self.selection_map[child_id] = new_state
                self.tree.item(child_id, image=self.checked_img if new_state else self.unchecked_img)
        else: # If it's a file, update the parent directory's state
            parent_id = self.tree.parent(item_id)
            if parent_id:
                all_children_checked = all(self.selection_map.get(child, False) for child in self.tree.get_children(parent_id))
                self.selection_map[parent_id] = all_children_checked
                self.tree.item(parent_id, image=self.checked_img if all_children_checked else self.unchecked_img)
        
        self._update_button_states()

    def _toggle_all_selection(self):
        """Toggles the selection state for all items in the tree."""
        self.all_selected_state = not self.all_selected_state
        new_image = self.checked_img if self.all_selected_state else self.unchecked_img
        self.tree.heading("#0", image=new_image)

        for item_id in self.selection_map:
            self.selection_map[item_id] = self.all_selected_state
            self.tree.item(item_id, image=new_image)
        self._update_button_states()

    def _populate_file_list(self, paths):
        files_to_add = []
        for path in paths:
            if path.is_dir():
                for ext in ("**/*.fb2", "**/*.fb2.zip"):
                    files_to_add.extend(path.rglob(ext))
            elif path.is_file() and path.suffix in ['.fb2', '.zip']:
                files_to_add.append(path)

        for file_path in files_to_add:
            if any(p == file_path for p in self.file_map.values()): continue

            dir_path_str = str(file_path.parent)
            if dir_path_str not in self.directory_nodes:
                dir_node_id = self.tree.insert("", "end", text=dir_path_str, open=True, image=self.checked_img)
                self.directory_nodes[dir_path_str] = dir_node_id
                self.selection_map[dir_node_id] = True
            else:
                dir_node_id = self.directory_nodes[dir_path_str]

            size = file_path.stat().st_size
            file_id = self.tree.insert(dir_node_id, "end", text=f"  {file_path.name}", values=(self._format_size(size), "...", "..."), image=self.checked_img)
            self.file_map[file_id] = file_path
            self.selection_map[file_id] = True      # Default to selected
        
        self._update_button_states()

    def _clear_list(self):
        self.tree.delete(*self.tree.get_children())
        self.file_map.clear()
        self.directory_nodes.clear()
        self.selection_map.clear()
        self._update_button_states()
        self.status_label.config(text="Select files or directories to begin.")

    def _update_button_states(self):
        # Enable buttons if at least one file is selected for conversion
        any_selected = any(self.selection_map.get(item_id, False) for item_id in self.file_map)
        state = "normal" if any_selected else "disabled"
        self.convert_button.config(state=state)
        
        # Parse button is enabled if any files exist in the list
        self.parse_button.config(state="normal" if self.file_map else "disabled")

    def _add_files(self):
        filepaths = filedialog.askopenfilenames(
            title="Select FB2 files",
            filetypes=(("FictionBook files", "*.fb2 *.fb2.zip"), ("All files", "*.*"))
        )
        if filepaths:
            self._populate_file_list([Path(p) for p in filepaths])

    def _add_directory(self):
        dirpath = filedialog.askdirectory(title="Select a directory containing FB2 files")
        if dirpath:
            self._populate_file_list([Path(dirpath)])
    
    def _format_size(self, size_bytes):
        if size_bytes is None: return ""
        if size_bytes > 1024 * 1024:
            return f"{size_bytes / (1024*1024):.2f} MB"
        return f"{size_bytes / 1024:.1f} KB"

    def _start_metadata_parsing(self):
        self.status_label.config(text="Parsing metadata...")
        self.parse_button.config(state="disabled")
        self.convert_button.config(state="disabled")
        threading.Thread(target=self._metadata_worker, daemon=True).start()
        self.root.after(100, self._process_queue)
        
    def _metadata_worker(self):
        # This could also be parallelized with a ThreadPoolExecutor for huge lists
        for item_id, path in self.file_map.items():
            metadata = FB2Book.get_quick_metadata(path)
            self.worker_queue.put(("metadata", item_id, metadata))
        self.worker_queue.put(("metadata_done", None, None))

    def _process_queue(self):
        try:
            while True:
                task_type, item_id, data = self.worker_queue.get_nowait()
                match task_type:
                    case "metadata":
                        self.tree.set(item_id, "author", data.get('author', 'N/A'))
                        self.tree.set(item_id, "title", data.get('title', 'N/A'))
                    case "metadata_done":
                        self.status_label.config(text="Metadata parsing complete.")
                        self._update_button_states()
                        return
                    case "status":
                        self.status_label.config(text=data)
                    case "convert_ok":
                        self.tree.item(item_id, tags=('success',))
                        self.tree.tag_configure('success', foreground='green')
                    case "convert_fail":
                        self.tree.item(item_id, tags=('failure',))
                        self.tree.tag_configure('failure', foreground='red')
                        log.error(f"Failed to convert {self.file_map.get(item_id)}: {data}")
                    case "conversion_done":
                        self.status_label.config(text=data)
                        self._update_button_states()
                        messagebox.showinfo("Complete", "Batch conversion process has finished.")
                        return
                    case "fatal_error":
                        self.status_label.config(text="A fatal error stopped the conversion.")
                        messagebox.showerror("Fatal Error", str(data))
                        self._update_button_states()
                        return
                    case _:
                        log.error(f"Unknown task type: {task_type}")
                        return
        except queue.Empty:
            self.root.after(100, self._process_queue)
            

def run_gui():
    root = tk.Tk()
    app = ConverterApp(root)
    root.mainloop()
