"""
Single source of truth for application name and version.

Resolution order:
  1. _version.py  — written by setuptools_scm during `python -m build`
                    or by build_exe.py before Nuitka compilation.
                    Always present in the Nuitka bundle.
  2. importlib.metadata — works when installed as a package via pip.
  3. Hard-coded fallback — for bare source checkouts with no build step.
"""
from __future__ import annotations

APP_NAME       = "FictionPub"
APP_NAME_SHORT = "fictionpub"
VERSION        = "0.0.0+unknown"

# Priority 1: generated _version.py (always available in Nuitka bundle)
try:
    from ._version import __version__, __app_name__
    VERSION  = __version__
    APP_NAME = __app_name__
except ImportError:
    pass

# Priority 2: installed package metadata (pip install / editable install)
if VERSION == "0.0.0+unknown":
    try:
        from importlib.metadata import version, PackageNotFoundError
        VERSION = version(APP_NAME_SHORT)
    except Exception:
        pass