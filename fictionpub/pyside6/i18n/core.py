"""
fictionpub/pyside6/i18n/core.py

i18n core: language state, lookup, and listener registry.

String data is loaded from lang.json (same directory) via the shared
resource loader.  Internally a TermLookup instance handles all
key + lang → text resolution with EN fallback.

Listener registry
-----------------
Uses weakref.WeakMethod for bound methods so that dialogs with
WA_DeleteOnClose are automatically de-registered when GC'd — no manual
unregister required.  Plain callables are stored as weakref.ref.
Dead references are pruned on each set_language() call.
"""

from __future__ import annotations

import weakref
from collections.abc import Callable
from contextlib import suppress

from ...resources.loader import load_json
from ...utils.term_lookup import TermLookup

# ---------------------------------------------------------------------------
# Load translation data once at import time.
# lang.json lives alongside this file in the fictionpub.pyside6.i18n package.
# ---------------------------------------------------------------------------

_raw: dict[str, dict[str, str]] = load_json("fictionpub.pyside6.i18n", "lang.json")
_lookup = TermLookup(_raw, default_lang="en")

SUPPORTED_LANGS: frozenset[str] = _lookup.languages()

_LANG: str = "en"

# Listener list: each entry is weakref.WeakMethod or weakref.ref
_listeners: list[weakref.ref] = []


# ---------------------------------------------------------------------------
# Public API  (unchanged from previous version)
# ---------------------------------------------------------------------------


def t(key: str, **kwargs) -> str:
    """
    Return the UI string for *key* in the current language.
    Falls back to English when the key is missing in the active language.
    Supports named .format() substitutions:  t("bar.ready_n_files", n=5)
    """
    text = _lookup.get(key, _LANG, default=key)
    if kwargs:
        with suppress(KeyError, IndexError):
            text = text.format(**kwargs)

    return text


def set_language(lang: str) -> None:
    """
    Change the active language and notify all live registered listeners.
    Dead weak references are pruned during this call.
    """
    global _LANG
    _LANG = lang if lang in SUPPORTED_LANGS else "en"

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
    Register a zero-arg callable to be called on every set_language().
    Bound methods → WeakMethod; plain callables → weakref.ref.
    Re-registering the same callable is a no-op.
    """
    _listeners[:] = [ref for ref in _listeners if ref() is not None]

    try:
        new_ref: weakref.ref = weakref.WeakMethod(fn)  # type: ignore[assignment]
    except TypeError:
        new_ref = weakref.ref(fn)

    for ref in _listeners:
        if ref() is fn:
            return

    _listeners.append(new_ref)


def unregister_listener(fn: Callable[[], None]) -> None:
    """Remove a previously registered callable (no-op if not found)."""
    _listeners[:] = [ref for ref in _listeners if ref() is not fn]
