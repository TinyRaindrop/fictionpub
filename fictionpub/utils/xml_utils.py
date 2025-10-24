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

# --- Conversion helpers ---

def get_tag_name(element: etree._Element) -> str:
    """Returns tag name without a namespace prefix."""
    return etree.QName(element.tag).localname


def copy_id(source: etree._Element, target: etree._Element):
    """Sets target.id if source.id exists."""
    if id := source.get('id'): 
        target.set('id', id)


def get_attrib_dict(element: etree._Element) -> dict[str, str]:
    """Returns a proper dictionary of element attributes."""
    return {str(k): str(v) for k, v in element.attrib.items()} 


def unwrap_element(element: etree._Element, parent: etree._Element):
    """Unwraps an element by moving its content to the parent and removing it."""
    # Move text
    parent.text = (parent.text or '') + (element.text or '')
    # Move children
    # TODO: test this function! It probably appends children to the end
    for child in list(element):
        parent.append(child)
    # Move tail
    parent.tail = (parent.tail or '') + (element.tail or '')
    parent.remove(element)


def replace_element(element: etree._Element, new_tag: str) -> etree._Element:
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
