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
    # Args already have some defaults, 
    # but we're specifying sane defaults here as well
    output_path: Path | None = None
    toc_depth: int = 4  
    split_level: int = 1
    split_size_kb: int = 0  # 0 means no splitting
    improve_typography: bool = False
    # word length range [min, max] to qualify for typography processing
    # using very conservative values as defaults
    word_len_nbsp_range: tuple[int, int] = (1, 1)  
    word_len_nobreak_range: tuple[int, int] = (4, 6)
    custom_stylesheet: Path | None = None


class ConversionMode(Enum):
    """Defines the context for the conversion (e.g., main text vs. notes)."""
    MAIN = auto()   # main content bodies
    NOTE = auto()   # note / comment bodies
    ELEMENT = auto()
    