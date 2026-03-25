"""
Post processing of converted to XHTML bodies.
"""

import logging
from typing import NamedTuple

from lxml import etree

from ..models.conversion import ConversionConfig
from ..models.structures import BodyType
from ..utils import xml_utils as xu

# Post processing plugins. Must work on xhtml_body
from . import typography

log = logging.getLogger("fb2_converter")


class Tag(NamedTuple):
    name: str
    clss: str = ""

    @classmethod
    def from_el(cls, el: etree._Element | None) -> "Tag":
        if el is None:
            return Tag("None")
        name = xu.get_tag_name(el)
        clss = el.attrib.get("class", "")
        return Tag(name, clss)

    def matches(self, tag_list: list) -> bool:
        """Returns True if Tag is in provided list."""
        return any(self.name == tag.name and tag.clss in self.clss for tag in tag_list)


class PostProcessor:
    """
    Post processing of converted XHTML.
    Fixes unfinished element conversions, cleans up redundant tags,
    applies typographic improvements.
    """

    def __init__(self, config: ConversionConfig):
        self.config = config

    def run(self, xhtml_body: etree._Element, body_type: BodyType = BodyType.MAIN) -> None:
        """Method to run for cleaning up the generated XHTML tree."""
        self.body = xhtml_body

        if body_type in (BodyType.NOTE, BodyType.COMMENT):
            self._fix_note_backlinks()

        self._strip_heading_formatting()
        self._handle_empty_line()
        # TODO: test whether this is even necessary
        self._remove_empty_elements()

        if self.config.improve_typography:
            typography.improve_typography(
                self.body,
                self.config.word_len_nbsp_range,
                self.config.word_len_nobreak_range,
            )

    def _fix_note_backlinks(self) -> None:
        """Moves backlinks in footnotes inside the first `p or div`."""
        for backlink in self.body.iterfind(".//a[@class='backlink']"):
            next_el = backlink.getnext()
            if next_el is not None and xu.get_tag_name(next_el) in ["p", "div"]:
                next_text = next_el.text or ""
                # move <p/div> text to backlink's tail
                next_el.text = None
                next_el.insert(0, backlink)
                backlink.tail = "\u00a0" + next_text  # add NBSP
            else:
                parent = backlink.getparent()
                parent_id = parent.get("id") if parent is not None else None
                log.info(f"Backlink could not be placed into <aside> id={parent_id}")

    def _strip_heading_formatting(self) -> None:
        """
        Strips unwanted formatting from headings.
        Strips `<p>`, unwraps its content. Multiple `<p>`s become `<span>`s with `<br/>`.
        """
        # h1..h6, p.subtitle
        heading_tags = [f"h{i}" for i in range(1, 7)]
        heading_tags.append('p[@class="subtitle"]')
        heading_query = " | ".join([f".//{tag}" for tag in heading_tags])

        for heading in self.body.xpath(heading_query):  # type: ignore
            # 1. Strip bold/italic tags. // Leave italics intact?
            etree.strip_tags(heading, "em", "strong", "b", "i")

            h_length = len(heading)
            # 2. Single <p>: unwrap directly
            if h_length == 1:
                if xu.get_tag_name(heading[0]) == "p":
                    etree.strip_tags(heading, "p")
                    heading.text = heading.text.strip()
                else:
                    log.debug(
                        f"Heading contains single non-<p> element: <{xu.get_tag_name(heading[0])}>"
                    )

            # 3. Multiple children: unwrap each <p> into <span> with <br/>
            elif h_length > 1:
                # strip leading whitespace
                if heading.text:
                    heading.text = heading.text.lstrip()

                for child in heading:
                    if xu.get_tag_name(child) == "p":
                        span = xu.replace_tag(child, "span")
                        # Insert <br/> after the span if not the last child
                        if span != heading[-1]:
                            br = etree.Element("br")
                            heading.insert(heading.index(span) + 1, br)
                    else:
                        log.debug(
                            f"Heading contains non-<p> element: <{xu.get_tag_name(child)}>"
                        )

                # strip trailing whitespace from the last child
                if heading[-1].tail:
                    heading[-1].tail = heading[-1].tail.rstrip()

    def _handle_empty_line(self) -> None:
        """
        Converts necessary `empty-line`, discards redundant ones.
        Replaces `empty-line` with `class="space-after/before"` on a sibling element.
        Inside titles, replaces `empty-line` with `br`.
        """
        heading_tags: list[Tag] = [Tag(f"h{i}") for i in range(1, 7)]
        heading_tags.append(Tag("p", "subtitle"))
        excl_tags: list[Tag] = [Tag("figure"), Tag("div", "poem")]
        excl_tags.extend(heading_tags)

        for empty_line in self.body.iterfind(".//empty-line"):
            parent = empty_line.getparent()
            if parent is None:
                log.warning("<empty-line> has no parent. Skipping.")
                continue

            # 1. If empty-line is the last child or is followed by another empty-line
            next_el = empty_line.getnext()
            if next_el is None or xu.get_tag_name(next_el) == "empty-line":
                parent.remove(empty_line)
                continue

            # 2. Inside titles - convert to <br/> or remove
            if Tag.from_el(parent).matches(heading_tags):
                parent.replace(empty_line, etree.Element("br"))

            # 3. As spacers between other elements
            else:
                prev_el = empty_line.getprevious()
                neighbor_tags = [
                    Tag.from_el(el) for el in [prev_el, next_el] if el is not None
                ]
                if any(tag.matches(excl_tags) for tag in neighbor_tags):
                    # Skip empty-line around excluded tags
                    parent.remove(empty_line)
                    continue

                target_el = None
                cls = ""

                # If previous element exists and is of valid type, use it
                if prev_el is not None:
                    target_el = prev_el
                    cls = "space-after"
                # Otherwise, check the next element
                elif next_el is not None:
                    target_el = next_el
                    cls = "space-before"

                # If a valid target element was found, update the class
                if target_el is not None:
                    xu.add_class(target_el, cls)

                parent.remove(empty_line)

    def _remove_empty_elements(self) -> None:
        """Removes empty elements, handling whitespace and nested structures."""
        tags = ["p", "div", "span", "em", "strong"]
        tag_conditions = " or ".join([f"self::{tag}" for tag in tags])
        xpath_query = f".//*[{tag_conditions}][not(*) and normalize-space()='' and not(@id)]"
        
        # While loop for multiple passes to remove nested empty elements
        elements_removed = True
        while elements_removed:
            elements_removed = False
            
            for el in self.body.xpath(xpath_query):  # type: ignore
                parent = el.getparent()
                if parent is not None:
                    # Preserve tail
                    if el.tail:
                        previous = el.getprevious()
                        if previous is not None:
                            previous.tail = (previous.tail or "") + el.tail
                        else:
                            parent.text = (parent.text or "") + el.tail
                    
                    parent.remove(el)
                    elements_removed = True
                    log.debug(f"Removed empty <{el.tag}> from <{parent.tag}>.")
