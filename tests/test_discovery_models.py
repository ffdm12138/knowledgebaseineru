from src.discovery.models import CandidateBatch, PaperCandidate
from src.discovery import search_openalex, search_semantic_scholar
from src.discovery.search_openalex import parse_openalex_work
from src.discovery.search_semantic_scholar import parse_semantic_scholar_paper


def test_candidate_batch_round_trip():
    batch = CandidateBatch(
        original_query="snow",
        expanded_queries=["snow", "blowing snow"],
        sources=["openalex"],
        candidates=[PaperCandidate(title="T", doi="https://doi.org/10.1/A", source="openalex")],
    )
    restored = CandidateBatch.from_dict(batch.to_dict())
    assert restored.candidates[0].doi == "10.1/a"
    assert restored.expanded_queries == ["snow", "blowing snow"]


def test_parse_openalex_work_extracts_oa_pdf():
    work = {
        "id": "https://openalex.org/W1",
        "display_name": "Snow Paper",
        "publication_year": 2020,
        "doi": "https://doi.org/10.2/snow",
        "cited_by_count": 4,
        "authorships": [{"author": {"display_name": "A Author"}}],
        "primary_location": {
            "pdf_url": "https://example.org/snow.pdf",
            "source": {"display_name": "Journal"},
        },
        "open_access": {"is_oa": True, "oa_url": "https://example.org/landing"},
    }
    candidate = parse_openalex_work(work, query="snow", domain_id="blowing_snow_physics")
    assert candidate.doi == "10.2/snow"
    assert candidate.pdf_url.endswith(".pdf")
    assert candidate.open_access is True


def test_parse_semantic_scholar_paper_extracts_doi_and_pdf():
    paper = {
        "paperId": "abc",
        "title": "Snow Paper",
        "year": 2021,
        "authors": [{"name": "A Author"}],
        "externalIds": {"DOI": "10.3/snow"},
        "openAccessPdf": {"url": "https://example.org/snow.pdf"},
        "isOpenAccess": True,
        "citationCount": 7,
    }
    candidate = parse_semantic_scholar_paper(paper)
    assert candidate.source == "semantic_scholar"
    assert candidate.doi == "10.3/snow"
    assert candidate.open_access is True


def test_search_modules_return_empty_on_network_error(monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("network down")

    monkeypatch.setattr(search_openalex.requests, "get", boom)
    monkeypatch.setattr(search_semantic_scholar.requests, "get", boom)

    assert search_openalex.search_openalex("snow") == []
    assert search_semantic_scholar.search_semantic_scholar("snow") == []
