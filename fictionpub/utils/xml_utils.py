from lxml import etree

from ..models import namespaces as NS

# -------------------------------
# Element find helpers


def elem_find(
    element: etree._Element | etree._ElementTree, tag, namespaces=NS.FB2_MAP
) -> etree._Element | None:
    """Helper to find an element with given <tag> using a namespace."""
    return element.find(tag, namespaces)


def elem_findall(
    element: etree._Element | etree._ElementTree, tag, namespaces=NS.FB2_MAP
) -> list[etree._Element]:
    """Helper to find all elements of <tag> using a namespace."""
    return element.findall(tag, namespaces)


def elem_findtext(element: etree._Element, tag, namespaces=NS.FB2_MAP, default="") -> str:
    """Helper to find all elements of <tag> using a namespace."""
    return element.findtext(tag, default, namespaces)


# -------------------------------
# Metadata helpers


def get_person_name(author_element: etree._Element | None) -> str:
    """Helper to format a person's name from <first-name>, etc."""
    if author_element is None:
        return ""
    first = elem_findtext(author_element, "fb:first-name")
    middle = elem_findtext(author_element, "fb:middle-name")
    last = elem_findtext(author_element, "fb:last-name")
    return " ".join(filter(None, [first, middle, last])).strip()


def get_metadata_tags(element: etree._Element, tag_list: list[str]) -> dict:
    """Finds text for each tag in a list, and returns a {tag: text} dictionary."""
    meta: dict[str, str] = {
        tag: text
        for tag in tag_list
        if (text := elem_findtext(element, f"fb:{tag}"))  # if not empty
    }
    return meta


# -------------------------------
# Tag/attribute manipulation


def get_tag_name(element: etree._Element) -> str:
    """Returns tag name without a namespace prefix."""
    return etree.QName(element.tag).localname


def copy_id(source: etree._Element, target: etree._Element) -> None:
    """Sets target.id if source.id exists."""
    if id := source.get("id"):
        target.set("id", id)


def get_attrib_dict(element: etree._Element) -> dict[str, str]:
    """Returns a proper dictionary of element attributes."""
    return {str(k): str(v) for k, v in element.attrib.items()}


def replace_tag(element: etree._Element, new_tag: str) -> etree._Element:
    """Replaces an element with a new tag, preserving attributes and children."""
    parent = element.getparent()
    if parent is None:
        raise ValueError(f"Element {element.tag} has no parent; cannot replace.")

    attrib = get_attrib_dict(element)
    new_element = etree.Element(new_tag, attrib)
    # Copy text
    new_element.text = element.text
    for child in element:
        new_element.append(child)
    new_element.tail = element.tail

    parent.replace(element, new_element)
    return new_element


def add_class(el: etree._Element, cls: str) -> None:
    """Adds a class to an element, ensuring no duplicates."""
    current_class = set(el.get("class", "").split())
    if cls not in current_class:
        current_class.add(cls)
        el.set("class", " ".join(current_class))


def remove_attr(element: etree._Element, name: str) -> None:
    """Removes an argument if it exists."""
    if name in element.attrib:
        del element.attrib[name]


# -------------------------------
# Text extraction


def itertext(el: etree._Element) -> str | None:
    """Returns all text content in the element subtree as a string."""
    if el is None:
        return None
    result = " ".join(t.strip() for t in el.itertext() if t.strip())  # type: ignore
    return result or None


def itertext_separated(el: etree._Element | None) -> str | None:
    """
    Returns text content in the element subtree, separated by newlines.
    Accepts both FB2 XML and converted XHTML elements.
    """
    if el is None:
        return None

    # FB2 / XHTML tags which would be separated by a newline.
    block_tags = {
        "div",
        "p",
        "v",
        "subtitle",
        "text-author",
        "empty-line",
        "th",
        "td",
        "title",
        "epigraph",
        "blockquote",
        "poem",
        "stanza",
        "q",
    }
    block_tags.update({f"h{i}" for i in range(1, 7)})

    def _walk(node: etree._Element):
        if node is None:
            return

        tag = get_tag_name(node)
        is_block = tag in block_tags

        if node.text:
            yield node.text

        for child in node:
            yield from _walk(child)

        if is_block:
            yield "\n"

        if node.tail:
            yield node.tail

    # Join everything into one string with \n marking the boundaries
    raw_text = "".join(_walk(el))

    # Clean whitespaces
    clean_lines = []
    for line in raw_text.split("\n"):
        clean_line = line.strip()
        if clean_line:
            clean_lines.append(clean_line)

    # Join with one newline
    return "\n".join(clean_lines) or None


# -------------------------------
# Debug utils


def pretty_print_xml(element: etree._Element | etree._ElementTree) -> str:
    """Returns a pretty-printed XML string of the element/tree."""
    # return etree.tostring(element, pretty_print=True, encoding='utf-8').decode('utf-8')
    return etree.tostring(element, pretty_print=True, encoding="unicode")
