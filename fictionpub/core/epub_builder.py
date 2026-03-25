"""
Handles the creation of the EPUB file structure and packaging.
"""

import copy
import logging
import os
import re
import shutil
import uuid
import zipfile
from pathlib import Path
from typing import NamedTuple

from lxml import etree

from .. import app_info
from ..epub.constants import EPUB_TYPES_MAP
from ..epub.constants import FNames as FN
from ..epub.link_resolver import LinkResolver
from ..epub.opf_builder import OpfBuilder
from ..epub.toc_utils import TOCItem, iter_toc_items
from ..models import namespaces as NS
from ..models.conversion import ConversionConfig
from ..models.metadata import BookMetadata, EpubMetadata
from ..models.structures import BinaryInfo, BodyType, ConvertedBody, FileInfo
from ..resources.loader import get_css_path
from ..resources.localized_terms import LocalizedTerms
from ..utils import xml_utils as xu

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
    def from_root(cls, root: Path) -> "Paths":
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
        self.source_path = source_path
        tmp: Path = source_path.parent / f"{source_path.stem}_epub_temp"
        self.paths: Paths = Paths.from_root(tmp)

        self.config: ConversionConfig = config

        self.metadata: BookMetadata = BookMetadata()
        self.binaries: dict[str, BinaryInfo] = {}
        self.annotation_el: etree._Element | None = None
        self.main_docs: list[FileInfo] = []
        self.note_docs: list[FileInfo] = []
        self.doc_list: list[FileInfo] = []
        self.toc_items: list[TOCItem] = []
        self.local_terms: LocalizedTerms

    def set_metadata(self, metadata: BookMetadata) -> None:
        """
        Receives BookMetadata from the FB2Book.
        Initializes LocalizedTerms with the book's language.
        Generates EPUB package identifier and sreates EpubMetadata.
        """
        self.metadata = metadata

        # Lang could be undefined.
        # Let methods be aware of this and decide whether a fallback is necessary.
        self.lang: str = metadata.lang
        self.local_terms = LocalizedTerms(self.lang)

        # With local_terms initialized, get translated genre names
        tr_genres = [self.local_terms.get_genre(g) for g in metadata.genres]

        self.epub_meta: EpubMetadata = EpubMetadata(
            book_meta=self.metadata,
            epub_id=f"urn:uuid:{uuid.uuid4()}",
            app_name=app_info.APP_NAME,
            app_version=app_info.VERSION,
            app_url=app_info.APP_URL,
            lang_genres=tr_genres,
            description=None,
        )

    def set_annotation(self, xhtml_annotation: etree._Element | None) -> None:
        """Sets the converted `<annotation>` element in metadata."""
        if xhtml_annotation is None:
            return
        self.annotation_el = xhtml_annotation
        self.epub_meta.description = xu.itertext_separated(xhtml_annotation)

    def set_binaries(self, binaries: dict[str, BinaryInfo]) -> None:
        self.binaries = binaries

    def add_docs(self, converted_docs: list[ConvertedBody]) -> None:
        """
        Receives a list of documents and calls MAIN/NOTE doc handlers.
        """
        for doc in converted_docs:
            if doc.body_type == BodyType.MAIN:
                file_info = self._process_main_doc(doc)
            else:
                # BodyType.NOTE and BodyType.COMMENT
                file_info = self._process_note_doc(doc)
            
            if file_info:
                self.doc_list.append(file_info)

    def _process_main_doc(self, doc: ConvertedBody) -> FileInfo | None:
        """Receives a converted body and wraps it in a full HTML document."""
        html, body = self._create_html(doc.file_id, doc.title)
        # Copy all children from converted body to new html
        body.extend(list(doc.body))
        
        # Remove div.halftitle if it contains nothing more than Author/Title
        combinations = (
                self.metadata.title,
                self.metadata.author,
            )
        halftitle: etree._Element | None = xu.get_halftitle(body)
        if halftitle is not None and xu.match_halftitle(halftitle, combinations):
            body.remove(halftitle)
            log.debug(f"Doc id={doc.file_id}: Removing halftitle.")
            if len(body) == 0:
                log.debug(f"Doc id={doc.file_id} is now empty. Skipping.")
                return None
        
        return FileInfo(doc.file_id, doc.title, html, body_type=doc.body_type)

    def _process_note_doc(self, doc: ConvertedBody) -> FileInfo | None:
        """
        Wraps a converted note body in a full HTML document with an h1 title.

        Title source priority:
          1. Text extracted from div.fb2title (the FB2 body-level <title>),
             unless it matches a generic localized label ("Notes").
          2. Localized heading for the body's file id.
        """
        if len(doc.body) == 0:
            log.warning(f"Note body with id '{doc.file_id}' is empty. Skipping.")
            return None

        # start with the converter-supplied title if available,
        # otherwise fall back to a localized heading based on the body name
        local_title = self.local_terms.get_heading(doc.file_id)
        all_local_titles = self.local_terms.get_all_headings(doc.file_id)
        html, body = self._create_html(doc.file_id, local_title)
        # Copy all children from converted body to new html
        body.extend(list(doc.body))

        h1 = etree.Element("h1")
        h1.text = local_title

        halftitle: etree._Element | None = xu.get_halftitle(body)

        if halftitle is not None:
            ht_text = xu.itertext(halftitle).capitalize()
            if ht_text and ht_text not in all_local_titles:
                h1.text = ht_text
            body.replace(halftitle, h1)
            log.debug(f"Doc id={doc.file_id}: Using '{ht_text}' as a title.")
            # Ensure the H1 is the first child
            if body.index(h1) != 0:
                body.remove(h1)
                body.insert(0, h1)
                log.warning(f"Note body '{doc.file_id}': h1 was not the 1st child of body. Fixed.")

        else:
            # No original title existed, so inject a new H1 at the very top
            body.insert(0, h1)
            log.debug(f"Doc id={doc.file_id}: Using '{local_title}' as a title.")

        return FileInfo(doc.file_id, local_title, html, body_type=doc.body_type)

    def build(self) -> None:
        """
        Generates metadata files and zips the workspace into an .epub file.
        add_docs() must be called before building.
        """
        try:
            self._setup_workspace()

            self._create_static_docs()

            # Sort doc_list according to the order attribute
            self.doc_list.sort()

            # Create an {id: doc} dictionary for faster lookup
            self.doc_map = {doc.id: doc for doc in self.doc_list}

            LinkResolver(self.doc_list).resolve()
            self._resolve_image_paths()

            # Build nested list of headings to be used in NAV/NCX generation
            self._build_toc()
            self._create_nav()
            self.doc_list.sort()  # Re-sort after adding NAV

            # Generate additional files, assemble EPUB
            self._create_ncx()
            self._create_opf()
            self._create_container_xml()
            self._create_stylesheet()
            self._write_documents()
            self._write_binaries()
            self._zip_epub()

            log.info("EPUB build complete.")

        finally:
            self._cleanup_workspace()

    def _setup_workspace(self) -> None:
        """Creates a clean temporary directory for EPUB contents."""
        self._cleanup_workspace()

        for p in self.paths:
            p.mkdir(parents=True, exist_ok=True)

    def _cleanup_workspace(self) -> None:
        """Removes the temporary directory."""
        if self.paths.root.exists():
            shutil.rmtree(self.paths.root)

    def _create_cover_page(self, use_svg=True) -> None | FileInfo:
        """
        Adds a cover image if it exists.
        Pass use_svg = False if <svg> causes issues.
        """
        cover_id = self.metadata.cover_id
        if cover_id is None:
            log.info("No cover image was found. Skipping coverpage creation.")
            return None

        cover_img = self.binaries.get(cover_id)
        if cover_img is None:
            log.warning(
                f"Cover image with id '{cover_id}' not found in binaries. Skipping coverpage creation."
            )
            return None

        img_filename = cover_img.filename
        img_href = f"../{FN.IMAGES}/{img_filename}"  # Relative to Text/cover.xhtml

        fileid = "cover"
        local_title = self.local_terms.get_heading(fileid) or "Cover"
        html, body = self._create_html(fileid, local_title)
        etree.SubElement(
            body, "h1", attrib={"class": "hidden", "title": local_title}
        ).text = ""

        if cover_img.dimensions is None:
            log.warning(f"Could not determine dimensions of cover image '{img_filename}'.")
            use_svg = False

        if use_svg:
            width, height = cover_img.dimensions or (1264, 1680)
            # SVG cover for full screen scaling
            div = etree.SubElement(
                body,
                "div",
                attrib={
                    "style": "text-align: center; margin: 0; padding: 0; height: 100vh;"
                },
            )

            svg = etree.SubElement(
                div,
                "svg",
                nsmap=NS.SVG_MAP,
                attrib={
                    "version": "1.1",
                    "viewBox": f"0 0 {width} {height}",
                    "preserveAspectRatio": "xMidYMid meet",
                    "width": "100%",
                    "height": "100%",
                },
            )

            etree.SubElement(
                svg,
                "image",
                attrib={
                    "width": str(width),
                    "height": str(height),
                    f"{{{NS.XLINK}}}href": img_href,
                },
            )

        else:
            # Simple div>img
            etree.SubElement(body, "div", attrib={"class": "cover-image"}).append(
                etree.Element("img", src=img_href, alt="Cover Image")
            )

        prop = "svg" if use_svg else ""
        return FileInfo(fileid, local_title, html, prop, order=0)

    def _create_title_page(self) -> FileInfo:
        """Creates Titlepage.xhtml"""
        fileid = "titlepage"
        book_title = self.metadata.title or "[Untitled]"
        book_author = self.metadata.author

        html, body = self._create_html(fileid, book_title)
        div = etree.SubElement(body, "div", {"class": "titlepage-wrap"})
        if book_author:
            etree.SubElement(div, "p", attrib={"class": "book-author"}).text = book_author
        etree.SubElement(div, "h1", attrib={"class": "book-title"}).text = book_title

        return FileInfo(fileid, book_title, html, order=1)

    def _create_docinfo_page(self) -> FileInfo | None:
        """Creates Docinfo.xhtml"""
        info_sections = {
            "Book Info": self.metadata.title_info.todict(),
            "Publication Info": self.metadata.pub._asdict(),
            "Original Publication": self.metadata.src._asdict(),
            "Document Info": self.metadata.doc._asdict(),
            "Converter": {
                "Program used": f"{self.epub_meta.app_name} {self.epub_meta.app_version}",
                "URL": self.epub_meta.app_url,
            },
        }

        has_metadata = any(info_sections.values())
        if not has_metadata:
            log.info("No metadata available for docinfo page. Skipping.")
            return None

        fileid = "docinfo"
        local_title = self.local_terms.get_heading(fileid) or "Document info"
        html, body = self._create_html(fileid, local_title)
        etree.SubElement(body, "h1").text = local_title

        for section_title, data in info_sections.items():
            if data:
                etree.SubElement(
                    body, "p", attrib={"class": "subtitle"}
                ).text = section_title
                dl = etree.SubElement(body, "dl")  # Definition list for semantics
                for key, value in data.items():
                    # Skip adding annotation
                    if key == "annotation" or not value:
                        continue

                    dt = etree.SubElement(dl, "dt")
                    dt.text = key.replace("-", " ").replace("_", " ").capitalize()

                    dd = etree.SubElement(dl, "dd")
                    if isinstance(value, list):
                        dd.text = ", ".join(value)
                    else:
                        dd.text = str(value)

        return FileInfo(fileid, local_title, html, order=-2)  # -2 = second last

    def _create_annotation_page(self) -> FileInfo | None:
        """
        Creates Annotation.xhtml from an already converted <annotation>.
        """
        if self.annotation_el is None:
            log.info("Found no annotation. Skipping.")
            return None

        fileid = "annotation"
        local_title = self.local_terms.get_heading(fileid) or "Annotation"
        html, body = self._create_html(fileid, title=local_title)
        etree.SubElement(
            body, "h1", attrib={"class": "hidden", "title": local_title}
        ).text = ""

        body.append(self.annotation_el)

        return FileInfo(fileid, local_title, html, order=3)

    def _create_static_docs(self) -> None:
        """Creates front/back matter documents (cover, title, copyright)."""
        docs = [
            self._create_cover_page(),
            self._create_title_page(),
            self._create_docinfo_page(),
            self._create_annotation_page(),
        ]
        docs = [d for d in docs if d is not None]
        self.doc_list.extend(docs)

    def _resolve_image_paths(self) -> None:
        """Constructs full image paths and inserts src attr. for every <img> element."""
        referenced_ids: set[str] = set()

        for doc in self.doc_list:
            for img in doc.html.iterfind(".//img[@data-img-id]"):
                img_id = img.get("data-img-id")
                if not img_id:
                    continue
                referenced_ids.add(img_id)

                binary = self.binaries.get(img_id)
                if binary:
                    src = f"../{FN.IMAGES}/{binary.filename}"
                    del img.attrib["data-img-id"]  # Clean up temporary attribute
                else:
                    src = "#"  # Fallback for missing images
                    log.warning(f"Image source for ID '{img_id}' not found.")
                img.set("src", src)

        if self.config.remove_unused_images:
            unused: set[str] = (
                self.binaries.keys() - referenced_ids - {self.metadata.cover_id}
            )
            for img_id in unused:
                log.debug(f"Removing unused image: {img_id}")
                del self.binaries[img_id]

    def _build_toc(self) -> None:
        """
        Parses the generated XHTML content files to build a structured Table of Contents.
        Finds heading tags, generates missing IDs, and cleans up titles that contain note links.
        """
        id_counter = 1

        # h1..h[depth]
        for doc in self.doc_list:
            # limit TOC depth for note documents to at most 2 levels
            max_depth = self.config.toc_depth
            if doc.is_note:
                max_depth = min(max_depth, 2)

            heading_tags = [f"h{i}" for i in range(1, max_depth + 1)]
            heading_query = " | ".join([f".//{tag}" for tag in heading_tags])

            if not isinstance(doc.html, etree._Element):
                log.warning(
                    f"[build_toc]: No HTML found for {doc.filename} file. Skipping."
                )
                continue

            headings = doc.html.xpath(heading_query)

            for heading in headings:  # type: ignore
                heading_id = heading.get("id")
                if not heading_id:
                    heading_id = f"toc_id_{id_counter}"
                    heading.set("id", heading_id)
                    id_counter += 1

                # First, try the 'title' attribute
                title = heading.get("title")
                if title is not None and title.strip():
                    toc_text = title
                else:
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
                    toc_text = re.sub(r"\s+", " ", toc_text).strip()

                level = int(heading.tag[-1])

                self.toc_items.append(
                    TOCItem(
                        level=level,
                        text=toc_text,
                        href_nav=f"{doc.filename}#{heading_id}",
                        href_ncx=f"{FN.TEXT}/{doc.filename}#{heading_id}",
                    )
                )

        log.info(f"Generated TOC with {len(self.toc_items)} entries from XHTML files.")

    def _create_nav(self) -> None:
        """Creates the EPUB3 nav.xhtml file with proper nesting."""
        fileid = "nav"
        if fileid not in EPUB_TYPES_MAP:
            log.warning("missing EPUB:type for NAV. Skipping.")
            return

        epub_type = EPUB_TYPES_MAP[fileid].epub_type

        local_title = self.local_terms.get_heading("toc", "Table of Contents")
        html, body = self._create_html(fileid, local_title, add_body_type=False)
        nav = etree.SubElement(
            body, "nav", attrib={f"{{{NS.EPUB}}}type": epub_type, "id": "toc"}
        )
        etree.SubElement(nav, "h1").text = local_title

        ol = etree.SubElement(nav, "ol")

        # A list that tracks the parent <ol> for each level. level_parents[0] is the root.
        level_parents = [ol]

        for item, depth in iter_toc_items(self.toc_items, self.config.toc_depth):
            while len(level_parents) > depth:
                level_parents.pop()
            if len(level_parents) < depth:
                new_ol = etree.SubElement(level_parents[-1][-1], "ol")
                level_parents.append(new_ol)
            li = etree.SubElement(level_parents[-1], "li")
            a = etree.SubElement(li, "a", href=item.href_nav)
            a.text = item.text

        # --- Landmarks ---
        nav_landmarks = etree.SubElement(
            body,
            "nav",
            attrib={"id": "landmarks", f"{{{NS.EPUB}}}type": "landmarks", "hidden": ""},
        )
        etree.SubElement(nav_landmarks, "h1", attrib={"hidden": ""}).text = "Landmarks"
        ol_landmarks = etree.SubElement(nav_landmarks, "ol")

        # First, add a self-referential link to the Table of Contents
        li = etree.SubElement(ol_landmarks, "li")
        a = etree.SubElement(li, "a", href="#toc", attrib={f"{{{NS.EPUB}}}type": epub_type})
        a.text = local_title

        for doc in self.doc_list:
            if doc.id in EPUB_TYPES_MAP:
                li = etree.SubElement(ol_landmarks, "li")
                epub_type = EPUB_TYPES_MAP[doc.id].epub_type
                a = etree.SubElement(
                    li,
                    "a",
                    href=f"{doc.filename}",
                    attrib={f"{{{NS.EPUB}}}type": epub_type},
                )
                a.text = self.local_terms.get_heading(doc.id)

        file_info = FileInfo(fileid, local_title, html, prop="nav", order=-1)  # -1 = last
        self.doc_list.append(file_info)

    def _create_ncx(self) -> None:
        """Creates the EPUB2-compatible toc.ncx file with proper nesting."""
        ncx_path = self.paths.oebps / FN.NCX
        ncx = etree.Element("ncx", version="2005-1", nsmap=NS.NCX_MAP)  # type: ignore
        head = etree.SubElement(ncx, "head")
        etree.SubElement(head, "meta", name="dtb:uid", content=self.epub_meta.epub_id)
        etree.SubElement(
            head, "meta", name="dtb:depth", content="1"
        )  # TODO: toc_level / current max level?
        etree.SubElement(head, "meta", name="dtb:totalPageCount", content="0")
        etree.SubElement(head, "meta", name="dtb:maxPageNumber", content="0")

        doc_title = etree.SubElement(ncx, "docTitle")
        etree.SubElement(doc_title, "text").text = self.metadata.title
        doc_author = etree.SubElement(ncx, "docAuthor")
        etree.SubElement(doc_author, "text").text = self.metadata.author

        nav_map = etree.SubElement(ncx, "navMap")

        # A list that tracks the parent <navPoint> for each level
        level_parents = [nav_map]
        play_order = 1

        for item, depth in iter_toc_items(self.toc_items, self.config.toc_depth):
            while len(level_parents) > depth:
                level_parents.pop()
            nav_point = etree.SubElement(
                level_parents[-1],
                "navPoint",
                id=f"navpoint-{play_order}",
                playOrder=str(play_order),
            )
            play_order += 1
            nav_label = etree.SubElement(nav_point, "navLabel")
            etree.SubElement(nav_label, "text").text = item.text
            etree.SubElement(nav_point, "content", src=item.href_ncx)
            level_parents.append(nav_point)  # always push — popped when a sibling arrives

        self._write_html(ncx, ncx_path, doctype=False)

    def _create_opf(self) -> None:
        """Creates the content.opf file."""
        opf_path = self.paths.oebps / FN.OPF
        root = OpfBuilder(self.epub_meta, self.doc_list, self.binaries).build()
        self._write_html(root, opf_path, doctype=False)

    def _create_container_xml(self) -> None:
        """Generates the META-INF/container.xml file."""
        container_path = self.paths.meta_inf / FN.CONTAINER
        container = etree.Element("container", version="1.0", nsmap=NS.CONTAINER_MAP)  # type: ignore
        rootfiles = etree.SubElement(container, "rootfiles")
        etree.SubElement(
            rootfiles,
            "rootfile",
            attrib={
                "full-path": FN.OEBPS + "/" + FN.OPF,
                "media-type": "application/oebps-package+xml",
            },
        )

        self._write_html(container, container_path, doctype=False)

    def _create_stylesheet(self) -> None:
        """Copies the default or custom CSS file to the Styles directory."""
        source: Path | None = None
        destination: Path = self.paths.styles / FN.CSS

        if self.config.custom_stylesheet:
            custom_css = Path(self.config.custom_stylesheet)
            if custom_css.is_file():
                source = custom_css
                log.info(f"Using custom stylesheet: {custom_css}")
            else:
                log.warning(
                    f"Custom stylesheet not found at {custom_css}. Provide a valid path. Falling back to default."
                )

        if source is None:
            default_css = get_css_path("default.css")
            if default_css and default_css.is_file():
                source = default_css
                log.info(f"Using default stylesheet: {default_css}")
            else:
                log.warning(
                    f"Default stylesheet not found at {default_css}. Creating an empty stylesheet."
                )

        if source:
            shutil.copy(source, destination)
            # source.copy(destination)     # Python 3.14: Path.copy(dest)
        else:
            css_text = "/* Default stylesheet is missing. This empty file has been created instead. */\n"
            destination.write_text(css_text, encoding="utf-8")

    def _write_binaries(self) -> None:
        """Writes all image files to the images directory."""
        for binary in self.binaries.values():
            filepath = self.paths.images / binary.filename
            with open(filepath, "wb") as f:
                f.write(binary.data)
                log.debug(f"Saved binary: {binary.filename}")

    def _write_documents(self) -> None:
        """Writes XHTML etree objects to files in the Text directory."""
        for doc in self.doc_list:
            if doc.html is not None:
                filepath = self.paths.text / doc.filename
                self._write_html(doc.html, filepath)

    def _zip_epub(self) -> None:
        """Creates the final .epub archive."""
        epub_path = self.config.output_path

        if not epub_path:
            epub_path = self.source_path.with_suffix(".epub")

        with zipfile.ZipFile(epub_path, "w", zipfile.ZIP_DEFLATED) as zf:
            # The mimetype file must be the first and uncompressed
            mimetype_content = "application/epub+zip"
            zf.writestr("mimetype", mimetype_content, compress_type=zipfile.ZIP_STORED)

            # Walk through the temp directory and add all other files
            for root, _, filenames in os.walk(self.paths.root):
                for file in filenames:
                    if file == "mimetype":
                        continue
                    filepath = Path(root) / file
                    arcname = filepath.relative_to(self.paths.root)
                    zf.write(filepath, str(arcname))

            log.info(f"✅ Success! EPUB file created at: {epub_path}")

    def _create_html(
        self,
        file_id: str | None,
        title: str = "",
        add_body_type=True,
        use_stylesheet=True,
    ) -> tuple[etree._Element, etree._Element]:
        """Creates a basic XHTML structure with head > title and body."""
        html = etree.Element("html", nsmap=NS.XHTML_MAP)
        # Set language attributes for accessibility and correct rendering
        if self.lang:
            html.set("lang", self.lang)
            html.set(f"{{{NS.XML}}}lang", self.lang)

        head = etree.SubElement(html, "head")
        etree.SubElement(head, "meta", charset="UTF-8")
        if title:
            etree.SubElement(head, "title").text = title
        if use_stylesheet:
            etree.SubElement(
                head,
                "link",
                rel="stylesheet",
                href=f"../{FN.STYLES}/{FN.CSS}",
                type="text/css",
            )

        body = etree.SubElement(html, "body")
        if file_id:
            body_class = f"{file_id}-body"
            body.set("class", body_class)
            if add_body_type and file_id in EPUB_TYPES_MAP:
                body_type = EPUB_TYPES_MAP[file_id].epub_type
                if body_type:
                    body.set(f"{{{NS.EPUB}}}type", body_type)
        return html, body

    @staticmethod
    def _write_html(
        html: etree._Element, filepath: Path | str, doctype=True, notify=True
    ) -> None:
        """Writes an XHTML element tree to a file."""
        args = {
            "pretty_print": True,
            "xml_declaration": True,  # not needed for HTML5, but Sigil will insert it anyway
            "encoding": "UTF-8",
        }
        if doctype:
            args["doctype"] = "<!DOCTYPE html>"

        etree.ElementTree(html).write(str(filepath), **args)

        if notify:
            # log filename, not full path
            log.info(f"Created: {Path(filepath).name}")
