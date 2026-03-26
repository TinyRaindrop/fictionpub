"""
i18n package entry point.

Import from here everywhere:
    from .i18n import t, set_language, get_language, register_listener, unregister_listener, SUPPORTED_LANGS
"""

from .core import (  # noqa: F401  (re-exported)
    SUPPORTED_LANGS,
    get_language,
    register_listener,
    set_language,
    t,
    unregister_listener,
)
