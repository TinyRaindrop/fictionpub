from typing import NamedTuple


class FNames:
    """Folder / File names that EpubBuilder uses."""

    META_INF: str = "META-INF"
    OEBPS: str = "OEBPS"
    TEXT: str = "Text"
    IMAGES: str = "Images"
    STYLES: str = "Styles"
    CSS: str = "style.css"
    NCX: str = "toc.ncx"
    OPF: str = "content.opf"
    CONTAINER: str = "container.xml"


class EpubStructureItem(NamedTuple):
    """A structured immutable representation of an EPUB structural component."""

    epub_type: str = ""
    guide_type: str = ""


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
