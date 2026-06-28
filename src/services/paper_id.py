"""Canonical paper_id generation helpers.

Priority chain for paper_id resolution:
  1. CLI --paper-id (highest, enforced by caller)
  2. sidecar.canonical_paper_id
  3. sidecar.proposed_paper_id
  4. DOI metadata → year + first_author + short_title_slug
  5. chinese_title → year + first_author + chinese_title_slug
  6. title/year/authors → year + first_author + title_slug
  7. title/year → year + title_slug
  8. filename fallback (last resort, always warns)
"""
from __future__ import annotations

import re

from loguru import logger

from src.naming import sanitize_paper_id, validate_paper_id


def _slug(text: str, max_len: int = 50) -> str:
    text = text or ""
    slug = re.sub(r"[^一-鿿A-Za-z0-9]+", "_", text).strip("_").lower()
    if len(slug) > max_len:
        slug = slug[:max_len].rstrip("_")
    return slug or "untitled"


def _first_author_slug(authors: list | str | None) -> str:
    if not authors:
        return ""
    first = authors[0] if isinstance(authors, list) else str(authors).split(",", 1)[0]
    if isinstance(first, dict):
        first = first.get("last") or first.get("family") or first.get("name") or ""
    first = str(first).strip()
    if not first:
        return ""
    # If "Family, Given" format, take family name
    if "," in first:
        first = first.split(",", 1)[0].strip()
    return _slug(first, max_len=24)


def generate_paper_id(
    *,
    year: int | None,
    title: str,
    authors: list | str | None = None,
    chinese_title: str = "",
) -> str:
    """Generate a filesystem-safe paper_id.

    Priority:
      1. year + first_author + (chinese_title or title_slug)
      2. year + title_slug
      3. first_author + title_slug
      4. title_slug only (fallback)

    If author metadata is missing, preserve the historic fallback
    ``{year}_{title_slug}`` to avoid surprising existing imports.
    """
    title_slug = _slug(chinese_title or title, max_len=50)
    author_slug = _first_author_slug(authors)
    if year and author_slug:
        candidate = f"{year}_{author_slug}_{title_slug}"
    elif year:
        candidate = f"{year}_{title_slug}"
    elif author_slug:
        candidate = f"{author_slug}_{title_slug}"
    else:
        candidate = title_slug
    candidate = sanitize_paper_id(candidate)
    validate_paper_id(candidate)
    return candidate


def resolve_paper_id(
    *,
    cli_paper_id: str = "",
    canonical_paper_id: str = "",
    proposed_paper_id: str = "",
    doi: str = "",
    title: str = "",
    year: int | None = None,
    authors: list | str | None = None,
    chinese_title: str = "",
    filename_stem: str = "",
) -> tuple[str, list[str]]:
    """Resolve the final paper_id using the full priority chain.

    Returns (paper_id, warnings).

    Priority:
      1. cli_paper_id (explicit --paper-id)
      2. canonical_paper_id (from sidecar, trusted)
      3. proposed_paper_id (from metadata enrichment)
      4. Generate from DOI metadata (year + first_author + title)
      5. Generate from title/year/authors
      6. Fallback to filename stem (always warns)
    """
    warnings: list[str] = []

    # 1. CLI explicit
    if cli_paper_id:
        try:
            validate_paper_id(cli_paper_id)
        except ValueError as e:
            raise ValueError(f"invalid --paper-id: {e}") from e
        return cli_paper_id, warnings

    # 2. sidecar canonical
    if canonical_paper_id:
        try:
            validate_paper_id(canonical_paper_id)
        except ValueError:
            warnings.append(f"sidecar canonical_paper_id invalid: {canonical_paper_id!r}")
        else:
            return canonical_paper_id, warnings

    # 3. sidecar proposed
    if proposed_paper_id:
        try:
            validate_paper_id(proposed_paper_id)
        except ValueError:
            warnings.append(f"sidecar proposed_paper_id invalid: {proposed_paper_id!r}")
        else:
            return proposed_paper_id, warnings

    # 4-5. Generate from metadata
    if title or year or authors:
        pid = generate_paper_id(
            year=year,
            title=title,
            authors=authors,
            chinese_title=chinese_title,
        )
        return pid, warnings

    # 6. Filename fallback (last resort)
    if filename_stem:
        pid = sanitize_paper_id(filename_stem)
        try:
            validate_paper_id(pid)
        except ValueError:
            pid = "untitled"
        warnings.append(
            "paper_id generated from filename fallback; "
            "pass --doi/--title/--year/--paper-id or run metadata enrichment for canonical naming"
        )
        return pid, warnings

    raise ValueError(
        "cannot resolve paper_id: no CLI paper_id, sidecar metadata, title/year, "
        "or filename stem provided"
    )
