"""
Utilities for constructing the OPF metadata section.
"""

import logging
from datetime import UTC, datetime

from lxml import etree

from ..models import namespaces as NS
from ..models.metadata import BookMetadata, EpubMetadata
from ..models.structures import BinaryInfo, FileInfo
from .constants import EPUB_TYPES_MAP
from .constants import FNames as FN

log = logging.getLogger("fb2_converter")


class OpfBuilder:
    """A builder for constructing the OPF file of an EPUB."""

    def __init__(
        self,
        epub_meta: EpubMetadata,
        doc_list: list[FileInfo],
        binaries: dict[str, BinaryInfo],
    ):
        self.epub_meta = epub_meta
        self.doc_list = doc_list
        self.binaries = binaries

    def build(self) -> etree._Element:
        """Constructs the OPF XML tree based on the provided metadata, documents, and binaries."""
        root = etree.Element("package", version="3.0", nsmap=NS.OPF_MAP)
        root.set("unique-identifier", "BookId")
        self._fill_metadata(root)
        self._fill_manifest_and_spine(root)
        return root

    def _fill_metadata(self, root: etree._Element) -> None:
        """Fills the OPF `<metadata>` section."""
        m = etree.SubElement(root, "metadata")
        metadata: BookMetadata = self.epub_meta.book_meta

        # Identifier
        _add_dc(m, "identifier", self.epub_meta.epub_id, element_id="BookId")

        # Title
        if metadata.title:
            _add_dc(m, "title", metadata.title, element_id="main-title")
            _add_meta(m, "title-type", "main", refines="main-title")

        # Creator: author
        if metadata.author:
            _add_dc(m, "creator", metadata.author, element_id="author")
            _add_meta(m, "role", "aut", refines="author", scheme="marc:relators")

        # Creator: translators
        for i, transl in enumerate(metadata.title_info.translators):
            transl_id = f"translator{i}"
            _add_dc(m, "creator", transl, element_id=transl_id)
            _add_meta(m, "role", "trl", refines=transl_id, scheme="marc:relators")

        # Series
        if metadata.title_info.sequence:
            # TODO: there could be multiple sequences
            _add_meta(
                m,
                "belongs-to-collection",
                metadata.title_info.sequence,
                id="collection",
            )
            _add_meta(
                m,
                "group-position",
                metadata.title_info.sequence_number,
                refines="collection",
            )

        # Language
        _add_dc(m, "language", metadata.lang)

        # Source-Title info
        _add_meta_custom(m, name="original-title", content=metadata.src.title)
        # TODO: duplicates title-info > src-lang. Pick one
        _add_meta(m, "source-language", metadata.src.src_lang)

        # original publication date # TODO: confirm syntax!
        created_date = metadata.src.date
        _add_meta(m, "dcterms:created", created_date)

        # Publish-info
        pub = metadata.pub
        _add_dc(m, "publisher", pub.publisher)
        if pub.year:
            _add_dc(m, "date", pub.year, element_id="pub-date")
            _add_meta(
                m,
                "dcterms:event",
                "publication",
                refines="pub-date",
                scheme="marc:relators",
            )

        if pub.isbn:
            _add_dc(m, "identifier", f"urn:isbn:{pub.isbn}")

        # Document-info
        if metadata.doc:
            _add_meta(m, "ocr", metadata.doc.src_ocr)

        # Subjects / genres (already localized)
        for genre in self.epub_meta.lang_genres:
            _add_dc(m, "subject", genre)

        # Cover image id
        if metadata.cover_id:
            _add_meta_custom(m, name="cover", content=metadata.cover_id)

        # Description
        _add_dc(m, "description", self.epub_meta.description)

        # Generator
        if self.epub_meta.app_name:
            gen_name = f"{self.epub_meta.app_name} {self.epub_meta.app_version}".strip()
            _add_meta_custom(m, name="generator", content=gen_name)

        # Modification timestamp
        modified = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        _add_meta(m, prop="dcterms:modified", value=modified)

    def _fill_manifest_and_spine(self, root: etree._Element) -> None:
        """
        Fills the OPF `<manifest>`, `<spine>`, and `<guide>` sections
        based on the provided documents and binaries.
        """
        # Manifest, Spine, Guide
        manifest = etree.SubElement(root, "manifest")
        spine = etree.SubElement(root, "spine", toc="ncx")
        guide = etree.SubElement(root, "guide")  # for compatibility with EPUB2 readers

        # 1. Add NCX and CSS to the Manifest
        etree.SubElement(
            manifest,
            "item",
            id="ncx",
            href="toc.ncx",
            attrib={"media-type": "application/x-dtbncx+xml"},
        )
        etree.SubElement(
            manifest,
            "item",
            id="css",
            href="Styles/style.css",
            attrib={"media-type": "text/css"},
        )

        # 2. Add all documents from doc_map to Manifest, Spine, Guide
        for doc in self.doc_list:
            if doc is None:
                log.warning("[OPF] an xhtml file is missing. Skipping.")
                continue

            # 2.1. Manifest
            href = f"{FN.TEXT}/{doc.filename}"
            item = etree.SubElement(
                manifest,
                "item",
                id=doc.id,
                href=href,
                attrib={"media-type": "application/xhtml+xml"},
            )
            if doc.prop:
                item.set("properties", doc.prop)

            # 2.2. Spine
            if doc.is_note or doc.id == "nav":  # ? make 'cover' non-linear as well ?
                # Footnote bodies are non-linear
                spine.append(etree.Element("itemref", idref=doc.id, linear="no"))
            else:
                spine.append(etree.Element("itemref", idref=doc.id))

            # 2.3. Guide
            if doc.id in EPUB_TYPES_MAP:
                guide_type = EPUB_TYPES_MAP[doc.id].guide_type
                etree.SubElement(
                    guide, "reference", type=guide_type, title=doc.title, href=href
                )

        # 3. Add images to Manifest
        for img in self.binaries.values():
            href = f"{FN.IMAGES}/{img.filename}"
            # using img.filename as ID
            item = etree.SubElement(
                manifest,
                "item",
                id=img.filename,
                href=href,
                attrib={"media-type": img.media_type},
            )
            if img.prop:
                item.set("properties", img.prop)


# -----------------------
# XML helpers


def _add_dc(
    parent: etree._Element, tag: str, text: str | None, element_id: str = ""
) -> etree._Element | None:
    """Creates a Dublin Core element. Returns None if tag or text is empty."""
    if not tag or text in (None, ""):
        return None
    el = etree.SubElement(parent, f"{{{NS.DC}}}{tag}")
    el.text = str(text)
    if element_id:
        el.set("id", element_id)
    return el


def _add_meta(
    parent: etree._Element,
    prop: str,
    value: str | int | None,
    id: str = "",
    refines: str = "",
    scheme: str = "",
) -> etree._Element | None:
    """
    Creates a <meta> element. Returns None if prop or value is empty.

    Optional args:
        - id: ID for the <meta> element.
        - refines: ID of the element this <meta> refines.
        - scheme: scheme for the <meta> element.
    """
    if not prop or value in (None, ""):
        return None

    attrs: dict[str, str] = {"property": prop}
    if id:
        attrs["id"] = id
    if refines:
        attrs["refines"] = f"#{refines}"
    if scheme:
        attrs["scheme"] = scheme

    el = etree.SubElement(parent, "meta", attrib=attrs)
    el.text = str(value)
    return el


def _add_meta_custom(parent: etree._Element, **attrs: str) -> etree._Element:
    """Creates a <meta> element with arbitrary attributes (key=value pairs)."""
    return etree.SubElement(parent, "meta", attrib=attrs)
