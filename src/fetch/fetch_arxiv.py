"""Conservative arXiv PDF URL resolver from known metadata."""
import re

from src.fetch.models import FetchResult


ARXIV_ID_RE = re.compile(r"^\d{4}\.\d{4,5}(v\d+)?$|^[a-z\-]+(\.[A-Z]{2})?/\d{7}(v\d+)?$", re.I)


def resolve_arxiv_pdf(doi: str, metadata: dict | None = None) -> FetchResult:
    metadata = metadata or {}
    external = metadata.get("externalIds") or metadata.get("external_ids") or {}
    arxiv_id = external.get("ArXiv") or external.get("arXiv") or metadata.get("arxiv_id") or ""
    if not arxiv_id or not ARXIV_ID_RE.match(arxiv_id):
        return FetchResult(doi=doi, source="arxiv", metadata=metadata, error="no arXiv id")
    return FetchResult(
        doi=doi,
        success=True,
        source="arxiv",
        pdf_url=f"https://arxiv.org/pdf/{arxiv_id}.pdf",
        oa_status="green",
        metadata=metadata,
    )

