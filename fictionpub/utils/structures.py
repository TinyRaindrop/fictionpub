import logging

from dataclasses import dataclass, fields
from typing import NamedTuple, get_type_hints
from lxml import etree
from PIL import Image
from io import BytesIO

__all__ = ["EPUB_TYPES_MAP", "EpubStructureItem", "FileInfo", "BinaryInfo", "TOCItem", "FNames"]

log = logging.getLogger("fb2_converter")


# Not actually using these enforcer decorators (@enforce_xx_types)
# Only enforces if the annotation is a real type object, like int, str, tuple.
# Skips more complex cases like list[int], Optional[str], Union[int, str], int | None
def enforce_dataclass_types(cls):
    """Decorator that enforces type hints for dataclass fields at runtime."""
    orig_init = cls.__init__

    def __init__(self, *args, **kwargs):
        orig_init(self, *args, **kwargs)
        for f in fields(self):
            val = getattr(self, f.name)
            typ = f.type
            if isinstance(typ, type) and not isinstance(val, typ):
                raise TypeError(
                    f"{cls.__name__}.{f.name} must be {typ.__name__}, got {type(val).__name__}"
                )
    cls.__init__ = __init__
    return cls


def enforce_namedtuple_types(cls):
    """Decorator that enforces type hints for NamedTuple fields at runtime."""
    orig_new = cls.__new__

    def __new__(cls, *args, **kwargs):
        self = orig_new(cls, *args, **kwargs)
        hints = get_type_hints(cls)

        for name, typ in hints.items():
            val = getattr(self, name)
            if isinstance(typ, type) and not isinstance(val, typ):
                raise TypeError(
                    f"{cls.__name__}.{name} must be {typ.__name__}, got {type(val).__name__}"
                )
        return self

    cls.__new__ = __new__
    return cls


class EpubStructureItem(NamedTuple):
    """A structured immutable representation of an EPUB structural component."""
    epub_type: str = ''
    guide_type: str = ''


_RAW_EPUB_TYPES = {
    # key: (epub_type, guide_type)
    "cover": ("cover", "cover"),
    "titlepage": ("titlepage", "titlepage"),
    "copyright": ("copyright-page", "copyright-page"),
    "annotation": ("frontmatter", "other.frontmatter"),
    "maintext": ("bodymatter", "text"),
    "nav": ("toc", "toc"),
    "notes": ("footnotes", "other.footnotes"),
    "comments": ("endnotes", "other.footnotes"),
}

# Generate a dictionary of {key: (epub_type, guide_type)}
EPUB_TYPES_MAP: dict[str, EpubStructureItem] = {
    key: EpubStructureItem(epub_type=epub, guide_type=guide)
    for key, (epub, guide) in _RAW_EPUB_TYPES.items()
}


@dataclass
class FileInfo():
    """A container for xhtml file metadata and content."""
    id: str
    title: str
    html: etree._Element
    prop: str = ''
    order: int | None = None

    def __post_init__(self):
        self.filename = self.id + ".xhtml"


@dataclass
class BinaryInfo():
    """Container for binary file content, metadata, and manipulation methods."""
    filename: str
    type: str
    data: bytes
    prop: str = ''   # e.g. "cover-image"

    _wh: tuple[int, int] | None = None  # width, height
    orientation: str = ''      # "v" (vertical) or "h" (horizontal)
    
    @property
    def dimensions(self) -> tuple[int, int] | None:
        """Returns image dimensions using Pillow."""  
        if self._wh is None:
            try:
                with Image.open(BytesIO(self.data)) as img:
                    self._wh = img.size
                    self._update_orientation()
            except Exception as e:
                log.error(f"Error reading image '{self.filename}': {e}")
                return None
        return self._wh

    # TODO: remove setter    
    @dimensions.setter
    def dimensions(self, value: tuple[int, int]):
        """Allow manual override of cached dimensions."""
        # Validate input before setting
        if not (isinstance(value, tuple) and len(value) == 2 and
                all(isinstance(dim, int) and dim > 0 for dim in value)):
            raise ValueError("Dimensions must be a tuple of two positive integers (width, height).")
        self._wh = value
    
    def _update_orientation(self):
        """Internal helper to set 'orientation' based on current dimensions."""
        if self._wh is not None:
            w, h = self._wh
            if w == h:
                self.orientation = "square"
            elif w > h:
                self.orientation = "wide"
            else:
                self.orientation = "tall"

    def resize(self, max_width: int, max_height: int):
        """
        Resize image to fit within given max dimensions while preserving aspect ratio.
        Updates all relevant information (dimensions, orientation).
        """
        try:
            with Image.open(BytesIO(self.data)) as img:
                img.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)
                with BytesIO() as output:
                    # TODO: implement image optimization as a separate method, with pngquant for greyscale images
                    img.save(output, format=img.format or "PNG")
                    # TODO: only save if output size < original, 5% margin
                    self.data = output.getvalue()
                self._wh = img.size
                self._update_orientation()
        except Exception as e:
            log.warning(f"Failed to resize '{self.filename}': {e}")


class TOCItem(NamedTuple):
    """A container for Table of Contents items."""
    level: int
    text: str
    href_nav: str
    href_ncx: str


class FNames:
    """Folder / File names that EpubBuilder uses."""
    META_INF: str = 'META-INF'
    OEBPS: str = 'OEBPS'
    TEXT: str = 'Text'
    IMAGES: str = 'Images'
    STYLES: str = 'Styles'
    CSS: str = 'style.css'
    NCX: str = 'toc.ncx'
    OPF: str = 'content.opf'
    CONTAINER: str = 'container.xml'
