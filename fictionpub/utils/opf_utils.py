from datetime import datetime, timezone
from lxml import etree

from ..utils.namespaces import Namespaces as NS


def _add_dc_element(parent: etree._Element, tag: str, value: str, element_id=None):
    """Creates a Dublin Core element if the text is valid."""
    if value:
        element = etree.SubElement(parent, f"{{{NS.DC}}}{tag}")
        element.text = str(value)
        if element_id:
            element.set("id", element_id)
        return element
    return None


def _add_meta_property(parent: etree._Element, property: str, value: str, id: str = '', refines: str = '', scheme: str = ''):
    """
    Adds a <meta> element that refines a DC element via its ID.
    Id: this <meta> tag's id. Refines: id of an element which is refined.
    """
    # Ensure the required attributes have values before creating the tag
    if not all([property, value]) or not any([id, refines]):
        return
        
    attrs = {
        key: value
        for key, value in {
            "refines": f"#{refines}" if refines else None,
            "property": property,
            "id": id,
            "scheme": scheme,
        }.items()
        if value is not None
    }

    meta_tag = etree.SubElement(parent, "meta", attrib=attrs)
    meta_tag.text = str(value)


def fill_opf_metadata(meta_element, metadata):
    """Fills the OPF metadata section from a dictionary."""
    title = metadata.get("title")
    if title:
        _add_dc_element(meta_element, "title", metadata.get("title"), element_id="main-title")
        _add_meta_property(meta_element, property="title-type", value="main", refines="main-title")

    author = metadata.get("author")
    if author:
        _add_dc_element(meta_element, "creator", author, element_id="author")
        _add_meta_property(meta_element, property="role", value="aut", refines="author", scheme="marc:relators") 
        # 'aut' = Author

    # Skipping original author/title, but it will be displayed on copyright page.
    """
    original_title = metadata.get('src-title-info', {}).get('title')
    if original_title and original_title != title:
        orig_title_el = _add_dc_element(meta_element, "title", original_title, element_id="orig-title")
        _add_meta_property(meta_element, prop="title-type", value="original", refines_id="orig-title")

    original_author = metadata.get('src-title-info', {}).get('author')
    if original_author and original_author != author:
        _add_dc_element(meta_element, "contributor", original_author, element_id="orig-author")
        _add_meta_property(meta_element, prop="role", value="aut", refines_id="orig-author", scheme="marc:relators")
    """    

    # metadata['producer'] is never set
    producer_name = metadata.get("producer")    # EPUB producer
    if producer_name:
        _add_dc_element(meta_element, "contributor", producer_name, element_id="producer")
        _add_meta_property(meta_element, property="role", value="bkp", refines="producer", scheme="marc:relators",)
        # 'bkp' = Book Producer

    book_id = metadata.get('id')
    if book_id:
        _add_dc_element(meta_element, "identifier", f"urn:uuid:{book_id}")

    isbn = metadata.get("publish-info", {}).get("isbn")
    if isbn:
        _add_dc_element(meta_element, "identifier", f"urn:isbn:{isbn}")
    
    _add_dc_element(meta_element, "publisher", metadata.get("publish-info", {}).get("publisher"))
    _add_dc_element(meta_element, "date", metadata.get("publish-info", {}).get("year"))
    _add_dc_element(meta_element, "language", metadata.get("lang"))

    for genre in metadata.get("genres", []):
        _add_dc_element(meta_element, "subject", genre)

    # Book series, #number
    sequence = metadata.get('title-info', {}).get('sequence')
    _add_meta_property(meta_element, property="belongs-to-collection", value=sequence, id="collection")
    sequence_number = metadata.get('title-info', {}).get('sequence-number')
    _add_meta_property(meta_element, property="group-position", value=sequence_number, refines="collection")

    created_date = metadata.get('src-title-info', {}).get('date')   # original publication date
    _add_meta_property(meta_element, property="dcterms:created", value=created_date)
    modified_date = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    _add_meta_property(meta_element, property="dcterms:modified", value=modified_date)
