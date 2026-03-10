from datetime import datetime, timezone
from lxml import etree

from ..utils.namespaces import Namespaces as NS


def _add_dc_element(parent: etree._Element, tag: str, text: str | None, element_id=None):
    """Creates a Dublin Core element."""
    # Ensure the required attributes have values before creating the tag
    if not all([tag, text]):
        return None
    
    dc = etree.SubElement(parent, f"{{{NS.DC}}}{tag}")
    dc.text = str(text)
    if element_id:
        dc.set("id", element_id)
    return dc


def _add_meta_element(parent: etree._Element, prop: str, value: str | None, 
                       id: str = '', refines: str = '', scheme: str = ''):
    """
    Creates a <meta> element with attributes.
    
    Optional args:
        - id: ID for the <meta> element.
        - refines: ID of the element this <meta> refines.
        - scheme: scheme for the <meta> element.
    """
    # Basic argument validation
    if not all([prop, value]):
        return None

    attrs = {
        key: value
        for key, value in {
            "refines": f"#{refines}" if refines else '',
            "property": prop,
            "id": id,
            "scheme": scheme,
        }.items()
        if value != ''
    }

    meta = etree.SubElement(parent, "meta", attrib=attrs)
    meta.text = str(value)
    return meta


def _add_meta_custom(parent: etree._Element, attrs: dict):
    """Adds a <meta> element with custom attributes."""
    return etree.SubElement(parent, "meta", attrib=attrs)


def fill_opf_metadata(meta_element: etree._Element, metadata: dict):
    """Fills the OPF metadata section from a dictionary."""
    # Identifier
    book_id = metadata.get('id')
    _add_dc_element(meta_element, "identifier", book_id, element_id="BookId")

    # Title-info
    title = metadata.get("title")
    if title:
        _add_dc_element(meta_element, "title", title, element_id="main-title")
        _add_meta_element(meta_element, prop="title-type", value="main", refines="main-title")

    author = metadata.get("author")
    if author:
        _add_dc_element(meta_element, "creator", author, element_id="author")
        _add_meta_element(meta_element, prop="role", value="aut", refines="author", scheme="marc:relators") 
        # 'aut' = Author

    # TODO: remove
    # metadata['producer'] is never set
    producer_name = metadata.get("producer")    # EPUB producer
    if producer_name:
        _add_dc_element(meta_element, "contributor", producer_name, element_id="producer")
        _add_meta_element(meta_element, prop="role", value="bkp", refines="producer", scheme="marc:relators")
        # 'bkp' = Book Producer

    # title_info = metadata.get('title-info')
    title_info = metadata   # TODO: move keys into 'title-info' in _extract_metadata() 
    if title_info:
        # Translators
        for i, transl in enumerate(title_info.get('translators', [])):
            transl_id = f"translator{i}"
            _add_dc_element(meta_element, "creator", transl, element_id=transl_id)
            _add_meta_element(meta_element, prop="role", value="trl", refines=transl_id, scheme="marc:relators")

        # Book series, #number
        sequence = title_info.get('sequence')
        _add_meta_element(meta_element, prop="belongs-to-collection", value=sequence, id="collection")
        sequence_number = title_info.get('sequence-number')
        _add_meta_element(meta_element, prop="group-position", value=sequence_number, refines="collection")

    _add_dc_element(meta_element, "language", metadata.get("lang"))

    # Src-Title-info
    src_info = metadata.get('src-title-info')
    if src_info:
        _add_meta_element(meta_element, prop="original-title", value=src_info.get('book-title'))

        # TODO: duplicates title-info > src-lang. Pick one
        _add_meta_element(meta_element, prop="source-language", value=src_info.get('src-lang'))
        
        _add_meta_element(meta_element, prop="ocr", value=src_info.get('src-ocr'))
        
        # original publication date # TODO: confirm syntax!
        created_date = src_info.get('date')
        _add_meta_element(meta_element, prop="dcterms:created", value=created_date)
    
    # Publish-info
    pub_info = metadata.get("pub")
    if pub_info:
        _add_dc_element(meta_element, "publisher", pub_info.get("publisher"))
        # Publication date
        _add_dc_element(meta_element, "date", pub_info.get("year"), element_id="pub-date")
        _add_meta_element(meta_element, prop="dcterms:event", value="publication", refines="pub-date", scheme="marc:relators")
        
        isbn = pub_info.get("isbn")
        if isbn:
            _add_dc_element(meta_element, "identifier", f"urn:isbn:{isbn}")

    # Genres
    for genre in metadata.get("genres", []):
        _add_dc_element(meta_element, "subject", genre)
    
    # Cover image id
    cover_id = metadata.get('cover-id')
    if cover_id:
        _add_meta_custom(meta_element, {'name': "cover", 'content': cover_id})

    # FB2 annotation as description
    _add_dc_element(meta_element, "description", metadata.get('description'))

    # Generator name+version
    app_name = metadata.get('app_name')
    if app_name:
        gen_name = f"{app_name} {metadata.get('app_version', '')}".strip()
        _add_meta_custom(meta_element, {'name': "generator", 'content': gen_name})

    # Timestamp
    modified_date = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    _add_meta_element(meta_element, prop="dcterms:modified", value=modified_date)