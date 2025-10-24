"""
Handles the creation of the EPUB file structure and packaging.
"""
import copy
import logging
import os
import re
import shutil
import zipfile
from pathlib import Path
from typing import NamedTuple

from lxml import etree

from ..terms.localized_terms import LocalizedTerms
from ..utils.config import ConversionConfig
from ..utils.namespaces import Namespaces as NS
from ..utils.opf_utils import fill_opf_metadata
from ..utils.structures import ConvertedBody, EPUB_TYPES_MAP, FileInfo, BinaryInfo, TOCItem, FNames as FN


log = logging.getLogger("fb2_converter")


class Paths(NamedTuple):
    """Paths to directories of standard EPUB directory structure."""
    root: Path
    oebps: Path
    text: Path
    images: Path
    styles: Path
    meta_inf: Path

    @classmethod
    def from_root(cls, root: Path) -> 'Paths':
        return cls(
            root=root,
            oebps=root / FN.OEBPS,
            text=root / FN.OEBPS / FN.TEXT,
            images=root / FN.OEBPS / FN.IMAGES,
            styles=root / FN.OEBPS / FN.STYLES,
            meta_inf=root / FN.META_INF,
        )


class EpubBuilder:
    """
    Constructs the EPUB package.
    Manages the file structure, writes content, generates metadata, and zips the final file.
    """
    def __init__(self, source_path: Path, config: ConversionConfig):
        """Initializes the builder."""
        self.source_path = source_path
        tmp: Path = source_path.parent / f"{source_path.stem}_epub_temp"
        self.paths: Paths = Paths.from_root(tmp)
        self.config = config

        self.metadata: dict = {}
        self.annotation_el: etree._Element | None = None
        self.binaries: dict[str, BinaryInfo] = {}
        self.main_docs: list[FileInfo] = []
        self.note_docs: list[FileInfo] = []
        self.doc_list: list[FileInfo] = []
        self.toc_items: list[TOCItem] = []
        self.id_to_doc_map: dict[str, str] = {}
        self.local_terms: LocalizedTerms


    def cleanup_workspace(self):
        """Removes the temporary directory."""
        if self.paths.root.exists():
            shutil.rmtree(self.paths.root)


    def setup_workspace(self):
        """Creates a clean temporary directory for EPUB contents."""
        self.cleanup_workspace()
        
        for p in self.paths:
            p.mkdir(parents=True, exist_ok=True)


    def set_metadata(self, metadata: dict):
        """
        Receives metadata from the FB2Book.
        Initializes LocalizedTerms with the book's language.
        """
        self.metadata = metadata
        # Lang could be undefined. 
        # Let methods be aware of this and decide whether a fallback is necessary.
        self.lang: str = metadata.get('lang', '')
        self.local_terms = LocalizedTerms(self.lang)

        # With local_terms initialized, get translated genre names
        self.metadata['genres'] = [self.local_terms.get_genre(g) for g in metadata['genres']]


    def set_annotation(self, converted_annotation: etree._Element | None):
        """Sets the converted <annotation> element in metadata."""
        if isinstance(converted_annotation, etree._Element):
            self.annotation_el = converted_annotation


    def set_binaries(self, binaries: dict[str, BinaryInfo]):
        self.binaries = binaries
        

    def add_main_docs(self, converted_docs: list[ConvertedBody]):
        """
        Accepts split documents with pre-generated filenames and adds them to the list.
        """
        for doc in converted_docs:
            html, body = self._create_html(doc.file_id, doc.title)
            body.extend(list(doc.body))
            # Move all children from converted body to new html
            file_info = FileInfo(doc.file_id, doc.title, html)
            self.doc_list.append(file_info)


    def add_note_docs(self, converted_docs: list[ConvertedBody]):
        """Accepts converted note bodies and adds them to the list."""
        for doc in converted_docs:
            title = self.local_terms.get_heading(doc.file_id)
            html, body = self._create_html(doc.file_id, title)
            # Move all children from converted body to new html
            body.extend(list(doc.body))
            # current_heading = body[0] if len(body) > 0 else None
            # TODO: replace the existing heading with a proper one
            heading = etree.Element("h1")
            heading.text = title
            body.insert(0, heading)
            file_info = FileInfo(doc.file_id, title, html, is_note=True)
            self.doc_list.append(file_info)


    def build(self):
        """
        Generates metadata files and zips the workspace into an .epub file.
        add_main_docs() and add_note_docs() must be called before building.
        """
        self._create_static_docs()
        
        # Sort doc_list according to the order attribute
        self.doc_list.sort()

        # Create an {id: doc} dictionary for faster lookup
        self.doc_map = {doc.id: doc for doc in self.doc_list}

        self._build_id_map()
        self._resolve_internal_links()
        self._insert_backlink_hrefs()
        self._resolve_image_paths()
        
        # Build nested list of headings to be used in NAV/NCX generation
        self._build_toc()
        self._create_nav()
        self.doc_list.sort()    # Re-sort after adding NAV
        
        # Generate additional files, assemble EPUB
        self._create_ncx()
        self._create_opf()
        self._create_container_xml()
        self._create_stylesheet()
        self._write_documents()
        self._write_binaries()
        self._zip_epub()
        # self.cleanup_workspace()
        log.info("EPUB build complete.")


    def _create_cover_page(self, use_svg = True):
        """
        Adds a cover image if it exists.
        Pass use_svg = False if <svg> causes issues.
        """
        cover_id = self.metadata.get('cover-id')
        if cover_id is None:
            log.warning("No cover image was found. Skipping coverpage creation.")
            return None
        
        cover_img = self.binaries.get(cover_id)
        if cover_img is None:
            log.warning(f"Cover image with id '{cover_id}' not found in binaries. Skipping coverpage creation.")
            return None
        
        img_filename = cover_img.filename
        img_href = f"../{FN.IMAGES}/{img_filename}"    # Relative to Text/cover.xhtml

        fileid = "cover"    
        local_title = self.local_terms.get_heading(fileid) or "Cover"
        html, body = self._create_html(fileid, local_title)
        etree.SubElement(body, "h1", attrib={'hidden': ''}).text = local_title

        if cover_img.dimensions is None:
            log.warning(f"Could not determine dimensions of cover image '{img_filename}'.")
            use_svg = False

        if use_svg:
            width, height = cover_img.dimensions or (1264, 1680)
            # SVG cover for full screen scaling
            div = etree.SubElement(body, "div", attrib={
                "style": "text-align: center; margin: 0; padding: 0; height: 100vh;"})

            svg = etree.SubElement(div,"svg", nsmap=NS.SVG_MAP, attrib={
                "version": "1.1",
                "viewBox": f"0 0 {width} {height}",
                "preserveAspectRatio": "xMidYMid meet",
                "width": "100%",
                "height": "100%"
            })

            etree.SubElement(svg, 'image', attrib={
                "width": str(width),
                "height": str(height),
                f'{{{NS.XLINK}}}href': img_href
            })
        
        else:
            # Simple div>img
            etree.SubElement(body, "div", attrib={"class": "cover-image"}).append(
                etree.Element("img", src=img_href, alt="Cover Image")
            )
        
        prop = 'svg' if use_svg else ''
        return FileInfo(fileid, local_title, html, prop, order=0)


    def _create_title_page(self) -> FileInfo:
        """Creates Titlepage.xhtml"""
        fileid = "titlepage"
        book_title = self.metadata.get('title') or "[Untitled]"
        book_author = self.metadata.get('author')
        
        html, body = self._create_html(fileid, book_title) 
        if book_author:
            etree.SubElement(body, "p", attrib={'class': 'book-author'}).text = book_author
        etree.SubElement(body, "h1", attrib={'class': 'book-title'}).text = book_title

        return FileInfo(fileid, book_title, html, order=1)


    def _create_copyright_page(self) -> FileInfo | None:
        """Creates Copyright.xhtml"""
        info_sections = {
            "Publication Info": self.metadata.get('pub', {}),
            "Original Publication": self.metadata.get('src', {}),
            "Document Info": self.metadata.get('doc', {}),
            # 'title-info' doesn't exist, its keys are top level
            "Book Info": self.metadata.get('title-info', {})
        }
        
        has_metadata = any(info_sections.values())
        if not has_metadata:
            log.warning("No metadata available for copyright page. Skipping.")
            return None

        fileid = "copyright"        
        local_title = self.local_terms.get_heading(fileid) or "Copyright"
        html, body = self._create_html(fileid, local_title) 
        # create a subtitle instead of h1?
        etree.SubElement(body, "h1").text = local_title
        etree.SubElement(body, "p", attrib={'class': 'subtitle'}).text = local_title
        
        for section_title, data in info_sections.items():
            if data:
                etree.SubElement(body, "h2").text = section_title
                dl = etree.SubElement(body, "dl") # Definition list for semantics
                for key, value in data.items():
                    # Skip adding annotation to copyright page
                    if key == 'annotation' or not value:
                        continue
                    
                    dt = etree.SubElement(dl, "dt")
                    dt.text = key.replace('-', ' ').replace('_', ' ').capitalize()
                    
                    dd = etree.SubElement(dl, "dd")
                    if isinstance(value, list):
                        dd.text = ", ".join(value)
                    else:
                        dd.text = str(value)

        return FileInfo(fileid, local_title, html, order=-2)    # -2 = second last


    def _create_annotation_page(self) -> FileInfo | None:
        """
        Creates Annotation.xhtml from an already converted <annotation>.
        set_annotation() must be called first.
        """
        if self.annotation_el is None:
            log.info("Found no annotation. Skipping.")
            return None
        
        fileid = "annotation"
        local_title = self.local_terms.get_heading(fileid) or "Annotation"
        html, body = self._create_html(fileid, title=local_title)
        etree.SubElement(body, "h1", attrib={'hidden': ''}).text = local_title
  
        body.append(self.annotation_el)

        return FileInfo(fileid, local_title, html, order=3)
    

    def _create_static_docs(self):
        """Creates front/back matter documents (cover, title, copyright)."""
        docs = [
            self._create_cover_page(),
            self._create_title_page(),
            self._create_copyright_page(),
            self._create_annotation_page(),
        ]
        docs = [d for d in docs if d is not None]
        self.doc_list.extend(docs)


    def _build_toc(self):
        """
        Parses the generated XHTML content files to build a structured Table of Contents.
        Finds heading tags, generates missing IDs, and cleans up titles that contain note links.
        """
        id_counter = 1

        heading_tags = [f'h{i}' for i in range(1, self.config.toc_depth + 1)]
        headings_query = " | ".join([f".//{tag}" for tag in heading_tags])
        
        for doc in self.doc_list:
            if not isinstance(doc.html, etree._Element):
                log.warning(f"[build_toc]: No HTML found for {doc.filename} file. Skipping.")
                continue

            headings = doc.html.xpath(headings_query)
            
            for heading in headings:     # type: ignore
                heading_id = heading.get('id')
                if not heading_id:
                    heading_id = f"toc_id_{id_counter}"
                    heading.set('id', heading_id)
                    id_counter += 1

                toc_text = ""
                # Create a copy for modification
                heading_clone = copy.deepcopy(heading)

                # Remove <a>.noteref and <br> elements
                for el in heading_clone.xpath('.//a[@class="noteref"] | .//br'):
                    parent = el.getparent()
                    if parent is not None:
                        parent.remove(el)

                # Join text, remove newlines and collapse multiple spaces
                toc_text = "".join(heading_clone.itertext())
                toc_text = re.sub(r'\s+', ' ', toc_text).strip()

                level = int(heading.tag[-1])
                
                self.toc_items.append(TOCItem(
                    level=level,
                    text=toc_text, 
                    href_nav=f"{doc.filename}#{heading_id}",
                    href_ncx=f"{FN.TEXT}/{doc.filename}#{heading_id}"
                ))

        log.info(f"Generated TOC with {len(self.toc_items)} entries from XHTML files.")


    def _create_nav(self) -> FileInfo | None:
        """Creates the EPUB3 nav.xhtml file with proper nesting."""
        fileid = "nav"
        if fileid not in EPUB_TYPES_MAP: 
            log.warning("missing EPUB:type for NAV. Skipping.")
            return None
        epub_type = EPUB_TYPES_MAP[fileid].epub_type

        local_title = self.local_terms.get_heading('toc', "Table of Contents")
        html, body = self._create_html(fileid, local_title, add_body_type=False)
        nav = etree.SubElement(body, "nav", attrib={f"{{{NS.EPUB}}}type": epub_type, "id": "toc"})
        etree.SubElement(nav, "h1").text = local_title
        
        ol = etree.SubElement(nav, "ol")
        
        # A list that tracks the parent <ol> for each level. level_parents[0] is the root.
        level_parents = [ol]

        for item in self.toc_items:
            if item.level > self.config.toc_depth:
                continue

            # If we need to go deeper, create a new <ol> and add it to the list
            if item.level > len(level_parents):
                # Get the last <li> in the current parent <ol>
                # TODO: add range checks to avoid going out of bounds
                last_li = level_parents[-1][-1]
                ol = etree.SubElement(last_li, "ol")
                level_parents.append(ol)
            else:
                # Go up in levels
                while item.level < len(level_parents):
                    level_parents.pop()
                # Get last <ol>
                ol = level_parents[-1]

            # ol is the current parent <ol>
            li = etree.SubElement(ol, "li")
            a = etree.SubElement(li, "a", href=item.href_nav)
            a.text = item.text

        # --- Landmarks ---
        nav_landmarks = etree.SubElement(body, "nav", attrib={
            'id': 'landmarks', f"{{{NS.EPUB}}}type": "landmarks", 'hidden': ''
        })
        etree.SubElement(nav_landmarks, "h1", attrib={'hidden': ''}).text = "Landmarks"
        ol_landmarks = etree.SubElement(nav_landmarks, "ol")
        
        # First, add a self-referential link to the Table of Contents
        li = etree.SubElement(ol_landmarks, "li")
        a = etree.SubElement(li, "a", href="#toc", 
                            attrib={f"{{{NS.EPUB}}}type": epub_type})
        a.text = local_title

        for doc in self.doc_list:
            if doc.id in EPUB_TYPES_MAP:
                li = etree.SubElement(ol_landmarks, "li")
                epub_type = EPUB_TYPES_MAP[doc.id].epub_type
                a = etree.SubElement(li, "a", href=f"{doc.filename}", 
                                    attrib={f"{{{NS.EPUB}}}type": epub_type})
                a.text = self.local_terms.get_heading(doc.id)

        file_info = FileInfo(fileid, local_title, html, prop='nav', order=-1)    # -1 = last
        self.doc_list.append(file_info)


    def _create_ncx(self):
        """Creates the EPUB2-compatible toc.ncx file with proper nesting."""
        ncx_path = self.paths.oebps / FN.NCX
        ncx = etree.Element("ncx", version="2005-1", nsmap=NS.NCX_MAP)      # type: ignore
        head = etree.SubElement(ncx, "head")
        etree.SubElement(head, "meta", name="dtb:uid", content=self.metadata['id'])
        etree.SubElement(head, "meta", name="dtb:depth", content="1")
        etree.SubElement(head, "meta", name="dtb:totalPageCount", content="0")
        etree.SubElement(head, "meta", name="dtb:maxPageNumber", content="0")

        doc_title = etree.SubElement(ncx, "docTitle")
        etree.SubElement(doc_title, "text").text = self.metadata['title']
        doc_author = etree.SubElement(ncx, "docAuthor")
        etree.SubElement(doc_author, "text").text = self.metadata['author']
        
        nav_map = etree.SubElement(ncx, "navMap")
        
        # A list that tracks the parent <navPoint> for each level
        level_parents = [nav_map]
        play_order = 1

        for item in self.toc_items:
            if item.level > self.config.toc_depth:
                continue

            while item.level < len(level_parents):
                level_parents.pop()
            
            parent_navpoint = level_parents[-1]
            
            nav_point = etree.SubElement(parent_navpoint, "navPoint", id=f"navpoint-{play_order}", playOrder=str(play_order))
            play_order += 1
            
            nav_label = etree.SubElement(nav_point, "navLabel")
            etree.SubElement(nav_label, "text").text = item.text
            etree.SubElement(nav_point, "content", src=item.href_ncx)

            if item.level >= len(level_parents):
                level_parents.append(nav_point)

        self._write_html(ncx, ncx_path, doctype=False)
        

    def _create_opf(self):
        """Creates the content.opf file."""
        opf_path = self.paths.oebps / FN.OPF
        root = etree.Element("package", version="3.0", nsmap=NS.OPF_MAP)
        root.set("unique-identifier", self.metadata['id'])
    
        # Metadata
        meta = etree.SubElement(root, "metadata")
        fill_opf_metadata(meta, self.metadata)

        # Set a cover image in metadata
        cover_image_id = self.metadata.get('cover-image')
        if cover_image_id:
            etree.SubElement(meta, "meta", name="cover", content=cover_image_id)
        
        # Manifest, Spine, Guide
        manifest = etree.SubElement(root, "manifest")
        spine = etree.SubElement(root, "spine", toc="ncx")
        guide = etree.SubElement(root, "guide")     # for compatibility with EPUB2 readers

        # Add NCX and CSS to the Manifest
        etree.SubElement(manifest, "item", id="ncx", href="toc.ncx", attrib={"media-type": "application/x-dtbncx+xml"})
        etree.SubElement(manifest, "item", id="css", href="Styles/style.css", attrib={"media-type": "text/css"})
        
        # Add all documents from doc_map to Manifest, Spine, Guide
        for doc in self.doc_list:
            if doc is None: 
                log.warning("[OPF] an xhtml file is missing. Skipping.")
                continue
            
            # Manifest
            href = f"{FN.TEXT}/{doc.filename}"
            item = etree.SubElement(manifest, "item", id=doc.id, href=href, 
                                    attrib={"media-type": "application/xhtml+xml"})
            if doc.prop:
                item.set('properties', doc.prop)

            # Spine
            if doc.is_note:     # ? make 'cover' non-linear as well ?
                # Footnote bodies are non-linear
                spine.append(etree.Element("itemref", idref=doc.id, linear="no"))   
            else:
                spine.append(etree.Element("itemref", idref=doc.id))

            # Guide
            if doc.id in EPUB_TYPES_MAP:
                guide_type = EPUB_TYPES_MAP[doc.id].guide_type
                etree.SubElement(guide, "reference", type=guide_type, title=doc.title, href=href)


        # Add images to Manifest
        for id, img in self.binaries.items():
            href = f"{FN.IMAGES}/{img.filename}"
            item = etree.SubElement(manifest, "item", id=id, href=href, attrib={"media-type": img.type})
            if img.prop:
                item.set('properties', img.prop)

        self._write_html(root, opf_path, doctype=False)


    def _create_container_xml(self):
        """Generates the META-INF/container.xml file."""
        container_path = self.paths.meta_inf / FN.CONTAINER
        container = etree.Element("container", version="1.0", nsmap=NS.CONTAINER_MAP)   # type: ignore
        rootfiles = etree.SubElement(container, 'rootfiles')
        etree.SubElement(rootfiles, "rootfile", attrib={
            "full-path": FN.OEBPS + "/" + FN.OPF,
            "media-type": "application/oebps-package+xml"
        })

        self._write_html(container, container_path, doctype=False)


    def _create_stylesheet(self):
        """Copies the default or custom CSS file to the Styles directory."""
        source: Path | None = None
        destination: Path = self.paths.styles / FN.CSS
        
        def get_package_path():
            package_name = __package__ or ""
            # Compute number of levels: 1 if top-level, >1 if in subpackages
            levels_up = max(len(package_name.split('.')), 1)
            # Go up to top-level package
            package_root = Path(__file__).parents[levels_up - 1]
            return package_root

        default_css: Path = get_package_path() / "css" / "default.css"
        
        if self.config.custom_stylesheet:
            custom_css = Path(self.config.custom_stylesheet)
            if custom_css.is_file():
                source = custom_css
                log.info(f"Using custom stylesheet: {custom_css}")
            else:
                log.warning(f"Custom stylesheet not found at {custom_css}. Provide a valid path. Falling back to default.")

        if source is None:
            if default_css.is_file():
                source = default_css
                log.info(f"Using default stylesheet: {default_css}")
            else:
                log.warning(f"Default stylesheet not found at {default_css}. Creating an empty stylesheet.")
        
        if source:
            shutil.copy(source, destination)
            # source.copy(destination)     # Python 3.14: Path.copy(dest)
        else:
            css_text = "/* Default stylesheet is missing. This empty file has been created instead. */\n"
            destination.write_text(css_text, encoding='utf-8')


    def _write_binaries(self):
        """Writes all image files to the images directory."""
        for binary in self.binaries.values():
            filepath = self.paths.images / binary.filename
            with open(filepath, 'wb') as f:
                f.write(binary.data)
                log.debug(f"Saved binary: {binary.filename}")


    def _write_documents(self):
        """Writes XHTML etree objects to files in the Text directory."""
        for doc in self.doc_list:
            if doc.html is not None:
                filepath = self.paths.text / doc.filename
                self._write_html(doc.html, filepath)


    def _zip_epub(self):
        """Creates the final .epub archive."""
        epub_path = self.config.output_path

        if not epub_path:
            epub_path = self.source_path.with_suffix('.epub')

        with zipfile.ZipFile(epub_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            # The mimetype file must be the first and uncompressed
            mimetype_content = 'application/epub+zip'
            zf.writestr('mimetype', mimetype_content, compress_type=zipfile.ZIP_STORED)
            
            # Walk through the temp directory and add all other files
            for root, _, filenames in os.walk(self.paths.root):
                for file in filenames:
                    if file == 'mimetype':
                        continue
                    filepath = Path(root) / file
                    arcname = filepath.relative_to(self.paths.root)
                    zf.write(filepath, str(arcname))
    
            log.info(f"✅ Success! EPUB file created at: {epub_path}")


    def _create_html(self, file_id: str | None, title: str = "", 
                     add_body_type = True, use_stylesheet = True) -> tuple[etree._Element, etree._Element]:
        """Creates a basic XHTML structure with head > title and body."""
        html = etree.Element("html", nsmap=NS.XHTML_MAP)
        # Set language attributes for accessibility and correct rendering
        if self.lang:
            html.set('lang', self.lang)
            html.set(f'{{{NS.XML}}}lang', self.lang)

        head = etree.SubElement(html, "head")
        etree.SubElement(head, "meta", charset="UTF-8")
        if title:
            etree.SubElement(head, "title").text = title
        if use_stylesheet:
            etree.SubElement(head, "link", rel="stylesheet", 
                             href=f"../{FN.STYLES}/{FN.CSS}", type="text/css")

        body = etree.SubElement(html, "body")
        if file_id:
            body_class = f"{file_id}-body"
            body.set('class', body_class)
            if add_body_type and file_id in EPUB_TYPES_MAP:
                body_type = EPUB_TYPES_MAP[file_id].epub_type
                if body_type: body.set(f'{{{NS.EPUB}}}type', body_type)
        return html, body
       

    @staticmethod
    def _write_html(html: etree._Element, filepath: Path | str, doctype=True, notify=True):
        """Writes an XHTML element tree to a file."""
        args = {
            'pretty_print': True,
            'xml_declaration': True,  # not needed for HTML5, but Sigil will insert it anyway
            'encoding': 'UTF-8',            
        }
        if doctype:
            args['doctype'] = '<!DOCTYPE html>'

        etree.ElementTree(html).write(str(filepath), **args)

        if notify:
            # log filename, not full path
            log.info(f"Created: {Path(filepath).name}")


    def _build_id_map(self):
        """Creates a map of all element IDs to their final host filename."""
        for doc in self.doc_list:
            if doc.html is None: 
                continue
            for element in doc.html.iterfind(".//*[@id]"):
                el_id = element.get('id')
                if el_id:
                    self.id_to_doc_map[el_id] = doc.id


    def _resolve_internal_links(self):
        """
        Iterates through all documents and fixes hrefs for internal links.
        """
        for doc in self.doc_list:
            if doc.html is None: 
                continue
            for a in doc.html.iterfind(".//a[@href]"):
                href = a.get('href', '')
                if not href.startswith('#'): 
                    log.debug("External link found, skipping.")
                    continue

                target_id = href.lstrip('#')
                target_doc_id = self.id_to_doc_map.get(target_id)

                if target_doc_id in self.doc_map:
                    target_doc = self.doc_map[target_doc_id]
                    # Update the link to point to the correct file
                    a.set('href', f"{target_doc.filename}#{target_id}")
                    
                    # If target doc is notes/comments
                    if target_doc.is_note:
                        cls = 'noteref'
                        link_type = a.get('link-type')
                        if link_type:
                            if link_type != 'note':
                                log.debug(f"Noteref id='{a.get('id')}', invalid link-type")
                            a.attrib.pop('link-type')
                        else:
                            cls += ' comment'
                        a.attrib.update({
                            'class': cls, 
                            f'{{{NS.EPUB}}}type': 'noteref',
                        })
                    
                        # PostProcessor.remove_sup_from_noteref(a)


                else:
                    log.warning(f"Broken internal link found for id: {target_id}")
                    a.set('broken', 'true')
                    # a.tag = 'span'    # turn into <span>
                    # del a.attrib['href']
    
    
    def _insert_backlink_hrefs(self):
        """Adds a return link to the end of each footnote."""
        for doc in self.doc_list:
            if not doc.is_note: continue
            for backlink in doc.html.iterfind(f'.//a[@class="backlink"]'):
                back_href = backlink.get('href')
                
                if not back_href:
                    log.debug(f"Broken backlink: id='{backlink.get('id')}")
                    continue
                
                back_href = back_href.lstrip('#')               
                target_doc_id = self.id_to_doc_map.get(back_href)
                if target_doc_id:
                    target_doc = self.doc_map.get(target_doc_id)
                    if target_doc:
                        backlink.set('href', f'{target_doc.filename}#{back_href}')


    def _resolve_image_paths(self):
        """Changes <img> placeholders to point to actual image files."""
        for doc in self.doc_list:
            for img in doc.html.iterfind('.//img[@data-fb2-id]'):
                fb2_id = img.get('data-fb2-id')
                if not fb2_id: continue
                image_info = self.binaries.get(fb2_id)
                if image_info:
                    src = f"..{FN.IMAGES}/{image_info.filename}"
                    del img.attrib['data-fb2-id']   # Clean up temporary attribute
                else:
                    src = "#"   # Fallback for missing images
                    log.warning(f"Image source for ID '{fb2_id}' not found.")
                img.set('src', src)

def pretty_print_xml(element: etree._Element | etree._ElementTree) -> str:
    """Returns a pretty-printed XML string of the element/tree."""
    # return etree.tostring(element, pretty_print=True, encoding='utf-8').decode('utf-8')
    return etree.tostring(element, pretty_print=True, encoding='unicode')