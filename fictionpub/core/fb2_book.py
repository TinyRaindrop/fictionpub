"""
Contains the logic for parsing and representing an FB2 file.
"""
import base64
import logging
import uuid
import zipfile
from pathlib import Path
from lxml import etree

from ..utils.namespaces import Namespaces as NS
from ..utils.structures import BinaryInfo
from ..utils import xml_utils as xu


log = logging.getLogger("fb2_converter")

class FB2Book:
    """
    Represents a parsed FB2 file.

    This class handles the low-level parsing of the FB2 XML, extracting
    metadata, binary objects (images), and the main book content.
    It can parse both plain .fb2 and zipped .fb2.zip files.
    """

    def __init__(self, filepath: Path):
        """Initializes with the path to the FB2 file."""
        self.filepath = filepath
        self.tree: etree._ElementTree   # | None = None   # removing None to satisfy type checker

        # Extracted data
        self.metadata: dict[str, str | dict ] = {}
        self.binaries: dict[str, BinaryInfo] = {}
        self.referenced_ids = set()
        self.id_map: dict[str, etree._Element] = {}
        self.cover_img: tuple[str, int, int] | None = None
        self.main_bodies: list[etree._Element] = []
        self.note_bodies: list[etree._Element] = []


    def parse(self):
        """
        Parses the FB2 file and populates the instance attributes.
        This is the main entry point for this class.
        """
        self._parse_xml_tree()
        if self.tree is None: 
            # TODO: Throw exception, abort current thread (book)
            return
        self._extract_metadata()
        self._create_referenced_ids_set()
        self._extract_binaries()
        self._find_cover_image()
        self._extract_bodies()
        self._map_internal_ids()
        log.info(f"Parsed '{self.filepath.name}' successfully.")


    @staticmethod
    def get_quick_metadata(filepath: Path) -> dict[str, str]:
        """
        A fast method to parse only the essential metadata from an FB2 file
        without loading the entire document.
        Returns a dictionary with 'author' and 'title'.
        """
        author = "Unknown Author"
        title = "Untitled"
        
        def _parse_title_info(element):
            """Helper to extract data from a title-info element."""
            nonlocal author, title
            title_elem = xu.elem_find(element, 'fb:book-title')
            if title_elem is not None and title_elem.text:
                title = title_elem.text

                authors = [
                    xu.get_person_name(author)
                    for author in xu.elem_findall(elem, 'fb:author') ]
                author = ", ".join(authors)

                elem.clear()    # Clear the element from memory

        try:
            events = ("end",)
            tag_to_find = f"{{{NS.FB2}}}title-info"

            if str(filepath).endswith('.fb2.zip'):
                with zipfile.ZipFile(filepath, 'r') as zf:
                    fb2_files = [name for name in zf.namelist() if name.endswith('.fb2')]
                    if not fb2_files: return {'author': 'N/A', 'title': 'No .fb2 in zip'}
                    with zf.open(fb2_files[0]) as fb2_file:
                        context = etree.iterparse(fb2_file, events=events, tag=tag_to_find)
                        for _, elem in context:
                            _parse_title_info(elem)
                            break   # Stop parsing after the first title-info is found
            else:
                # Same logic for a regular file
                context = etree.iterparse(str(filepath), events=events, tag=tag_to_find)
                for _, elem in context:
                    _parse_title_info(elem)
                    break

        except (etree.XMLSyntaxError, zipfile.BadZipFile, FileNotFoundError) as e:
            log.warning(f"Quick metadata parse failed for {filepath.name}: {e}")
            return {'author': 'Parse Error', 'title': 'Parse Error'}
            
        return {'author': author, 'title': title}
    

    def _parse_xml_tree(self):
        """Loads the XML file into an lxml tree, handling .fb2 and .fb2.zip files."""
        if str(self.filepath).endswith('.fb2.zip'):
            with zipfile.ZipFile(self.filepath, 'r') as zf:
                # Find the .fb2 file inside the archive
                fb2_files = [name for name in zf.namelist() if name.endswith('.fb2')]
                if not fb2_files:
                    raise FileNotFoundError("No .fb2 file found inside the zip archive.")
                
                # Open the first .fb2 file found as a stream and parse it
                with zf.open(fb2_files[0]) as fb2_file:
                    self.tree = etree.parse(fb2_file)
        else:
            self.tree = etree.parse(str(self.filepath))


    def _extract_metadata(self):
        """Parses the <description> tag to get book metadata using xml_utils."""

        """Extracts detailed metadata from the <description> tag."""
        meta = {}
        genres = set()
        generated_id = str(uuid.uuid4())
        default_lang = "uk"

        desc = xu.elem_find(self.tree, './/fb:description')
        if desc is None:
            # Set defaults and return
            self.metadata = {'title': 'Untitled', 
                             'author': 'Unknown author', 
                             'id': generated_id }
            # Not setting 'lang': default_lang. Keeping it undefined.
            return

        # --- Title Info ---
        title_info = xu.elem_find(desc, 'fb:title-info')
        if title_info is not None:
            title_info_tags = ['book-title', 'keywords', 'date', 'lang']
            meta.update(xu.get_metadata_tags(title_info, title_info_tags))
            meta.update({
                # 'author': xu.get_person_name(xu.element_find(title_info, 'fb:author')),
                'authors': [
                    xu.get_person_name(author)
                    for author in xu.elem_findall(title_info, 'fb:author')],
                'translators': [
                    xu.get_person_name(t)
                    for t in xu.elem_findall(title_info, 'fb:translator')
                ],
            })

            self.annotation_el = xu.elem_find(title_info, 'fb:annotation')

            # Add genres to the set
            genres.update(g.text for g in xu.elem_findall(title_info, 'fb:genre'))

            # Series, series number
            seq = xu.elem_find(title_info, 'fb:sequence')
            if seq is not None:
                meta['sequence'] = seq.get('name')                    
                seq_num = seq.get('number') 
                if seq_num and seq_num.isdigit():
                    meta['sequence-number'] = int(seq_num)

        # Ensure Title, Author are set
        meta['title'] = meta.get('book-title', "Untitled")
        meta['author'] = meta['authors'][0] if meta.get('authors') else "Unknown Author"

        # --- Language and Localization ---
        # If Lang doesn't exist in FB2 description, do not set a value in meta{}
        # meta['lang'] = meta.get('lang', default_lang)

        # --- Source Title Info ---
        src_title_info = xu.elem_find(desc, 'fb:src-title-info')
        if src_title_info is not None:
            src_title_info_tags = ['book-title', 'date', 'src-lang']
            meta['src'] = xu.get_metadata_tags(src_title_info, src_title_info_tags) 
            meta['src']['author'] = xu.get_person_name(xu.elem_find(src_title_info, 'fb:author'))
                
            # Add genres to the set
            genres.update(g.text for g in xu.elem_findall(src_title_info, 'fb:genre'))

        # --- Document Info ---
        doc_info = xu.elem_find(desc, 'fb:document-info')
        if doc_info is not None:
            doc_info_tags = ['program-used', 'date', 'id', 'version']
            meta['doc'] = xu.get_metadata_tags(doc_info, doc_info_tags)                   
            meta['doc']['author'] = xu.get_person_name(xu.elem_find(doc_info, 'fb:author'))

        # Ensure id, date are set
        meta['id'] = meta.get('doc', {}).get('id', generated_id)
        meta['date'] = meta.get('doc', {}).get('date', '')

        # --- Publish Info ---
        pub_info = xu.elem_find(desc, 'fb:publish-info')
        if pub_info is not None:
            pub_info_tags = ['book-name', 'publisher', 'city', 'year', 'isbn']
            meta['pub'] = xu.get_metadata_tags(pub_info, pub_info_tags)

        # --- Genre Translation ---
        # TODO: move it into EpubBuilder (metadata generation)
        # meta['genres'] = [self.local_terms.get_genre(g) for g in genres]
        
        self.metadata = meta


    def _extract_binaries(self):
        """Finds all <binary> tags, decodes and stores them."""

        # Find and decode all binary objects
        for binary in xu.elem_findall(self.tree, './/fb:binary'):
            binary_id = binary.get('id')
            
            # Skip binaries that are never referenced
            # ? Better be moved to builder / post-convert cleanup
            if binary_id not in self.referenced_ids:
                continue
            
            content_type = binary.get('content-type')
            if not (binary_id and binary.text and content_type):
                log.warning(f"Invalid binary {binary_id} {content_type}. Skipping.")
                continue
            
            ext = content_type.split('/')[-1]
            if ext == 'jpeg': ext = 'jpg'
            filename = self._normalize_binary_name(binary_id, ext)

            try:
                # {binary_id}" was used in FB2, {filename} will be used in EPUB
                self.binaries[binary_id] = BinaryInfo(filename, content_type, base64.b64decode(binary.text))
            except (ValueError, TypeError) as e:
                log.warning(f"Could not decode binary with id '{binary_id}'. Error: {e}")
            

    def _normalize_binary_name(self, id: str, ext: str) -> str:
        """Conform the filename to id.ext and avoid name collisions."""
        base_name = id.lower()
        if not base_name.endswith(f".{ext}"):
            base_name = f"{id}.{ext}"
        
        filename = base_name
        existing_filenames: set[str] = {b.filename for b in self.binaries.values()}
        counter = 1

        while filename in existing_filenames:
            # Append a counter to avoid name collisions
            filename = f"{base_name}_{counter}.{ext}"
            counter += 1
        return filename


    def _find_cover_image(self):
        """Finds the cover image and its dimensions."""
        cover_el = xu.elem_find(self.tree.getroot(), './/fb:coverpage//fb:image')
        if cover_el is not None:
            cover_id = cover_el.get(f"{{{NS.XLINK}}}href", "").lstrip('#')
            if cover_id not in self.binaries:
                return

            self.metadata['cover-id'] = cover_id
            self.binaries[cover_id].prop = "cover-image"


    def _extract_bodies(self):
        """Gets the main <body> and notes/comments <body> elements."""       
        root = self.tree.getroot()  
        for body in root.iterfind('fb:body', NS.FB2_MAP):
            bname = body.get('name')
            if bname in ['notes', 'comments', 'footnotes']:
                self.note_bodies.append(body)
            else:
                self.main_bodies.append(body)
                if bname:
                    log.info(f"\tTreating body[name={bname}] as main content.")


    def _map_internal_ids(self):
        """Creates a map of all `id` attributes for internal linking."""
        # TODO: make it actually useful
        for element in self.tree.iterfind('.//*[@id]'):
            id_attr = element.get('id')
            if id_attr:
                self.id_map[id_attr] = element


    def _create_referenced_ids_set(self):
        """Creates a set of all `href` links."""
        for element in self.tree.iterfind('.//*[@l:href]', namespaces=NS.FB2_MAP):
            id = element.get(f'{{{NS.XLINK}}}href')
            if id:
                self.referenced_ids.add(id.lstrip('#'))
