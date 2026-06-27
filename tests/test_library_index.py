import json
import tempfile
from pathlib import Path

from src.library_index import (
    DOMAIN_REGISTRY,
    LibraryIndex,
    resolve_repo_path,
    validate_domains,
)


def test_validate_domains_accepts_valid_domains():
    assert validate_domains(
        "blowing_snow_physics",
        ["blowing_snow_physics", "aeolian_snow_transport"],
    ) == []


def test_validate_domains_reports_invalid_shapes():
    errors = validate_domains("", [])
    assert "primary_domain is empty" in errors
    assert "domains must be a non-empty list" in errors
    assert validate_domains("bad", ["bad"])
    assert validate_domains("abl_pbl", ["blowing_snow_physics"])


def test_resolve_repo_path_absolute_and_relative():
    absolute = Path.cwd().resolve()
    assert resolve_repo_path(absolute) == absolute
    resolved = resolve_repo_path("data/catalog/literature_catalog.json")
    assert resolved.is_absolute()
    assert resolved.name == "literature_catalog.json"


def test_library_index_get_upsert_delete_validate():
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "library_index.json"
        index = LibraryIndex(path)
        entry = {
            "paper_id": "p1",
            "title": "T",
            "year": 2020,
            "doi": "",
            "primary_domain": "abl_pbl",
            "domains": ["abl_pbl"],
            "raw_pdf": "data/raw/a.pdf",
            "markdown_path": "data/papers/p1/paper.md",
            "images_dir": "data/papers/p1/images",
            "status": "summarized",
            "bib_key": "a2020_t",
        }
        index.upsert(entry)
        assert index.get("p1")["bib_key"] == "a2020_t"
        assert index.validate() == []
        entry["title"] = "T2"
        index.upsert(entry)
        assert len(index.list_all()) == 1
        assert index.get("p1")["title"] == "T2"
        assert index.delete("p1") is True
        assert index.delete("p1") is False


def test_build_from_catalog_and_manifest_prefers_catalog_paths():
    catalog = {
        "papers": [{
            "paper_id": "p1",
            "title": "T",
            "year": 2020,
            "doi": "",
            "primary_domain": "abl_pbl",
            "domains": ["abl_pbl"],
            "raw_pdf": "data/raw/catalog.pdf",
            "markdown": "data/papers/p1/paper.md",
            "images_dir": "data/papers/p1/images",
            "status": "summarized",
            "citation": {"bib_key": "a2020_t"},
        }],
    }
    manifest = {
        "papers": [{
            "paper_id": "p1",
            "raw_pdf": r"E:\absolute\raw.pdf",
            "markdown": r"E:\absolute\paper.md",
            "images_dir": r"E:\absolute\images",
        }]
    }
    built = LibraryIndex.build_from_catalog_and_manifest(catalog, manifest)
    assert built["domains"] == DOMAIN_REGISTRY
    assert built["papers"][0]["markdown_path"] == "data/papers/p1/paper.md"
    assert built["papers"][0]["raw_pdf"] == "data/raw/catalog.pdf"
    json.dumps(built, ensure_ascii=False)
