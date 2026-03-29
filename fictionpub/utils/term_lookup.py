"""
fictionpub/utils/term_lookup.py

Lightweight key + lang → text resolver shared by the i18n module (GUI)
and LocalizedTerms (EPUB content generation).

Data contract
-------------
Both consumers work with the same structure:

    { "key": { "lang_code": "text", ... }, ... }

This class abstracts that lookup with language fallback, while remaining:
  - stateless (no app or UI coupling)
  - pickle-safe (plain dict + strings only; no lambdas, no weakrefs)
    → required because LocalizedTerms instances are shared with
      child processes via ProcessPoolExecutor.initializer
"""

from __future__ import annotations


class TermLookup:
    """
    Immutable resolver over a { key: { lang: text } } mapping.

    Parameters
    ----------
    data         : the full translation mapping
    default_lang : language used when the requested lang has no entry for a key
    """

    def __init__(
        self,
        data: dict[str, dict[str, str]],
        default_lang: str = "en",
    ) -> None:
        self._data         = data
        self._default_lang = default_lang

    # ------------------------------------------------------------------
    # Core lookup
    # ------------------------------------------------------------------

    def get(
        self,
        key: str,
        lang: str,
        default: str = "",
        *,
        fallback_lang: str | None = None,
    ) -> str:
        """
        Return the text for *key* in *lang*.

        Fallback order:
          1. entry[lang]
          2. entry[fallback_lang]  (if supplied, else entry[default_lang])
          3. *default*

        Parameters
        ----------
        key           : translation key
        lang          : preferred language code
        default       : returned when the key is absent entirely
        fallback_lang : override the instance-level default_lang for this call
                        (useful when the caller has a per-instance default, e.g.
                         LocalizedTerms with per-book default_lang)
        """
        entry = self._data.get(key)
        if not entry:
            return default

        text = entry.get(lang)
        if text:
            return text

        fb = fallback_lang if fallback_lang is not None else self._default_lang
        return entry.get(fb, default) or default

    def get_all(self, key: str) -> list[str]:
        """
        Return all non-empty translations for *key*, in insertion order.
        Returns an empty list if the key is absent.
        """
        entry = self._data.get(key)
        if not entry:
            return []
        return [v for v in entry.values() if v]

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def languages(self) -> frozenset[str]:
        """Return the set of all language codes present in the data."""
        langs: set[str] = set()
        for entry in self._data.values():
            langs.update(entry)
        return frozenset(langs)

    def __contains__(self, key: str) -> bool:
        return key in self._data

    def __len__(self) -> int:
        return len(self._data)

    def __repr__(self) -> str:
        return (
            f"TermLookup({len(self._data)} keys, "
            f"langs={sorted(self.languages())}, "
            f"default_lang={self._default_lang!r})"
        )
    