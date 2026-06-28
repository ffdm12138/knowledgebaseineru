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


# --- pending PDF overwrite protection ---

PDF_CONTENT_A = b"%PDF-1.4 content A"
PDF_CONTENT_B = b"%PDF-1.4 content B different"
DOI_SLUG = fetch_pipeline.safe_doi_slug("10.1000/xyz")  # e.g. "10.1000_xyz"


def _download_result(doi="10.1000/xyz", pdf_url="https://example.org/p.pdf"):
    return FetchResult(doi=doi, success=True, source="openalex",
                       pdf_url=pdf_url, oa_status="green")


def test_fetch_reuses_same_content_pending_pdf(monkeypatch, tmp_path):
    """同名同内容 pending PDF：复用已有，不重复覆盖。"""
    r = _download_result()
    monkeypatch.setattr(fetch_pipeline, "_build_resolvers",
                        lambda policy: [_mock_resolver("openalex", r)])

    # 预置同内容 pending PDF（使用 safe_doi_slug 匹配的文件名）
    pending_dir = tmp_path / "blowing_snow_physics" / "pending"
    pending_dir.mkdir(parents=True)
    existing = pending_dir / f"{DOI_SLUG}.pdf"
    existing.write_bytes(PDF_CONTENT_A)

    monkeypatch.setattr(fetch_pipeline.requests, "get",
                        lambda *args, **kwargs: FakeDownloadResponse(content=PDF_CONTENT_A))

    result = fetch_pipeline.fetch_oa_pdf("10.1000/xyz", domain_id="blowing_snow_physics",
                                          output_root=tmp_path)
    assert result.success is True
    assert Path(result.output_path).exists()
    # 应该复用已有文件（stem 不变，不带 sha8 后缀）
    assert Path(result.output_path).stem == DOI_SLUG
    # sidecar 指向最终 target
    assert result.sidecar_path
    assert result.sha256


def test_fetch_renames_different_content_pending_pdf(monkeypatch, tmp_path):
    """同名不同内容 pending PDF：自动加 sha8 后缀，不覆盖旧文件。"""
    r = _download_result()
    monkeypatch.setattr(fetch_pipeline, "_build_resolvers",
                        lambda policy: [_mock_resolver("openalex", r)])

    pending_dir = tmp_path / "blowing_snow_physics" / "pending"
    pending_dir.mkdir(parents=True)
    existing = pending_dir / f"{DOI_SLUG}.pdf"
    existing.write_bytes(PDF_CONTENT_A)

    monkeypatch.setattr(fetch_pipeline.requests, "get",
                        lambda *args, **kwargs: FakeDownloadResponse(content=PDF_CONTENT_B))

    result = fetch_pipeline.fetch_oa_pdf("10.1000/xyz", domain_id="blowing_snow_physics",
                                          output_root=tmp_path)
    assert result.success is True
    # 旧文件仍然存在且内容不变
    assert existing.read_bytes() == PDF_CONTENT_A
    # 新文件不同于旧文件
    new_path = Path(result.output_path)
    assert new_path != existing
    assert new_path.exists()
    assert new_path.read_bytes() == PDF_CONTENT_B
    # 新文件包含 sha8 后缀
    assert "_" in new_path.stem
    assert new_path.stem.startswith(f"{DOI_SLUG}_")
    # sidecar 指向新文件
    assert result.sidecar_path
    assert result.sha256


def test_fetch_tdm_raw_content_does_not_overwrite(monkeypatch, tmp_path):
    """TDM raw content 分支：同名不同内容不覆盖。"""
    content_a = b"%PDF-1.4 TDM content A"
    content_b = b"%PDF-1.4 TDM content B different"
    tdm_slug = fetch_pipeline.safe_doi_slug("10.1000/tdm")

    r = FetchResult(doi="10.1000/tdm", success=True, source="wiley_tdm",
                    raw={"content": content_a})
    monkeypatch.setattr(fetch_pipeline, "_build_resolvers",
                        lambda policy: [_mock_resolver("wiley_tdm", r)])

    pending_dir = tmp_path / "blowing_snow_physics" / "pending"
    pending_dir.mkdir(parents=True)
    existing = pending_dir / f"{tdm_slug}.pdf"
    existing.write_bytes(content_b)  # 预置不同内容的同名文件

    result = fetch_pipeline.fetch_pdf("10.1000/tdm", domain_id="blowing_snow_physics",
                                       output_root=tmp_path,
                                       access_policy=AccessPolicy())
    assert result.success is True
    # 旧文件未被覆盖
    assert existing.read_bytes() == content_b
    # 新文件存在且内容正确
    new_path = Path(result.output_path)
    assert new_path != existing
    assert new_path.read_bytes() == content_a


def test_fetch_sidecar_points_to_final_target(monkeypatch, tmp_path):
    """fetch 成功后 sidecar.pending_pdf 指向最终实际 target。"""
    r = _download_result()
    monkeypatch.setattr(fetch_pipeline, "_build_resolvers",
                        lambda policy: [_mock_resolver("openalex", r)])
    monkeypatch.setattr(fetch_pipeline.requests, "get",
                        lambda *args, **kwargs: FakeDownloadResponse(content=PDF_CONTENT_A))

    result = fetch_pipeline.fetch_oa_pdf("10.1000/xyz", domain_id="abl_pbl", output_root=tmp_path)
    assert result.success is True
    import json
    sidecar = json.loads(Path(result.sidecar_path).read_text(encoding="utf-8"))
    assert sidecar["pending_pdf"]
    assert sidecar["sha256"] == result.sha256
    assert sidecar["status"] == "pending"
    assert sidecar["source_kind"] == "open_access"
    assert sidecar["policy_mode"] == "oa_only"


def test_fetch_download_does_not_call_path_read_bytes(monkeypatch, tmp_path):
    r = _download_result()
    monkeypatch.setattr(fetch_pipeline, "_build_resolvers",
                        lambda policy: [_mock_resolver("openalex", r)])
    monkeypatch.setattr(fetch_pipeline.requests, "get",
                        lambda *args, **kwargs: FakeDownloadResponse(content=PDF_CONTENT_A))
    monkeypatch.setattr(Path, "read_bytes", lambda self: (_ for _ in ()).throw(AssertionError("read_bytes called")))

    result = fetch_pipeline.fetch_oa_pdf("10.1000/xyz", domain_id="abl_pbl", output_root=tmp_path)
    assert result.success is True
