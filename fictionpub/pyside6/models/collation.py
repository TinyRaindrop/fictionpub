"""
Natural sort key with correct Cyrillic collation.

natural_collation_key(s) returns a list of comparable tuples:

  (False, integer, ())     for a run of digits   → sorts numerically
  (True,  0, char_weights) for a run of letters   → sorted by per-char weight

Character weights
-----------------
Every other character maps to (1, unicode_codepoint), placing it after
all Cyrillic letters but still in a deterministic order.

Case is folded before building the key; case-insensitive sort is the
correct default for file-name display.
"""

from __future__ import annotations

import re

# ── Cyrillic letters weight table [UA+RU] ──

_CYR_LOWER = "абвгґдеёєжзиіїйклмнопрстуфхцчшщыьэюя"

# Map every Cyrillic letter (both cases) to its alphabetical position.
_CYR_WEIGHTS: dict[str, int] = {}
for _i, _ch in enumerate(_CYR_LOWER):
    _CYR_WEIGHTS[_ch] = _i
    _CYR_WEIGHTS[_ch.upper()] = _i

# TODO: sort latin before cyrillic. Don't use manual alphabet
def _char_key(c: str) -> tuple[int, int]:
    """
    Collation weight for a single character.

    Cyrillic letters → (0, alphabet_position)   — sort first
    Everything else   → (1, unicode_codepoint)   — sort after, by codepoint
    """
    if c in _CYR_WEIGHTS:
        return (0, _CYR_WEIGHTS[c])
    return (1, ord(c))


def natural_collation_key(s: str) -> list[tuple]:
    """
    Return a directly comparable sort key for *s*.

    Digit runs are sorted numerically; text runs use per-character
    collation weights so Cyrillic letters sort in alphabet order.

    Examples
    --------
    natural sort:   ['file1', 'file2', 'file10']      → correct order
    digit runs:     ['20', '200', '2000', '21']        → [20, 21, 200, 2000]
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
