"""
Contains the logic for parsing and representing an FB2 file.
"""
import base64
import logging
import zipfile
from io import BytesIO
from lxml import etree
from pathlib import Path
from PIL import Image

from ..utils.namespaces import Namespaces as NS
from ..utils.structures import BinaryInfo, BookMetadata, TitleInfo, SourceInfo, DocumentInfo, PublishInfo, CustomInfo, QuickMetadata, BodyType, FB2Body, MappedId
from ..utils import xml_utils as xu


log = logging.getLogger("fb2_converter")


class FB2Book:
    """
    Represents a parsed FB2 file.

    Responsibilities:
      - Load and parse the FB2 XML tree
      - Extract structured metadata into a BookMetadata instance
      - Decode and validate binary assets
      - Separate body elements into main content and note bodies

    Does NOT perform EPUB-layer shaping (no epub IDs, no localization,
    no description-text conversion). Those concerns belong to EpubBuilder.
    """

    def __init__(self, filepath: Path):
        self.filepath = filepath
        self.tree: etree._ElementTree

        self.metadata: BookMetadata = BookMetadata()
        self.binaries: dict[str, BinaryInfo] = {}
        self.referenced_ids: set[str] = set()
        self.bodies: list[FB2Body] = []


    def parse(self):
        """Parses the FB2 file and populates all instance attributes."""
        self._parse_xml_tree()
        self._create_referenced_ids_set()
        self._extract_binaries()            # must run before _extract_metadata (cover lookup)
        self._extract_metadata()
        self._extract_bodies()
        log.info(f"Parsed '{self.filepath.name}' successfully.")


    @staticmethod
    def get_quick_metadata(filepath: Path) -> QuickMetadata:
        """
        Extracts a QuickMetadata excerpt without loading the full XML tree.
        Supports .fb2 and .fb2.zip.
        """
        source = None
        opened_zip = None

        try:
            # Handle ZIP files
            if str(filepath).lower().endswith('.fb2.zip'):
                opened_zip = zipfile.ZipFile(filepath, 'r')
                # Find first .fb2 file in zip
                fb2_name = next((n for n in opened_zip.namelist() if n.lower().endswith('.fb2')), None)
                if not fb2_name:
                    return QuickMetadata(author='N/A', title='No .fb2 in zip')
                source = opened_zip.open(fb2_name)
            else:
                source = str(filepath)

            ti = TitleInfo()
            # Use iterparse to find the title-info block efficiently
            tag_to_find = f'{{{NS.FB2}}}title-info'
            context = etree.iterparse(source, events=('end',), tag=tag_to_find)
            
            for _, elem in context:
                ti = FB2Book._parse_title_info(elem)
                # Clean up memory
                elem.clear()
                # Stop after the first title-info
                break

            return QuickMetadata(
                author = ti.author,
                title  = ti.title,
                date   = ti.date,
                lang   = ti.lang,
            )

        except Exception as e:
            log.warning(f'Quick metadata extraction failed for {filepath.name}: {e}')
            return QuickMetadata(author='*ERROR*', title='* Failed to read metadata *')

        finally:
            if source is not None and not isinstance(source, str) and hasattr(source, 'close'):
                source.close()
            if opened_zip:
                opened_zip.close()

    # -------------------------------
    # Private: XML loading

    def _parse_xml_tree(self):
        """Loads the FB2 XML into an lxml tree. Handles .fb2 and .fb2.zip."""
        if str(self.filepath).endswith('.fb2.zip'):
            with zipfile.ZipFile(self.filepath, 'r') as zf:
                fb2_files = [n for n in zf.namelist() if n.endswith('.fb2')]
                if not fb2_files:
                    raise FileNotFoundError(f"No .fb2 file found inside {self.filepath.name}.")
                
                # Open the first .fb2 file found as a stream and parse it
                with zf.open(fb2_files[0]) as fb2_file:
                    self.tree = etree.parse(fb2_file)
        else:
            self.tree = etree.parse(str(self.filepath))


    # -------------------------------
    # Private: metadata extraction
    #
    # Three-layer design:
    #   Layer 1  _parse_*() static methods — pure XML reading.
    #            Each reads exactly one FB2 element and fills one dataclass.
    #            No defaults, no cross-field logic.
    #   Layer 2  _extract_metadata() — FB2 schema interpretation.
    #            Knows that genres accumulate across title-info + src-title-info,
    #            that writing date lives in title-info, that cover-id requires
    #            a binary lookup, etc. Assembles the BookMetadata instance.
    #   Layer 3  EpubBuilder / opf_utils — EPUB shaping (epub IDs, localization,
    #            description-text conversion). Not done here.

    def _extract_metadata(self):
        """
        Parses <description> and assembles self.metadata (BookMetadata).
        Delegates per-block XML reading to the _parse_*() static helpers.
        """
        desc = xu.elem_find(self.tree, './/fb:description')
        if desc is None:
            log.warning("No <description> found. Using defaults.")
            self.metadata = BookMetadata()
            return

        meta = BookMetadata()

        # --- title-info ---
        title_info_el = xu.elem_find(desc, 'fb:title-info')
        if title_info_el is not None:
            meta.title_info = FB2Book._parse_title_info(title_info_el)

        # --- src-title-info ---
        src_el = xu.elem_find(desc, 'fb:src-title-info')
        if src_el is not None:
            meta.src = FB2Book._parse_src_info(src_el)

        # --- document-info ---
        doc_el = xu.elem_find(desc, 'fb:document-info')
        if doc_el is not None:
            meta.doc = FB2Book._parse_doc_info(doc_el)

        # --- publish-info ---
        pub_el = xu.elem_find(desc, 'fb:publish-info')
        if pub_el is not None:
            meta.pub = FB2Book._parse_pub_info(pub_el)

        # --- custom-info ---
        # Each <custom-info info-type="key">value</custom-info> becomes one entry.
        for el in xu.elem_findall(desc, 'fb:custom-info'):
            text = (el.text or '').strip()
            if text:
                meta.custom_info.append(CustomInfo(
                    info_type = el.get('info-type', '').strip(),
                    text = text,
                ))

        # Cover id: requires binaries already extracted (_extract_binaries runs first)
        cover_el = xu.elem_find(self.tree.getroot(), './/fb:coverpage//fb:image')
        if cover_el is not None:
            cover_id = cover_el.get(f"{{{NS.XLINK}}}href", "").lstrip('#')
            if cover_id in self.binaries:
                meta.cover_id = cover_id
                self.binaries[cover_id].prop = "cover-image"

        self.metadata = meta


    @staticmethod
    def _parse_title_info(el: etree._Element) -> TitleInfo:
        """Layer 1: <title-info> → TitleInfo."""
        tags = xu.get_metadata_tags(el, 
                                    ['book-title', 'keywords', 'lang', 'date'])
        ti = TitleInfo(
            title    = tags.get('book-title') or 'Untitled',
            keywords = tags.get('keywords', ''),
            lang     = tags.get('lang', ''),
            date     = tags.get('date', ''),
        )
        ti.authors = [
            xu.get_person_name(a)
            for a in xu.elem_findall(el, 'fb:author')
        ]
        ti.translators = [
            xu.get_person_name(t)
            for t in xu.elem_findall(el, 'fb:translator')
        ]
        ti.annotation_el = xu.elem_find(el, 'fb:annotation')
        ti.genres = [
            g.text for g in xu.elem_findall(el, 'fb:genre') if g.text
        ]
        seq = xu.elem_find(el, 'fb:sequence')
        if seq is not None:
            ti.sequence = seq.get('name', '')
            seq_num = seq.get('number', '')
            if seq_num and seq_num.isdigit():
                ti.sequence_number = int(seq_num)
        return ti


    @staticmethod
    def _parse_src_info(el: etree._Element) -> SourceInfo:
        """Layer 1: <src-title-info> → SourceInfo."""
        tags = xu.get_metadata_tags(el, 
                                    ['book-title', 'date', 'src-lang'])   
        return SourceInfo(
            title    = tags.get('book-title', ''),
            date     = tags.get('date', ''),
            src_lang = tags.get('src-lang', ''),
            author   = xu.get_person_name(xu.elem_find(el, 'fb:author')),
        )


    @staticmethod
    def _parse_doc_info(el: etree._Element) -> DocumentInfo:
        """Layer 1: <document-info> → DocumentInfo."""
        tags = xu.get_metadata_tags(el, 
                                    ['program-used', 'date', 'id', 'version', 'src-ocr'])
        return DocumentInfo(
            program_used = tags.get('program-used', ''),
            date         = tags.get('date', ''),
            doc_id       = tags.get('id', ''),
            version      = tags.get('version', ''),
            author       = xu.get_person_name(xu.elem_find(el, 'fb:author')),
        )


    @staticmethod
    def _parse_pub_info(el: etree._Element) -> PublishInfo:
        """Layer 1: <publish-info> → PublishInfo."""
        tags = xu.get_metadata_tags(el, 
                                    ['book-name', 'publisher', 'city', 'year', 'isbn'])
        return PublishInfo(
            book_name = tags.get('book-name', ''),
            publisher = tags.get('publisher', ''),
            city      = tags.get('city', ''),
            year      = tags.get('year', ''),
            isbn      = tags.get('isbn', ''),
        )


    # -------------------------------
    # Private: binaries

    def _extract_binaries(self):
        """Finds all <binary> tags, decodes and validates them."""
        for binary in xu.elem_findall(self.tree, './/fb:binary'):
            binary_id = binary.get('id')

            if not binary_id:
                log.warning("Invalid binary: no id. Skipping.")
                continue
            if binary_id not in self.referenced_ids:
                log.warning(f"Binary '{binary_id}' is never referenced. Skipping.")
                continue
            if not binary.text:
                log.warning(f"Invalid binary '{binary_id}': empty content. Skipping.")
                continue

            content_type = binary.get('content-type', '')
            fb_ext = content_type.split('/')[-1].lower() if content_type else None
            if fb_ext == 'jpeg':
                fb_ext = 'jpg'

            # Read image, validate and check its format
            try:
                raw_data = base64.b64decode(binary.text)
                with Image.open(BytesIO(raw_data)) as img:
                    # Validate that it's an image format that Pillow can work with
                    if img.format is None:
                        raise ValueError("Unsupported or invalid image format")
                    
                    img.verify()
                    img_format = img.format.lower()
                    ext = 'jpg' if img_format == 'jpeg' else img_format
                    
            except (IOError, ValueError, SyntaxError) as e:
                log.warning(f"Invalid or corrupt image '{binary_id}': {e}")
                continue
            
            if ext != fb_ext:
                log.info(f"Fixed content-type mismatch: {binary_id}.{fb_ext} => {ext}.")
            
            # {binary_id}" was used in FB2, {filename} will be used in EPUB
            filename = self._normalize_binary_name(binary_id, ext)
            self.binaries[binary_id] = BinaryInfo(filename, f"image/{img_format}", raw_data)


    def _normalize_binary_name(self, id: str, ext: str) -> str:
        """Returns a collision-free filename for a binary asset."""
        base_name = id if id.endswith(f'.{ext}') else f'{id}.{ext}'
        filename = base_name
        existing = {b.filename for b in self.binaries.values()}
        counter = 1
        while filename in existing:
            filename = f'{base_name}_{counter}.{ext}'
            counter += 1
        return filename


    # -------------------------------
    # Private: bodies and ID map

    def _extract_bodies(self):
        """Separates FB2 <body> elements into main content and note bodies."""
        root = self.tree.getroot()
        for body in root.iterfind('fb:body', NS.FB2_MAP):
            bname = body.get('name', '').lower()

            if bname in ('notes', 'footnotes', 'примечания', 'сноски', 'примітки'):
                btype = BodyType.NOTE
            elif bname in ('comments', 'комментарии', 'коментарі'):
                btype = BodyType.COMMENT
            else:
                btype = BodyType.MAIN
                if bname:
                    log.info(f"Treating body[name={bname}] as main content.")
            self.bodies.append(FB2Body(body, btype))


    def _create_referenced_ids_set(self):
        """Collects all ids that are pointed to by at least one href."""
        self.mapped_ids = {}
        # Find all <a href=...> elements
        for element in self.tree.iterfind('.//*[@l:href]', namespaces=NS.FB2_MAP):
            href = element.get(f'{{{NS.XLINK}}}href')
            id = href.lstrip('#') if href else None
            if id:
                self.referenced_ids.add(id)
                """mi = MappedId(
                    id,
                    '',
                    body_name,
                    )
                mi.refs.append()"""

