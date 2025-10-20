"""
Handles the conversion of FB2 XML elements to XHTML.
"""
import copy
import logging
from enum import Enum, auto
from typing import NamedTuple
from lxml import etree

from ..utils.config import ConversionConfig
from ..utils.namespaces import Namespaces as NS
from ..utils.structures import BinaryInfo, FileInfo, FNames as FN
from ..utils import xml_utils as xu


log = logging.getLogger("fb2_converter")


class ConversionMode(Enum):
    """Defines the context for the conversion (e.g., main text vs. notes)."""
    MAIN = auto()   # main content bodies
    NOTE = auto()   # note / comment bodies
    ELEMENT = auto()


class Tag(NamedTuple):
    """Structure to represent an XHTML tag with attributes."""
    name: str
    attrib: dict | None = None

    def create(self) -> etree._Element:
        """Creates an lxml Element with the specified tag and attributes."""
        return etree.Element(self.name, self.attrib)


class ConvertedBody(NamedTuple):
    """
    Container for a single converted XHTML body, its title,
    attributes, and ID.
    """
    file_id: str
    title: str
    body: etree._Element


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
        self.id_map = id_map
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
            self._post_process(body_obj.body)

        return self._converted_bodies


    def convert_element(self, element: etree._Element) -> etree._Element | None:
        self.mode = ConversionMode.MAIN
        tmp_parent = etree.Element('div')
        self._recursive_convert(element, tmp_parent)   # ConversionMode.ELEMENT ?
        result = tmp_parent[0] if len(tmp_parent) > 0 else None
        if result is not None:
            self._post_process(result)
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
        tag = get_tag_name(fb2_element)

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
        
        xhtml_parent.append(new_xhtml_element)

        new_xhtml_element.text = fb2_element.text

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
            aside = Tag('aside', attrib).create()

            title_el = element.find(f'{{{NS.FB2}}}title')
            if title_el is not None:
                title_text = " ".join(title_el.itertext()).strip()  # type: ignore
                attrib = {
                    'href': f'#{element_id}-ref',   # backlink to the note reference
                    'class': 'backlink',
                    'id': f'{element_id}-back',
                    f'{{{NS.EPUB}}}type': 'backlink',
                }
                backlink = Tag('a', attrib).create()
                backlink.text = title_text
                # find first <p> or <div> to insert the backlink into
                next_el = title_el.getnext()
                if next_el is not None and get_tag_name(next_el) in ['p', 'div']:
                    next_text = next_el.text
                    if next_text: 
                        # add leading space after backlink and move the text to tail
                        next_text = ' ' + next_text.strip()
                        next_el.text = None
                        next_el.insert(0, backlink)
                        backlink.tail = next_text
                    else:
                        next_el.insert(0, backlink)
                else:
                    # If there's no suitable <p> or <div>, wrap in <span> and insert as 1st child of <aside>
                    # backlink_span = HTMLTag('span', {'class': 'backlink-float'}).create()
                    # backlink_span.append(backlink)
                    backlink.set('class', 'backlink bl-float')
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
        section = tag.create()
        if element_id: section.set('id', element_id)
        return section
    

    def _handle_title(self, element: etree._Element) -> etree._Element | None:
        """
        Handles <title> tags. Improved logic for <p> tags inside titles:
        - If one <p>, its content is unwrapped directly into the heading.
        - If multiple <p>s, they become <span>s separated by <br/>.
        """
        level = self._get_heading_level(element)
        if self.mode == ConversionMode.NOTE: level = 2
        h = f'h{level}'
        title_text = " ".join(element.itertext()).strip() # type: ignore

        parent = element.getparent()
        if parent is not None:
            parent_level = self._get_heading_level(parent)
            # TODO: investigate usage of _current_title
            if parent_level == self.split_level - 1:
                self._current_title = title_text
                if self._converted_bodies:
                    last_doc = self._converted_bodies[-1]
                    self._converted_bodies[-1] = last_doc._replace(title=title_text)

        # TODO: remove inner <p> if only one exists (in post-processing?)

        new_element = Tag(h).create()
        copy_id(element, new_element)
        return new_element
    

    def _handle_image(self, element: etree._Element) -> etree._Element | None:
        # TODO: handle p>img as inline?, section>img as fullscreen?
        img_id = element.get(f'{{{NS.XLINK}}}href', '').lstrip('#')
        if not img_id or img_id not in self.binary_map:
            return None
        
        binary = self.binary_map[img_id]
        img_attrib = {'src': f'../{FN.IMAGES}/{binary.filename}'}
        dimensions = binary.dimensions
        if dimensions is not None:
            img_attrib.update({
                'data-width': str(dimensions[0]), 
                'data-height': str(dimensions[1]),
                'data-orientation': binary.orientation
            })
        if element_id := element.get('id'):
            img_attrib['id'] = element_id
        
        figure = etree.Element('figure', {'class': 'image'})
        etree.SubElement(figure, 'img', img_attrib)
        return figure

    
    def _handle_link(self, element: etree._Element) -> etree._Element | None:
        href = element.get(f'{{{NS.XLINK}}}href', '').lstrip('#')
        attrib = {}
        if href:
            attrib = {
                'href': f'#{href}',
                'id': f'{href}-ref'
            }
            link_type = element.get('type')
            if link_type:
                attrib['link-type'] = link_type

        link = etree.Element('a', attrib)
        return link
        return Tag('a', attrib).create()


    def _handle_default(self, element: etree._Element) -> etree._Element | None:
        """Handles simple tag conversions using the `tag_map`."""
        if self.mode == ConversionMode.NOTE:
            pass
        
        fb2_tag = get_tag_name(element)
        if fb2_tag in self.tag_map:
            html_tag, html_attrib = self.tag_map[fb2_tag]
        else:
            html_tag = 'div'
            html_attrib = {'class': fb2_tag}
        
        # Merge attributes with existing ones (typically only 'id', 'name')
        attrib = {str(k): str(v) for k, v in element.attrib.items()} 
        attrib.update(html_attrib or {})

        elem = etree.Element(html_tag, attrib)
        # return HTMLTag(html_tag, attrib).create()
        return elem
    

    @staticmethod
    def _get_heading_level(element: etree._Element) -> int:
        """Determines heading level by counting the number of <section> ancestors. """
        # The tag must be in the Clark notation {namespace}tag
        section_tag = f"{{{NS.FB2}}}section"
        depth = sum(1 for _ in element.iterancestors(section_tag))
        return min(depth, 6) or 1   # Min depth is 1, max is 6
    
    # --- Post-Processing Methods ---

    def _post_process(self, xhtml_body: etree._Element):
        """
        NEW: A dedicated method for cleaning up the generated XHTML tree.
        It uses native lxml methods for efficient and readable manipulation.
        """
        # 1. Handle <br> tags that were converted from <empty-line>
        # This is more robust as it uses iterfind and sibling navigation.
        for br in xhtml_body.iterfind(".//br"):
            parent = br.getparent()
            if parent is None: continue
            
            # If a <br> is the only thing in a <p>, give the <p> a special class
            # and remove the <br>. This is better for CSS styling.
            if parent.tag == 'p' and not parent.text and len(parent) == 1:
                parent.set('class', 'empty-line-p')
                parent.remove(br)

        # 2. Strip unwanted formatting from headings
        # etree.strip_tags is the perfect tool for this job.
        # Use a single XPath expression to find all heading levels.
        # The '|' operator acts as a union.
        for heading in xhtml_body.xpath('.//h1 | .//h2 | .//h3 | .//h4 | .//h5 | .//h6'): # type: ignore
            # etree.strip_tags(heading, 'em', 'strong', 'b', 'i')
            # Strip <p> from headings, unwrap its content. Multiple <p>s become <span>s with <br/>. Convert <empty-line> to <br/>.
            # Replace <empty-line> with <br>
            for empty_line in heading.iterfind(".//empty-line"):
                br = etree.Element('br')
                parent = empty_line.getparent()
                if parent is not None:
                    parent.replace(empty_line, br)

            if len(heading) == 1:
                if get_tag_name(heading[0]) == 'p':
                    # Single <p>: unwrap directly
                    unwrap_element(heading[0], heading)
                else:
                    log.debug(f"Heading contains single non-<p> element: <{get_tag_name(heading[0])}>")
            elif len(heading) > 1:
                # Multiple children: unwrap each <p> into <span> with <br/>
                for child in heading:
                    if get_tag_name(child) == 'p':
                        span = replace_element(child, 'span')
                        # Insert <br/> after the span if not the last child
                        if span != heading[-1]:
                            br = etree.Element('br')
                            heading.insert(heading.index(span) + 1, br)
                    else:
                        log.debug(f"Heading contains non-<p> element: <{get_tag_name(child)}>")

        # 3. Clean up note links (unwrap sup > a and a > sup)
        for a in xhtml_body.iterfind(".//a[@class='noteref']"):
            etree.strip_tags(a, 'sup') # Remove any <sup> inside <a>
            parent = a.getparent()
            if parent is not None and parent.tag == 'sup':
                grandparent = parent.getparent()
                if grandparent is not None:
                    # Replace the <sup> with its child <a>
                    grandparent.replace(parent, a)
  

    def _resolve_image_paths(self, xhtml_body: etree._Element):
        """Changes <img> placeholders to point to actual image files."""
        for img in xhtml_body.xpath('.//img[@data-fb2-id]'):    # type: ignore
            fb2_id = img.get('data-fb2-id')
            image_info = self.binary_map.get(fb2_id)
            if image_info:
                src = f"..{FN.IMAGES}/{image_info.filename}"
            else:
                src = "#"   # Fallback for missing images
                log.warning(f"Image source for ID '{fb2_id}' not found.")
            img.set('src', src)
            del img.attrib['data-fb2-id']   # Clean up temporary attribute


    def _resolve_note_links(self, xhtml_body: etree._Element):
        """Finds all note links, adds epub:type, and sets an ID."""
        for a in xhtml_body.xpath('.//a[starts-with(@href, "#")]'):     # type: ignore
            target_id = a.get('href', '#').lstrip('#')
            target_file = self.id_map.get(target_id)
            if target_file in ['notes.xhtml', 'comments.xhtml']:
                a.set(f'{{{NS.EPUB}}}type', 'noteref')
                # Set an ID on the link itself for the backlink to target
                if not a.get('id'):
                    a.set('id', f"noteref-{target_id}")





    # @staticmethod
    def _cleanup_markup(self, xhtml_body: etree._Element):
        """Performs final cleanup on the generated XHTML."""
        # 1. Handle <empty-line/>
        # add class="space-after" to the previous <p> or <div>
        for empty_line in xhtml_body.xpath("//*[local-name()='empty-line']"):   # type: ignore
            prev_el = empty_line.getprevious()
            next_el = empty_line.getnext()
            if all((el is not None) and (el.tag in ('p', 'div')) for el in [prev_el, next_el]):
                prev_el.set("class", (prev_el.get("class", "") + " space-after").strip())
            
            parent = empty_line.getparent()
            if parent is not None:
                parent.remove(empty_line)

        # 2. Unwrap sup>a and a>sup note links
        for a in xhtml_body.xpath(".//a[@class='noteref']"):    # type: ignore
            # Remove any child <sup> tags
            etree.strip_tags(a, 'sup')
            # If the <a> tag itself is wrapped in a <sup>, unwrap it
            parent = a.getparent()
            if parent is not None and parent.tag == 'sup':
                grandparent = parent.getparent()
                if grandparent is not None:
                    grandparent.replace(parent, a)

        # 3. Remove trailing whitespaces

        # 4. Remove <em>, <strong> from <h1..h6> and <p>.subtitle


    def _improve_typography(self, xhtml_body: etree._Element):
        # 1. Insert NBSP after/before first/last word inside <p>.
        first_word_length = 1
        last_word_length = 1

        # 4. Wrap short words at the start and the end of <p> into span.nobreak to avoid hyphenation. 
        first_word_length = 4
        last_word_length = 7

    # --- END of ElementConverter ---


def get_tag_name(element: etree._Element) -> str:
    return etree.QName(element.tag).localname

def copy_id(source: etree._Element, target: etree._Element):
    if id := source.get('id'): target.set('id', id)

def unwrap_element(element: etree._Element, parent: etree._Element):
    """Unwraps an element by moving its content to the parent and removing it."""
    # Move text
    parent.text = (parent.text or '') + (element.text or '')
    # Move children
    for child in list(element):
        parent.append(child)
    # Move tail
    parent.tail = (parent.tail or '') + (element.tail or '')
    # Remove <p>
    parent.remove(element)

def replace_element(element: etree._Element, new_tag: str) -> etree._Element:
    """Replaces an element with a new tag, preserving attributes and children."""
    parent = element.getparent()
    if parent is None:
        raise ValueError("Element has no parent; cannot replace.")
    
    new_element = Tag(new_tag, dict(element.attrib)).create()
    new_element.text = element.text
    for child in element:
        new_element.append(child)
    new_element.tail = element.tail

    parent.replace(element, new_element)
    return new_element