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
    to specific methods based on the FB2 tag name. 
    It also manages the splitting of content into multiple documents based on section levels.

    When operating in **NOTE** mode we must take extra care:
    * preserve the top‑level heading if present and surface it as the
      document title instead of silently overwriting it later.
    * distinguish between true footnote sections (usually have an `id`)
      and grouping/container sections so that nested structures are retained.
    * use the passed `id_map` to recognize links that point into the note
      bodies and mark them as `link-type="note"` so the builder can style
      them properly.
    """
    
    def __init__(self, binary_map: dict, id_map: dict, config: ConversionConfig):
        """
        Initializes the converter with contextual data and sets up the
        dispatch maps for tag conversion.

        Args:
            binary_map: mapping of FB2 image IDs to BinaryInfo objects.
            id_map: mapping of every FB2 element id to the name of the body
                where it was defined.  This is used for automatic
                noteref/link-type detection during conversion.
            config: user-supplied conversion configuration.
        """
        self.binary_map: dict[str, BinaryInfo] = binary_map
        # keep the original id_map for noteref detection
        self.id_map = id_map
        # store configuration for later use
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
        Converts a full FB2 `body` element and runs post-processing.
        For MAIN mode, this can return multiple documents if splitting occurs.

        In **NOTE** mode the returned ``ConvertedBody.title`` will be
        adjusted after conversion to match the first heading found within
        the body (typically the "Notes"/"Footnotes" label) so that the
        builder can display an appropriate page title without having to
        override it later.
        """        
        self.mode = mode
        self._converted_bodies: list[ConvertedBody] = []
        self._level_counters = [0] * 6
        
        # Initialize the base document count before hitting the first section
        if self.mode == ConversionMode.MAIN:
            self._level_counters[0] = 1

        self._current_title = "Content"

        self._start_new_body(fb2_body, level=1)
        
        # Convert while splitting
        # TODO: convert first, insert split markers, split later?
        for child in fb2_body:
            self._recursive_convert(child, self._current_body)

        # Post-process all converted bodies
        for body_obj in self._converted_bodies:
            PostProcessor(self.config, self.mode).run(body_obj.body)

        # NOTE mode tweaks -------------------------------------------------
        if self.mode == ConversionMode.NOTE:
            adjusted: list[ConvertedBody] = []
            for body_obj in self._converted_bodies:
                title = body_obj.title
                # look for the first heading element inside the body
                first_heading = None
                for el in body_obj.body:
                    tag = xu.get_tag_name(el)
                    if tag.startswith('h') and len(tag) == 2 and tag[1].isdigit():
                        first_heading = el
                        break
                if first_heading is not None and first_heading.text:
                    # use the heading text if it is not trivial
                    text = first_heading.text.strip()
                    if text and text != title:
                        title = text
                adjusted.append(body_obj._replace(title=title))
            self._converted_bodies = adjusted

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

        # Generate hierarchical name based on the counters
        name_parts = [str(c) for c in self._level_counters[:level] if c > 0]
        if not name_parts: 
            name_parts = [str(self._level_counters[0] or 1)]
        
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

        # --- Structural Section Unwrapping & ID Preservation ---
        if tag == 'section':
            element_id = fb2_element.get('id')

            if self.mode == ConversionMode.MAIN:
                level = self._get_heading_level(fb2_element)
                
                if level <= self.split_level:
                    # ONLY split if the current document actually has content.
                    if self._has_actual_content():
                        level_index = level - 1
                        if level_index < len(self._level_counters):
                            self._level_counters[level_index] += 1
                            # Reset sub-level counters
                            for i in range(level_index + 1, len(self._level_counters)):
                                self._level_counters[i] = 0
                                
                        self._start_new_body(fb2_element, level)
                    else:
                        # Adopt the empty document to avoid blank pages.
                        level_index = level - 1
                        if level_index < len(self._level_counters) and self._level_counters[level_index] == 0:
                            self._level_counters[level_index] = 1
                            
                        # Update the file ID of the adopted document to match the correct hierarchy
                        new_file_id = self._generate_part_name(fb2_element, level)
                        self._converted_bodies[-1] = self._converted_bodies[-1]._replace(file_id=new_file_id)

                    target_parent = self._current_body
                else:
                    target_parent = xhtml_parent
                
                # Preserve section ID before unwrapping
                if element_id:
                    target_parent.append(etree.Element('div', {'id': element_id, 'class': 'section-anchor'}))

                for child in fb2_element:
                    self._recursive_convert(child, target_parent)
                return

            elif self.mode == ConversionMode.NOTE:
                has_child_section = any(xu.get_tag_name(ch) == 'section' for ch in fb2_element)
                
                # If it's a structural/grouping section (has children or lacks an ID), unwrap it.
                if not element_id or has_child_section:
                    # Preserve section ID before unwrapping
                    if element_id:
                        xhtml_parent.append(etree.Element('div', {'id': element_id, 'class': 'section-anchor'}))
                    
                    for child in fb2_element:
                        self._recursive_convert(child, xhtml_parent)
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
        """
        Converts atomic footnote sections into `<aside>` elements.
        Note: Structural sections are unwrapped upstream in `_recursive_convert`.
        """
        element_id = element.get('id')
        
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
            link_attrib = {
                'href': f'#{element_id}-ref',   # point to the note reference
                'class': 'backlink',
                'id': f'{element_id}-back',
                f'{{{NS.EPUB}}}type': 'backlink',
            }
            backlink = etree.Element('a', link_attrib)
            backlink.text = f"{title_text}."  # append a dot
            aside.insert(0, backlink)
            element.remove(title_el)
            
        return aside
    

    def _handle_title(self, element: etree._Element) -> etree._Element | None:
        """
        Converts `title` tag to h1..h6 based on nesting level.

        """
        parent = element.getparent()
        if parent is None:
            log.warning("Found <title> without a parent. Skipping.")
            return None

        # Check if this is a top-level body title
        if xu.get_tag_name(parent) == 'body':
            attrib = {'class': 'fb2title'}
            
            # Preserve the ID if the title has one
            element_id = element.get('id')
            if element_id:
                attrib['id'] = element_id
                
            div_title = etree.Element('div', attrib)

            return div_title

        # <poem> title => p.subtitle
        elif xu.get_tag_name(parent) == "poem":
            return self._handle_default(element, convert_as='subtitle')
            
        level = self._get_heading_level(element)
        adjusted_level = max(1, level-1)
        h = f'h{adjusted_level}'

        title_text = " ".join(element.itertext()).strip() # type: ignore
        
        # Drop titles that are empty or contain only whitespace
        if not title_text:
            log.debug("Found empty <title>. Skipping.")
            return None
        
        parent_level = self._get_heading_level(parent)
        # Assign this title to the current document if it matches the split threshold
        if parent_level <= self.split_level:
            self._current_title = title_text
            if self._converted_bodies:
                last_doc = self._converted_bodies[-1]
                self._converted_bodies[-1] = last_doc._replace(title=title_text)

        new_element = etree.Element(h)
        xu.copy_id(element, new_element)
        return new_element
    

    def _handle_image(self, element: etree._Element) -> etree._Element | None:
        """
        Converts `image` tag to `figure`.
        Saves dimensions as attributes.
        """
        # TODO: handle p>img as inline?, section>img as fullscreen?
        img_id = element.get(f'{{{NS.XLINK}}}href', '').lstrip('#')
        if not img_id or img_id not in self.binary_map:
            return None
        
        binary = self.binary_map[img_id]

        img_attrib = {'src': f'../{FN.IMAGES}/{binary.filename}'}
        fig_attrib = {'class': 'image'}

        dimensions = binary.dimensions
        if dimensions is not None:
            img_attrib.update({
                'data-width': str(dimensions[0]), 
                'data-height': str(dimensions[1]),
                'data-orientation': binary.orientation
            })
            
            fig_attrib['class'] += f" {binary.orientation}".strip()
        
        img = etree.Element('img', img_attrib)
        xu.copy_id(element, img)
        
        parent = element.getparent()
        if parent is not None and xu.get_tag_name(parent) in ['p', 'subtitle']:
            # Inline <img> inside a paragraph.
            return img
        else:
            # Otherwise, wrap it in a <figure>.
            figure = etree.Element('figure', fig_attrib)
            figure.append(img)
            return figure

    
    def _handle_link(self, element: etree._Element) -> etree._Element | None:
        """Creates `a` and copies over href.

        When the target of an internal link lives inside a note/comment body
        we automatically tag it with ``link-type="note"``.  The builder
        later uses that attribute to apply the correct ``noteref`` class and
        distinguish between footnotes and endnotes/comments.
        """
        # log.debug(f"_handle_link invoked on element: {xu.get_tag_name(element)}, attrs={element.attrib}")
        href = element.get(f'{{{NS.XLINK}}}href') or element.get('href')
        attrib = {}
        # defaults so we can refer to them later even if href is None
        is_external = False
        target_id: str = ''
        
        if href:
            is_external = not href.startswith("#")
            # Save prefix and clear it from href
            prefix = "" if is_external else "#"
            target_id = href.lstrip("#")

            attrib = {
                'href': f'{prefix}{target_id}'
            }

            # propagate FB2 type attribute if present
            link_type = element.get('type')
            if link_type:
                attrib['link-type'] = link_type

            # automatic detection using id_map
            if not is_external and target_id:
                body_name = self.id_map.get(target_id)
                # log.debug(f"_handle_link: target_id={target_id}, body_name={body_name}")
                if body_name and body_name.lower() not in ('main', ''):
                    # any non-main body is assumed to be notes/comments
                    # mark the link unambiguously as a note reference
                    attrib['link-type'] = 'note'

        else:
            attrib={'class': 'empty'}
        
        link = etree.Element('a', attrib)
        xu.copy_id(element, link)

        # if this is an internal link pointing into a notes/comments body,
        # make sure the reference has an ID so that backlinks from the note
        # known as <a class="backlink" href="#...-ref"> can resolve.
        if not is_external and target_id:
            # always generate an ID for internal links, even for repeated references
            if link.get('id') is None:
                    count = self.note_ref_counters.get(target_id, 0) + 1
                    self.note_ref_counters[target_id] = count
                    if count == 1:
                        new_id = f"{target_id}-ref"
                    else:
                        new_id = f"{target_id}-ref-{count}"
                    link.set('id', new_id)
                    # log.debug(f"internal link id assigned: {new_id} (target {target_id})")
        return link


    def _handle_style(self, element: etree._Element) -> etree._Element | None:
        """Converts `style` tag to `span` with class=name."""
        name = element.get('name')
        if not name:
            return None
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
        """Determines heading level by counting the number of `<section>` ancestors.

        The returned value is clamped to the range 1–6.  Previously note mode
        forced every heading to level 1; we now honour the original nesting so
        that authors can create sub‑sections inside a notes body if they wish.
        """
        section_tag = f"{{{NS.FB2}}}section"
        depth = sum(1 for _ in element.iterancestors(section_tag))
        # always treat the body/first section as level‑1 and increment for each ancestor
        level = depth + 1
        return min(level, 6) or 1


    def _has_actual_content(self) -> bool:
        """Checks if the current document has substantial content, ignoring invisible anchors."""
        if self._current_body.text and self._current_body.text.strip():
            return True
        
        for child in self._current_body:
            # If we find anything other than our invisible ID anchors, it has content
            if child.get('class') != 'section-anchor':
                return True
            # Even if it's an anchor, check if it somehow has text attached
            if child.text and child.text.strip():
                return True
            if child.tail and child.tail.strip():
                return True
        
        return False

    # --- END of ElementConverter ---
