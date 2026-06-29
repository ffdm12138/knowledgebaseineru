"""Guard against reintroducing v1 legacy concepts into the v2-only codebase.

Scans source/doc directories (excluding tests/ and __pycache__) for forbidden
v1 tokens. ``paper.md`` is allowed only inside scripts/validate_v2_library.py,
whose job is to detect and reject it.
"""
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

FORBIDDEN_TOKENS = [
    "papers_pdf",
    "register_manual_pdf",
    "import_pending_pdf",
    "library_index",
    "identity_index",
    "domain_catalog",
    "domain_library",
    "legacy-only",
    "literature_catalog",
    "ai_summary",
    "main_findings",
    "relevance_to_my_work",
]

SCAN_DIRS = ["src", "scripts", "config", "web", "skills", "docs"]


def _source_files() -> list[Path]:
    out: list[Path] = []
    for sub in SCAN_DIRS:
        base = REPO / sub
        if not base.exists():
            continue
        for p in base.rglob("*"):
            if not p.is_file():
                continue
            if "__pycache__" in p.parts:
                continue
            if p.suffix in {".pyc", ".png", ".jpg", ".jpeg", ".pdf", ".zip"}:
                continue
            out.append(p)
    return out


def test_no_forbidden_legacy_tokens():
    offenders: list[str] = []
    for path in _source_files():
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for token in FORBIDDEN_TOKENS:
            if token in text:
                offenders.append(f"{path.relative_to(REPO)}: {token}")
    assert not offenders, "forbidden v1 tokens found:\n" + "\n".join(offenders)


def test_paper_md_not_a_formal_path():
    """paper.md must not appear as a formal asset path in src/ or scripts/
    (except scripts/validate_v2_library.py, which guards against it)."""
    offenders: list[str] = []
    for path in _source_files():
        if "tests" in path.parts:
            continue
        rel = str(path.relative_to(REPO)).replace("\\", "/")
        if rel == "scripts/validate_v2_library.py":
            continue  # legitimately detects/rejects paper.md
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if "paper.md" in text:
            offenders.append(rel)
    assert not offenders, "paper.md referenced as a path in:\n" + "\n".join(offenders)


def test_writer_does_not_read_legacy_citation_field():
    """src/writer and src/bib must not read a flat 'citation' field on catalog entries."""
    offenders: list[str] = []
    for sub in ("src/writer", "src/bib.py"):
        base = REPO / sub
        paths = [base] if base.is_file() else list(base.rglob("*.py"))
        for path in paths:
            if "__pycache__" in path.parts:
                continue
            text = path.read_text(encoding="utf-8")
            if '"citation"' in text or "'citation'" in text or ".get(\"citation\"" in text:
                offenders.append(str(path.relative_to(REPO)))
    assert not offenders, "legacy citation field still read in:\n" + "\n".join(offenders)
