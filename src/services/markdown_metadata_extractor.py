"""Extract bibliographic metadata from MinerU-converted Markdown.

Reads a MinerU markdown file and attempts to extract:
- DOI (full text scan, regex)
- Title (first markdown heading or prominent early line)
- Authors (lines after title with person-name patterns)
- Year (DOI metadata, copyright line, catalog fallback)
- Venue / journal name
- Abstract (text between Abstract and Introduction markers)

All extraction is heuristic; results are candidates, not authoritative.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from loguru import logger

# ── DOI regex (same as metadata_enrichment_service) ───────────────────
_DOI_RE = re.compile(
    r"""(?ix)
    (?:doi\s*[:=\s]+)?
    (?:https?://(?:dx\.)?doi\.org/)?
    (10\.\d{4,}/[^\s<>"')\]};,]+)
    """,
)
_DOI_TRAILING_RE = re.compile(r"""[.,;)\]};:'"]+$""")

# ── Patterns for extracting metadata ──────────────────────────────────

# Lines that are clearly NOT titles
_NON_TITLE_PATTERNS = re.compile(
    r"^(?:abstract|introduction|references?|acknowledg|"
    r"received|accepted|published|"
    r"keywords?|nomenclature|contents?|"
    r"correspondence|author|email|"
    r"copyright|\©|http|www\.|doi\s*[:=]|"
    r"figure|table|appendix|"
    r"supplementary|supporting|"
    r"all rights reserved)",
    re.IGNORECASE,
)

# Lines that look like author names
_AUTHOR_SEPARATORS = re.compile(r"[,;]|\band\b|\s{2,}")
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_AFFILIATION_MARKERS = re.compile(
    r"(?:university|institute|college|laboratory|department|"
    r"school|academy|center|centre|faculty|"
    r"china|usa|uk|japan|germany|france|canada|"
    r"©|copyright|http|www\.|received|accepted)",
    re.IGNORECASE,
)

# Year extraction patterns
_YEAR_RE = re.compile(r"\b(19\d{2}|20[0-2]\d)\b")
_COPYRIGHT_YEAR_RE = re.compile(r"(?:©|copyright)\s*(?:©\s*)?(19\d{2}|20[0-2]\d)", re.IGNORECASE)

# Abstract section markers
_ABSTRACT_START = re.compile(r"^#+\s*abstract\s*$", re.IGNORECASE | re.MULTILINE)
_SECTION_HEADING = re.compile(r"^#+\s+", re.MULTILINE)

# MinerU artifact: garbled DOI markers that still contain the number
_GARBLED_DOI_RE = re.compile(r"10[.?\s]+\d{4,}[.?\s]+[^\s]{3,}")


@dataclass
class ExtractedMetadata:
    """Candidates extracted from a MinerU markdown file."""
    paper_id: str = ""
    doi_candidates: list[str] = field(default_factory=list)
    title_candidates: list[str] = field(default_factory=list)
    author_candidates: list[list[str]] = field(default_factory=list)
    year_candidates: list[int] = field(default_factory=list)
    venue_candidates: list[str] = field(default_factory=list)
    abstract_candidate: str = ""
    first_3000_chars: str = ""
    matched_lines: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "paper_id": self.paper_id,
            "doi_candidates": self.doi_candidates,
            "title_candidates": self.title_candidates,
            "author_candidates": self.author_candidates,
            "year_candidates": self.year_candidates,
            "venue_candidates": self.venue_candidates,
            "abstract_candidate": self.abstract_candidate,
            "first_3000_chars": self.first_3000_chars[:3000],
            "matched_lines": self.matched_lines[:50],
            "warnings": self.warnings,
        }


def _extract_dois(text: str) -> list[str]:
    """Extract all DOI candidates from text."""
    dois = []
    seen = set()
    for m in _DOI_RE.finditer(text):
        raw = _DOI_TRAILING_RE.sub("", m.group(1))
        if "/" in raw and 6 < len(raw) < 120 and raw not in seen:
            dois.append(raw)
            seen.add(raw)
    # Also try garbled MinerU DOIs (with ? or . separators)
    for m in _GARBLED_DOI_RE.finditer(text[:5000]):
        raw = m.group(0)
        # Try to clean up: replace ? and extra spaces
        cleaned = re.sub(r"[?\s]+", "", raw)
        if "/" in cleaned and 6 < len(cleaned) < 120 and cleaned not in seen:
            # For garbled DOIs, try to reconstruct with proper separators
            # Pattern: 10.XXXX/j.XXXX-XXXX.XXXXXX
            reconstructed = re.sub(r"(\d)j(\d)", r"\1/j\2", cleaned)
            if reconstructed != cleaned and reconstructed not in seen:
                dois.append(reconstructed)
                seen.add(reconstructed)
    return dois


def _extract_title_candidates(lines: list[str]) -> list[str]:
    """Extract title candidates from markdown lines."""
    candidates = []
    # 1. Look for markdown heading (# Title)
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("# ") and not stripped.startswith("## "):
            title = stripped[2:].strip()
            if len(title) > 10 and not _NON_TITLE_PATTERNS.match(title):
                candidates.append(title)
                break

    # 2. If no heading found, look at first substantial non-empty lines
    if not candidates:
        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if len(stripped) > 15 and not _NON_TITLE_PATTERNS.match(stripped):
                if not _EMAIL_RE.search(stripped) and not _AFFILIATION_MARKERS.search(stripped):
                    candidates.append(stripped)
                    break

    return candidates


def _extract_author_candidates(lines: list[str]) -> list[list[str]]:
    """Extract author name candidates from lines after the title."""
    candidates: list[list[str]] = []
    in_title_area = True
    found_title = False

    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            if found_title:
                in_title_area = False
            continue

        # Detect title
        if stripped.startswith("# ") and not found_title:
            found_title = True
            continue

        if not found_title:
            continue

        # After title, look for author-like lines (within first 10 lines after title)
        if i > 0 and not in_title_area:
            continue

        # Skip obvious non-author lines
        if _NON_TITLE_PATTERNS.match(stripped):
            continue
        if _EMAIL_RE.search(stripped):
            continue
        if stripped.startswith("!["):  # image
            continue
        if re.match(r"^https?://", stripped):
            continue
        if re.match(r"^[\d.,\s]+$", stripped):  # just numbers
            continue

        # Check if this looks like an author line
        # Has commas, "and", or multiple capitalized words
        words = stripped.split()
        if len(words) < 2 or len(words) > 30:
            continue

        # If line has lots of affiliation markers, skip
        if len(_AFFILIATION_MARKERS.findall(stripped)) >= 2:
            continue

        # Try to split into individual authors
        # Common patterns: "A. B. Author", "Author, A.B.", "Author et al."
        # Split by comma, "and", or multiple spaces
        author_names = _split_author_line(stripped)
        if author_names and len(author_names) >= 1:
            candidates.append(author_names)
            break  # Take the first plausible author line

    return candidates


def _split_author_line(line: str) -> list[str]:
    """Split an author line into individual author names."""
    # Remove leading numbers/superscript markers
    line = re.sub(r"[\d,\s]*$", "", line)
    line = re.sub(r"^[\d,\s*]+", "", line)

    # Split by common separators
    parts = re.split(r",\s*(?=[A-Z])|\s{2,}|\band\b", line)
    names = []
    for part in parts:
        part = part.strip().rstrip(",*0123456789")
        # Remove affiliation superscripts
        part = re.sub(r"[\d,*]+$", "", part)
        part = part.strip()
        if len(part) > 2 and not _AFFILIATION_MARKERS.search(part):
            # Check if it looks like a person name (has capital letters, not all caps keywords)
            if re.search(r"[A-Z][a-z]", part) or re.search(r"[A-Z]{2,}", part):
                names.append(part)
    return names


def _extract_year_candidates(text: str, lines: list[str]) -> list[int]:
    """Extract publication year candidates."""
    candidates: list[int] = []
    seen = set()

    # 1. Copyright line
    for line in lines[:30]:
        m = _COPYRIGHT_YEAR_RE.search(line)
        if m:
            year = int(m.group(1))
            if 1900 <= year <= 2026 and year not in seen:
                candidates.append(year)
                seen.add(year)

    # 2. "Received ... 2005" pattern
    for line in lines[:30]:
        m = re.search(r"(?:received|accepted|published).*?((?:19|20)\d{2})", line, re.IGNORECASE)
        if m:
            year = int(m.group(1))
            if 1900 <= year <= 2026 and year not in seen:
                candidates.append(year)
                seen.add(year)

    return candidates


def _extract_abstract(text: str) -> str:
    """Extract abstract text (between Abstract and Introduction headings)."""
    # Find "Abstract" heading
    abs_match = _ABSTRACT_START.search(text)
    if not abs_match:
        # Try "ABSTRACT" without markdown heading
        abs_match = re.search(r"(?i)^abstract\s*$", text, re.MULTILINE)
        if not abs_match:
            return ""

    start = abs_match.end()

    # Find next section heading after abstract
    next_heading = _SECTION_HEADING.search(text, start)
    end = next_heading.start() if next_heading else min(start + 3000, len(text))

    abstract = text[start:end].strip()
    # Clean up
    abstract = re.sub(r"\n{3,}", "\n\n", abstract)
    if len(abstract) < 50:
        return ""
    return abstract[:2000]


def extract_metadata_from_markdown(
    markdown_path: str | Path,
    paper_id: str = "",
    max_scan_chars: int = 10000,
) -> ExtractedMetadata:
    """Extract bibliographic metadata candidates from a MinerU markdown file.

    Args:
        markdown_path: Path to the MinerU markdown file.
        paper_id: The paper_id for reference.
        max_scan_chars: Maximum characters to scan for structured extraction
                        (DOI scan always covers full text).

    Returns:
        ExtractedMetadata with all candidates found.
    """
    path = Path(markdown_path)
    result = ExtractedMetadata(paper_id=paper_id)

    if not path.exists():
        result.warnings.append(f"markdown file not found: {path}")
        return result

    try:
        text = path.read_text(encoding="utf-8")
    except Exception as e:
        result.warnings.append(f"failed to read {path}: {e}")
        return result

    lines = text.split("\n")
    scan_text = text[:max_scan_chars]
    result.first_3000_chars = text[:3000]

    # ── DOI extraction (full text) ─────────────────────────────────
    result.doi_candidates = _extract_dois(text)
    if result.doi_candidates:
        result.matched_lines.append(f"DOI candidates: {result.doi_candidates}")

    # ── Title extraction ───────────────────────────────────────────
    result.title_candidates = _extract_title_candidates(lines)
    if result.title_candidates:
        result.matched_lines.append(f"Title: {result.title_candidates[0]}")

    # ── Author extraction ──────────────────────────────────────────
    result.author_candidates = _extract_author_candidates(lines)
    if result.author_candidates:
        result.matched_lines.append(f"Authors: {result.author_candidates[0]}")

    # ── Year extraction ────────────────────────────────────────────
    result.year_candidates = _extract_year_candidates(scan_text, lines)

    # ── Abstract extraction ────────────────────────────────────────
    result.abstract_candidate = _extract_abstract(text)
    if result.abstract_candidate:
        result.matched_lines.append(f"Abstract: {len(result.abstract_candidate)} chars")

    if not any([result.doi_candidates, result.title_candidates, result.author_candidates]):
        result.warnings.append("no metadata candidates extracted from markdown")

    return result
