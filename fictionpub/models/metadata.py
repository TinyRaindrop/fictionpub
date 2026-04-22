from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import NamedTuple

from lxml import etree


@dataclass
class QuickMetadata:
    """Metadata excerpt with only a few most important fields. Parsed without a full tree load."""

    author: str = ""
    title: str = ""
    date: str = ""
    lang: str = ""


@dataclass
class TitleInfo:
    """Metadata block from FB2 `<title-info>`."""

    title: str = "Untitled"
    authors: list[str] = field(default_factory=list)
    translators: list[str] = field(default_factory=list)
    lang: str = ""
    genres: list[str] = field(default_factory=list)
    keywords: str = ""
    date: str = ""
    sequence: str = ""
    sequence_number: int | None = None
    annotation_el: etree._Element | None = field(default=None, repr=False)

    @property
    def author(self) -> str:
        """First author name, or empty string."""
        return self.authors[0] if self.authors else ""

    def todict(self):
        """For debugging purposes."""
        return {
            "title": self.title,
            "authors": self.authors,
            "translators": self.translators,
            "lang": self.lang,
            "genres": self.genres,
            "keywords": self.keywords,
            "date": self.date,
            "sequence": self.sequence,
            "sequence_number": self.sequence_number,
        }


class SourceInfo(NamedTuple):
    """Metadata block from FB2 `<src-title-info>`."""

    title: str = ""
    author: str = ""
    src_lang: str = ""
    date: str = ""
    # Ignoring <src-title-info> genres. They are usually set accidentally and are wrong.


class PublishInfo(NamedTuple):
    """Metadata block from FB2 `<publish-info>`."""

    book_name: str = ""
    publisher: str = ""
    city: str = ""
    year: str = ""
    isbn: str = ""


class DocumentInfo(NamedTuple):
    """Metadata block from FB2 `<document-info>`."""

    program_used: str = ""
    date: str = ""
    doc_id: str = ""
    version: str = ""
    author: str = ""
    src_ocr: str = ""


class CustomInfo(NamedTuple):
    """A single `<custom-info>` entry from the FB2 description."""

    info_type: str = ""
    text: str = ""


@dataclass
class BookMetadata:
    """
    Pure FB2 extraction result. Contains no EPUB-specific fields.

    EPUB-layer values (epub id, app info, localized genres, description text)
    are supplied separately at the point of use (EpubBuilder / OPF writer).
    """

    # nested info blocks (always present, defaulting to empty)
    title_info: TitleInfo = field(default_factory=TitleInfo)
    src: SourceInfo = field(default_factory=SourceInfo)
    doc: DocumentInfo = field(default_factory=DocumentInfo)
    pub: PublishInfo = field(default_factory=PublishInfo)

    # other assets
    custom_info: list[CustomInfo] = field(default_factory=list)
    cover_id: str | None = None

    # Convenience properties for most widely accessed fields.
    # These are delegating to title_info.
    @property
    def title(self) -> str:
        return self.title_info.title

    @property
    def author(self) -> str:
        return self.title_info.author or "Unknown Author"

    @property
    def authors(self) -> list:
        return self.title_info.authors

    @property
    def lang(self) -> str:
        return self.title_info.lang

    @property
    def genres(self) -> list:
        return self.title_info.genres

    @property
    def annotation_el(self) -> "etree._Element | None":
        return self.title_info.annotation_el

    @annotation_el.setter
    def annotation_el(self, e: "etree._Element | None"):
        self.title_info.annotation_el = e


@dataclass
class EpubMetadata:
    book_meta: BookMetadata
    epub_id: str  # mandatory
    app_name: str = ""
    app_version: str = ""
    app_url: str = ""
    lang_genres: list[str] = field(default_factory=list)
    description: str | None = None
    # Generate a fresh timestamp when the object is instantiated
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def date_opf(self) -> str:
        """Returns the strict ISO 8601 format needed for the OPF."""
        return self.timestamp.strftime("%Y-%m-%dT%H:%M:%SZ")

    @property
    def date_plain(self) -> str:
        """Returns a human-readable format for the xhtml page."""
        return self.timestamp.strftime("%Y-%m-%d %H:%M")
