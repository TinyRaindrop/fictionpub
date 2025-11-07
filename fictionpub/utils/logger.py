"""
Handles configuration of logging for the main process and for
multiprocessing workers.
"""
import logging
import sys
import os
import io
from pathlib import Path
from datetime import datetime
from logging.handlers import RotatingFileHandler

# Define a consistent log directory
LOG_DIR = Path("./logs")
MAX_LOG_FILES = 20
CONSOLE_LOG_FORMAT = "%(levelname)s: %(message)s"
FILE_LOG_FORMAT = (
    "%(asctime)s [%(process)d] %(levelname)s - [%(module)s:%(lineno)d] - %(message)s"
)


def setup_main_logger(console_level=logging.ERROR):
    """
    Configures the root logger for the main application process.

    This logger will handle console output (at the specified level)
    and file output (at DEBUG level) for a new, unique log file.
    It also performs log rotation.
    """
    logger = logging.getLogger("fb2_converter")
    logger.setLevel(logging.DEBUG)  # Capture all levels

    # Avoid adding duplicate handlers
    if logger.hasHandlers():
        logger.handlers.clear()

    # --- Console Handler ---
    # Logs to stdout, respecting the level set by CLI/GUI
    try:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(console_level)
        console_formatter = logging.Formatter(CONSOLE_LOG_FORMAT)
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)
    except Exception as e:
        # Fallback in case stdout is unusual (e.g., in pyinstaller --noconsole)
        print(f"Warning: Could not set up console logger: {e}")


    # --- File Handler (Rotation and New File) ---
    try:
        LOG_DIR.mkdir(exist_ok=True)

        # 1. Rotate old logs
        # Get logs, sort by creation time (oldest first)
        logs = sorted(
            [p for p in LOG_DIR.glob("converter_*.log") if p.is_file()],
            key=os.path.getmtime,
        )

        # Remove oldest logs if over limit
        files_to_remove = len(logs) - (MAX_LOG_FILES - 1)
        if files_to_remove > 0:
            for log_file in logs[:files_to_remove]:
                try:
                    log_file.unlink()
                except OSError:
                    pass  # Ignore errors if file is locked
        
        # 2. Create new log file for this run
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        new_log_path = LOG_DIR / f"converter_{timestamp}.log"

        file_handler = logging.FileHandler(new_log_path, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)  # Always log everything to file
        file_formatter = logging.Formatter(FILE_LOG_FORMAT, datefmt="%Y-%m-%d %H:%M:%S")
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)

        logger.info(
            "Main logger initialized. Console level: %s, File level: DEBUG. Logging to: %s",
            logging.getLevelName(console_level),
            new_log_path,
        )
    except Exception as e:
        logger.error("CRITICAL: Failed to set up file logging.", exc_info=True)


def setup_worker_logger():
    """
    Configures a temporary, in-memory logger for a child process.
    
    Returns:
        tuple[io.StringIO, logging.Handler]: 
            - The string buffer that will capture logs.
            - The handler attached to the logger.
    (Both must be closed by the caller)
    """
    log_stream = io.StringIO()
    
    # Create a handler that writes to the string buffer
    handler = logging.StreamHandler(log_stream)
    handler.setLevel(logging.DEBUG)  # Capture everything from this worker
    
    formatter = logging.Formatter(FILE_LOG_FORMAT, datefmt="%H:%M:%S")
    handler.setFormatter(formatter)

    # Get the logger for this process
    logger = logging.getLogger("fb2_converter")
    logger.handlers.clear()  # Remove any handlers inherited from parent
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    
    # Return the buffer and handler so they can be closed later
    return log_stream, handler
