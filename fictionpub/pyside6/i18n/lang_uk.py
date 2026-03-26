"""Ukrainian (uk) UI strings."""

STRINGS: dict[str, str] = {
    # Toolbar
    "toolbar.add_files":         "Додати файли",
    "toolbar.add_folder":        "Додати папку",
    "toolbar.remove":            "Видалити",
    "toolbar.remove_all":        "Видалити всі",
    "toolbar.remove_done":       "Видалити готові",
    "toolbar.select_toggle":     "{checked} з {total} вибрано",
    "toolbar.settings":          "⚙ Налаштування",
    "toolbar.app_settings":      "🔧",
    "toolbar.logs":              "📋 Журнали",
    "toolbar.about":             "ℹ Про програму",

    # Toolbar tooltips
    "tooltip.add_files":         "Додати файли .fb2 або .fb2.zip",
    "tooltip.add_folder":        "Рекурсивно знайти FB2 файли в директорії",
    "tooltip.remove":            "Видалити вибрані елементи зі списку",
    "tooltip.remove_all":        "Очистити весь список файлів",
    "tooltip.remove_done":       "Видалити всі успішно конвертовані файли",
    "tooltip.select_toggle":     "Клікніть, щоб вибрати всі / зняти вибір",
    "tooltip.settings":          "Налаштування конвертації",
    "tooltip.app_settings":      "Налаштування програми",
    "tooltip.logs":              "Відкрити директорію журналів",
    "tooltip.about":             "Про цю програму",

    # Tree header
    "tree.col_name":   "Назва файлу",
    "tree.col_status": "Статус",
    "tree.col_author": "Автор",
    "tree.col_title":  "Назва",
    "tree.col_date":   "Дата",
    "tree.col_lang":   "Мова",

    # Bottom bar
    "bar.ready":                 "Готово",
    "bar.scanning":              "Сканування…",
    "bar.ready_n_files":         "Готово — {n} файл(ів) у списку",
    "bar.converting_n":          "Конвертація {n} файл(ів)…",
    "bar.converting_progress":   "Конвертація… {done} / {total}",
    "bar.done":                  "Готово — оброблено {total} файл(ів).",
    "bar.cancelled":             "Скасовано.",
    "bar.cancelling":            "Скасування…",
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
    "settings.title":             "Налаштування конвертації",
    "settings.structure":         "Структура документа",
    "settings.toc_depth":         "Глибина змісту (1–6):",
    "settings.toc_depth_tip":     "Максимальний рівень заголовків у змісті.",
    "settings.split_level":       "Рівень розбивки (1–6):",
    "settings.split_level_tip":   "Розбити EPUB на окремі файли на цьому рівні заголовків.",
    "settings.split_size":        "Макс. розмір файлу:",
    "settings.split_size_tip":    "Підвищити рівень розбивки, якщо файли XHTML перевищують цей розмір. 0 = вимкнено.",
    "settings.split_size_unit":   " КБ",
    "settings.split_size_off":    "Вимкнено",
    "settings.processing":        "Обробка",
    "settings.remove_images":     "Видалити невикористані зображення",
    "settings.remove_images_tip": "Видалити зображення, на які немає посилань у тексті.",
    "settings.typography":        "Покращити типографіку",
    "settings.typography_tip":    "Увімкнути постобробку: нерозривні пробіли, span.nobreak тощо.",
    "settings.nbsp_range":        "Діапазон довжини слів для NBSP:",
    "settings.nobr_range":        "Діапазон довжини слів для nobreak:",
    "settings.output":            "Виведення",
    "settings.custom_css":        "Власний CSS:",
    "settings.css_placeholder":   "Використовувати вбудовану таблицю стилів",
    "settings.output_folder":     "Папка виведення:",
    "settings.output_placeholder":"В тій же папці, що й вхідний файл",
    "settings.performance":       "Продуктивність",
    "settings.threads":           "Робочих потоків (0=авто):",
    "settings.threads_tip":       "Кількість паралельних робочих процесів. 0 = автовизначення.",
    "settings.threads_auto":      "Авто",

    # App settings dialog
    "appsettings.title":         "Налаштування програми",
    "appsettings.appearance":    "Зовнішній вигляд",
    "appsettings.theme":         "Тема:",
    "appsettings.theme_system":  "Системна",
    "appsettings.theme_light":   "Світла",
    "appsettings.theme_dark":    "Темна",
    "appsettings.language":      "Мова:",

    # About dialog
    "about.title":       "Про FictionPub",
    "about.description": (
        "FictionPub конвертує електронні книги у форматі FB2 до формату EPUB 3. "
        "Підтримує пакетну обробку, паралельну конвертацію, власні таблиці стилів "
        "та постобробку типографіки."
    ),
    "about.built_with": (
        "<b>Створено за допомогою:</b> Python 3 · PySide6 / Qt 6 · "
        "concurrent.futures (ProcessPoolExecutor)"
    ),

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

    # Status tooltip
    "tooltip.warning_status": "Конвертацію завершено з попередженнями — перевірте журнали.",
}
