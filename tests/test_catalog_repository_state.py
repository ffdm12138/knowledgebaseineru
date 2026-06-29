from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.prepare_write_article_workdir import prepare_workdir
from scripts.validate_v2_library import validate_v2_library
from src.services.v2_library import (
    AllCatalogBuilder,
    PaperNumberLedger,
    empty_catalog,
    empty_metadata,
)


_REPO_ROOT = Path(__file__).resolve().parent.parent


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _metadata(pid: str, idx: int = 1) -> dict:
    metadata = empty_metadata(pid)
    metadata["title"]["original"] = f"Repository State Paper {idx}"
    metadata["year"] = 2024
    metadata["authors"] = [
        {"full_name": f"Author {idx}", "family": f"Author{idx}", "given": "A", "orcid": "", "affiliation": ""}
    ]
    metadata["first_author"]["family"] = f"Author{idx}"
    metadata["first_author"]["display"] = f"Author {idx}"
    metadata["container"]["journal"] = "Repository State Journal"
    metadata["publication"]["volume"] = "1"
    metadata["publication"]["number"] = "1"
    metadata["publication"]["issue"] = "1"
    metadata["publication"]["pages"] = "1-10"
    metadata["identifiers"]["doi"] = f"10.5555/repository-state.{idx}"
    metadata["pdf"]["sha256"] = "abc123"
    metadata["pdf"]["file_size"] = 4
    metadata["metadata_match"] = {
        "status": "matched",
        "source": "test",
        "confidence": 1.0,
        "matched_at": "2026-01-01",
        "warnings": [],
        "candidates": [],
    }
    return metadata


def _catalog(pid: str, number: str = "0000000000000001") -> dict:
    catalog = empty_catalog()
    catalog["paper_number"] = number
    catalog["paper_id"] = pid
    catalog["content_identity"]["content_title"] = "Repository State Paper"
    catalog["classification"]["primary_domain"] = "repo_state"
    catalog["screening"]["read_decision"] = "must_read"
    catalog["screening"]["relevance_score"] = 5
    return catalog


def _formal_paper(tmp_path: Path, idx: int = 1) -> tuple[Path, str, str]:
    number = f"{idx:016d}"
    pid = f"2024_author{idx}_repository_state_{idx}"
    folder = tmp_path / "data" / "papers" / pid
    (folder / "images").mkdir(parents=True)
    _write_json(folder / f"{pid}.metadata.json", _metadata(pid, idx))
    _write_json(folder / f"{pid}.catalog.json", _catalog(pid, number))
    (folder / f"{pid}.md").write_text("# Repository State Paper\n", encoding="utf-8")
    (folder / f"{pid}.pdf").write_bytes(b"%PDF")
    return folder, pid, number


def _content_only_all_catalog(pid: str, number: str) -> dict:
    catalog = _catalog(pid, number)
    return {
        "paper_number": number,
        "paper_id": pid,
        "source_id": "",
        "asset_refs": {
            "markdown": "",
            "pdf": "",
            "images_dir": "",
            "figures": [],
        },
        "content_identity": catalog["content_identity"],
        "classification": catalog["classification"],
        "screening": catalog["screening"],
        "research_card": catalog["research_card"],
        "evidence_profile": catalog["evidence_profile"],
        "content_notes": catalog["content_notes"],
        "provenance": catalog["provenance"],
    }


def test_committed_all_catalog_template_is_content_only():
    template_path = _REPO_ROOT / "data" / "catalog" / "all.catalog.template.json"
    data = json.loads(template_path.read_text(encoding="utf-8"))

    assert data == {"schema_version": "2.0", "updated_at": "", "papers": []}


def test_validate_rejects_old_all_catalog_wrapper(tmp_path):
    papers_dir = tmp_path / "data" / "papers"
    papers_dir.mkdir(parents=True)
    all_catalog = tmp_path / "data" / "catalog" / "all.catalog.json"
    entry = _content_only_all_catalog("paper_a", "0000000000000001")
    entry["catalog"] = {"classification": {}}
    entry["metadata"] = {"identifiers": {"doi": "10.1/legacy"}}
    _write_json(all_catalog, {"schema_version": "2.0", "updated_at": "", "papers": [entry]})

    errors, _ = validate_v2_library(papers_dir=papers_dir, all_catalog_path=all_catalog, check_paths=False)

    assert any("legacy wrapper/path key: catalog" in error for error in errors)
    assert any("must not embed metadata" in error for error in errors)


def test_pack_repo_has_no_stale_head_catalog_logic():
    text = (_REPO_ROOT / "scripts" / "pack_repo.py").read_text(encoding="utf-8")

    assert "_GIT_CATALOG_FILES" not in text
    assert "git show" not in text
    assert "HEAD:" not in text


def test_clean_checkout_empty_library_validate_passes(tmp_path):
    papers_dir = tmp_path / "data" / "papers"
    papers_dir.mkdir(parents=True)
    all_catalog = tmp_path / "data" / "catalog" / "all.catalog.json"

    errors, warnings = validate_v2_library(papers_dir=papers_dir, all_catalog_path=all_catalog, check_paths=False)

    assert errors == []
    assert warnings == []


def test_all_catalog_schema_version_must_be_v2(tmp_path):
    papers_dir = tmp_path / "data" / "papers"
    papers_dir.mkdir(parents=True)
    all_catalog = tmp_path / "data" / "catalog" / "all.catalog.json"
    _write_json(all_catalog, {"schema_version": "1.0", "papers": []})

    errors, _ = validate_v2_library(papers_dir=papers_dir, all_catalog_path=all_catalog, check_paths=False)

    assert "all.catalog.schema_version must be 2.0" in errors


@pytest.mark.parametrize("legacy_key", ["folder_path", "main_md", "metadata_file", "catalog_file", "display"])
def test_validate_rejects_legacy_path_fields(tmp_path, legacy_key):
    papers_dir = tmp_path / "data" / "papers"
    papers_dir.mkdir(parents=True)
    all_catalog = tmp_path / "data" / "catalog" / "all.catalog.json"
    entry = _content_only_all_catalog("paper_a", "0000000000000001")
    entry[legacy_key] = "legacy"
    _write_json(all_catalog, {"schema_version": "2.0", "updated_at": "", "papers": [entry]})

    errors, _ = validate_v2_library(papers_dir=papers_dir, all_catalog_path=all_catalog, check_paths=False)

    assert any(f"legacy wrapper/path key: {legacy_key}" in error for error in errors)


def test_prepare_reads_metadata_from_papers_not_all_catalog(tmp_path):
    source, pid, number = _formal_paper(tmp_path)
    all_catalog = tmp_path / "data" / "catalog" / "all.catalog.json"
    entry = _content_only_all_catalog(pid, number)
    _write_json(all_catalog, {"schema_version": "2.0", "updated_at": "", "papers": [entry]})
    write_dir = tmp_path / "write"

    report = prepare_workdir(argparse.Namespace(
        job_id="repo_state_job",
        paper_numbers=[number],
        primary_domain=None,
        topic=None,
        read_decision=None,
        min_relevance_score=None,
        limit=None,
        apply=True,
        dry_run=False,
        overwrite=False,
        all_catalog=all_catalog,
        papers_dir=source.parent,
        write_dir=write_dir,
    ))

    selected_path = write_dir / "repo_state_job" / "selected_catalog.json"
    selected = json.loads(selected_path.read_text(encoding="utf-8"))
    assert report["selected_count"] == 1
    assert "metadata" not in entry
    assert selected["papers"][0]["metadata"]["identifiers"]["doi"] == "10.5555/repository-state.1"
    assert selected["papers"][0]["catalog"]["schema_version"] == "2.0"


def test_all_catalog_builder_skips_invalid_source_catalog(tmp_path):
    source, pid, _ = _formal_paper(tmp_path)
    catalog_path = source / f"{pid}.catalog.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    catalog["schema_version"] = "1.0"
    _write_json(catalog_path, catalog)
    all_catalog = tmp_path / "data" / "catalog" / "all.catalog.json"
    builder = AllCatalogBuilder(
        tmp_path / "data" / "papers",
        all_catalog,
        PaperNumberLedger(tmp_path / "data" / "catalog" / "paper_number_ledger.json"),
    )

    data = builder.build(write=True)

    assert data["papers"] == []
    assert any("catalog.schema_version must be 2.0" in error for error in builder.last_errors)
