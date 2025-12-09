"""
The main conversion pipeline (Facade).

This module orchestrates the entire conversion process, using the other
core modules to perform specific tasks.
"""
from pathlib import Path

from ..utils.config import ConversionConfig
from .fb2_book import FB2Book
from .fb2_to_html_converter import FB2ToHTMLConverter, ConversionMode
from .epub_builder import EpubBuilder


class ConversionPipeline:
    """
    A facade that simplifies the conversion process.

    The UI layer (CLI or GUI) interacts with this class to run a conversion.
    It coordinates the activities of the parser, converter, and builder.
    """

    def __init__(self, config: ConversionConfig):
        """Initializes the pipeline with a specific configuration."""
        self.config = config


    def convert(self, source_path: Path):
        """
        Executes the full FB2 to EPUB conversion for a single file.
        """
        # 1. Parse the FB2 file to extract its contents into a structured object
        fb2_book = FB2Book(source_path)
        fb2_book.parse()

        # 2. Initialize the XHTML converter with data from the parsed book
        converter = FB2ToHTMLConverter(
            binary_map=fb2_book.binaries,
            id_map=fb2_book.id_map,
            config=self.config
        )

        # 3. Initialize the builder, set up the workspace, pass some FB2 data
        builder = EpubBuilder(source_path, self.config)
        builder.set_binaries(fb2_book.binaries)
        builder.set_metadata(fb2_book.metadata)

        # 4. Convert the FB2 bodies to XHTML documents
        main_doc_fragments = []
        for body in fb2_book.main_bodies:
            main_doc_fragments.extend(converter.convert_body(body, ConversionMode.MAIN))

        note_doc_fragments = []
        for body in fb2_book.note_bodies:
            note_doc_fragments.extend(converter.convert_body(body, ConversionMode.NOTE))

        if fb2_book.annotation_el is not None:
            converted_annotation = converter.convert_element(fb2_book.annotation_el)
            builder.set_annotation(converted_annotation)

        """
        main_docs = [
            converter.convert_body(body, ConversionMode.MAIN)
            for body in fb2_book.main_bodies
        ]
        note_docs = [
            converter.convert_body(body, ConversionMode.NOTE)
            for body in fb2_book.note_bodies
        ]
        
        builder.process_main_bodies(main_docs)
        builder.process_note_bodies(note_docs)
        """
        
        # 4. ASSEMBLE: Pass the fragments to the builder to create final documents.
        builder.add_main_docs(main_doc_fragments)
        builder.add_note_docs(note_doc_fragments)

        # 7. Build the final EPUB file (adds CSS, creates toc list, NAV, NCX, OPF, writes all docs to disk, zips the package)
        builder.build()

