import logging

from dataclasses import dataclass, fields
from typing import NamedTuple, get_type_hints
from PIL import Image
from io import BytesIO

from lxml import etree

__all__ = [
    "ConvertedBody", "EpubStructureItem", "EPUB_TYPES_MAP", 
    "FileInfo", "BinaryInfo", "TOCItem", "FNames"
]

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


class ConvertedBody(NamedTuple):
    """Container for a single converted XHTML body, its title, attributes, and ID."""
    file_id: str
    title: str
    body: etree._Element


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


@dataclass(order=False)
class FileInfo():
    """A container for xhtml file metadata and content."""
    id: str
    title: str
    html: etree._Element
    prop: str = ''
    is_note: bool = False
    order: int | None = None
    """Sorting order is [positive, None, negative reversed]: 0, 1, 2, None, -2, -1"""

    def __post_init__(self):
        self.filename = self.id + ".xhtml"

    def __lt__(self, other):
        return self._sort_key() < other._sort_key()

    def _sort_key(self):
        # Tuples are compared by first element, then second
        if self.is_note:
            return (3, 0)                 # Group 3: notes/comments at the very end
        if self.order is None:
            return (1, 0)                 # Group 1: None values in the middle
        elif self.order < 0:
            return (2, -self.order)       # Group 2: Negative values, sorted descending
        else:
            return (0, self.order)        # Group 0: Positive values, sorted ascending

@dataclass
class BinaryInfo():
    """Container for binary file content, metadata, and manipulation methods."""
    filename: str
    type: str
    data: bytes
    prop: str = ''   # e.g. "cover-image"
    orientation: str = ''      # "v" (vertical) or "h" (horizontal)
    _wh: tuple[int, int] | None = None  # width, height
    
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
