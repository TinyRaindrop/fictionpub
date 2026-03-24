from collections.abc import Iterator
from typing import NamedTuple


class TOCItem(NamedTuple):
    """A container for Table of Contents items."""

    level: int
    text: str
    href_nav: str
    href_ncx: str


def iter_toc_items(items: list[TOCItem], max_depth: int) -> Iterator[tuple[TOCItem, int]]:
    """
    Yields (item, depth) for building nested TOC structures.
    Filters items beyond max_depth, clamps forward jumps to at most one level
    deeper to prevent gaps in nesting. depth is 1-based.
    """
    current_depth = 0
    for item in items:
        if item.level > max_depth:
            continue
        depth = min(item.level, current_depth + 1)
        current_depth = depth
        yield item, depth
