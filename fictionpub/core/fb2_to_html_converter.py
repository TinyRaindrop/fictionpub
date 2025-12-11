"""
Handles the conversion of FB2 XML elements to XHTML.
"""
import logging
from typing import NamedTuple

from lxml import etree

from ..post_processing.post_processor import PostProcessor
from ..utils import xml_utils as xu
from ..utils.config import ConversionConfig, ConversionMode
from ..utils.namespaces import Namespaces as NS
from ..utils.structures import BinaryInfo, ConvertedBody, FNames as FN


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

    This class uses a handler-based approach, dispatching element conversion
    to specific methods based on the FB2 tag name. This avoids large if-elif
    blocks and makes the converter easily extensible.
    """

    def __init__(self, binary_map: dict, id_map: dict, config: ConversionConfig):
        """
        Initializes the converter with contextual data and sets up the
        dispatch maps for tag conversion.
        """
        self.binary_map: dict[str, BinaryInfo] = binary_map
        self.id_map = id_map    # TODO: consider using it for noteref identification
        self.split_level = config.split_level
        self.split_size = config.split_size_kb
        self.config = config

        # Map for direct tag-to-tag conversions. 
        # FB2 tags are mapped to strings of 'tag' or tuples of (tag, attributes)
        self.tag_map: dict[str, Tag] = {
            'body': Tag('body'),
            'p': Tag('p'),
            'subtitle': Tag('p', {'class': 'subtitle'}),
            'text-author': Tag('p', {'class': 'text-author'}),
            'strong': Tag('strong'), 'b': Tag('strong'),
            'em': Tag('em'), 'emphasis': Tag('em'),
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
            'empty-line': Tag('empty-line')  # cleaned up in post-processing
            # annotation, epigraph, poem, stanza -> div class=tag
        }

        # Dispatch map for tags that require special handling.
        self._handler_map = {
            'section': self._handle_section,
            'title': self._handle_title,
            'a': self._handle_link,
            'image': self._handle_image,
            'style': self._handle_style,
        }


    def convert_body(self, fb2_body: etree._Element, mode: ConversionMode) -> list[ConvertedBody]:
        """
        Converts a full FB2 <body> element and runs post-processing.
        For MAIN mode, this can return multiple documents if splitting occurs.
        """        
        self.mode = mode
        self._converted_bodies: list[ConvertedBody] = []
        self._level_counters = [0] * 6
        self._current_title = "Content"
        
        # Create self._current_body and add
        self._start_new_body(fb2_body, level=1)
        
        # Convert while splitting
        for child in fb2_body:
            self._recursive_convert(child, self._current_body)

        # Post-process all converted bodies
        for body_obj in self._converted_bodies:
            PostProcessor(self.config, self.mode).run(body_obj.body)

        return self._converted_bodies


    def convert_element(self, element: etree._Element) -> etree._Element | None:
        self.mode = ConversionMode.MAIN     # ConversionMode.ELEMENT ?
        tmp_parent = etree.Element('div')
        self._recursive_convert(element, tmp_parent)   
        result = tmp_parent[0] if len(tmp_parent) > 0 else None
        if result is not None:
            PostProcessor(self.config, self.mode).run(result)
        return result

  
    def _generate_part_name(self, fb2_body: etree._Element, level: int) -> str:
        """Generates filename, file ID, and title for a body."""
        if self.mode == ConversionMode.NOTE:
            body_name = fb2_body.get('name')
            if body_name is None:       # this should never happen
                body_name = "notes"
                log.warning("Note body without name attribute found; using 'notes'.")
            return body_name.lower()

        # Hierarchical naming for main content
        level_index = level - 1
        if level_index < 0: level_index = 0
        self._level_counters[level_index] += 1
        for i in range(level_index + 1, len(self._level_counters)):
            self._level_counters[i] = 0
        name_parts = [str(c) for c in self._level_counters[:level] if c > 0]
        if not name_parts: name_parts = [str(self._level_counters[0])]
        
        file_id = f"part_{'_'.join(name_parts)}"
        return file_id


    def _start_new_body(self, fb2_body: etree._Element, level: int):
        """Creates a new ConvertedBody and sets it as the current target."""
        file_id = self._generate_part_name(fb2_body, level)
        
        self._current_body = etree.Element('body')
        # Create and store the new document.
        # All content will be added to this body during conversion.
        body_data = ConvertedBody(
            file_id=file_id,
            title=self._current_title,
            body=self._current_body,
        )
        self._converted_bodies.append(body_data)


    def _recursive_convert(self, fb2_element: etree._Element, xhtml_parent: etree._Element):
        """Core recursive engine for converting FB2 elements to XHTML."""
        tag = xu.get_tag_name(fb2_element)

        # --- Isolate Splitting Logic ---
        # Check for the special split case before calling any handler.
        if tag == 'section' and self.mode == ConversionMode.MAIN:
            level = self._get_heading_level(fb2_element)
            if level == self.split_level:
                self._start_new_body(fb2_element, level)
                # This section's children get appended directly to the new body.
                # The <section> tag itself is discarded.
                for child in fb2_element:
                    self._recursive_convert(child, self._current_body)
                return

        # --- Standard Recursive Flow ---
        handler = self._handler_map.get(tag, self._handle_default)
        new_xhtml_element = handler(fb2_element)

        if new_xhtml_element is None: return
    
        new_xhtml_element.text = fb2_element.text
        xhtml_parent.append(new_xhtml_element)

        for child in fb2_element:
            # Recursion continues inside the newly created element.
            self._recursive_convert(child, new_xhtml_element)
            if child.tail:
                if len(new_xhtml_element) > 0:
                    last_child = new_xhtml_element[-1]
                    last_child.tail = (last_child.tail or '') + child.tail
                else:
                    new_xhtml_element.text = (new_xhtml_element.text or '') + child.tail

    # --- SECTION AND TITLE HANDLERS ---

    def _handle_section(self, element: etree._Element) -> etree._Element | None:
        element_id = element.get('id')
        """if mode == ConversionMode.NOTE and element_id:
            return self._handle_note_section(element)
        else: # no ID ConversionMode.MAIN
            return self._handle_main_section(element)
        """
        # sections with id are footnote wrappers in notes mode
        # TODO: improve wrapper detection (must have title, referenced by link)
        if self.mode == ConversionMode.NOTE and element_id:
            attrib = {
                'class': 'footnote',
                'id': element_id,
                f'{{{NS.EPUB}}}type': 'footnote',
                'role': 'doc-footnote',
            }
            aside = etree.Element('aside', attrib)

            title_el = element.find(f'{{{NS.FB2}}}title')
            if title_el is not None:
                title_text = " ".join(title_el.itertext()).strip()  # type: ignore
                attrib = {
                    'href': f'#{element_id}-ref',   # point to the note reference
                    'class': 'backlink',
                    'id': f'{element_id}-back',
                    f'{{{NS.EPUB}}}type': 'backlink',
                }
                backlink = etree.Element('a', attrib)
                backlink.text = f"{title_text}.\u00A0"  # dot + NBSP
                # insert as the 1st child, will be adjusted in post-processing
                aside.insert(0, backlink) 
                element.remove(title_el)
            return aside
        
        # Default section handling
        if self.mode == ConversionMode.NOTE:
            tag = Tag('div', {'class': 'note-section'})
        else:
            # ConversionMode.MAIN or ELEMENT
            # TODO: unwrap sections
            tag = Tag('section')
        section = etree.Element(tag.name, tag.attrib)
        xu.copy_id(element, section)
        return section
    

    def _handle_title(self, element: etree._Element) -> etree._Element | None:
        """
        Handles <title> tags. Improved logic for <p> tags inside titles:
        - If one <p>, its content is unwrapped directly into the heading.
        - If multiple <p>s, they become <span>s separated by <br/>.
        """
        parent = element.getparent()
        if parent is None:
            log.debug("Found <title> without a parent. Skipping.")
            return None

        # <poem> title => p.subtitle
        if xu.get_tag_name(parent) == "poem":
            return self._handle_default(element, convert_as='subtitle')
            
        level = self._get_heading_level(element)
        if self.mode == ConversionMode.NOTE: level = 1
        h = f'h{level}'
        title_text = " ".join(element.itertext()).strip() # type: ignore

        parent_level = self._get_heading_level(parent)
        # TODO: investigate usage of _current_title
        if parent_level == self.split_level - 1:
            self._current_title = title_text
            if self._converted_bodies:
                last_doc = self._converted_bodies[-1]
                self._converted_bodies[-1] = last_doc._replace(title=title_text)

        new_element = etree.Element(h)
        xu.copy_id(element, new_element)
        return new_element
    

    def _handle_image(self, element: etree._Element) -> etree._Element | None:
        # TODO: handle p>img as inline?, section>img as fullscreen?
        img_id = element.get(f'{{{NS.XLINK}}}href', '').lstrip('#')
        if not img_id or img_id not in self.binary_map:
            return None
        
        binary = self.binary_map[img_id]
        attrib = {'src': f'../{FN.IMAGES}/{binary.filename}'}
        dimensions = binary.dimensions
        if dimensions is not None:
            attrib.update({
                'data-width': str(dimensions[0]), 
                'data-height': str(dimensions[1]),
                'data-orientation': binary.orientation
            })
        
        figure = etree.Element('figure', {'class': 'image'})
        img = etree.SubElement(figure, 'img', attrib)
        xu.copy_id(element, img)
        return figure

    
    def _handle_link(self, element: etree._Element) -> etree._Element | None:
        """Creates `a` and copies over href."""
        href = element.get(f'{{{NS.XLINK}}}href')
        attrib = {}
        
        if href:
            is_external = not href.startswith("#")
            # Save prefix and clear it from href
            prefix = "" if is_external else "#"
            href = href.lstrip("#")

            a_id = element.get('id')
            if (a_id):
                log.warning(f"Overwriting existing <a> id: {a_id}")
            attrib = {
                'href': f'{prefix}{href}',
                'id': f'{href}-ref'
            }
            # TODO: remove? link-type isn't very useful. 
            # Instead, use a dict of <aside> IDs to identify noterefs
            link_type = element.get('type')
            if link_type:
                attrib['link-type'] = link_type

        else:
            attrib={'class': 'empty'}
        
        link = etree.Element('a', attrib)
        return link


    def _handle_style(self, element: etree._Element) -> etree._Element | None:
        name = element.get('name')
        if not name:
            return
        span = etree.Element('span', attrib={'class': name})
        return span


    def _handle_default(self, element: etree._Element, convert_as: str | None = None) -> etree._Element | None:
        """
        Handles simple tag conversions using the `tag_map`.
        Defaults to `div class="tag"` for the rest of cases.
        
        Args:
            element: The FB2 element to convert.
            convert_as: Optional FB2 tag name to override the default mapping.
        """        
        fb2_tag = convert_as or xu.get_tag_name(element)

        if fb2_tag in self.tag_map:
            html_tag, html_attrib = self.tag_map[fb2_tag]
        else:
            # <div class="fb2_tag"> for poem, epigraph, etc.
            html_tag = 'div'
            html_attrib = {'class': fb2_tag}
        
        # Merge attributes with existing ones (typically only 'id', 'name')
        attrib = xu.get_attrib_dict(element) 
        attrib.update(html_attrib or {})

        elem = etree.Element(html_tag, attrib)
        return elem
    

    def _get_heading_level(self, element: etree._Element) -> int:
        """Determines heading level by counting the number of <section> ancestors. """
        # The tag must be in the Clark notation {namespace}tag
        section_tag = f"{{{NS.FB2}}}section"
        depth = sum(1 for _ in element.iterancestors(section_tag))
        return min(depth, 6) or 1   # Min depth is 1, max is 6     


    # --- END of ElementConverter ---
