"""
The main conversion pipeline (Facade).

This module orchestrates the entire conversion process, using the other
core modules to perform specific tasks.
"""

from pathlib import Path

from lxml.etree import _Element

from fictionpub.models.conversion import BatchAnchor, ConversionConfig
from fictionpub.models.structures import ConvertedBody
from fictionpub.post_processing.post_processor import PostProcessor

from .epub_builder import EpubBuilder
from .fb2_book import FB2Book
from .fb2_to_html_converter import FB2ToHTMLConverter


class ConversionPipeline:
    """
    A facade that simplifies the conversion process.

    The UI layer (CLI or GUI) interacts with this class to run a conversion.
    It coordinates the activities of the parser, converter, and builder.
    """

    def __init__(self, config: ConversionConfig):
        """Initializes the pipeline with a specific configuration."""
        self.config = config

    def convert(self, source_path: Path, anchor: BatchAnchor | None = None) -> None:
        """
        Execute the full FB2 → EPUB conversion for a single file.

        Parameters
        ----------
        source_path : source .fb2 / .fb2.zip file
        anchor      : precomputed batch anchor for output-path resolution;
                      forwarded to EpubBuilder unchanged.
        """
        # 1. Parse
        fb2_book = FB2Book(source_path)
        fb2_book.parse()

        # 2. Initialize converter and builder
        converter = FB2ToHTMLConverter(binary_map=fb2_book.binaries, config=self.config)
        builder = EpubBuilder(source_path, self.config, anchor=anchor)
        builder.set_binaries(fb2_book.binaries)
        builder.set_metadata(fb2_book.metadata)

        # 3. Convert all FB2 bodies and annotation
        doc_fragments: list[ConvertedBody] = []
        for fb2body in fb2_book.bodies:
            doc_fragments.extend(converter.convert_body(fb2body))

        annotation: _Element | None = (
            converter.convert_element(fb2_book.metadata.annotation_el)
            if fb2_book.metadata.annotation_el is not None
            else None
        )

        # 4. Post-process: run cleanup transformations on the converted XHTML documents
        post_processor = PostProcessor(self.config)
        for df in doc_fragments:
            post_processor.run(df.body, df.body_type)
        if annotation is not None:
            post_processor.run(annotation)

        # 5. Assemble: pass the fragments to the builder to create final documents
        builder.set_annotation(annotation)
        builder.add_docs(doc_fragments)

        # 6. Build — writes all files, zips the EPUB
        builder.build()
