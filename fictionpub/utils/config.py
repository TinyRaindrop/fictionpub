"""
Defines configuration and settings for the conversion process.
"""
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ConversionConfig:
    """
    A container for all settings related to a conversion task.
    This object is created by the UI (CLI or GUI) and passed to the ConversionPipeline.
    """
    # Args already has defaults, but 
    output_path: Path | None = None
    toc_depth: int = 4  
    split_level: int = 1
    split_size_kb: int = 0  # 0 means no splitting
    custom_stylesheet: Path | None = None

