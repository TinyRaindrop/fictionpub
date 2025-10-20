"""
Handles the parallel processing of a batch of files.
This class contains the ThreadPoolExecutor and is used by both the CLI and GUI.
"""
import logging
import os
import concurrent.futures
from pathlib import Path
from typing import Callable

from .pipeline import ConversionPipeline
from ..utils.config import ConversionConfig


log = logging.getLogger("fb2_converter")


def _convert_single_file(path: Path, config: ConversionConfig) -> Path:
    """
    A standalone function to be the target for the executor.
    It runs the full conversion pipeline on a single file.
    """
    log.info(f"Processing {path}")
    pipeline = ConversionPipeline(config)
    pipeline.convert(path)
    return path  # Return the path on success


class BatchProcessor:
    """Orchestrates the conversion of multiple files in parallel."""

    def __init__(self, config: ConversionConfig):
        self.config = config
        

    def run(self, files: list[Path], progress_callback: Callable | None = None):
        """
        Processes a list of files in parallel using a ThreadPoolExecutor.

        Args:
            files: A list of Path objects to convert.
            progress_callback: A function to be called as each file completes.
                               It receives the result (Path) or exception.
        """
        max_workers = (os.cpu_count() or 1) + 4        # os.process_cpu_count() in python>=3.13
        log.info(f"Starting batch processing with up to {max_workers} worker threads.")

        with concurrent.futures.ThreadPoolExecutor(max_workers) as executor:
            # Submit all conversion tasks
            future_to_path = {
                executor.submit(_convert_single_file, path, self.config): path
                for path in files
            }

            # Process results as they are completed
            for future in concurrent.futures.as_completed(future_to_path):
                path = future_to_path[future]

                # The responsibility of handling the exception is now passed   
                # to the callback function provided by the caller (CLI or GUI).
                exc = future.exception()
                if progress_callback:
                    if exc:
                        # Pass the exception object to the callback
                        progress_callback(path, None, exc)
                    else:
                        # Pass the result to the callback
                        progress_callback(path, future.result(), None)
