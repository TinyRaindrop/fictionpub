"""
Lightweight i18n layer.

Usage:
    from .i18n import t, set_language

    label.setText(t("toolbar.add_files"))

To add a new string: add it to both _EN and _UK dicts with the same key.
Widgets that need to react to language changes implement retranslate_ui()
and connect it to AppState.language_changed.
"""

from typing import Callable

_LANG: str = "en"
_listeners: list[Callable[[], None]] = []

# ---------------------------------------------------------------------------
# English source strings
# ---------------------------------------------------------------------------
_EN: dict[str, str] = {
    # Toolbar
    "toolbar.add_files":         "Add Files",
    "toolbar.add_folder":        "Add Folder",
    "toolbar.remove":            "Remove",
    "toolbar.remove_all":        "Remove All",
    "toolbar.remove_done":       "Remove Done",
    "toolbar.select_all":        "✓ All",
    "toolbar.select_none":       "✗ None",
    "toolbar.settings":          "⚙ Settings",
    "toolbar.app_settings":      "🔧",
    "toolbar.logs":              "📋 Logs",
    "toolbar.n_of_m_selected":   "{checked} of {total} selected",

    # Toolbar tooltips
    "tooltip.add_files":         "Add individual .fb2 or .fb2.zip files",
    "tooltip.add_folder":        "Scan a directory recursively for FB2 files",
    "tooltip.remove":            "Remove selected items from the list",
    "tooltip.remove_all":        "Clear the entire file list",
    "tooltip.remove_done":       "Remove all successfully converted files",
    "tooltip.select_all":        "Select all files",
    "tooltip.select_none":       "Deselect all files",
    "tooltip.settings":          "Configure conversion options",
    "tooltip.app_settings":      "Application preferences",
    "tooltip.logs":              "Open the logs directory",

    # Tree header
    "tree.col_name":   "Status / Filename",
    "tree.col_author": "Author",
    "tree.col_title":  "Title",
    "tree.col_date":   "Date",
    "tree.col_lang":   "Lang",

    # Bottom bar
    "bar.ready":                 "Ready",
    "bar.scanning":              "Scanning…",
    "bar.ready_n_files":         "Ready — {n} file(s) in list",
    "bar.converting_n":          "Converting {n} file(s)…",
    "bar.converting_progress":   "Converting… {done}/{total}",
    "bar.done":                  "Done — {total} file(s) processed.",
    "bar.cancelled":             "Cancelled.",
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
    "settings.title":            "Conversion Settings",
    "settings.structure":        "Document Structure",
    "settings.toc_depth":        "TOC depth (1–6):",
    "settings.toc_depth_tip":    "Maximum heading level to include in the table of contents.",
    "settings.split_level":      "Split level (1–6):",
    "settings.split_level_tip":  "Split the EPUB into separate files at this heading level.",
    "settings.split_size":       "Max file size:",
    "settings.split_size_tip":   "Raise split level if XHTML files exceed this size. 0 = disabled.",
    "settings.split_size_unit":  " KB",
    "settings.split_size_off":   "Disabled",
    "settings.processing":       "Processing",
    "settings.remove_images":    "Remove unused images",
    "settings.remove_images_tip":"Strip images that are not referenced in the text.",
    "settings.typography":       "Improve typography",
    "settings.typography_tip":   "Enable post-processing: non-breaking spaces, no-break spans, etc.",
    "settings.nbsp_range":       "NBSP word length range:",
    "settings.nobr_range":       "No-break word length range:",
    "settings.output":           "Output",
    "settings.custom_css":       "Custom CSS:",
    "settings.css_placeholder":  "Use built-in stylesheet",
    "settings.output_folder":    "Output folder:",
    "settings.output_placeholder":"Same folder as input file",
    "settings.performance":      "Performance",
    "settings.threads":          "Worker threads (0=auto):",
    "settings.threads_tip":      "Number of parallel worker processes. 0 = auto-detect.",
    "settings.threads_auto":     "Auto",

    # App settings dialog
    "appsettings.title":         "Application Settings",
    "appsettings.appearance":    "Appearance",
    "appsettings.theme":         "Theme:",
    "appsettings.theme_system":  "System",
    "appsettings.theme_light":   "Light",
    "appsettings.theme_dark":    "Dark",
    "appsettings.language":      "Language:",

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

    # Tooltip — status icons
    "tooltip.warning_status": "Conversion finished with warnings — check logs for details.",
}


# ---------------------------------------------------------------------------
# Ukrainian translations
# ---------------------------------------------------------------------------
_UK: dict[str, str] = {
    # Toolbar
    "toolbar.add_files":         "Додати файли",
    "toolbar.add_folder":        "Додати папку",
    "toolbar.remove":            "Видалити",
    "toolbar.remove_all":        "Видалити всі",
    "toolbar.remove_done":       "Видалити готові",
    "toolbar.select_all":        "✓ Всі",
    "toolbar.select_none":       "✗ Жодного",
    "toolbar.settings":          "⚙ Налаштування",
    "toolbar.app_settings":      "🔧",
    "toolbar.logs":              "📋 Журнали",
    "toolbar.n_of_m_selected":   "{checked} з {total} вибрано",

    # Toolbar tooltips
    "tooltip.add_files":         "Додати файли .fb2 або .fb2.zip",
    "tooltip.add_folder":        "Рекурсивно знайти FB2 файли в директорії",
    "tooltip.remove":            "Видалити вибрані елементи зі списку",
    "tooltip.remove_all":        "Очистити весь список файлів",
    "tooltip.remove_done":       "Видалити всі успішно конвертовані файли",
    "tooltip.select_all":        "Вибрати всі файли",
    "tooltip.select_none":       "Зняти вибір з усіх файлів",
    "tooltip.settings":          "Налаштування конвертації",
    "tooltip.app_settings":      "Налаштування програми",
    "tooltip.logs":              "Відкрити директорію журналів",

    # Tree header
    "tree.col_name":   "Статус / Назва файлу",
    "tree.col_author": "Автор",
    "tree.col_title":  "Назва",
    "tree.col_date":   "Дата",
    "tree.col_lang":   "Мова",

    # Bottom bar
    "bar.ready":                 "Готово",
    "bar.scanning":              "Сканування…",
    "bar.ready_n_files":         "Готово — {n} файл(ів) у списку",
    "bar.converting_n":          "Конвертація {n} файл(ів)…",
    "bar.converting_progress":   "Конвертація… {done}/{total}",
    "bar.done":                  "Готово — оброблено {total} файл(ів).",
    "bar.cancelled":             "Скасовано.",
    "bar.logs_folder":           "📂 Папка журналів",
    "bar.last_log":              "📋 Останній журнал",
    "bar.convert":               "Конвертувати",
    "bar.cancel":                "Скасувати",
    "tooltip.logs_folder":       "Відкрити папку журналів у файловому менеджері",
    "tooltip.last_log":          "Переглянути журнал останнього запуску",

    # Dialogs — general
    "dlg.ok":     "OK",
    "dlg.cancel": "Скасувати",
    "dlg.close":  "Закрити",
    "dlg.copy":   "Копіювати все",
    "dlg.yes":    "Так",
    "dlg.no":     "Ні",

    # Settings dialog
    "settings.title":            "Налаштування конвертації",
    "settings.structure":        "Структура документа",
    "settings.toc_depth":        "Глибина змісту (1–6):",
    "settings.toc_depth_tip":    "Максимальний рівень заголовків у змісті.",
    "settings.split_level":      "Рівень розбивки (1–6):",
    "settings.split_level_tip":  "Розбити EPUB на окремі файли на цьому рівні заголовків.",
    "settings.split_size":       "Макс. розмір файлу:",
    "settings.split_size_tip":   "Підвищити рівень розбивки, якщо файли XHTML перевищують цей розмір. 0 = вимкнено.",
    "settings.split_size_unit":  " КБ",
    "settings.split_size_off":   "Вимкнено",
    "settings.processing":       "Обробка",
    "settings.remove_images":    "Видалити невикористані зображення",
    "settings.remove_images_tip":"Видалити зображення, на які немає посилань у тексті.",
    "settings.typography":       "Покращити типографіку",
    "settings.typography_tip":   "Увімкнути постобробку: нерозривні пробіли, span.nobreak тощо.",
    "settings.nbsp_range":       "Діапазон довжини слів для NBSP:",
    "settings.nobr_range":       "Діапазон довжини слів для nobreak:",
    "settings.output":           "Виведення",
    "settings.custom_css":       "Власний CSS:",
    "settings.css_placeholder":  "Використовувати вбудовану таблицю стилів",
    "settings.output_folder":    "Папка виведення:",
    "settings.output_placeholder":"В тій же папці, що й вхідний файл",
    "settings.performance":      "Продуктивність",
    "settings.threads":          "Робочих потоків (0=авто):",
    "settings.threads_tip":      "Кількість паралельних робочих процесів. 0 = автовизначення.",
    "settings.threads_auto":     "Авто",

    # App settings dialog
    "appsettings.title":         "Налаштування програми",
    "appsettings.appearance":    "Зовнішній вигляд",
    "appsettings.theme":         "Тема:",
    "appsettings.theme_system":  "Системна",
    "appsettings.theme_light":   "Світла",
    "appsettings.theme_dark":    "Темна",
    "appsettings.language":      "Мова:",

    # Log viewer
    "logviewer.title_file":      "Журнал — {name}",
    "logviewer.filter_label":    "Фільтр:",
    "logviewer.filter_tip":      "Введіть текст для фільтрації рядків…",
    "logviewer.filter_all":      "Усі",
    "logviewer.filter_warnings": "Попередження",
    "logviewer.filter_errors":   "Помилки",

    # Context menu
    "ctx.open_epub":   "Відкрити EPUB",
    "ctx.open_fb2":    "Відкрити вихідний FB2",
    "ctx.open_folder": "Відкрити папку",
    "ctx.view_log":    "Переглянути журнал",
    "ctx.remove":      "Видалити",

    # MessageBox titles / messages
    "msg.remove_all_title":    "Видалити всі",
    "msg.remove_all_text":     "Видалити всі файли зі списку?",
    "msg.no_files_title":      "Файли не вибрані",
    "msg.no_files_text":       "Будь ласка, позначте хоча б один файл перед конвертацією.",
    "msg.no_logs_title":       "Журнали",
    "msg.no_logs_dir":         "Директорія журналів ще не існує.",
    "msg.no_logs_files":       "Файли журналів не знайдені.",
    "msg.close_title":         "Конвертація виконується",
    "msg.close_text":          "Конвертація ще виконується. Скасувати та вийти?",
    "msg.no_epub_title":       "Файл не знайдено",
    "msg.no_epub_text":        "Вихідний EPUB файл не знайдено:\n{path}",

    # File dialog filters
    "filter.fb2":   "FB2 файли (*.fb2 *.fb2.zip)",
    "filter.css":   "CSS файли (*.css)",
    "filter.all":   "Усі файли (*)",

    # Tooltip — status icons
    "tooltip.warning_status": "Конвертацію завершено з попередженнями — перевірте журнали.",
}

_BUNDLES: dict[str, dict[str, str]] = {
    "en": _EN,
    "uk": _UK,
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def t(key: str, **kwargs) -> str:
    """
    Look up a UI string by key in the current language, falling back to English.
    Supports simple .format() substitutions:  t("bar.ready_n_files", n=5)
    """
    bundle = _BUNDLES.get(_LANG, _EN)
    text   = bundle.get(key) or _EN.get(key, key)
    if kwargs:
        try:
            text = text.format(**kwargs)
        except KeyError:
            pass
    return text


def set_language(lang: str) -> None:
    """Change the active language and notify all registered listeners."""
    global _LANG
    if lang not in _BUNDLES:
        lang = "en"
    _LANG = lang
    for fn in _listeners:
        fn()


def get_language() -> str:
    return _LANG


def register_listener(fn: Callable[[], None]) -> None:
    """Register a zero-arg callable to be called whenever the language changes."""
    if fn not in _listeners:
        _listeners.append(fn)


def unregister_listener(fn: Callable[[], None]) -> None:
    _listeners.discard(fn) if hasattr(_listeners, "discard") else None
    try:
        _listeners.remove(fn)
    except ValueError:
        pass