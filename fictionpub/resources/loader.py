import json
import logging
from pathlib import Path
from importlib import resources as res
import tkinter as tk


log = logging.getLogger("fb2_converter")


ICONS_PACKAGE = "fictionpub.resources.icons"
TERMS_PACKAGE = "fictionpub.resources.terms"
CSS_PACKAGE = "fictionpub.resources.css"


def _resource_path(package: str, filename: str) -> Path | None:
    """Return a real filesystem path for a resource using importlib.resources."""
    try:
        resource = res.files(package).joinpath(filename)
        with res.as_file(resource) as path:
            return path
    except Exception as e:
        log.error(f"Resource not found: {package}/{filename}: {e}")
        return None


def load_text(package: str, filename: str) -> str | None:
    """Return file content as text."""
    path = _resource_path(package, filename)
    if not path or not path.is_file():
        return None
    return path.read_text(encoding="utf-8")


def load_json(package: str, filename: str) -> dict:
    """Load JSON from resources folder."""
    path = _resource_path(package, filename)
    if not path or not path.is_file():
        log.error(f"JSON not found: {package}/{filename}")
        return {}

    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        log.error(f"Failed to load JSON {filename}: {e}")
        return {}


def load_terms_json(filename: str):
    return load_json(TERMS_PACKAGE, filename)


def load_binary(package: str, filename: str) -> bytes | None:
    """Return bytes from resource file."""
    path = _resource_path(package, filename)
    if not path or not path.is_file():
        return None
    return path.read_bytes()


def load_icon_image(filename: str) -> tk.PhotoImage:
    """
    Load a Tkinter PhotoImage from packaged resources/icons/*.png
    Scales down large images automatically.
    """
    data = load_binary(ICONS_PACKAGE, filename)
    if data is None:
        log.error(f"Failed to load icon {filename}")
        return tk.PhotoImage(width=16, height=16)

    img = tk.PhotoImage(data=data)
    if img.width() > 24:
        scale = img.width() // 16
        if scale > 1:
            img = img.subsample(scale)

    return img


def get_icon_path(filename: str) -> Path | None:
    """Return filesystem path to an image inside resources/icons."""
    return _resource_path(ICONS_PACKAGE, filename)


def get_css_path(filename="default.css") -> Path | None:
    """Return filesystem path to a CSS file inside resources/css."""
    return _resource_path(CSS_PACKAGE, filename)
