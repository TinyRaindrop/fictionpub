"""
Defines configuration and result types for the conversion process,
plus the single source of truth for EPUB output-path resolution.

resolve_epub_path()
-------------------
Both EpubBuilder and MainWindow call this function so the resolved path
is computed exactly once with identical logic.

BatchAnchor
-----------
Precomputed once per batch by BatchProcessor and forwarded through the
pipeline.  Captures the common ancestor of all source files so that
retain_folder_structure can produce consistent relative paths even when
the source files come from different directories or drives.

Cross-drive handling (Windows)
-------------------------------
If files span more than one Windows drive letter (or more than one POSIX
root), each drive's files are placed in a subfolder named after the
drive letter (without the colon), and the full absolute path below that
drive is replicated:

    E:\\books\\fantasy\\book.fb2  →  <out>/e/books/fantasy/book.epub
    F:\\docs\\book.fb2            →  <out>/f/docs/book.epub

Single-drive / POSIX
--------------------
The common ancestor of all source-file parent directories is stripped,
and the remainder is replicated under output_path:

    source files common ancestor : /books
    /books/fantasy/book.fb2      →  <out>/fantasy/book.epub
    /books/scifi/book.fb2        →  <out>/scifi/book.epub
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

@dataclass
class ConversionConfig:
    """
    All settings for a single conversion task.
    Created by the UI layer and forwarded to ConversionPipeline.
    """

    # ── Output location ──────────────────────────────────────────────────
    # None  → place the .epub next to the source file
    output_path: Path | None = None
    # Only meaningful when output_path is set:
    # mirror the relative directory structure of each source file
    # under output_path, starting from the batch's common ancestor.
    retain_folder_structure: bool = False

    # ── Document structure ───────────────────────────────────────────────
    toc_depth:    int = 4
    split_level:  int = 2
    split_size_kb: int = 0   # 0 = disabled  # TODO: implement

    # ── Processing ───────────────────────────────────────────────────────
    remove_unused_images: bool = True
    improve_typography:   bool = False
    # Conservative defaults for typography processing word-length ranges
    word_len_nbsp_range:    tuple[int, int] = (1, 1)
    word_len_nobreak_range: tuple[int, int] = (4, 6)

    # ── Stylesheet ───────────────────────────────────────────────────────
    custom_stylesheet: Path | None = None

    # ── Parallelism ──────────────────────────────────────────────────────
    num_threads: int = 0   # 0 = auto-detect


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

class ConversionStatus(Enum):
    SUCCESS = auto()
    WARNING = auto()
    FAILURE = auto()


@dataclass
class ConversionResult:
    path: Path
    status: ConversionStatus
    log_output: str = ""
    error: Exception | None = None


# ---------------------------------------------------------------------------
# Batch anchor — precomputed once for a whole batch
# ---------------------------------------------------------------------------

@dataclass
class BatchAnchor:
    """
    Common-ancestor descriptor for a conversion batch.

    cross_drive : True when source files span multiple drive letters (Win)
                  or cannot share a common absolute ancestor.
    common      : The common ancestor Path, valid only when cross_drive=False.
    """
    cross_drive: bool = False
    common: Path | None = None


def compute_batch_anchor(paths: list[Path]) -> BatchAnchor:
    """
    Compute the BatchAnchor for a list of source file paths.
    Uses resolved absolute paths to normalise symlinks and relative refs.
    """
    if not paths:
        return BatchAnchor()

    # Work with the resolved parent directories
    parents = [p.resolve().parent for p in paths]

    # Group by drive letter (Windows) or the empty string (POSIX)
    drives = {p.drive for p in parents}

    if len(drives) > 1:
        # Files on different drives — no single common ancestor possible
        return BatchAnchor(cross_drive=True)

    if len(parents) == 1:
        return BatchAnchor(cross_drive=False, common=parents[0])

    try:
        common = Path(os.path.commonpath(parents))
        return BatchAnchor(cross_drive=False, common=common)
    except ValueError:
        # commonpath raises ValueError for mixed absolute/relative or cross-drive
        return BatchAnchor(cross_drive=True)


# ---------------------------------------------------------------------------
# EPUB output-path resolution — single source of truth
# ---------------------------------------------------------------------------

def _epub_stem(source: Path) -> str:
    """Strip .fb2 or .fb2.zip extension and return the bare stem."""
    name = source.name
    if name.endswith(".fb2.zip"):
        return name[:-8]
    if name.endswith(".fb2"):
        return name[:-4]
    return source.stem


def resolve_epub_path(
    source: Path,
    config: ConversionConfig,
    anchor: BatchAnchor | None = None,
) -> Path:
    """
    Return the full Path where the output .epub should be written.

    This is the single source of truth called by both EpubBuilder and
    MainWindow so that the path never diverges between writing and opening.

    Rules
    -----
    1. config.output_path is None
       → <source_parent>/<stem>.epub  (same folder as source)

    2. config.output_path set, retain_folder_structure=False
       → <output_path>/<stem>.epub  (flat output)

    3. config.output_path set, retain_folder_structure=True, single drive
       → <output_path>/<rel_to_common>/<stem>.epub

    4. config.output_path set, retain_folder_structure=True, cross-drive
       → <output_path>/<drive_letter>/<abs_path_below_drive>/<stem>.epub
    """
    stem = _epub_stem(source)
    resolved_source = source.resolve()

    # ── Rule 1: no custom output_path ────────────────────────────────────
    if config.output_path is None:
        return source.parent / f"{stem}.epub"

    out = config.output_path

    # ── Rule 2: flat output ───────────────────────────────────────────────
    if not config.retain_folder_structure or anchor is None:
        return out / f"{stem}.epub"

    # ── Rules 3 & 4: structured output ───────────────────────────────────
    src_parent = resolved_source.parent

    if anchor.cross_drive:
        # ── Rule 4: cross-drive ───────────────────────────────────────────
        drive = resolved_source.drive  # 'C:' on Windows, '' on POSIX
        if drive:
            # Windows: 'E:' → folder 'e'; strip drive root from parts
            drive_folder = drive.lower().rstrip(":")
            # parts[0] is 'E:\\', parts[1:] is the rest of the path
            rel_parts = src_parent.parts[1:]
            rel = Path(*rel_parts) if rel_parts else Path()
            if str(rel) == ".":
                return (out / drive_folder / f"{stem}.epub")
            return out / drive_folder / rel / f"{stem}.epub"
        else:
            # POSIX without drives — use path relative to '/'
            # parts[0] is '/', parts[1:] is the rest
            rel_parts = src_parent.parts[1:]
            rel = Path(*rel_parts) if rel_parts else Path()
            if str(rel) == ".":
                return out / f"{stem}.epub"
            return out / rel / f"{stem}.epub"

    else:
        # ── Rule 3: same drive / POSIX with common ancestor ───────────────
        common = anchor.common
        if common is None:
            return out / f"{stem}.epub"
        try:
            rel = src_parent.relative_to(common)
        except ValueError:
            # Safety fallback: src_parent is somehow outside common
            return out / f"{stem}.epub"
        return out / rel / f"{stem}.epub"