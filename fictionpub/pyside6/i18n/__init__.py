"""
fictionpub/pyside6/i18n/__init__.py

Package entry point — re-exports the full public API from core.

Import from here everywhere:
    from .i18n import t, set_language, get_language
    from .i18n import register_listener, unregister_listener, SUPPORTED_LANGS
"""

from .core import (  # noqa: F401
    SUPPORTED_LANGS,
    get_language,
    register_listener,
    set_language,
    t,
    unregister_listener,
)
