"""
Defines configuration and settings for the conversion process.
"""

from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path


@dataclass
class ConversionConfig:
    """
    A container for all settings related to a conversion task.
    This object is created by the UI (CLI or GUI) and passed to the ConversionPipeline.
    """

    # Output location
    output_path: Path | None = None
    # When True and output_path is set, the source file's immediate parent
    # directory name is replicated under output_path.
    # e.g. /books/fantasy/book.fb2 → /output/fantasy/book.epub
    retain_folder_structure: bool = False

    # Document structure
    toc_depth: int = 4
    split_level: int = 2   # split at each h1..h6
    split_size_kb: int = 0        # 0 = disabled  # TODO: implement

    # Processing
    remove_unused_images: bool = True
    improve_typography: bool = False
    # word length range [min, max] to qualify for typography processing
    # using very conservative values as defaults
    word_len_nbsp_range: tuple[int, int] = (1, 1)
    word_len_nobreak_range: tuple[int, int] = (4, 6)

    # Stylesheet
    custom_stylesheet: Path | None = None

    # Parallelism
    num_threads: int = 0          # 0 = auto-detect


class ConversionStatus(Enum):
    SUCCESS = auto()
    WARNING = auto()
    FAILURE = auto()


@dataclass
class ConversionResult:
    path: Path
    status: ConversionStatus
    log_output: str = ""
    error: Exception | None = None