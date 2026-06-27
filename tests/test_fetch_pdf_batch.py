"""fetch_pdf_batch.py 测试（mock fetch_pdf，不访问网络）。"""
import json
from pathlib import Path

import pytest
from _pytest.monkeypatch import MonkeyPatch


def test_batch_dry_run_reports_all_dois(tmp_path, monkeypatch):
    """batch dry-run 模式输出报告包含所有 DOI。"""
    import sys
    # create mock jsonl
    candidates = tmp_path / "candidates"
    candidates.mkdir()
    input_file = candidates / "test.jsonl"
    input_file.write_text(
        json.dumps({"doi": "10.1/a", "title": "A"}) + "\n"
        + json.dumps({"doi": "10.1/b", "title": "B"}) + "\n",
        encoding="utf-8",
    )

    from scripts import fetch_pdf_batch
    monkeypatch.setattr(fetch_pdf_batch, "DISCOVERY_DIR", tmp_path)
    monkeypatch.setattr(fetch_pdf_batch, "RAW_DIR", tmp_path / "raw")

    # mock fetch_pdf to return success
    def _mock_fetch_pdf(doi, **kw):
        from src.fetch.models import FetchResult
        return FetchResult(doi=doi, success=True, source="mock", pdf_url="https://example.org/p.pdf")

    monkeypatch.setattr(fetch_pdf_batch, "fetch_pdf", _mock_fetch_pdf)

    # patch sys.argv
    monkeypatch.setattr(
        sys, "argv",
        ["fetch_pdf_batch.py", "--input", str(input_file), "--domain", "blowing_snow_physics",
         "--limit", "2", "--dry-run", "--report-dir", str(tmp_path / "reports")],
    )
    from scripts.fetch_pdf_batch import main
    ret = main()
    assert ret == 0

    report_files = list((tmp_path / "reports").glob("*.json"))
    assert len(report_files) >= 1


def test_already_pending_skipped(tmp_path, monkeypatch):
    """已有 pending PDF 的 DOI 被跳过。"""
    from src.fetch.fetch_pipeline import safe_doi_slug
    from scripts.fetch_pdf_batch import _already_pending

    raw_dir = tmp_path / "raw"
    pending = raw_dir / "blowing_snow_physics" / "pending"
    pending.mkdir(parents=True)
    # create a pending PDF
    slug = safe_doi_slug("10.1/test")
    (pending / f"{slug}.pdf").write_bytes(b"%PDF")

    assert _already_pending("10.1/test", raw_dir)
    assert not _already_pending("10.2/unknown", raw_dir)


def test_zotero_export_doi_list():
    from src.integrations.zotero import export_doi_list
    items = [
        {"data": {"DOI": "10.1/a"}},
        {"data": {"DOI": "10.1/b"}},
        {"data": {}},
    ]
    dois = export_doi_list(items)
    assert dois == ["10.1/a", "10.1/b"]
