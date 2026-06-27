"""duplicate_detector 本地查重测试（不联网）。"""
import json
from pathlib import Path

from src.duplicate_detector import (
    detect_all,
    detect_duplicate_by_doi,
    detect_duplicate_by_sha256,
    detect_possible_duplicate_by_title,
)
from src.library_index import LibraryIndex
from src.manifest import PaperManifest


def _write_index(tmp_path: Path, papers: list[dict]) -> LibraryIndex:
    idx_path = tmp_path / "library_index.json"
    data = {"version": "0.1", "description": "", "domains": {}, "papers": papers}
    idx_path.write_text(json.dumps(data), encoding="utf-8")
    return LibraryIndex(idx_path)


def _write_manifest(tmp_path: Path, papers: list[dict]) -> PaperManifest:
    mpath = tmp_path / "papers_manifest.json"
    mpath.parent.mkdir(parents=True, exist_ok=True)
    mpath.write_text(json.dumps({"version": "0.1", "papers": papers}), encoding="utf-8")
    return PaperManifest(mpath)


def test_doi_duplicate(tmp_path):
    idx = _write_index(tmp_path, [{"paper_id": "p1", "doi": "10.1/abc", "title": "T", "year": 2020}])
    res = detect_duplicate_by_doi("https://doi.org/10.1/ABC", index=idx)
    assert res.matched is True
    assert res.confidence == 1.0
    assert res.canonical_paper_id == "p1"
    assert "doi" in res.matched_fields


def test_sha256_duplicate(tmp_path):
    mfst = _write_manifest(tmp_path, [{"paper_id": "p1", "sha256": "abc123", "status": "converted"}])
    res = detect_duplicate_by_sha256("ABC123", manifest=mfst)
    assert res.matched is True
    assert res.confidence == 1.0
    assert res.canonical_paper_id == "p1"


def test_sha256_failed_status_not_canonical(tmp_path):
    mfst = _write_manifest(tmp_path, [{"paper_id": "p1", "sha256": "abc123", "status": "failed"}])
    res = detect_duplicate_by_sha256("abc123", manifest=mfst)
    assert res.matched is False


def test_title_year_possible_duplicate(tmp_path):
    idx = _write_index(tmp_path, [{"paper_id": "p1", "doi": "", "title": "Blowing Snow Sublimation", "year": 2020}])
    # exact title + year
    res = detect_possible_duplicate_by_title("Blowing Snow Sublimation", 2020, index=idx)
    assert res and res[0].matched is True
    assert res[0].confidence >= 0.85
    # similar title, close year
    res2 = detect_possible_duplicate_by_title("Blowing Snow Sublimation Study", 2021, index=idx)
    assert res2 and res2[0].confidence >= 0.6


def test_no_duplicate(tmp_path):
    idx = _write_index(tmp_path, [{"paper_id": "p1", "doi": "10.1/x", "title": "Alpha", "year": 2020}])
    mfst = _write_manifest(tmp_path, [{"paper_id": "p1", "sha256": "h1", "status": "converted"}])
    out = detect_all(doi="10.2/y", sha256="h2", title="Completely Different Topic", year=2099,
                    index=idx, manifest=mfst)
    assert out["is_duplicate"] is False
    assert out["canonical_paper_id"] is None


def test_detect_all_doi_takes_priority(tmp_path):
    idx = _write_index(tmp_path, [{"paper_id": "p1", "doi": "10.1/x", "title": "T", "year": 2020}])
    mfst = _write_manifest(tmp_path, [])
    out = detect_all(doi="10.1/x", sha256="zzz", title="T", year=2020, index=idx, manifest=mfst)
    assert out["is_duplicate"] is True
    assert out["canonical_paper_id"] == "p1"
