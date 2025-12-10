"""
The main entry point for the FB2 to EPUB Converter application.

This module inspects command-line arguments to decide whether to launch
the command-line interface (CLI) or the graphical user interface (GUI).
"""
from enum import Enum
import sys
import logging

from .terms.localized_terms import LocalizedTerms


class AppMode(Enum):
    CLI = 1
    GUI = 2
    AUTO = 3


def main(mode: AppMode = AppMode.AUTO):
    """
    Launches either the CLI or the GUI based on the presence of command-line arguments.
    """
    log = logging.getLogger("fb2_converter")

    # Load term translations from JSONs
    LocalizedTerms.load_terms()
    
    if mode == AppMode.AUTO:
        # sys.argv[0] is always the name of the script itself.
        # If the list has more than one item, it means the user has provided arguments.
        mode = AppMode.CLI if len(sys.argv) > 1 else AppMode.GUI

    if mode == AppMode.CLI:
        try:
            from .cli import run_cli
            run_cli()
        except Exception:
            log.exception("A critical error occurred while running the CLI.")
            sys.exit(1)
    
    elif mode == AppMode.GUI:
        try:
            from .gui import run_gui
            log.info("No input file provided, launching GUI...")
            run_gui()
        except ImportError as e:
            log.error(f"GUI dependencies are missing. Please install them. Error: {e}")
            sys.exit(1)
        except Exception:
            log.exception("A critical error occurred while running the GUI.")
            sys.exit(1)


if __name__ == '__main__':
    main()
