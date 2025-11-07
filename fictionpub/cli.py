"""
Handles command-line argument parsing and initiates the conversion.
This is the entry point for the console script.
"""
import argparse
import logging
from pathlib import Path

from .core.batch_processor import BatchProcessor
from .utils.config import ConversionConfig
from .utils.logger import setup_main_logger  # Import the new setup function


# Get logger (will be configured in run_cli)
log = logging.getLogger("fb2_converter")


def int_in_range(min_val, max_val):
    """Checks if value is an int in [min_val, max_val] range."""
    def checker(value):
        ivalue = int(value)
        # if ivalue < min_val or max_val < ivalue:
        if not (min_val <= ivalue <= max_val):
            raise argparse.ArgumentTypeError(f"Value must be between {min_val} and {max_val}, got {ivalue}")
        return ivalue
    return checker

def int_tuple():
    """Checks if value is an (int, int) tuple."""
    def checker(value):
        tvalue = tuple(int(v.strip()) for v in value.split(','))
        if len(tvalue) != 2:
            raise argparse.ArgumentTypeError(f"Value must be a comma separated (int, int) tuple, got {tvalue}")
        return tvalue
    return checker


def run_cli():
    """
    The main function for the command-line interface.
    Parses arguments and runs the conversion pipeline.
    """
    parser = argparse.ArgumentParser(
        description="A robust FB2 to EPUB3 converter.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("input_paths", type=Path, nargs="+", 
                        help="Input .fb2, .fb2.zip files or/and folders separated by a space.")
    parser.add_argument("-o", "--output", type=Path, default=None, 
                        help="Output folder or filename (for single input). If omitted, each output is placed next to the input file.")
    parser.add_argument("-t", "--toc-depth", type=int_in_range(1, 6), default=4,
                        help="Maximum heading level to include in TOC [1..6] (e.g., 4 to include h1-h4).")
    parser.add_argument("-s", "--split-level", type=int_in_range(1, 6), default=1, 
                        help="Heading level to split chapters into separate files [1..6] (e.g. 2 to split at every h2).")
    parser.add_argument("-z", "--split-size", type=int, default="0", 
                        help="Increment split-level if XHTML files exceed this size in KB. 0 to disable.")
    parser.add_argument("-c", "--css", type=Path, default=None, 
                        help="Path to a custom CSS file.")
    parser.add_argument("-typ", "--typography", action="store_true", help="Enable typography post-processing.")
    parser.add_argument("-typ-nbsp", type=int_tuple(), default=(1, 1), help="Typography: word length range to add NBSP (int, int).")
    parser.add_argument("-typ-nobr", type=int_tuple(), default=(4, 6), help="Typography: word length range to wrap in <span>.nobreak (int, int).")
    parser.add_argument("--threads", type=int, default="0", 
                        help="Number of parallel threads to use for conversion. 0 to use max.")

    args = parser.parse_args()
    
    console_level = logging.ERROR
    setup_main_logger(console_level)
    log.info(f"Console logger set to level: {logging.getLevelName(console_level)}")

    # Collect all files to be processed
    files_to_process = []
    for path in args.input_paths:
        if not path.exists():
            log.warning(f"Input path does not exist, skipping: {path}")
            continue
        if path.is_dir():
            for ext in ("**/*.fb2", "**/*.fb2.zip"):
                files_to_process.extend(path.rglob(ext))
        elif path.is_file() and path.suffix in ['.fb2', '.zip']:
            filename = str(path)
            if filename.endswith('.fb2') or filename.endswith('.fb2.zip'):
                files_to_process.append(path)

    if not files_to_process:
        log.warning("No .fb2 or .fb2.zip files found to process.")
        return

    # Create configuration and run batch processor
    config = ConversionConfig(
        output_path=args.output,
        toc_depth=args.toc_depth,
        split_level=args.split_level,
        split_size_kb=args.split_size,
        improve_typography=args.typography,
        word_len_nbsp_range=args.typ_nbsp,
        word_len_nobreak_range=args.typ_nobr,
        custom_stylesheet=args.css,
        num_threads=args.threads,
    )
    processor = BatchProcessor(config)

    num_files = len(files_to_process)
    log.info(f"Found {len(files_to_process)} files. Starting conversion...")
    
    completed_count = 0
    def progress_callback(path: Path, result: Path | None, exc: Exception | None):
        nonlocal completed_count
        completed_count += 1
        # pad completed_count with spaces for alignment
        completed_str = str(completed_count).rjust(len(str(num_files)))
        prefix = f"[{completed_str}/{num_files}]"
        if exc:
            print(f"{prefix} ❌ Error: {path.name}", flush=True)
            print(f"  └─ {exc}", flush=True)
            # Also log the error to file/console handlers
            # Set exc_info=False to avoid duplicate stack trace on console
            # (file log will have full trace from worker)
            log.error(f"Failed to convert {path.name}: {exc}", exc_info=False) 
        else:
            print(f"{prefix} ✅ Done: {path.name}", flush=True)
    
    processor.run(files_to_process, progress_callback)

    print("\nBatch conversion finished.")
