"""
fictionpub/pyside6/models/collation.py

Natural sort key with correct Ukrainian (Cyrillic) collation.

Problems solved
---------------
1. Lexicographic digit ordering: '20', '200', '2000', '21' should sort
   as 20, 21, 200, 2000 — not 20, 200, 2000, 21.

2. Ukrainian ґ (U+0491) lives in the *extended* Cyrillic Unicode block,
   so plain Unicode ordering places it after я (U+044F).  In the Ukrainian
   alphabet ґ follows г immediately.

Solution
--------
natural_collation_key(s) returns a list of comparable tuples:

  (False, integer, ())     for a run of digits   → sorts numerically
  (True,  0, char_weights) for a run of letters   → sorted by per-char weight

Character weights
-----------------
Ukrainian alphabet letters map to (0, position) where position is the
0-based index in the standard Ukrainian alphabet
    а б в г ґ д е є ж з и і ї й к л м н о п р с т у ф х ц ч ш щ ь ю я
so г=13, ґ=14, д=15, …

Every other character maps to (1, unicode_codepoint), placing it after
all Ukrainian letters but still in a deterministic order.

Case is folded before building the key; case-insensitive sort is the
correct default for file-name display.
"""

from __future__ import annotations

import re

# ── Ukrainian alphabet weight table ──────────────────────────────────────────

_UA_LOWER = "абвгґдеєжзиіїйклмнопрстуфхцчшщьюя"

# Map every Ukrainian letter (both cases) to its alphabetical position.
_UA_WEIGHTS: dict[str, int] = {}
for _i, _ch in enumerate(_UA_LOWER):
    _UA_WEIGHTS[_ch] = _i
    _UA_WEIGHTS[_ch.upper()] = _i


def _char_key(c: str) -> tuple[int, int]:
    """
    Collation weight for a single character.

    Ukrainian letters → (0, alphabet_position)   — sort first, in UA order
    Everything else   → (1, unicode_codepoint)   — sort after, by codepoint
    """
    if c in _UA_WEIGHTS:
        return (0, _UA_WEIGHTS[c])
    return (1, ord(c))


def natural_collation_key(s: str) -> list[tuple]:
    """
    Return a directly comparable sort key for *s*.

    Digit runs are sorted numerically; text runs use per-character
    collation weights so Ukrainian letters sort in alphabet order.

    Examples
    --------
    natural sort:   ['file1', 'file2', 'file10']      → correct order
    digit runs:     ['20', '200', '2000', '21']        → [20, 21, 200, 2000]
    Ukrainian:      ['гора', 'ґрунт', 'дах']           → г, ґ, д  ✓
    """
    parts = re.split(r"(\d+)", s.lower())
    result: list[tuple] = []
    for part in parts:
        if not part:
            continue
        if part.isdigit():
            # (False, int, ()) — numerics sort before text at the same position
            result.append((False, int(part), ()))
        else:
            result.append((True, 0, tuple(_char_key(c) for c in part)))
    return result
