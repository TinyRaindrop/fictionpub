"""
i18n core: language state, lookup, and listener registry.

Listener registry uses weakref.WeakMethod so that bound methods registered
by widgets are automatically dropped when the widget is garbage-collected.
This means dialogs with WA_DeleteOnClose never need to manually unregister —
once the C++ side is deleted and the Python object is GC'd, the weak
reference returns None and the entry is pruned on the next set_language call.

Plain callables (lambdas, module-level functions) are stored as weakref.ref.
"""

import weakref
from typing import Callable

from .lang_en import STRINGS as _EN
from .lang_uk import STRINGS as _UK

_BUNDLES: dict[str, dict[str, str]] = {
    "en": _EN,
    "uk": _UK,
}

SUPPORTED_LANGS: frozenset[str] = frozenset(_BUNDLES)

_LANG: str = "en"

# Each entry is a weakref.WeakMethod or weakref.ref.
# Using a list; order is preserved (registration order = notification order).
_listeners: list[weakref.ref] = []


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def t(key: str, **kwargs) -> str:
    """
    Look up a UI string by key in the current language, falling back to English.
    Supports .format() substitutions:  t("bar.ready_n_files", n=5)
    """
    bundle = _BUNDLES.get(_LANG, _EN)
    text   = bundle.get(key) or _EN.get(key, key)
    if kwargs:
        try:
            text = text.format(**kwargs)
        except (KeyError, IndexError):
            pass
    return text


def set_language(lang: str) -> None:
    """
    Change the active language and notify all live registered listeners.
    Dead weak references are pruned during this call.
    """
    global _LANG
    _LANG = lang if lang in _BUNDLES else "en"

    live: list[weakref.ref] = []
    for ref in _listeners:
        fn = ref()
        if fn is not None:
            live.append(ref)
            fn()
    _listeners[:] = live


def get_language() -> str:
    return _LANG


def register_listener(fn: Callable[[], None]) -> None:
    """
    Register a callable to be invoked on every set_language() call.
    Bound methods are stored as WeakMethod; plain callables as weakref.ref.
    Re-registering the same callable is a no-op.
    """
    # Prune dead refs first
    _listeners[:] = [ref for ref in _listeners if ref() is not None]

    # Build the weak reference
    try:
        new_ref: weakref.ref = weakref.WeakMethod(fn)  # type: ignore[assignment]
    except TypeError:
        new_ref = weakref.ref(fn)

    # Deduplicate: don't add if the same live callable is already registered
    for ref in _listeners:
        if ref() is fn:
            return

    _listeners.append(new_ref)


def unregister_listener(fn: Callable[[], None]) -> None:
    """Remove a previously registered callable (no-op if not found)."""
    _listeners[:] = [ref for ref in _listeners if ref() is not fn]
