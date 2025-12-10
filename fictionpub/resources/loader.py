import json
import logging
from pathlib import Path
from importlib import resources as res

from PIL import Image, ImageTk


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


def _load_pil_image(package: str, filename: str) -> Image.Image | None:
    """Load and return a PIL Image from a resource file."""
    path = _resource_path(package, filename)
    if not path or not path.is_file():
        return None
    return Image.open(path)


def load_icon_image(filename: str, size: int) -> ImageTk.PhotoImage:
    """
    Load a Tkinter PhotoImage from packaged resources/icons/*.png
    Scales down large images to specified size in px.
    """
    img = _load_pil_image(ICONS_PACKAGE, filename)
    if img is None:
        log.error(f"Failed to load icon {filename}")
        # Fallback: blank image of required size
        img = Image.new("RGBA", (size, size))
    
    else:
        # Downscale if needed
        max_dimension = max(img.size)
        print(max_dimension)
        if max_dimension > size:
            img = img.resize((size, size), Image.Resampling.LANCZOS)

    # Convert back to Tk-compatible PhotoImage
    return ImageTk.PhotoImage(img)



def get_icon_path(filename: str) -> Path | None:
    """Return filesystem path to an image inside resources/icons."""
    return _resource_path(ICONS_PACKAGE, filename)


def get_css_path(filename="default.css") -> Path | None:
    """Return filesystem path to a CSS file inside resources/css."""
    return _resource_path(CSS_PACKAGE, filename)
