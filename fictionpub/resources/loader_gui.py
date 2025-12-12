import logging
from pathlib import Path

from PIL import Image, ImageTk

from .loader import _resource_path


log = logging.getLogger("fb2_converter")

# TODO: refactor resource loader, separate gui-related resources into its own module

ICONS_PACKAGE = "fictionpub.resources.icons"


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
        if max_dimension > size:
            img = img.resize((size, size), Image.Resampling.LANCZOS)

    # Convert back to Tk-compatible PhotoImage
    return ImageTk.PhotoImage(img)


def get_icon_path(filename: str) -> Path | None:
    """Return filesystem path to an image inside resources/icons."""
    return _resource_path(ICONS_PACKAGE, filename)
