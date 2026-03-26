"""English (en) UI strings."""

STRINGS: dict[str, str] = {
    # Toolbar
    "toolbar.add_files":         "Add Files",
    "toolbar.add_folder":        "Add Folder",
    "toolbar.remove":            "Remove",
    "toolbar.remove_all":        "Remove All",
    "toolbar.remove_done":       "Remove Done",
    "toolbar.select_toggle":     "{checked} of {total} selected",
    "toolbar.settings":          "⚙ Settings",
    "toolbar.app_settings":      "🔧",
    "toolbar.logs":              "📋 Logs",
    "toolbar.about":             "ℹ About",

    # Toolbar tooltips
    "tooltip.add_files":         "Add individual .fb2 or .fb2.zip files",
    "tooltip.add_folder":        "Scan a directory recursively for FB2 files",
    "tooltip.remove":            "Remove selected items from the list",
    "tooltip.remove_all":        "Clear the entire file list",
    "tooltip.remove_done":       "Remove all successfully converted files",
    "tooltip.select_toggle":     "Click to select all / deselect all",
    "tooltip.settings":          "Configure conversion options",
    "tooltip.app_settings":      "Application preferences",
    "tooltip.logs":              "Open the logs directory",
    "tooltip.about":             "About this application",

    # Tree header
    "tree.col_name":   "Filename",
    "tree.col_status": "Status",
    "tree.col_author": "Author",
    "tree.col_title":  "Title",
    "tree.col_date":   "Date",
    "tree.col_lang":   "Lang",

    # Bottom bar
    "bar.ready":                 "Ready",
    "bar.scanning":              "Scanning…",
    "bar.ready_n_files":         "Ready — {n} file(s) in list",
    "bar.converting_n":          "Converting {n} file(s)…",
    "bar.converting_progress":   "Converting… {done} / {total}",
    "bar.done":                  "Done — {total} file(s) processed.",
    "bar.cancelled":             "Cancelled.",
    "bar.cancelling":            "Cancelling…",
    "bar.logs_folder":           "📂 Logs folder",
    "bar.last_log":              "📋 Last log",
    "bar.convert":               "Convert",
    "bar.cancel":                "Cancel",
    "tooltip.logs_folder":       "Open the logs directory in your file manager",
    "tooltip.last_log":          "View the log from the most recent run",

    # Dialogs — general
    "dlg.ok":     "OK",
    "dlg.cancel": "Cancel",
    "dlg.close":  "Close",
    "dlg.copy":   "Copy All",
    "dlg.yes":    "Yes",
    "dlg.no":     "No",

    # Settings dialog
    "settings.title":             "Conversion Settings",
    "settings.structure":         "Document Structure",
    "settings.toc_depth":         "TOC depth (1–6):",
    "settings.toc_depth_tip":     "Maximum heading level to include in the table of contents.",
    "settings.split_level":       "Split level (1–6):",
    "settings.split_level_tip":   "Split the EPUB into separate files at this heading level.",
    "settings.split_size":        "Max file size:",
    "settings.split_size_tip":    "Raise split level if XHTML files exceed this size. 0 = disabled.",
    "settings.split_size_unit":   " KB",
    "settings.split_size_off":    "Disabled",
    "settings.processing":        "Processing",
    "settings.remove_images":     "Remove unused images",
    "settings.remove_images_tip": "Strip images that are not referenced in the text.",
    "settings.typography":        "Improve typography",
    "settings.typography_tip":    "Enable post-processing: non-breaking spaces, no-break spans, etc.",
    "settings.nbsp_range":        "NBSP word length range:",
    "settings.nobr_range":        "No-break word length range:",
    "settings.output":            "Output",
    "settings.custom_css":        "Custom CSS:",
    "settings.css_placeholder":   "Use built-in stylesheet",
    "settings.output_folder":     "Output folder:",
    "settings.output_placeholder":"Same folder as input file",
    "settings.performance":       "Performance",
    "settings.threads":           "Worker threads (0=auto):",
    "settings.threads_tip":       "Number of parallel worker processes. 0 = auto-detect.",
    "settings.threads_auto":      "Auto",

    # App settings dialog
    "appsettings.title":         "Application Settings",
    "appsettings.appearance":    "Appearance",
    "appsettings.theme":         "Theme:",
    "appsettings.theme_system":  "System",
    "appsettings.theme_light":   "Light",
    "appsettings.theme_dark":    "Dark",
    "appsettings.language":      "Language:",

    # About dialog
    "about.title":       "About FictionPub",
    "about.description": (
        "FictionPub converts FB2 e-books to the EPUB 3 format. "
        "It supports batch processing, parallel conversion, custom stylesheets, "
        "and typography post-processing."
    ),
    "about.built_with": (
        "<b>Built with:</b> Python 3 · PySide6 / Qt 6 · "
        "concurrent.futures (ProcessPoolExecutor)"
    ),

    # Log viewer
    "logviewer.title_file":      "Log — {name}",
    "logviewer.filter_label":    "Filter:",
    "logviewer.filter_tip":      "Type to filter lines…",
    "logviewer.filter_all":      "All",
    "logviewer.filter_warnings": "Warnings",
    "logviewer.filter_errors":   "Errors",

    # Context menu
    "ctx.open_epub":   "Open EPUB",
    "ctx.open_fb2":    "Open source FB2",
    "ctx.open_folder": "Open containing folder",
    "ctx.view_log":    "View Log",
    "ctx.remove":      "Remove",

    # MessageBox titles / messages
    "msg.remove_all_title":    "Remove All",
    "msg.remove_all_text":     "Remove all files from the list?",
    "msg.no_files_title":      "No Files Selected",
    "msg.no_files_text":       "Please check at least one file before converting.",
    "msg.no_logs_title":       "Logs",
    "msg.no_logs_dir":         "No log directory found yet.",
    "msg.no_logs_files":       "No log files found.",
    "msg.close_title":         "Conversion in Progress",
    "msg.close_text":          "A conversion is still running. Cancel it and quit?",
    "msg.no_epub_title":       "File Not Found",
    "msg.no_epub_text":        "The output EPUB file was not found:\n{path}",

    # File dialog filters
    "filter.fb2":   "FB2 Files (*.fb2 *.fb2.zip)",
    "filter.css":   "CSS Files (*.css)",
    "filter.all":   "All Files (*)",

    # Status tooltip
    "tooltip.warning_status": "Conversion finished with warnings — check logs for details.",
}
