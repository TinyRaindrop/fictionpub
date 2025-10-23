"""
Post processing of converted to XHTML bodies.
"""
import logging

from lxml import etree

from . import typography
from ..utils.config import ConversionConfig, ConversionMode
from ..utils import xml_utils as xu

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
                if next_text: 
                    # move <p/div> text to backlink's tail
                    next_el.text = None
                    next_el.insert(0, backlink)
                    backlink.tail = next_text.lstrip()


    def _strip_heading_formatting(self):
        """Strips unwanted formatting from headings."""
        # TODO: p.subtitle as well?
        for heading in self.body.xpath('.//h1 | .//h2 | .//h3 | .//h4 | .//h5 | .//h6'): # type: ignore
            # Strip bold/italic tags. // Leave italics intact?
            etree.strip_tags(heading, 'em', 'strong', 'b', 'i')

            # Strip <p> from headings, unwrap its content. Multiple <p>s become <span>s with <br/>. Convert <empty-line> to <br/>.
            # Replace <empty-line> with <br>
            for empty_line in heading.iterfind(".//empty-line"):
                parent = empty_line.getparent()
                if parent is not None:
                    br = etree.Element('br')
                    parent.replace(empty_line, br)

            if len(heading) == 1:
                if xu.get_tag_name(heading[0]) == 'p':
                    # Single <p>: unwrap directly
                    xu.unwrap_element(heading[0], heading)
                else:
                    log.debug(f"Heading contains single non-<p> element: <{xu.get_tag_name(heading[0])}>")
            elif len(heading) > 1:
                # Multiple children: unwrap each <p> into <span> with <br/>
                for child in heading:
                    if xu.get_tag_name(child) == 'p':
                        span = xu.replace_element(child, 'span')
                        # Insert <br/> after the span if not the last child
                        if span != heading[-1]:
                            br = etree.Element('br')
                            heading.insert(heading.index(span) + 1, br)
                    else:
                        log.debug(f"Heading contains non-<p> element: <{xu.get_tag_name(child)}>")


    def _handle_empty_line(self):
        """
        Replaces `empty-line` elements with `class="space-after/before"` 
        on preceding/following `p or div`.
        Should be run after _strip_heading_formatting().
        """
        tags = ('p', 'div')
        for empty_line in self.body.iterfind(".//empty-line"):
            target_el = empty_line.getprevious()
            cls = ""

            # If previous element exists and is of valid type, use it
            if target_el is not None and target_el.tag in tags:
                cls = " space-after"
            else:
                # Otherwise, check the next element
                next_el = empty_line.getnext()
                if next_el is not None and next_el.tag in tags:
                    target_el = next_el
                    cls = " space-before"

            # If a valid target element was found, update the class
            if target_el is not None:
                el_cls = target_el.get("class", "").strip()
                target_el.set("class", (el_cls + cls))

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
                parent.replace(sup, a)


    def _remove_empty_elements(self):
        """Removes empty `p, div, span` elements."""
        for tag in ['p', 'div', 'span']:
            for el in self.body.xpath(f".//{tag}[not(node())]"):  # type: ignore
                parent = el.getparent()
                if parent is not None:
                    parent.remove(el)
                    log.debug(f"Removed empty {el} from {parent}.")


    @staticmethod
    def remove_sup_from_noteref(a: etree._Element):
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

