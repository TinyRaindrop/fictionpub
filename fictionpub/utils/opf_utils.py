"""
Utilities for constructing the OPF metadata section.

"""
from datetime import datetime, timezone
from lxml import etree

from .namespaces import Namespaces as NS
from ..models.metadata import BookMetadata, EpubMetadata


def _add_dc(parent: etree._Element, tag: str, text: str | None,
            element_id: str = '') -> etree._Element | None:
    """Creates a Dublin Core element. Returns None if tag or text is empty."""
    if not tag or text in (None, ''):
        return None
    el = etree.SubElement(parent, f"{{{NS.DC}}}{tag}")
    el.text = str(text)
    if element_id:
        el.set("id", element_id)
    return el


def _add_meta(parent: etree._Element, prop: str, value: str | int | None,
              id: str = '', refines: str = '', scheme: str = '') -> etree._Element | None:

    """
    Creates a <meta> element. Returns None if prop or value is empty.
    
    Optional args:
        - id: ID for the <meta> element.
        - refines: ID of the element this <meta> refines.
        - scheme: scheme for the <meta> element.
    """
    if not prop or value in (None, ''):
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


def fill_opf_metadata(
    meta_element: etree._Element,
    # metadata: BookMetadata,
    epub_meta: EpubMetadata,
) -> None:
    """
    Fills the OPF <metadata> element with information from
	FB2's BookMetadata and newly created EpubMetadata.
    """
    m: etree._Element= meta_element    # local alias
    metadata: BookMetadata = epub_meta.book_meta    # TODO: remove from EpubMetadata or keep?

    # Identifier
    _add_dc(m, "identifier", epub_meta.epub_id, element_id="BookId")

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
        _add_meta(m, "belongs-to-collection", metadata.title_info.sequence, id="collection")
        _add_meta(m, "group-position", metadata.title_info.sequence_number, refines="collection")

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
        _add_meta(m, "dcterms:event", "publication", refines="pub-date", scheme="marc:relators")

    if pub.isbn:
        _add_dc(m, "identifier", f"urn:isbn:{pub.isbn}")

    # Document-info
    if metadata.doc:
        _add_meta(m, "ocr", metadata.doc.src_ocr)

    # Subjects / genres (already localized)
    for genre in epub_meta.lang_genres:
        _add_dc(m, "subject", genre)
    
    # Cover image id
    if metadata.cover_id:
        _add_meta_custom(m, name="cover", content=metadata.cover_id)

    # Description
    _add_dc(m, "description", epub_meta.description)

    # Generator
    if epub_meta.app_name:
        gen_name = f"{epub_meta.app_name} {epub_meta.app_version}".strip()
        _add_meta_custom(m, name="generator", content=gen_name)

    # Modification timestamp
    modified = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    _add_meta(m, prop="dcterms:modified", value=modified)
