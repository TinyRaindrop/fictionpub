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
from enum import Enum, auto
from typing import NamedTuple

from lxml import etree

from ..models import namespaces as NS
from ..models.structures import BodyType, FileInfo
from ..utils import xml_utils as xu


class LinkType(Enum):
    """Defines classification categories for links."""
    NOTE = auto()
    COMMENT = auto()
    REGULAR = auto()
    EXTERNAL = auto()
    INVALID = auto()


class LinkEntry(NamedTuple):
    element: etree._Element
    link_type: LinkType
    target_doc: FileInfo | None
    target_id: str


NOTE_TYPES = frozenset({LinkType.NOTE, LinkType.COMMENT})


log = logging.getLogger("fb2_converter")


class LinkResolver:
    """
    Resolves all internal links across a finalised EPUB document list.

    Usage:
        LinkResolver(doc_list).resolve()
    """

    def __init__(self, doc_list: list[FileInfo]):
        self._doc_map: dict[str, FileInfo] = {doc.id: doc for doc in doc_list}
        self._id_to_doc: dict[str, str] = self._build_id_map(doc_list)
        # counters for generating unique IDs on repeated note references
        self._note_ref_counters: dict[str,int] = {}


    def resolve(self) -> None:
        """
        Single entry point.
        Two-pass resolution to handle dynamically assigned noteref IDs.
        Pass 1: resolve note/comment links, which assigns -ref IDs to anchors.
        Pass 2: rebuild the id map, then resolve all remaining links.
        """
        note_links, other_links = self._collect_links()

        for entry in note_links:
            self._apply_link(entry)

        self._id_to_doc = self._build_id_map(list(self._doc_map.values()))

        for entry in other_links:
            # Re-lookup: backlinks targeting dynamic -ref IDs may now be resolvable
            target_doc: FileInfo | None = self._find_target_doc(entry.target_id)
            link_type = LinkType.REGULAR if (entry.link_type == LinkType.INVALID and target_doc) else entry.link_type
            self._apply_link(entry._replace(link_type=link_type, target_doc=target_doc))


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


    def _collect_links(self) -> tuple[list[LinkEntry], list[LinkEntry]]:
        """Single scan: classifies all links and splits them into two buckets."""
        note_links: list[LinkEntry] = []
        other_links: list[LinkEntry] = []

        for doc in self._doc_map.values():
            if doc.html is None:
                continue
            self._current_doc_id = doc.id
            for a in doc.html.iterfind('.//a[@href]'):
                target_id = a.get('href', '').lstrip('#')
                target_doc: FileInfo | None = self._find_target_doc(target_id)
                link_type: LinkType = self._determine_link_type(a, target_doc)
                entry = LinkEntry(a, link_type, target_doc, target_id)
                bucket = note_links if link_type in NOTE_TYPES else other_links
                bucket.append(entry)

        return note_links, other_links


    def _find_target_doc(self, target_id: str) -> FileInfo | None:
        doc_id = self._id_to_doc.get(target_id)
        if doc_id is None:
            return None
        return self._doc_map.get(doc_id)


    def _determine_link_type(self, a: etree._Element, target_doc: FileInfo | None) -> LinkType:
        """
        Link classification criteria:
        1. NOTE: Note reference (anchor)
            * has link-type="note" (sufficient)
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
    
        if not a.get('href', '').startswith('#'):
            return LinkType.EXTERNAL
        
        if target_doc is None:
            return LinkType.INVALID
        
        data_link_type = a.attrib.pop('data-link-type', '').lower()
        if data_link_type == 'note':
            return LinkType.NOTE
        elif data_link_type:
            log.debug(f"Noteref id='{a.get('id')}': unexpected link-type '{data_link_type}'")
        
        if (target_doc.body_type == BodyType.COMMENT and
            target_doc.id != self._current_doc_id and
            'backlink' not in a.get('class', '')):
            return LinkType.COMMENT
        
        return LinkType.REGULAR


    def _apply_link(self, entry: LinkEntry) -> None:
        """Modifies a link according to its LinkType."""
        a, link_type, target_doc, target_id = entry
        match link_type:
            case LinkType.NOTE:
                self._apply_noteref(a, target_id)
            case LinkType.COMMENT:
                self._apply_noteref(a, target_id, extra_class='comment')
            case LinkType.REGULAR:
                pass
            case LinkType.EXTERNAL:
                # leave untouched
                return
            case LinkType.INVALID:
                self._mark_broken(a, target_id)
                return
            case _:
                log.warning(f"Unexpected LinkType for id='{a.get('id')}' with href='{a.get('href', '')}'")
                return

        if target_doc:
            a.set('href', f'{target_doc.filename}#{target_id}')


    def _apply_noteref(self, a: etree._Element, target_id: str, extra_class: str = '') -> None:
        a_class = ' '.join(['noteref', extra_class]).strip()
        a.attrib.update({
            'class': a_class,
            f'{{{NS.EPUB}}}type': 'noteref',
            # 'role': 'doc-noteref' ?
        })

        self._set_noteref_id(a, target_id)
        self._remove_sup_tag(a)


    def _set_noteref_id(self, a: etree._Element, target_id: str) -> None:
        """Adds a unique 'target-ref' id to noteref elements."""
        if a.get('id') is None:
            count = self._note_ref_counters.get(target_id, 0) + 1
            self._note_ref_counters[target_id] = count
            # note backlink points to 'ref', which is the first reference
            suffix = '' if count == 1 else f'-{count}'
            a.set('id', f'{target_id}-ref{suffix}')


    def _remove_sup_tag(self, a: etree._Element) -> None: 
        """
        Removes `sup` from a note reference link (from `sup > a` and `a > sup`).
        Noterefs are styled via CSS and don't need a `sup` tag.
        """
        etree.strip_tags(a, 'sup')
        # If the <a> tag itself is wrapped in a <sup>, unwrap it
        parent = a.getparent()
        if parent is not None and parent.tag == 'sup':
            grandparent = parent.getparent()
            if grandparent is not None:
                # Replace the <sup> with its child <a>
                grandparent.replace(parent, a)


    def _mark_broken(self, a: etree._Element, target_id: str) -> None:
        """
        Removes href from broken links to avoid Epubcheck errors. 
        Marks the element with 'broken-link' class.
        """
        if 'backlink' in a.attrib.get('class' ,''):
            log.warning(f"Note id='{target_id.rstrip('-ref')}' exists, but is never refenced.")
        else:
            log.warning(f"Broken internal link: target id='{target_id}' not found in any document.")
        xu.add_class(a, 'broken-link')
        xu.remove_attr(a, 'href')
        a.set('data-target', target_id)
