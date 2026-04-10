"""
fictionpub/resources/localized_terms.py

Provides per-book translated strings used during EPUB generation
(genre names, section headings, etc.).

Internally uses TermLookup for key + lang → text resolution, replacing
the old Term NamedTuple approach with the shared utility.

Public API and multiprocessing interface (inject_terms / get_terms) are
unchanged so batch_processor.py requires no modification.

Language lifecycle
------------------
Language is per-book (set from FB2 metadata), entirely independent of
the GUI language.  A LocalizedTerms instance is created once per file
inside the conversion pipeline worker.
"""

from __future__ import annotations

import logging
from typing import ClassVar

from ..utils.term_lookup import TermLookup
from .loader import load_terms_json

log = logging.getLogger("fb2_converter")


def clear_lang(lang: str) -> str:
    """Normalise a language code to a 2-letter ISO 639-1 code."""
    lang_map = {"ua": "uk"}
    clean = lang_map.get(lang) or lang[:2].lower()
    if clean != lang:
        log.info("[Language]: Using %s instead of %s.", clean, lang)
    return clean


class LocalizedTerms:
    """
    Wrapper for translatable EPUB content strings.

    Class-level TermLookup instances hold the full translation tables;
    instances carry only the language preference for a specific book.

    Usage
    -----
    Call LocalizedTerms.load_terms() once at startup (or let it lazy-load).
    Construct instances with the book's language code:

        terms = LocalizedTerms(lang=metadata["lang"])
        heading = terms.get_heading("toc")

    Multiprocessing
    ---------------
    The class-level data is passed to child processes via get_terms() /
    inject_terms().  TermLookup is pickle-safe (plain dicts + strings).
    """

    # Class-level lookup tables, shared across all instances
    _GENRES: ClassVar[TermLookup | None] = None
    _HEADINGS: ClassVar[TermLookup | None] = None

    # Supported book languages (derived from heading data after first load)
    _SUPPORTED_BOOK_LANGS: ClassVar[frozenset[str]] = frozenset()

    # ------------------------------------------------------------------
    # Class-level lifecycle
    # ------------------------------------------------------------------

    @classmethod
    def _build_lookup(cls, filename: str) -> TermLookup:
        """Load a terms JSON file and wrap it in a TermLookup."""
        data = load_terms_json(filename)
        return TermLookup(data, default_lang="uk")

    @classmethod
    def load_terms(cls) -> None:
        """
        Load genre and heading translations from JSON resource files.
        Must be called once before creating instances (or is called lazily).
        """
        cls._GENRES = cls._build_lookup("genres.json")
        cls._HEADINGS = cls._build_lookup("headings.json")
        cls._SUPPORTED_BOOK_LANGS = cls._HEADINGS.languages()

    @classmethod
    def inject_terms(cls, terms: tuple[TermLookup, TermLookup]) -> None:
        """
        Inject pre-loaded TermLookup objects into the class.
        Called once inside each ProcessPoolExecutor worker via the initializer.
        """
        cls._GENRES, cls._HEADINGS = terms
        if cls._HEADINGS is not None:
            cls._SUPPORTED_BOOK_LANGS = cls._HEADINGS.languages()

    @classmethod
    def get_terms(cls) -> tuple[TermLookup, TermLookup]:
        """
        Return (genres_lookup, headings_lookup) for passing to child processes.
        Triggers a lazy load if the tables have not been loaded yet.
        """
        if cls._GENRES is None or cls._HEADINGS is None:
            cls.load_terms()
        return cls._GENRES, cls._HEADINGS  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # Instance lifecycle
    # ------------------------------------------------------------------

    def __init__(self, lang: str = "uk", default_lang: str = "uk") -> None:
        """
        Parameters
        ----------
        lang         : language code from FB2 metadata (e.g. "uk", "ru", "en")
        default_lang : fallback language when the book's lang has no translation
        """
        lang = clear_lang(lang)

        # Ensure tables are available (lazy load on first instantiation)
        if self.__class__._GENRES is None or self.__class__._HEADINGS is None:
            log.debug("[LocalizedTerms] Missing terms — loading from file.")
            self.__class__.load_terms()

        supported = self.__class__._SUPPORTED_BOOK_LANGS
        if lang not in supported:
            log.info(
                "Unsupported book language: '%s'. Must be one of %s. Falling back to [%s].",
                lang,
                sorted(supported),
                default_lang,
            )
            lang = default_lang

        self.lang = lang or default_lang
        self.default_lang = default_lang

    # ------------------------------------------------------------------
    # Term accessors
    # ------------------------------------------------------------------

    def _get(self, lookup: TermLookup, key: str, default: str = "") -> str:
        """Resolve key → text using this instance's lang + default_lang."""
        return lookup.get(key, self.lang, default=default, fallback_lang=self.default_lang)

    def get_genre(self, key: str, default: str = "") -> str:
        """Return a genre name in the book's language."""
        return self._get(self.__class__._GENRES, key, default)  # type: ignore[arg-type]

    def get_heading(self, key: str, default: str = "") -> str:
        """Return a section heading in the book's language."""
        return self._get(self.__class__._HEADINGS, key, default)  # type: ignore[arg-type]

    def get_all_headings(self, key: str, default: str = "") -> list[str]:
        """
        Return all non-empty translations of a heading key across all languages.
        Falls back to [default] when the key is absent.
        Used when searching for known heading text variants in source FB2.
        """
        result = self.__class__._HEADINGS.get_all(key)  # type: ignore[union-attr]
        return result if result else [default]
