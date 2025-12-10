import logging
from typing import NamedTuple

from ..resources.loader import load_terms_json


log = logging.getLogger("fb2_converter")


class Term(NamedTuple):
    """Represents a term with Ukrainian, Russian and English names."""
    uk: str
    ru: str
    en: str


class LocalizedTerms:
    """
    A wrapper class for translatable text. Loads available translations from json.
    Instances can be initialized with a lang parameter and use get_term() methods.
    """
    _GENRES: dict[str, Term] = {}
    _HEADINGS: dict[str, Term] = {}

    @staticmethod
    def _get_json_data(filename: str) -> dict[str, Term]:
        """Parses json data and returns a dict of {key: Term}."""
        data = load_terms_json(filename)
        return {k: Term(**v) for k, v in data.items()}


    @classmethod
    def load_terms(cls):
        """LocalizedTerms.load_terms() must be called once before creating instances."""
        cls._GENRES = cls._get_json_data("genres.json")
        cls._HEADINGS = cls._get_json_data("headings.json")


    @classmethod
    def inject_terms(cls, terms: tuple):
        """
        Manually sets terms data returned by get_terms().
        Used for initialization in multiprocessing.
        """
        cls._GENRES, cls._HEADINGS = terms


    @classmethod
    def get_terms(cls) -> tuple:
        """Returns (GENRES, HEADINGS) tuple."""
        return cls._GENRES, cls._HEADINGS


    def __init__(self, lang: str ='uk', default_lang = 'uk'):
        """Pass lang=metadata['lang']. Default_lang is used as a fallback in getters."""
        if lang not in Term._fields:
            log.warning(f"Unsupported book language: '{lang}'. Must be one of {Term._fields}. Falling back to [{default_lang}].")
            lang = default_lang
        self.lang = lang or default_lang
        self.default_lang = default_lang    # used as a fallback in getters

        if not self.__class__._GENRES or not self.__class__._HEADINGS:
            log.debug(f"[LocalizedTerms] Missing terms. Loading from file.")
            self.__class__.load_terms()


    def _get_translation(self, dictionary, key, default='') -> str:
        """General method to fetch a term from a dictionary with language fallback."""
        term = dictionary.get(key)
        if not term:
            return default

        translation = getattr(term, self.lang, None)

        # Fall back to default lang if requested lang doesn't have a translation
        if translation is None:
            translation = getattr(term, self.default_lang, default)

        return translation


    def get_genre(self, key, default=''):
        """Get a genre translation."""
        return self._get_translation(self.__class__._GENRES, key, default)


    def get_heading(self, key, default=''):
        """Get a heading translation."""
        return self._get_translation(self.__class__._HEADINGS, key, default)


    def get_all_headings(self, key, default=''):
        """Get a list of all heading translations for a given key."""
        term = self._HEADINGS.get(key)
        if not term:
            return [default]
        return [translation for translation in term if translation]

# --- END of LocalizedTerms class ---
