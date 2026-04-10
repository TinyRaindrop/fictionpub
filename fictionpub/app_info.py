"""
Single source of truth for application metadata.
"""

import pathlib

APP_NAME = "FictionPub"
APP_NAME_SHORT = "fictionpub"
APP_AUTHOR = "TinyRaindrop"
APP_AUTHORS = [{"name": APP_AUTHOR}]
APP_ORG = APP_AUTHOR
APP_DESCRIPTION = "FB2 to EPUB ebook converter."
APP_URL = "https://github.com/TinyRaindrop/fictionpub"

# 1. Dev Environment: Get real-time git version dynamically on every launch
try:
    from setuptools_scm import get_version

    # root is one level up
    _root = pathlib.Path(__file__).parent.parent
    VERSION = get_version(root=_root)
except Exception:
    # 2. Nuitka Compiled Exe: Fallback to the statically generated file
    # (Triggered because setuptools_scm is excluded in Nuitka build)
    try:
        from ._version import __version__ as VERSION
    except ImportError:
        # 3. Standard Pip Install: Fallback to static package metadata
        # (Triggered if _version.py is missing and importlib.metadata is available)
        try:
            import importlib.metadata

            VERSION = importlib.metadata.version(APP_NAME_SHORT)
        except Exception:
            # 4. Bare git clone fallback
            # Catches both ImportError and PackageNotFoundError
            VERSION = "0.0.0+unknown"
