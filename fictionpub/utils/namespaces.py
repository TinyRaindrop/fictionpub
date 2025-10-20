class Namespaces:
    """A container for XML namespaces and their corresponding maps for lxml."""
    # Namespace URIs
    FB2 = "http://www.gribuser.ru/xml/fictionbook/2.0"
    XLINK = "http://www.w3.org/1999/xlink"
    XHTML = "http://www.w3.org/1999/xhtml"
    EPUB = "http://www.idpf.org/2007/ops"
    XML = "http://www.w3.org/XML/1998/namespace"
    SVG = "http://www.w3.org/2000/svg"
    OPF = "http://www.idpf.org/2007/opf"
    DC = "http://purl.org/dc/elements/1.1/"
    NCX = "http://www.daisy.org/z3986/2005/ncx/"
    CONTAINER = "urn:oasis:names:tc:opendocument:xmlns:container"

    # Namespace Maps
    FB2_MAP = {'fb': FB2, 'l': XLINK}
    XHTML_MAP = {None: XHTML, 'epub': EPUB}
    XPATH_MAP = {'x': XHTML}
    SVG_MAP = {None: SVG, 'xlink': XLINK}
    OPF_MAP = {None: OPF, 'dc': DC}
    NCX_MAP = {None: NCX}
    CONTAINER_MAP = {None: CONTAINER}



