"""
Handles the conversion of FB2 XML elements to XHTML.
"""
import logging
from typing import NamedTuple

from lxml import etree

from ..post_processing.post_processor import PostProcessor
from ..utils import xml_utils as xu
from ..utils.models import ConversionConfig, ConversionMode
from ..utils.namespaces import Namespaces as NS
from ..utils.structures import BinaryInfo, ConvertedBody


log = logging.getLogger("fb2_converter")


class Tag(NamedTuple):
    """Structure to represent an XHTML tag with attributes."""
    name: str
    attrib: dict | None = None

    def create(self) -> etree._Element:
        """Creates an lxml Element with the specified tag and attributes."""
        return etree.Element(self.name, self.attrib)


class FB2ToHTMLConverter:
    """
    Transforms lxml Elements from the FB2 namespace to the XHTML namespace.

    Uses a handler-based dispatch system. Every FB2 tag is routed through
    `_recursive_convert`, which calls a handler and follows one of two paths:

      handler returns an element → append to parent, recurse children normally.
      handler returns None       → handler already managed its children; stop.

    `_handle_section` participates fully in this contract. It handles all cases
    that require taking over child recursion (split, adopt, atomic aside). The one
    remaining case — a structural-unwrap section whose children belong in the
    *caller's* parent rather than in `self._current_body` — stays as an explicit
    early branch in `_recursive_convert`, because only that method knows its own
    `xhtml_parent`. It is kept small and clearly labelled.
    """

    def __init__(self, binary_map: dict, id_map: dict, config: ConversionConfig):
        """
        Args:
            binary_map: FB2 image IDs → BinaryInfo objects.
            id_map:     Every FB2 element id → name of its containing body.
                        Used for automatic noteref / link-type detection.
            config:     User-supplied conversion configuration.
        """
        self.binary_map: dict[str, BinaryInfo] = binary_map
        self.id_map = id_map
        self.split_level = config.split_level
        self.split_size = config.split_size_kb
        self.config = config
        # counters for generating unique IDs on repeated note references
        self.note_ref_counters: dict[str,int] = {}

        # map of straightforward FB2 tag → XHTML tag/attributes tuples;
        # anything not listed here falls back to `div.class=fb2tag`
        self.tag_map: dict[str, Tag] = {
            'body': Tag('body'),
            'p': Tag('p'),
            'subtitle': Tag('p', {'class': 'subtitle'}),
            'text-author': Tag('p', {'class': 'text-author'}),
            'strong': Tag('strong'), 'b': Tag('strong'),
            'em': Tag('em'), 'emphasis': Tag('em'), 'i': Tag('em'),
            'strikethrough': Tag('s'), 's': Tag('s'),
            'cite': Tag('blockquote', {'class': 'q'}),
            'v': Tag('p', {'class': 'v'}),
            'table': Tag('table'),
            'tr': Tag('tr'),
            'th': Tag('th'),
            'td': Tag('td'),
            'sup': Tag('sup'),
            'sub': Tag('sub'),
            'code': Tag('code'), #HTMLTag('span', {'class': 'code'}),
            'ol': Tag('ol'),
            'ul': Tag('ul'),
            'li': Tag('li'),
            'empty-line': Tag('empty-line'),  # resolved up in post-processing
            # annotation, epigraph, poem, stanza -> div class=tag
        }

        # Handlers for tags that need more than a simple tag/attrib substitution.
        # Contract: return an xhtml element, or return None after managing own children.
        self._handler_map = {
            'section': self._handle_section,
            'title':   self._handle_title,
            'a':       self._handle_link,
            'image':   self._handle_image,
            'style':   self._handle_style,
        }


    # -------------------------------
    # Public API

    def convert_body(self, fb2_body: etree._Element, mode: ConversionMode) -> list[ConvertedBody]:
        """
        Converts a full FB2 <body> and returns one or more ConvertedBody objects.
        MAIN mode may produce multiple documents when splitting is active.
        NOTE mode always returns one document per FB2 body.
        """
        self.mode = mode
        self._converted_bodies: list[ConvertedBody] = []
        self._section_depth = 0
        self._level_counters = [1] + [0] * 5   
        
        self._current_title = "Content"

        self._start_new_body(fb2_body)

        # Convert
        for child in fb2_body:
            self._recursive_convert(child, self._current_body)

        # Post-process all converted bodies
        for body_obj in self._converted_bodies:
            PostProcessor(self.config, self.mode).run(body_obj.body)

        return self._converted_bodies


    def convert_element(self, element: etree._Element) -> etree._Element | None:
        """Converts a single FB2 element outside of a full body context (e.g. annotation)."""
        saved_mode = getattr(self, 'mode', ConversionMode.MAIN)
        self.mode = ConversionMode.MAIN
        self._section_depth = 0

        tmp_parent = etree.Element('div')
        self._recursive_convert(element, tmp_parent)
        result = tmp_parent[0] if len(tmp_parent) > 0 else None
        if result is not None:
            PostProcessor(self.config, self.mode).run(result)

        self.mode = saved_mode
        return result


    # -------------------------------
    # Core recursive engine

    def _recursive_convert(self, fb2_element: etree._Element, xhtml_parent: etree._Element):
        """
        Converts one FB2 element and recurses into its children.

        The only special case handled here (outside the handler dispatch) is a
        structural-unwrap section whose depth exceeds the split threshold. In this
        case children must be appended into *this method's* xhtml_parent, which
        _handle_section cannot access without a signature change.  All other section
        outcomes are handled inside _handle_section.
        """
        tag = xu.get_tag_name(fb2_element)

        # Structural unwrap: deep section, MAIN mode only
        # A section nested below the split threshold is not a document boundary and
        # is not an <aside>. Its children belong directly in the calling parent.
        # This is the one case where child recursion cannot be delegated to a handler.
        if (tag == 'section'
                and self.mode == ConversionMode.MAIN
                and self._get_section_depth(fb2_element) > self.split_level):
            element_id = fb2_element.get('id')
            if element_id:
                xhtml_parent.append(etree.Element('div', {'id': element_id, 'class': 'section-anchor'}))
            self._section_depth += 1
            for child in fb2_element:
                self._recursive_convert(child, xhtml_parent)
            self._section_depth -= 1
            return

        # Standard dispatch
        handler = self._handler_map.get(tag, self._handle_default)
        new_element = handler(fb2_element)

        if new_element is None:
            return

        new_element.text = fb2_element.text
        xhtml_parent.append(new_element)

        for child in fb2_element:
            self._recursive_convert(child, new_element)
            if child.tail:
                if len(new_element) > 0:
                    last_child = new_element[-1]
                    last_child.tail = (last_child.tail or '') + child.tail
                else:
                    new_element.text = (new_element.text or '') + child.tail


    # -------------------------------
    # Section handler

    def _handle_section(self, element: etree._Element) -> etree._Element | None:
        """
        Handles sections that are *not* pure structural unwraps into the caller's parent.
        (That single remaining case lives in _recursive_convert — see note there.)

        Outcomes covered here:

          MAIN, depth <= split_level  → split or adopt current document, then unwrap
                                        children into self._current_body. Returns None.

          NOTE, grouping section      → unwrap children into self._current_body. Returns None.
          (no id, or has child sections)

          NOTE, atomic footnote       → convert to <aside>. Returns the element so
          (has id, no child sections)   _recursive_convert appends it and recurses children.
        """
        self._section_depth += 1
        try:
            return self._dispatch_section(element)
        finally:
            self._section_depth -= 1


    def _dispatch_section(self, element: etree._Element) -> etree._Element | None:
        """Routes a section to the correct outcome. Called only from _handle_section."""
        element_id = element.get('id')

        if self.mode == ConversionMode.MAIN:
            # depth <= split_level: document boundary
            self._split_or_adopt(element)
            self._unwrap_into(element, element_id, self._current_body)
            return None

        # NOTE mode
        has_child_section = any(xu.get_tag_name(ch) == 'section' for ch in element)

        if element_id and not has_child_section:
            # Atomic footnote: convert to <aside>, let standard flow recurse children
            return self._make_footnote_aside(element)
        else:
            # Grouping / structural section: unwrap into current body
            self._unwrap_into(element, element_id, self._current_body)
            return None


    def _split_or_adopt(self, element: etree._Element):
        """
        Manages the document split for a section at or above the split threshold.

        If the current document has real content, starts a new document.
        If it is still empty, renames it in-place ('adopt') to avoid a blank page.
        """
        level_index = self._section_depth - 1

        if self._has_actual_content():
            self._level_counters[level_index] += 1
            for i in range(level_index + 1, len(self._level_counters)):
                self._level_counters[i] = 0
            self._start_new_body(element)
        else:
            # Adopt the empty document: give it the identity of this section.
            if self._level_counters[level_index] == 0:
                self._level_counters[level_index] = 1
            new_file_id = self._generate_part_name(element)
            self._converted_bodies[-1] = self._converted_bodies[-1]._replace(file_id=new_file_id)


    def _unwrap_into(self,
                     element: etree._Element,
                     element_id: str | None,
                     target: etree._Element):
        """Recurses all children of element into target, emitting an ID anchor first if needed."""
        if element_id:
            target.append(etree.Element('div', {'id': element_id, 'class': 'section-anchor'}))
        for child in element:
            self._recursive_convert(child, target)


    def _make_footnote_aside(self, element: etree._Element) -> etree._Element:
        """
        Builds the <aside> shell for an atomic footnote section.
        Extracts <title> as a backlink prepended to the aside.
        Children (everything except <title>) are recursed by the standard flow.
        """
        element_id = element.get('id')
        attrib = {
            'class':              'footnote',
            'id':                 element_id,
            f'{{{NS.EPUB}}}type': 'footnote',
            'role':               'doc-footnote',
        }
        aside = etree.Element('aside', attrib)

        title_el = element.find(f'{{{NS.FB2}}}title')
        if title_el is not None:
            title_text = " ".join(title_el.itertext()).strip()  # type: ignore
            backlink = etree.Element('a', {
                'href':               f'#{element_id}-ref',
                'class':              'backlink',
                'id':                 f'{element_id}-back',
                f'{{{NS.EPUB}}}type': 'backlink',
            })
            backlink.text = f'{title_text}.'
            aside.insert(0, backlink)
            element.remove(title_el)

        return aside


    # -------------------------------
    # Element handlers

    def _handle_title(self, element: etree._Element) -> etree._Element | None:
        """Converts <title> to h1–h6 based on current section depth."""
        parent = element.getparent()
        if parent is None:
            log.warning("Found <title> without a parent. Skipping.")
            return None

        parent_tag = xu.get_tag_name(parent)

        # Body-level title → div.fb2title (builder extracts it later)
        if parent_tag == 'body':
            attrib = {'class': 'fb2title'}
            element_id = element.get('id')
            if element_id:
                attrib['id'] = element_id
            return etree.Element('div', attrib)

        # Poem title → p.subtitle
        if parent_tag == 'poem':
            return self._handle_default(element, convert_as='subtitle')

        # _section_depth is already incremented by _handle_section before children
        # are dispatched, so it correctly reflects the enclosing section's depth.
        level = min(self._section_depth, 6) or 1

        title_text = " ".join(element.itertext()).strip()  # type: ignore
        if not title_text:
            log.debug("Found empty <title>. Skipping.")
            return None

        # Update the current document's title if this heading belongs to a
        # section at or above the split threshold.
        if self._section_depth <= self.split_level:
            self._current_title = title_text
            if self._converted_bodies:
                self._converted_bodies[-1] = self._converted_bodies[-1]._replace(title=title_text)

        h = etree.Element(f'h{level}')
        xu.copy_id(element, h)
        return h


    def _handle_image(self, element: etree._Element) -> etree._Element | None:
        """Converts <image> to <figure><img>, or bare <img> when inside a paragraph."""
        # TODO: handle p>img as inline, section>img as fullscreen?
        img_id = element.get(f'{{{NS.XLINK}}}href', '').lstrip('#')
        if not img_id or img_id not in self.binary_map:
            log.warning(f"Image does not exist. Id={img_id}. Skipping.")
            return None

        binary = self.binary_map[img_id]

        img_attrib = {'data-img-id': img_id}
        fig_attrib = {'class': 'image'}

        dimensions = binary.dimensions
        if dimensions is not None:
            img_attrib.update({
                'data-width':       str(dimensions[0]),
                'data-height':      str(dimensions[1]),
                'data-orientation': binary.orientation,
            })
            fig_attrib['class'] += f" {binary.orientation}".strip()

        img = etree.Element('img', img_attrib)
        xu.copy_id(element, img)

        parent = element.getparent()
        if parent is not None and xu.get_tag_name(parent) in ('p', 'subtitle'):
            # Inline <img> inside a paragraph.
            return img

        # Otherwise, wrap it in a <figure>.
        figure = etree.Element('figure', fig_attrib)
        figure.append(img)
        return figure


    def _handle_link(self, element: etree._Element) -> etree._Element | None:
        """
        Converts <a> and resolves href.

        Internal links whose target lives in a note/comment body are tagged with
        data-link-type="note". This is a build-time-only attribute removed during
        link resolution in EpubBuilder._resolve_internal_links().
        """
        href = element.get(f'{{{NS.XLINK}}}href') or element.get('href')

        if not href:
            return etree.Element('a', {'class': 'empty'})

        is_external = not href.startswith('#')
        target_id = href.lstrip('#')
        prefix = "" if is_external else "#"
        attrib: dict = {'href': f'{prefix}{target_id}'}

        link_type = element.get('type')
        if link_type:
            attrib['data-link-type'] = link_type

        if not is_external and target_id:
            body_name = self.id_map.get(target_id)
            if body_name and body_name.lower() not in ('main', ''):
                attrib['data-link-type'] = 'note'

        link = etree.Element('a', attrib)
        xu.copy_id(element, link)

        # Generate id for internal links without one
        if not is_external and target_id and link.get('id') is None:
            count = self.note_ref_counters.get(target_id, 0) + 1
            self.note_ref_counters[target_id] = count
            suffix = '' if count == 1 else f'-{count}'
            link.set('id', f'{target_id}-ref{suffix}')

        return link


    def _handle_style(self, element: etree._Element) -> etree._Element | None:
        """Converts <style name="X"> to <span class="X">."""
        name = element.get('name')
        if not name:
            return None
        return etree.Element('span', {'class': name})


    def _handle_default(self, element: etree._Element, convert_as: str | None = None) -> etree._Element | None:
        """
        Simple tag substitution via tag_map; falls back to <div class="fb2tag">.

        Args:
            element:    The FB2 element to convert.
            convert_as: Optional tag name override (used by _handle_title for poem titles).
        """
        fb2_tag = convert_as or xu.get_tag_name(element)

        if fb2_tag in self.tag_map:
            html_tag, html_attrib = self.tag_map[fb2_tag]
        else:
            # poem, epigraph, etc.
            html_tag, html_attrib = 'div', {'class': fb2_tag}

        # Merge attributes with existing ones (typically only 'id', 'name')
        attrib = xu.get_attrib_dict(element)
        attrib.update(html_attrib or {})
        return etree.Element(html_tag, attrib)

    
    # -------------------------------
    # Document splitting helpers

    def _generate_part_name(self, fb2_element: etree._Element) -> str:
        """Generates a file ID for a new document body."""
        if self.mode == ConversionMode.NOTE:
            body_name = fb2_element.get('name')
            if body_name is None:
                log.warning("Note body without 'name' attribute; using 'notes'.")
                body_name = 'notes'
            return body_name.lower()

        name_parts = [str(c) for c in self._level_counters if c > 0]
        return f"part_{'_'.join(name_parts) or '1'}"


    def _start_new_body(self, fb2_element: etree._Element):
        """Creates a new ConvertedBody and makes it the active conversion target."""
        file_id = self._generate_part_name(fb2_element)
        self._current_body = etree.Element('body')
        self._converted_bodies.append(ConvertedBody(
            file_id=file_id,
            title=self._current_title,
            body=self._current_body,
        ))


    def _has_actual_content(self) -> bool:
        """Returns True if the current body contains anything beyond invisible ID anchors."""
        if self._current_body.text and self._current_body.text.strip():
            return True
        for child in self._current_body:
            if child.get('class') != 'section-anchor':
                return True
            if (child.text and child.text.strip()) or (child.tail and child.tail.strip()):
                return True
        return False


    def _get_section_depth(self, element: etree._Element) -> int:
        """
        Returns the nesting depth of element by counting <section> ancestors.
        Used only for the structural-unwrap check in _recursive_convert.
        Prefer reading self._section_depth inside handlers, where it is already current.
        """
        section_tag = f'{{{NS.FB2}}}section'
        return sum(1 for _ in element.iterancestors(section_tag)) + 1
