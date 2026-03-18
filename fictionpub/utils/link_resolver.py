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
from .structures import LinkType, BodyType, FileInfo
from . import xml_utils as xu


log = logging.getLogger("fb2_converter")


"""
 
Note section criteria:
    1. Note
        * body name="notes"
        * section has id
        * is being targeted by <a link-type="note">
    
    2. Comment
        * body name="comments"
        * section has id

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
            self._current_doc_id = doc.id
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


    def _determine_link_type(self, a: etree._Element) -> LinkType:
        """
        Link classification criteria:
        1. NOTE: Note reference (anchor)
            * has link-type="note"
            * target BodyType is NOTE

        2. COMMENT: Comment reference (anchor)
            * target BodyType is COMMENT
            * target body is not current body
            * not a backlink

        3. REGULAR: Regular internal link (Toc, index, cross-reference)
            * starts with #
            * target id exists
        
        4. EXTERNAL: External link (http, etc)
            * doesn't start with #
        """
        # FB2 schema specifies that "Footnotes should be implemented by links referring
        # to additional bodies in the same document", but we can't trust that all files obey this.
        href = a.get('href', '')
        if not href.startswith('#'):
            return LinkType.EXTERNAL
        
        data_link_type = a.attrib.pop('data-link-type', '').lower()
        if data_link_type == 'note':
            return LinkType.NOTE
        elif data_link_type:
            log.debug(f"Noteref id='{a.get('id')}': unexpected link-type '{data_link_type}'")
        
        target_id  = href.lstrip('#')
        target_doc = self._find_target_doc(target_id)
        
        if target_doc is None:
            return LinkType.INVALID

        if (target_doc.body_type == BodyType.COMMENT and
            target_doc.id != self._current_doc_id and
            'backlink' not in a.get('class', '')):
            return LinkType.COMMENT
        
        return LinkType.REGULAR     


    def _resolve_link(self, a: etree._Element) -> None:
        ltype = self._determine_link_type(a)
        match ltype:
            case LinkType.NOTE:
                self._apply_noteref(a)
                pass

            case LinkType.COMMENT:
                self._apply_noteref(a)
                xu.add_class(a, 'comment')
                pass

            case LinkType.REGULAR:
                pass

            case LinkType.EXTERNAL:
                pass

            case LinkType.INVALID:
                pass

        href = a.get('href', '')

        if not href.startswith('#'):
            return  # external link, leave untouched

        # Consume the temporary attribute
        link_type = a.get('data-link-type')
        xu.remove_attr(a, 'data-link-type')

        target_id  = href.lstrip('#')
        target_doc = self._find_target_doc(target_id)

        if target_doc is None:
            # TODO: and if target_id doesn't exist (to prevent epubcheck errors)
            self._mark_broken(a)
            return

        a.set('href', f'{target_doc.filename}#{target_id}')

        if target_doc.is_note:
            self._apply_noteref(a)
        elif a.get('class') == 'backlink':
            pass  # backlinks resolved above via href update; no extra attrs needed


    def _find_target_doc(self, target_id: str) -> FileInfo | None:
        doc_id = self._id_to_doc.get(target_id)
        if doc_id is None:
            return None
        return self._doc_map.get(doc_id)


    def _apply_noteref(self, a: etree._Element, additional_class: str = '') -> None:
        a_class = ' '.join(['noteref', additional_class]).strip()
        a.attrib.update({
            'class': a_class,
            f'{{{NS.EPUB}}}type': 'noteref',
            # 'role': 'doc-noteref' ?
        })           


    def _mark_broken(self, a: etree._Element) -> None:
        target_id = a.get('href', '').lstrip('#')
        log.warning(f"Broken internal link: target id='{target_id}' not found in any document.")
        current_class = a.get('class', '')
        a.set('class', f"{current_class} broken-link".strip())
        # Remove href from broken backlinks
        if 'backlink' in current_class:
            xu.remove_attr(a, 'href')
            a.set('data-target', target_id)
