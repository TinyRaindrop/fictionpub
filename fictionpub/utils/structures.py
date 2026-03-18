from enum import Enum, auto
import logging

from dataclasses import dataclass, field
from typing import NamedTuple
from PIL import Image
from io import BytesIO

from lxml import etree


log = logging.getLogger("fb2_converter")


class BodyType(Enum):
    """Defines types of bodies used in FB2 document."""
    MAIN = auto()
    NOTE = auto()
    COMMENT = auto()


class LinkType(Enum):
    """Defines classification categories for links."""
    NOTE = auto()
    COMMENT = auto()
    REGULAR = auto()
    EXTERNAL = auto()
    INVALID = auto()


class FB2Body(NamedTuple):
    body: etree._Element
    body_type: BodyType


class ConvertedBody(NamedTuple):
    """Container for a single converted XHTML body, its title, attributes, and ID."""
    file_id: str
    title: str
    body: etree._Element
    body_type: BodyType


class EpubStructureItem(NamedTuple):
    """A structured immutable representation of an EPUB structural component."""
    epub_type: str = ''
    guide_type: str = ''


_RAW_EPUB_TYPES = {
    # key: (epub_type, guide_type)
    "cover": ("cover", "cover"),
    "titlepage": ("titlepage", "title-page"),
    "copyright": ("copyright-page", "copyright-page"),
    "annotation": ("frontmatter", "other.frontmatter"),
    "part_1": ("bodymatter", "text"),
    "nav": ("toc", "toc"),
    "notes": ("footnotes", "notes"),
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

# ---------------------------------------------------------------------------
# Metadata dataclasses
# ---------------------------------------------------------------------------

@dataclass
class QuickMetadata:
    """Metadata excerpt with only a few most important fields. Parsed without a full tree load."""
    author: str = ''
    title: str = ''
    date: str = ''
    lang: str = ''


@dataclass
class TitleInfo:
    """Metadata block from FB2 `<title-info>`."""
    title:           str             = 'Untitled'
    authors:         list            = field(default_factory=list)  # list[str]
    translators:     list            = field(default_factory=list)  # list[str]
    lang:            str             = ''
    genres:          list            = field(default_factory=list)  # list[str]
    keywords:        str             = ''
    date:            str             = ''
    sequence:        str             = ''
    sequence_number: int | None      = None
    annotation_el:   'etree._Element | None' = field(default=None, repr=False)

    @property
    def author(self) -> str:
        """First author name, or empty string."""
        return self.authors[0] if self.authors else ''


@dataclass
class SourceInfo:
    """Metadata block from FB2 `<src-title-info>`."""
    title:    str = ''
    author:   str = ''
    src_lang: str = ''
    date:     str = ''
    # Ignoring <src-title-info> genres. They are usually set accidentally and are wrong.


@dataclass
class PublishInfo:
    """Metadata block from FB2 `<publish-info>`."""
    book_name:  str = ''
    publisher:  str = ''
    city:       str = ''
    year:       str = ''
    isbn:       str = ''


@dataclass
class DocumentInfo:
    """Metadata block from FB2 `<document-info>`."""
    program_used: str = ''
    date:         str = ''
    doc_id:       str = ''
    version:      str = ''
    author:       str = ''
    src_ocr:      str = ''


@dataclass
class CustomInfo:
    """A single `<custom-info>` entry from the FB2 description."""
    info_type: str = ''
    text:      str = ''


@dataclass
class BookMetadata:
    """
    Pure FB2 extraction result. Contains no EPUB-specific fields.

    EPUB-layer values (epub id, app info, localized genres, description text)
    are supplied separately at the point of use (EpubBuilder / OPF writer).
    """
    # nested info blocks (always present, defaulting to empty)
    title_info: TitleInfo = field(default_factory=TitleInfo)
    src: SourceInfo      = field(default_factory=SourceInfo)
    doc: DocumentInfo    = field(default_factory=DocumentInfo)
    pub: PublishInfo     = field(default_factory=PublishInfo)

    # other assets
    custom_info: list[CustomInfo] = field(default_factory=list)
    cover_id: str | None = None

    # Convenience properties for most widely accessed fields.
    # These are delegating to title_info.
    @property
    def title(self) -> str:        return self.title_info.title
    @property
    def author(self) -> str:       return self.title_info.author or 'Unknown Author'
    @property
    def authors(self) -> list:     return self.title_info.authors
    @property
    def lang(self) -> str:         return self.title_info.lang
    @property
    def genres(self) -> list:      return self.title_info.genres
    @property
    def annotation_el(self) -> 'etree._Element | None': return self.title_info.annotation_el
    @annotation_el.setter
    def annotation_el(self, e: 'etree._Element | None'): self.title_info.annotation_el = e


@dataclass
class EpubMetadata:
    book_meta:   BookMetadata
    epub_id:     str    # mandatory
    app_name:    str = ''
    app_version: str = ''
    app_url:     str = ''
    lang_genres: list[str] = field(default_factory=list)
    description: str | None = None
   