"""Semantic Scholar Graph API search."""
import os

import requests
from loguru import logger

from src.discovery.models import PaperCandidate, normalize_doi


S2_SEARCH_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
S2_FIELDS = "title,year,authors,externalIds,venue,url,abstract,citationCount,openAccessPdf,isOpenAccess"


def _headers() -> dict[str, str]:
    api_key = os.environ.get("SEMANTIC_SCHOLAR_API_KEY", "").strip()
    return {"x-api-key": api_key} if api_key else {}


def parse_semantic_scholar_paper(paper: dict, query: str = "", domain_id: str | None = None) -> PaperCandidate:
    external = paper.get("externalIds") or {}
    pdf = paper.get("openAccessPdf") or {}
    authors = [a.get("name", "") for a in paper.get("authors") or [] if a.get("name")]
    return PaperCandidate(
        title=paper.get("title") or "",
        year=paper.get("year"),
        authors=authors,
        doi=normalize_doi(external.get("DOI")),
        venue=paper.get("venue") or "",
        abstract=paper.get("abstract") or "",
        source="semantic_scholar",
        source_id=paper.get("paperId") or "",
        url=paper.get("url") or "",
        pdf_url=pdf.get("url") or "",
        open_access=bool(paper.get("isOpenAccess") or pdf.get("url")),
        citation_count=paper.get("citationCount"),
        query=query,
        domain_id=domain_id,
        raw=paper,
    )


def search_semantic_scholar(query: str, domain_id: str | None = None, limit: int = 25) -> list[PaperCandidate]:
    try:
        response = requests.get(
            S2_SEARCH_URL,
            params={"query": query, "limit": limit, "fields": S2_FIELDS},
            headers=_headers(),
            timeout=20,
        )
        response.raise_for_status()
        data = response.json()
    except Exception as exc:
        logger.warning(f"Semantic Scholar search failed for {query!r}: {exc}")
        return []
    return [
        parse_semantic_scholar_paper(paper, query=query, domain_id=domain_id)
        for paper in data.get("data", [])
    ]

