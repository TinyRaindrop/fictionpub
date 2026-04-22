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


class FileRole(NamedTuple):
    """Represents semantic roles of an EPUB structural component."""

    epub_type: str
    guide_type: str


EPUB_TYPES = {
    "cover": FileRole("cover", "cover"),
    "titlepage": FileRole("titlepage", "title-page"),
    "copyright": FileRole("copyright-page", "copyright-page"),
    "annotation": FileRole("frontmatter", "other.frontmatter"),
    "part_1": FileRole("bodymatter", "text"),
    "nav": FileRole("toc", "toc"),
    "notes": FileRole("footnotes", "notes"),
    "comments": FileRole("endnotes", "other.footnotes"),
}
