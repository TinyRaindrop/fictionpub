import json
import logging
from pathlib import Path
from typing import NamedTuple


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
    def _get_json_data(filename) -> dict[str, Term]:
        json_path = Path(__file__).parent / filename    # or simply use relative Path(filename)
        if not json_path.is_file():
            log.warning(f"[LocalizedTerms]: {filename} is not found")
            return {}
        
        terms: dict = {}
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            for key, translations in data.items():
                terms[key] = Term(**translations)
        return terms
    
    @classmethod
    def load_terms(cls):
        """LocalizedTerms.load_terms() must be called once before creating instances."""
        cls._GENRES = cls._get_json_data("genres.json")
        cls._HEADINGS = cls._get_json_data("headings.json")

    def __init__(self, lang: str ='uk', default_lang = 'uk'):
        """Pass lang=metadata['lang']. Default_lang is used as a fallback in getters."""
        if lang not in Term._fields:
            log.warning(f"Unsupported book language: '{lang}'. Must be one of {Term._fields}. Falling back to [{default_lang}].")
            lang = default_lang
        self.lang = lang or default_lang
        self.default_lang = default_lang    # used as a fallback in getters

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
        return self._get_translation(self._GENRES, key, default)
    
    def get_heading(self, key, default=''):
        """Get a heading translation."""
        return self._get_translation(self._HEADINGS, key, default)
    
    def get_all_headings(self, key, default=''):
        """Get a list of all heading translations for a given key."""
        term = self._HEADINGS.get(key)
        if not term:
            return [default]
        return [translation for translation in term if translation]

# --- END of LocalizedTerms class ---
