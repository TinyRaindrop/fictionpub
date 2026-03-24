"""
Handles the conversion of FB2 XML elements to XHTML.
"""
import logging
from typing import NamedTuple

from lxml import etree

from ..models import namespaces as NS
from ..models.conversion import ConversionConfig
from ..models.structures import BinaryInfo, BodyType, FB2Body, ConvertedBody
from ..utils import xml_utils as xu


log = logging.getLogger("fb2_converter")


class Tag(NamedTuple):
    """Structure to represent an XHTML tag with attributes."""
    name: str
    attrib: dict[str, str] | None = None

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
    """

    def __init__(self, binary_map: dict, config: ConversionConfig):
        """
        Args:
            binary_map: FB2 image IDs → BinaryInfo objects.
            config:     User-supplied conversion configuration.
        """
        self.binary_map: dict[str, BinaryInfo] = binary_map
        self.split_level = config.split_level
        self.split_size = config.split_size_kb
        self.config = config

        self.part_counters: dict[BodyType, int] = {}

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
        # Result: return an xhtml element, or return None after managing own children.
        self._handler_map = {
            'section': self._handle_section,
            'title':   self._handle_title,
            'a':       self._handle_link,
            'image':   self._handle_image,
            'style':   self._handle_style,
        }


    # -------------------------------
    # Public API

    def convert_body(self, fb2body: FB2Body) -> list[ConvertedBody]:
        """
        Converts a full FB2 <body> and returns one or more ConvertedBody objects.
        MAIN mode may produce multiple documents when splitting is active.
        NOTE mode always returns one document per FB2 body.
        """
        self.body_type: BodyType = fb2body.body_type
        self._converted_bodies: list[ConvertedBody] = []
        self._section_depth = 0

        # Get a number of parts already generated for a given BodyType
        initial_counter = self.part_counters.get(self.body_type, 0) + 1
        self._level_counters = [initial_counter] + [0] * 5
        # TODO: if multiple MAIN bodies and body>title on each, use it as h1, and begin section titles from h2s

        self._current_title = "Content"

        self._start_new_body(fb2body.body)

        # Convert
        for child in fb2body.body:
            self._recursive_convert(child, self._current_body)

        return self._converted_bodies


    def convert_element(self, element: etree._Element) -> etree._Element | None:
        """Converts a single FB2 element outside of a full body context (e.g. annotation)."""
        saved_type = getattr(self, 'mode', BodyType.MAIN)
        self.body_type = BodyType.MAIN
        self._section_depth = 0

        tmp_parent = etree.Element('div')
        self._recursive_convert(element, tmp_parent)
        result = tmp_parent[0] if len(tmp_parent) > 0 else None

        self.body_type = saved_type
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
        if tag == 'section':
            self._section_depth += 1
            
            # -- Structural unwrap: deep section in MAIN mode
            # Not a document boundary and not an <aside>.
            # Children go directly into the caller's parent, so we handle them here.

            if (self.body_type == BodyType.MAIN
                and self._section_depth > self.split_level):
                self._unwrap_into(fb2_element, xhtml_parent)
                self._section_depth -= 1
                return

        # -- Standard dispatch
        handler = self._handler_map.get(tag, self._handle_default)
        new_element = handler(fb2_element)

        if new_element is None:
            if tag == 'section':
                self._section_depth -= 1
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

        if tag == 'section':
            self._section_depth -= 1


    # -------------------------------
    # Section handler

    def _handle_section(self, element: etree._Element) -> etree._Element | None:
        """
        Routes a section to the correct outcome. _section_depth is managed by
        _recursive_convert, so it is already correct when this method runs.

        Outcomes:
          MAIN, depth <= split_level: split or adopt, unwrap into _current_body. Returns None.
          NOTE, grouping section    : unwrap into _current_body. Returns None.
          NOTE, atomic footnote     : build <aside> shell, return it so standard
            flow appends it and recurses children at correct depth.
        """
        element_id = element.get('id')

        if self.body_type == BodyType.MAIN:
            # depth <= split_level: document boundary
            self._split_or_adopt(element)
            self._unwrap_into(element, self._current_body)
            return None

        # NOTE mode
        has_child_section = any(xu.get_tag_name(ch) == 'section' for ch in element)

        if element_id and not has_child_section:
            # Atomic footnote: convert to <aside>, let standard flow recurse children
            return self._make_footnote_aside(element)
        else:
            # Grouping / structural section: unwrap into current body
            self._unwrap_into(element, self._current_body)
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
        
        self.part_counters[self.body_type] = self._level_counters[0]


    def _unwrap_into(self, element: etree._Element, target: etree._Element):
        """Recurses all children of element into target, emitting an ID anchor first if needed."""
        element_id = element.get('id')
        if element_id:
            target.append(etree.Element('div', {'id': element_id, 'class': 'section-anchor'}))
        for child in element:
            self._recursive_convert(child, target)


    def _make_footnote_aside(self, element: etree._Element) -> etree._Element:
        """
        Builds the `aside` shell for an atomic footnote section.
        Extracts `title` as a backlink prepended to the aside.
        Children (everything except `title`) are recursed by the standard flow.
        """
        element_id = element.get('id')
        aside_attr = {
            'class': 'footnote',
            'id': element_id,
            f'{{{NS.EPUB}}}type': 'footnote',
            'role': 'doc-footnote',
        }
        aside = etree.Element('aside', aside_attr)

        title_el = element.find(f'{{{NS.FB2}}}title')
        # TODO: title may contain noterefs (it shouldn't, but we can try to preserve them anyway)
        # <title>
        # <p><strong>Section subtitle text</strong><a l:href="#n533" type="note">[533]</a></p>
        # </title>
        if title_el is not None:
            title_text = xu.itertext(title_el)
            backlink_attr = {
                'href': f'#{element_id}-ref',
                'class': 'backlink',
                'id': f'{element_id}-back',
                f'{{{NS.EPUB}}}type': 'backlink',
                'role': 'doc-backlink',
            }
            backlink = etree.Element('a', backlink_attr)
            backlink.text = f'{title_text}.'
            aside.insert(0, backlink)
            element.remove(title_el)

        return aside


    # -------------------------------
    # Element handlers

    def _handle_title(self, element: etree._Element) -> etree._Element | None:
        """Converts `title` to h1-h6 based on current section depth."""
        parent = element.getparent()
        if parent is None:
            log.warning("Found <title> without a parent. Skipping.")
            return None

        parent_tag = xu.get_tag_name(parent)

        # Body-level title → div.halftitle (builder extracts it later)
        if parent_tag == 'body':
            attrib = {'class': 'halftitle'}
            element_id = element.get('id')
            if element_id:
                attrib['id'] = element_id
            return etree.Element('div', attrib)

        # Poem title → p.subtitle
        if parent_tag == 'poem':
            return self._handle_default(element, convert_as='subtitle')

        # In NOTE mode the body title becomes h1 (inserted by EpubBuilder),
        # so section titles must start at h2 to sit below it.
        offset = 1 if self.body_type != BodyType.MAIN else 0
        adjusted_level = min(max(self._section_depth + offset, 1), 6)

        title_text = xu.itertext(element)
        if not title_text:
            log.debug("Found empty <title>. Skipping.")
            return None

        # Update the current document's title if this heading belongs to a
        # section at or above the split threshold.
        if self._section_depth <= self.split_level:
            self._current_title = title_text
            if self._converted_bodies:
                self._converted_bodies[-1] = self._converted_bodies[-1]._replace(title=title_text)

        h = etree.Element(f'h{adjusted_level}')
        xu.copy_id(element, h)
        return h


    def _handle_image(self, element: etree._Element) -> etree._Element | None:
        """Converts `image` to `figure>img`, or inline `img` when inside a paragraph."""
        # TODO: section>img as fullscreen
        img_id = element.get(f'{{{NS.XLINK}}}href', '').lstrip('#')
        if not img_id or img_id not in self.binary_map:
            log.warning(f"Image {img_id} does not exist. Skipping.")
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
        if parent is not None and xu.get_tag_name(parent) in ('p', 'subtitle', 'a'):
            # Inline <img> inside a paragraph.
            return img

        # Otherwise, wrap it in a <figure>.
        figure = etree.Element('figure', fig_attrib)
        figure.append(img)
        return figure


    def _handle_link(self, element: etree._Element) -> etree._Element | None:
        """
        Converts `a` and copies its attributes.

        Internal links whose target lives in a note body are tagged with
        data-link-type="note". This attribute is removed later by LinkResolver.
        """
        href = element.get(f'{{{NS.XLINK}}}href') or element.get('href')

        if not href:
            return etree.Element('a', {'class': 'empty'})

        attrib: dict = {'href': href}

        link_type = element.get('type')
        if link_type:
            attrib['data-link-type'] = link_type

        link = etree.Element('a', attrib)
        xu.copy_id(element, link)

        return link


    def _handle_table(self, element: etree._Element) -> etree._Element | None:
        # TODO: handle align, valign, colspan, rowspan
        pass


    def _handle_style(self, element: etree._Element) -> etree._Element | None:
        """Converts `style name="X"` to `span class="X"`."""
        name = element.get('name')
        if not name:
            return None
        return etree.Element('span', {'class': name})


    def _handle_default(self, element: etree._Element, convert_as: str | None = None) -> etree._Element | None:
        """
        Simple tag substitution via tag_map. Falls back to `div class="fb2tag"`.

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
        # TODO: this would also merge style/align/valign attribs
        attrib = xu.get_attrib_dict(element)
        attrib.update(html_attrib or {})
        return etree.Element(html_tag, attrib)

    
    # -------------------------------
    # Document splitting helpers

    def _generate_part_name(self, fb2_element: etree._Element) -> str:
        """Generates a file ID for a new document body."""
        # BodyType.NOTE / COMMENT
        # TODO: this doesn't account for multiple bodies with the same name
        if self.body_type != BodyType.MAIN:
            body_name = fb2_element.get('name')
            if body_name is None:
                log.warning("Note body without 'name' attribute; using 'notes'.")
                body_name = 'notes'
            return body_name.lower()

        # BodyType.MAIN
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
            body_type=self.body_type
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
        Returns the nesting depth of element by counting `section` ancestors.
        Used only for the structural-unwrap check in _recursive_convert.
        Prefer reading self._section_depth inside handlers, where it is already current.
        """
        section_tag = f'{{{NS.FB2}}}section'
        return sum(1 for _ in element.iterancestors(section_tag)) + 1
