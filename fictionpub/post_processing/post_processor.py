"""
Post processing of converted to XHTML bodies.
"""
import logging

from lxml import etree

from ..utils.config import ConversionConfig, ConversionMode
from ..utils import xml_utils as xu

# Post processing plugins. Must work on xhtml_body
from . import typography


log = logging.getLogger("fb2_converter")


class PostProcessor():
    """
    Post processing of converted XHTML. 
    Fixes unfinished element conversions, cleans up redundant tags,
    applies typographic improvements.
    """
    def __init__(self, config: ConversionConfig, mode = ConversionMode.MAIN):
        self.config = config
        self.mode = mode


    def run(self, xhtml_body: etree._Element):
        """Method to run for cleaning up the generated XHTML tree."""
        self.body = xhtml_body

        if self.mode == ConversionMode.NOTE:
            self._fix_note_backlinks()

        self._strip_heading_formatting()
        self._handle_empty_line()
        self._remove_empty_elements()
        self._clean_noterefs()

        if self.config.improve_typography:
            typography.improve_typography(
                self.body,
                self.config.word_len_nbsp_range,
                self.config.word_len_nobreak_range
            )


    def _fix_note_backlinks(self):
        """Moves backlinks in footnotes inside the first `p or div`."""
        for backlink in self.body.iterfind(".//a[@class='backlink']"):
            next_el = backlink.getnext()
            if next_el is not None and xu.get_tag_name(next_el) in ['p', 'div']:
                next_text = next_el.text
                # move <p/div> text to backlink's tail
                next_el.text = None
                next_el.insert(0, backlink)
                backlink.tail = next_text


    def _strip_heading_formatting(self):
        """
        Strips unwanted formatting from headings.
        Strips `<p>`, unwraps its content. Multiple `<p>`s become `<span>`s with `<br/>`.
        """
        # h1..h6, p.subtitle
        heading_tags = [f'h{i}' for i in range(1, 6)]
        heading_tags.append('p[@class="subtitle"]')
        heading_query = " | ".join([f".//{tag}" for tag in heading_tags])
        
        for heading in self.body.xpath(heading_query):  # type: ignore
            # 1. Strip bold/italic tags. // Leave italics intact?
            etree.strip_tags(heading, 'em', 'strong', 'b', 'i')
            
            # 2. Single <p>: unwrap directly
            if len(heading) == 1:
                if xu.get_tag_name(heading[0]) == 'p':
                    xu.unwrap_element(heading[0], heading)
                else:
                    log.debug(f"Heading contains single non-<p> element: <{xu.get_tag_name(heading[0])}>")

            # 3. Multiple children: unwrap each <p> into <span> with <br/>
            elif len(heading) > 1:
                for child in heading:
                    if xu.get_tag_name(child) == 'p':
                        span = xu.replace_tag(child, 'span')
                        # Insert <br/> after the span if not the last child
                        if span != heading[-1]:
                            br = etree.Element('br')
                            heading.insert(heading.index(span) + 1, br)
                    else:
                        log.debug(f"Heading contains non-<p> element: <{xu.get_tag_name(child)}>")


    def _handle_empty_line(self):
        """
        Converts necessary `empty-line`, discards redundant ones.
        Replaces `empty-line` with `class="space-after/before"` on a sibling element.
        Inside titles, replaces `empty-line` with `br`.
        """
        target_tags = ('p', 'div')
    
        # h1..h6, p.subtitle
        heading_tags = [f'h{i}' for i in range(1, 6)]
        heading_tags.append('p[@class="subtitle"]') # TODO: this will not match 'if in' check
        excl_tags = ['figure']
        excl_tags.extend(heading_tags)

        for empty_line in self.body.iterfind(".//empty-line"):
            parent = empty_line.getparent()
            if parent is None: 
                log.warning("<empty-line> has no parent. Skipping.")
                continue

            # 1. Inside titles - convert to <br/> or remove
            if xu.get_tag_name(parent) in heading_tags:
                next_el = empty_line.getnext()
                # If empty-line is the last child or is followed by another empty-line
                if next_el is None or xu.get_tag_name(next_el) == 'empty-line':
                    parent.remove(empty_line)
                    continue          
                
                br = etree.Element('br')
                parent.replace(empty_line, br)

            # 2. As spacers between other elements
            else:
                # TODO: check if both prev and next are in excl_tags (empty-line around figure)
                target_el = empty_line.getprevious()
                cls = ""

                # If previous element exists and is of valid type, use it
                if target_el is not None and target_el.tag not in excl_tags:
                    cls = "space-after"
                else:
                    # Otherwise, check the next element
                    next_el = empty_line.getnext()
                    if next_el is not None and next_el.tag not in excl_tags:
                        target_el = next_el
                        cls = "space-before"

                # If a valid target element was found, update the class
                if target_el is not None:
                    el_cls = target_el.get("class", "")
                    target_el.set("class", " ".join((el_cls, cls)).strip())

                parent = empty_line.getparent()
                if parent is not None:
                    parent.remove(empty_line)


    def _clean_noterefs(self):
        """Removes `sup` from note references (unwrap `sup > a` and `a > sup`)."""
        # TODO: remove this method
        # class="noteref" doesn't exist at this stage, it's added later in EpubBuilder
        for sup in self.body.iterfind('.//sup'):
            parent = sup.getparent()
            if parent is None: continue
            # a > sup
            if parent.tag == 'a':
                etree.strip_tags(parent, 'sup')
            # sup > a
            elif len(sup) == 1 and sup[0].tag == 'a':
                a = sup[0]
                a.tail = sup.tail
                parent.replace(sup, a)


    def _remove_empty_elements(self):
        """Removes empty elements."""
        for tag in ['p', 'div', 'span', 'em', 'strong']:
            # TODO: verify that xpath matches all empty elements without text
            for el in self.body.xpath(f".//{tag}[not(node())]"):  # type: ignore
                parent = el.getparent()
                if parent is not None:
                    parent.remove(el)
                    log.debug(f"Removed empty {el} from {parent}.")


    @staticmethod
    def remove_sup_from_noteref(a: etree._Element): # TODO: remove?
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

