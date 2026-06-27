from pathlib import Path

from src.fetch import fetch_pipeline
from src.fetch.access_policy import AccessPolicy
from src.fetch.models import FetchResult


class FakeDownloadResponse:
    def __init__(self, content_type="application/pdf", content=b"%PDF-1.4\n", url="https://example.org/p.pdf"):
        self.headers = {"content-type": content_type}
        self._content = content
        self.url = url

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def raise_for_status(self):
        return None

    def iter_content(self, chunk_size=65536):
        yield self._content


def _mock_resolver(rname, result):
    class MockR:
        name = rname
        def resolve(self, ctx):
            return result
    return MockR()


def test_fetch_oa_pdf_dry_run_returns_candidate_without_writing(monkeypatch, tmp_path):
    r = FetchResult(doi="10.1000/abc", success=True, source="unpaywall",
                    pdf_url="https://example.org/p.pdf", oa_status="gold")
    monkeypatch.setattr(fetch_pipeline, "_build_resolvers",
                        lambda policy: [_mock_resolver("unpaywall", r)])
    result = fetch_pipeline.fetch_oa_pdf("10.1000/abc", domain_id="blowing_snow_physics",
                                          output_root=tmp_path, dry_run=True)
    assert result.success is True
    assert result.pdf_url.endswith(".pdf")
    assert not list(tmp_path.rglob("*"))


def test_fetch_oa_pdf_downloads_pdf_and_sidecar(monkeypatch, tmp_path):
    r = FetchResult(doi="10.1000/abc", success=True, source="openalex",
                    pdf_url="https://example.org/p.pdf", oa_status="green")
    monkeypatch.setattr(fetch_pipeline, "_build_resolvers",
                        lambda policy: [_mock_resolver("openalex", r)])
    monkeypatch.setattr(fetch_pipeline.requests, "get", lambda *args, **kwargs: FakeDownloadResponse())

    result = fetch_pipeline.fetch_oa_pdf("10.1000/abc", domain_id="abl_pbl", output_root=tmp_path)
    assert result.success is True
    assert Path(result.output_path).exists()
    assert Path(result.sidecar_path).exists()
    assert result.sha256


def test_fetch_oa_pdf_rejects_non_pdf_response(monkeypatch, tmp_path):
    r = FetchResult(doi="10.1000/abc", success=True, source="openalex",
                    pdf_url="https://example.org/page", oa_status="green")
    monkeypatch.setattr(fetch_pipeline, "_build_resolvers",
                        lambda policy: [_mock_resolver("openalex", r)])
    monkeypatch.setattr(
        fetch_pipeline.requests, "get",
        lambda *args, **kwargs: FakeDownloadResponse(content_type="text/html", url="https://example.org/page"),
    )
    result = fetch_pipeline.fetch_oa_pdf("10.1000/abc", output_root=tmp_path)
    assert result.success is False
    assert "not a PDF" in result.error
    assert not list(tmp_path.rglob("*.pdf"))


def test_fetch_oa_pdf_returns_failure_when_no_oa_candidate(monkeypatch, tmp_path):
    r = FetchResult(doi="10.1000/abc", source="unpaywall", error="not OA")
    monkeypatch.setattr(fetch_pipeline, "_build_resolvers",
                        lambda policy: [_mock_resolver("unpaywall", r)])
    result = fetch_pipeline.fetch_oa_pdf("10.1000/abc", output_root=tmp_path)
    assert result.success is False
    assert "not OA" in result.error


def test_fetch_oa_pdf_requires_doi():
    result = fetch_pipeline.fetch_oa_pdf("")
    assert result.success is False
    assert result.error == "doi is required"


# --- OA URL 选择：优先明确 PDF 字段，landing page 仅 fallback ---

class FakeJsonResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def test_unpaywall_prefers_url_for_pdf(monkeypatch):
    from src.fetch import fetch_unpaywall

    data = {
        "is_oa": True,
        "oa_status": "gold",
        "best_oa_location": {
            "url_for_pdf": "https://example.org/paper.pdf",
            "url": "https://example.org/landing",
            "license": "cc-by",
        },
        "oa_locations": [],
    }
    monkeypatch.setattr(
        fetch_unpaywall.requests,
        "get",
        lambda *args, **kwargs: FakeJsonResponse(data),
    )
    result = fetch_unpaywall.resolve_unpaywall("10.1/x")
    assert result.success is True
    assert result.pdf_url == "https://example.org/paper.pdf"
    assert result.metadata.get("maybe_landing_page") is not True


def test_unpaywall_fallback_landing_page_marked(monkeypatch):
    from src.fetch import fetch_unpaywall

    data = {
        "is_oa": True,
        "oa_status": "green",
        "best_oa_location": {
            "url": "https://example.org/landing",
            "license": "cc-by",
        },
        "oa_locations": [],
    }
    monkeypatch.setattr(
        fetch_unpaywall.requests,
        "get",
        lambda *args, **kwargs: FakeJsonResponse(data),
    )
    result = fetch_unpaywall.resolve_unpaywall("10.1/x")
    assert result.success is True
    assert result.pdf_url == "https://example.org/landing"
    assert result.metadata.get("maybe_landing_page") is True


def test_openalex_prefers_primary_pdf_url(monkeypatch):
    from src.fetch import fetch_openalex

    data = {
        "results": [
            {
                "doi": "https://doi.org/10.1/x",
                "primary_location": {"pdf_url": "https://example.org/paper.pdf"},
                "open_access": {"is_oa": True, "oa_status": "green", "oa_url": "https://example.org/landing"},
            }
        ]
    }
    monkeypatch.setattr(
        fetch_openalex.requests,
        "get",
        lambda *args, **kwargs: FakeJsonResponse(data),
    )
    result = fetch_openalex.resolve_openalex_pdf("10.1/x")
    assert result.success is True
    assert result.pdf_url == "https://example.org/paper.pdf"
    assert result.metadata.get("maybe_landing_page") is not True


def test_openalex_fallback_landing_page_marked(monkeypatch):
    from src.fetch import fetch_openalex

    data = {
        "results": [
            {
                "doi": "https://doi.org/10.1/x",
                "primary_location": {},
                "open_access": {"is_oa": True, "oa_status": "green", "oa_url": "https://example.org/landing"},
            }
        ]
    }
    monkeypatch.setattr(
        fetch_openalex.requests,
        "get",
        lambda *args, **kwargs: FakeJsonResponse(data),
    )
    result = fetch_openalex.resolve_openalex_pdf("10.1/x")
    assert result.success is True
    assert result.pdf_url == "https://example.org/landing"
    assert result.metadata.get("maybe_landing_page") is True

