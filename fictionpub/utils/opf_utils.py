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
    if not all([property, value]):
        return
    
    if refines:
        # Ensure parent element has a <dc> element with the specified ID
        if not parent.xpath(f".//*[@id='{refines}']"):
            return

    attrs = {
        key: value
        for key, value in {
            "refines": f"#{refines}" if refines else '',
            "property": property,
            "id": id,
            "scheme": scheme,
        }.items()
        if value != ''
    }

    meta_tag = etree.SubElement(parent, "meta", attrib=attrs)
    meta_tag.text = str(value)


def _add_meta_content(parent: etree._Element, name: str, content: str, scheme: str = ''):
    """
    Adds a <meta> element with name and content attributes.
    """
    # Ensure the required attributes have values before creating the tag
    if not all([name, content]):
        return

    attrs = {
        key: value
        for key, value in {
            "name": name,
            "content": content,
            "scheme": scheme,
        }.items()
        if value != ''
    }

    meta_tag = etree.SubElement(parent, "meta", attrib=attrs)


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
        _add_meta_property(meta_element, property="role", value="bkp", refines="producer", scheme="marc:relators")
        # 'bkp' = Book Producer

    book_id = metadata.get('id')
    if book_id:
        _add_dc_element(meta_element, "identifier", book_id, element_id="BookId")

    # Publish-info
    pub_info = metadata.get("pub")
    if pub_info:
        _add_dc_element(meta_element, "publisher", pub_info.get("publisher"))
        _add_dc_element(meta_element, "date", pub_info.get("year"), element_id="pub-date")
        _add_meta_property(meta_element, property="dcterms:event", value="publication", refines="pub-date", scheme="marc:relators")
        
        isbn = pub_info.get("isbn")
        if isbn:
            _add_dc_element(meta_element, "identifier", f"urn:isbn:{isbn}")
    
    _add_dc_element(meta_element, "language", metadata.get("lang"))

    for genre in metadata.get("genres", []):
        _add_dc_element(meta_element, "subject", genre)

    # Title-info
    # title_info = metadata.get('title-info')
    title_info = metadata   # TODO: move keys into 'title-info' in _extract_metadata() 
    if title_info:
        # Translators
        for i, transl in enumerate(title_info.get('translators', [])):
            transl_id = f"translator{i}"
            _add_dc_element(meta_element, "creator", transl, element_id=transl_id)
            _add_meta_property(meta_element, property="role", value="trl", refines=transl_id, scheme="marc:relators")

        # Book series, #number
        sequence = title_info.get('sequence')
        _add_meta_property(meta_element, property="belongs-to-collection", value=sequence, id="collection")
        sequence_number = title_info.get('sequence-number')
        _add_meta_property(meta_element, property="group-position", value=sequence_number, refines="collection")

    # Src-Title-info
    src_info = metadata.get('src-title-info')
    if src_info:
        _add_meta_property(meta_element, property="original-title", value=src_info.get('book-title'))

        # TODO: duplicates title-info > src-lang. Pick one
        _add_meta_property(meta_element, property="source-language", value=src_info.get('src-lang'))
        
        _add_meta_property(meta_element, property="ocr", value=src_info.get('src-ocr'))
        
        # original publication date # TODO: confirm syntax!
        created_date = src_info.get('date')
        _add_meta_property(meta_element, property="dcterms:created", value=created_date)

    modified_date = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    _add_meta_property(meta_element, property="dcterms:modified", value=modified_date)

    _add_dc_element(meta_element, "description", metadata.get('description'))
    
    app_name = metadata.get('app_name')
    if app_name:
        gen_name = f"{app_name} {metadata.get('app_version', '')}".strip()
        _add_meta_content(meta_element, "generator", gen_name)
