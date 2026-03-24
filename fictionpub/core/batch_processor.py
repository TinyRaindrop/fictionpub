"""
Handles the parallel processing of a batch of files.
This class contains the ThreadPoolExecutor and is used by both the CLI and GUI.
"""

import concurrent.futures
import logging
import os
import time
from collections.abc import Callable
from pathlib import Path

from ..models.conversion import ConversionConfig, ConversionResult, ConversionStatus
from ..resources.localized_terms import LocalizedTerms
from ..utils.logger import setup_worker_logger
from .pipeline import ConversionPipeline

log = logging.getLogger("fb2_converter")


class WarningTracker(logging.Filter):
    """A custom filter that tracks if any warnings were emitted."""

    def __init__(self):
        super().__init__()
        self.has_warnings = False

    def filter(self, record):
        if record.levelno == logging.WARNING:
            self.has_warnings = True
        return True


def _init_worker(genres, headings) -> None:
    """
    This function runs once inside every new child process.
    It receives the data and injects it into the local class.
    """
    LocalizedTerms.inject_terms((genres, headings))


def _convert_single_file(path: Path, config: ConversionConfig) -> ConversionResult:
    """
    A standalone function to be the target for the executor.
    It runs the full conversion pipeline on a single file and
    captures all its log output.

    Returns:
        tuple[Path, str, Exception | None]:
            - The path of the processed file.
            - The captured log output as a string.
            - An exception object if one occurred, else None.
    """
    # Set up in-memory logging for this worker process
    log_stream, log_handler = setup_worker_logger()
    worker_log = logging.getLogger("fb2_converter")

    # Attach the warning tracker
    tracker = WarningTracker()
    log_handler.addFilter(tracker)

    try:
        worker_log.info(f"Converting: {path.name}")

        # Main Conversion Logic
        pipeline = ConversionPipeline(config)
        pipeline.convert(path)

        status = (
            ConversionStatus.WARNING if tracker.has_warnings else ConversionStatus.SUCCESS
        )
        warn_status_msg = " (with warnings!)" if tracker.has_warnings else ""
        worker_log.info(
            f"Successfully finished{warn_status_msg} conversion for: {path.name}"
        )

        return ConversionResult(path, status, log_stream.getvalue())

    except Exception as e:
        # 1. Log the full traceback locally to the worker's buffer.
        # This ensures the details are saved to the log file later.
        worker_log.error(f"Failed conversion for: {path.name}", exc_info=True)

        # 2. Sanitize the exception.
        # Convert the exception to a built-in type with the string message.
        # This allows the main process to receive the error without crashing.
        safe_error_msg = f"{type(e).__name__}: {e!s}"
        safe_exc = RuntimeError(safe_error_msg)

        return ConversionResult(
            path=path,
            status=ConversionStatus.FAILURE,
            log_output=log_stream.getvalue(),
            error=safe_exc,
        )

    finally:
        # Clean up handlers and close the stream
        log_handler.close()
        log_stream.close()


class BatchProcessor:
    """Orchestrates the conversion of multiple files in parallel."""

    def __init__(self, config: ConversionConfig):
        self.config = config
        import pickle

        pickle.dumps(self.config)

    def run(self, files: list[Path], progress_callback: Callable | None = None) -> None:
        """
        Processes a list of files in parallel using Thread/ProcessPoolExecutor.

        Args:
            files: A list of Path objects to convert.
            progress_callback: A function to be called as each file completes.
                               It receives the (path, result, exception).
        """
        # Determine the number of worker threads
        th = self.config.num_threads
        max_workers = th if th > 0 else (os.cpu_count() or 1)
        print(
            f"\nStarting batch processing with up to {max_workers} worker threads.",
            flush=True,
        )

        # Map paths to their original index to maintain order
        path_to_index = {path: i for i, path in enumerate(files)}

        # This list will store results in the original file order
        # Each item will be: (path, log_string, exception)
        ordered_results: list[ConversionResult | None] = [None] * len(files)

        with concurrent.futures.ProcessPoolExecutor(
            max_workers,
            initializer=_init_worker,  # Function to run on start
            initargs=(LocalizedTerms.get_terms()),  # Arguments for that function
        ) as executor:
            # Submit all conversion tasks
            future_to_path = {
                executor.submit(_convert_single_file, path, self.config): path
                for path in files
            }

            # Process results as they are completed
            for future in concurrent.futures.as_completed(future_to_path):
                path = future_to_path[future]
                idx = path_to_index[path]

                try:
                    # Get the worker's result: (path, log_string, exception)
                    result_obj = future.result()
                    ordered_results[idx] = result_obj

                    # Call progress callback as items complete
                    if progress_callback:
                        progress_callback(result_obj)

                except Exception as e:
                    # This catches a critical failure in the worker itself
                    # (e.g., the process died)
                    log.error(
                        f"Critical worker failure for {path.name}: {e}", exc_info=True
                    )
                    ordered_results[idx] = ConversionResult(
                        path=path,
                        status=ConversionStatus.FAILURE,
                        log_output=f"CRITICAL FAILURE: {e}\n",
                        error=e,
                    )

            # Short delay for process shutdown
            time.sleep(0.05)

        # --- All processing is done ---
        log.info("Batch processing complete. Writing logs...")

        # Find the main file handler to write the buffered logs
        file_handler = next(
            (h for h in log.handlers if isinstance(h, logging.FileHandler)), None
        )

        # Now, iterate over the results in the original order
        for result in ordered_results:
            if result is None:
                # This should not happen if logic is correct
                log.error("Missing result in the list.")
                continue

            # Write the buffered log from the worker to the main log file
            if file_handler and result.log_output:
                try:
                    file_handler.stream.write(f"\n--- Log for {result.path.name} ---\n")
                    file_handler.stream.write(result.log_output)
                    file_handler.stream.write(f"--- End log for {result.path.name} ---\n\n")
                except Exception as e:
                    log.error(f"Failed to write buffered log for {result.path.name}: {e}")

        log.info("Log writing complete.")
