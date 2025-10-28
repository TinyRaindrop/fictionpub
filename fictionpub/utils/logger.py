import logging
import sys
import os

from datetime import datetime
from logging.handlers import RotatingFileHandler

def setup_logger():
    """
    Configures a root logger for the application.

    This setup provides a detailed format that includes the timestamp,
    log level, module name, and the message. It logs to the console.
    """
    # Get the root logger
    logger = logging.getLogger("fb2_converter")
    logger.setLevel(logging.INFO) # Set the lowest level to capture

    # Avoid adding duplicate handlers if this is called more than once
    if logger.hasHandlers():
        logger.handlers.clear()

    # Create a handler to print to the console (stderr)
    handler = logging.StreamHandler(sys.stdout)
    
    # Create a formatter and set it for the handler
    formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - [%(module)s:%(lineno)d] - %(message)s',
        datefmt='%H:%M:%S'
    )
    handler.setFormatter(formatter)

    # Add the handler to the logger
    logger.addHandler(handler)
