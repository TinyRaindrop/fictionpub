from lxml import etree

from .namespaces import Namespaces as NS

# --- Element find helpers ---

def elem_find(element: etree._Element | etree._ElementTree, tag, 
                namespaces=NS.FB2_MAP):
    """Helper to find an element with given <tag> using a namespace."""
    return element.find(tag, namespaces)


def elem_findall(element: etree._Element | etree._ElementTree, tag, 
                    namespaces=NS.FB2_MAP):
    """Helper to find all elements of <tag> using a namespace."""
    return element.findall(tag, namespaces)


def elem_findtext(element: etree._Element, tag, 
                    namespaces=NS.FB2_MAP, default=''):
    """Helper to find all elements of <tag> using a namespace."""
    return element.findtext(tag, default, namespaces)

# --- Metadata helpers ---

def get_person_name(author_element: etree._Element | None) -> str:
    """Helper to format a person's name from <first-name>, etc."""
    if author_element is None:
        return ""
    first = elem_findtext(author_element, 'fb:first-name')
    middle = elem_findtext(author_element, 'fb:middle-name')
    last = elem_findtext(author_element, 'fb:last-name')
    return " ".join(filter(None, [first, middle, last])).strip()


def get_metadata_tags(element: etree._Element, tag_list: list[str]) -> dict:
    """Finds text for each tag in a list, and returns a {tag: text} dictionary."""
    meta = {
        tag: text
        for tag in tag_list
        if (text := elem_findtext(element, f'fb:{tag}'))     # if not empty
    } 
    return meta
