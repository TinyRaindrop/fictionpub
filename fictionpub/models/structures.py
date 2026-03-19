import logging
from dataclasses import dataclass
from enum import Enum, auto
from io import BytesIO
from typing import NamedTuple

from lxml import etree
from PIL import Image


log = logging.getLogger("fb2_converter")


class BodyType(Enum):
    """Defines types of bodies used in FB2 document."""
    MAIN = auto()
    NOTE = auto()
    COMMENT = auto()


class FB2Body(NamedTuple):
    body: etree._Element
    body_type: BodyType


class ConvertedBody(NamedTuple):
    """Container for a single converted XHTML body, its title, attributes, and ID."""
    file_id: str
    title: str
    body: etree._Element
    body_type: BodyType

    
@dataclass(order=False)
class FileInfo():
    """A container for xhtml file metadata and content."""
    id: str
    title: str
    html: etree._Element
    prop: str = ''
    body_type: BodyType = BodyType.MAIN
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
    media_type: str
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
