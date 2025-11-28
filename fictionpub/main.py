# #nuitka-project: --onefile
# #nuitka-project: --standalone
# nuitka-project: --output-filename=fictionpub.exe
# nuitka-project: --output-dir=./dist/

# nuitka-project: --windows-console-mode=force
# (disable/force/attach/hide)

# nuitka-project: --lto=yes
# nuitka-project: --assume-yes-for-downloads

# nuitka-project: --enable-plugin=tk-inter

# include resource folder
# nuitka-project: --include-data-dir=fictionpub/resources=resources
# nuitka-project: --include-data-files=fictionpub/terms/*.json=terms/

# nuitka-project: --static-libpython=auto
# nuitka-project: --follow-imports


"""
The main entry point for the FB2 to EPUB Converter application.

This module inspects command-line arguments to decide whether to launch
the command-line interface (CLI) or the graphical user interface (GUI).
"""
import sys
import logging

from .terms.localized_terms import LocalizedTerms


def strip_pyinstaller_args():
    """
    Remove arguments PyInstaller injects into sys.argv 
    when spawning a multiprocessing bootstrap process.
    """
    pyinst_prefixes = (
        "--multiprocessing-fork",
        "--multiprocessing-spawn",
        "--piesubproc",
    )

    def is_bad(a):
        return a.startswith(pyinst_prefixes) or (
            # Arguments like: parent_pid=123, pipe_handle=123
            "=" in a and a.split("=")[0] in ("parent_pid", "pipe_handle")
        )

    sys.argv = [a for a in sys.argv if not is_bad(a)]


def main():
    """
    Launches either the CLI or the GUI based on the presence of command-line arguments.
    """
    log = logging.getLogger("fb2_converter")

    # Load term translations from JSONs
    LocalizedTerms.load_terms()
    
    strip_pyinstaller_args()

    # sys.argv[0] is always the name of the script itself.
    # If the list has more than one item, it means the user has provided arguments.
    
    if len(sys.argv) > 1:
        try:
            from .cli import run_cli
            run_cli()
        except Exception:
            # Top-level catch for critical failures during CLI startup.
            log.exception("A critical error occurred while running the CLI.")
            sys.exit(1)
    else:
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
