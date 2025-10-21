"""
Post processing of converted to XHTML bodies.
"""
import logging

from lxml import etree

from .fb2_to_html_converter import ConversionMode
from ..utils import xml_utils as xu

log = logging.getLogger("fb2_converter")


class PostProcessor():
    """
    Post processing of converted XHTML. 
    Fixes unfinished element conversions, cleans up redundant tags,
    applies typographic improvements.
    """
    def __init__(self, xhtml_body: etree._Element, mode = ConversionMode.MAIN):
        self.xhtml_body = xhtml_body
        self.mode = mode


    def run(self):
        """Method to run for cleaning up the generated XHTML tree."""
        if self.mode == ConversionMode.NOTE:
            self._fix_note_backlinks()

        self._strip_heading_formatting()
        self._handle_empty_line()
        self._remove_empty_elements()
        self._clean_noterefs()
        self._improve_typography()


    def _fix_note_backlinks(self):
        """Moves backlinks in footnotes inside the first <p> or <div>."""
        for backlink in self.xhtml_body.iterfind(".//a[@class='backlink']"):
            aside = backlink.getparent()            
            next_el = backlink.getnext()
            if next_el is not None and xu.get_tag_name(next_el) in ['p', 'div']:
                next_text = next_el.text
                if next_text: 
                    # add leading space after backlink and move the text to tail
                    next_text = ' ' + next_text.strip()
                    next_el.text = None
                    next_el.insert(0, backlink)
                    backlink.tail = next_text


    def _strip_heading_formatting(self):
        """Strips unwanted formatting from headings."""
        # TODO: p.subtitle as well?
        for heading in xhtml_body.xpath('.//h1 | .//h2 | .//h3 | .//h4 | .//h5 | .//h6'): # type: ignore
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


    def _remove_empty_elements(self):
        """Removes empty <p>, <div>, <span> elements."""
        for tag in ['p', 'div', 'span']:
            for el in self.xhtml_body.xpath(f".//{tag}[not(node())]"):  # type: ignore
                parent = el.getparent()
                if parent is not None:
                    parent.remove(el)
                    log.debug(f"Removed empty {el} from {parent}.")


    def _handle_empty_line(self):
        """Replaces <empty-line/> elements with class="space-after" on preceding <p> or <div>."""
        for empty_line in self.xhtml_body.xpath("//*[local-name()='empty-line']"):   # type: ignore
            prev_el = empty_line.getprevious()
            next_el = empty_line.getnext()
            if all((el is not None) and (el.tag in ('p', 'div')) for el in [prev_el, next_el]):
                prev_el.set("class", (prev_el.get("class", "") + " space-after").strip())
            
            parent = empty_line.getparent()
            if parent is not None:
                parent.remove(empty_line)


    def _clean_noterefs(self):
        """Removes<sup> from note references (unwrap sup > a and a > sup)."""
        for a in self.xhtml_body.iterfind(".//a[@class='noteref']"):
            # Remove any child <sup> tags from <a>
            etree.strip_tags(a, 'sup')
            # If the <a> tag itself is wrapped in a <sup>, unwrap it
            parent = a.getparent()
            if parent is not None and parent.tag == 'sup':
                grandparent = parent.getparent()
                if grandparent is not None:
                    # Replace the <sup> with its child <a>
                    grandparent.replace(parent, a)


    def _improve_typography(self):
        """Typography improvements like non-breaking spaces and special word hyphenation."""
        # 1. Insert NBSP after/before first/last word inside <p>.
        word_length_nbsp = (1, 1)   # first, last word lengths
        # 2. Wrap short words at the start and the end of <p> into <span>.nobreak to avoid hyphenation. 
        word_length_nobreak = (4, 7)

        def process_paragraphs(xhtml_body):
            for p in xhtml_body.iterfind(".//p"):
                # Using itertext to get text and tags together
                words = []
                for text in p.itertext():  # Iterate through the text content
                    words.extend(text.split())  # Split the text into words and collect them

                if not words:
                    continue

                # Check the first and last words
                first_word, last_word = words[0], words[-1]

                # Create a new list to hold the processed words
                processed_words = []

                # Process the first word for NBSP and nobreak
                if len(first_word) == word_length_nbsp[0]:
                    processed_words.append(f"{first_word}\u00A0")  # Add NBSP after the first word
                elif len(first_word) <= word_length_nobreak[0]:
                    processed_words.append(f'<span class="nobreak">{first_word}</span>')  # Wrap with span.nobreak
                else:
                    processed_words.append(first_word)

                # Add the middle words as they are
                processed_words.extend(words[1:-1])

                # Process the last word for NBSP and nobreak
                if len(last_word) == word_length_nbsp[1]:
                    processed_words.append(f"\u00A0{last_word}")  # Add NBSP before the last word
                elif len(last_word) <= word_length_nobreak[1]:
                    processed_words.append(f'<span class="nobreak">{last_word}</span>')  # Wrap with span.nobreak
                else:
                    processed_words.append(last_word)

                # Now, we need to reconstruct the paragraph with modified words
                p.clear()  # Clear the original content of the <p> tag
                p.text = " ".join(processed_words)  # Set the modified text as the new content


