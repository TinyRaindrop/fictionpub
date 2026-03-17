"""
Resolves all internal links in a finalised list of EPUB documents.

Functions:
  - Build a complete element-id → document map from the finished doc list.
  - Resolve noteref hrefs and apply noteref attributes (class, epub:type).
  - Resolve backlink hrefs.
  - Mark broken links.

This module has no dependency on EpubBuilder.
It receives the doc list after it's fully assembled and sorted.
"""
import logging

from lxml import etree

from .namespaces import Namespaces as NS
from .structures import FileInfo
from . import xml_utils as xu


log = logging.getLogger("fb2_converter")


"""
Link classification criteria:
    1. Note reference (anchor)
        * has link-type="note"
        * target BodyType is NOTE

    2. Comment reference (anchor)
        * target BodyType is COMMENT

    2. Regular link (Toc, index, cross-reference)
        * starts with #
        * target id exists
    
    3. External link (http, etc)
        * doesn't start with #
"""

class LinkResolver:
    """
    Resolves all internal links across a finalised EPUB document list.

    Usage:
        LinkResolver(doc_list).resolve()
    """

    def __init__(self, doc_list: list[FileInfo]):
        self._doc_map: dict[str, FileInfo] = {doc.id: doc for doc in doc_list}
        self._id_to_doc: dict[str, str] = self._build_id_map(doc_list)


    def resolve(self) -> None:
        """Single entry point. Resolves all links in all documents."""
        for doc in self._doc_map.values():
            if doc.html is None:
                continue
            for a in doc.html.iterfind('.//a[@href]'):
                self._resolve_link(a)


    def _build_id_map(self, doc_list: list[FileInfo]) -> dict[str, str]:
        """Maps every element id found in all documents to its doc id."""
        id_map: dict[str, str] = {}
        for doc in doc_list:
            if doc.html is None:
                continue
            for el in doc.html.iterfind('.//*[@id]'):
                el_id = el.get('id')
                if el_id:
                    id_map[el_id] = doc.id
        return id_map


    def _resolve_link(self, a: etree._Element) -> None:
        href = a.get('href', '')

        if not href.startswith('#'):
            return  # external link, leave untouched

        # Consume the temporary attribute
        link_type = a.get('data-link-type')
        xu.remove_attr(a, 'data-link-type')

        target_id  = href.lstrip('#')
        target_doc = self._find_target_doc(target_id)

        if target_doc is None:
            self._mark_broken(a)
            return

        a.set('href', f'{target_doc.filename}#{target_id}')

        if target_doc.is_note:
            self._apply_noteref(a, link_type)
        elif a.get('class') == 'backlink':
            pass  # backlinks resolved above via href update; no extra attrs needed


    def _find_target_doc(self, target_id: str) -> FileInfo | None:
        doc_id = self._id_to_doc.get(target_id)
        if doc_id is None:
            return None
        return self._doc_map.get(doc_id)


    def _apply_noteref(self, a: etree._Element, link_type: str | None) -> None:
        a.attrib.update({
            'class': 'noteref',
            f'{{{NS.EPUB}}}type': 'noteref',
        })
        
        if link_type != 'note':
            # No type: treat as comment reference
            xu.add_class(a, 'comment')
            if link_type:
                log.debug(f"Noteref id='{a.get('id')}': unexpected link-type '{link_type}'")


    def _mark_broken(self, a: etree._Element) -> None:
        target_id = a.get('href', '').lstrip('#')
        log.warning(f"Broken internal link: target id='{target_id}' not found in any document.")
        current_class = a.get('class', '')
        a.set('class', f"{current_class} broken-link".strip())
        # Remove href from broken backlinks
        if 'backlink' in current_class:
            xu.remove_attr(a, 'href')
            a.set('data-target', target_id)
