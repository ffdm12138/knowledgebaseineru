import argparse
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.check_write_tex_project import check_tex_project
from scripts.prepare_write_article_workdir import prepare_workdir
from scripts.write_catalog_tex_article import write_article


def _metadata(idx: int) -> dict:
    return {
        "citation_key": f"paper{idx}2024",
        "entry_type": "article",
        "title": {"original": f"Workflow Paper {idx}", "translated_zh": f"流程论文{idx}"},
        "authors": [{"full_name": f"Author {idx}", "family": f"Author{idx}", "given": "A"}],
        "year": 2024,
        "container": {"journal": "Workflow Journal", "conference": "", "booktitle": "", "publisher": "Test Press"},
        "publication": {"volume": "1", "number": str(idx), "issue": str(idx), "pages": f"{idx}-{idx + 10}", "article_number": ""},
        "identifiers": {"doi": f"10.1234/workflow.{idx}"},
        "links": {"url": f"https://example.org/{idx}"},
    }


def _catalog(idx: int, *, primary_domain: str = "snow_model", topic: str = "blowing snow") -> dict:
    return {
        "schema_version": "1.1",
        "display": {
            "title_original": f"Workflow Paper {idx}",
            "title_zh": f"流程论文{idx}",
            "year": 2024,
            "first_author": f"Author{idx}",
            "authors_short": f"Author{idx} et al.",
            "venue": "Workflow Journal",
            "doi": f"10.1234/workflow.{idx}",
        },
        "classification": {
            "primary_domain": primary_domain,
            "domains": [primary_domain],
            "topics": [topic],
            "keywords_en": [topic],
            "keywords_zh": ["测试"],
        },
        "research_card": {
            "one_sentence_summary_zh": f"论文{idx}提供了一个可用于写作流程测试的证据点。",
            "method_zh": f"方法{idx}",
            "main_conclusion_zh": f"结论{idx}",
            "usefulness_for_project_zh": f"用途{idx}",
        },
        "screening": {
            "relevance_score": idx,
            "reading_priority": idx,
            "read_decision": "must_read" if idx >= 2 else "optional",
            "best_for_sections": ["introduction", "discussion"],
        },
    }


def _make_library(tmp_path: Path, count: int = 3) -> tuple[Path, Path, Path, list[dict]]:
    papers_dir = tmp_path / "data" / "papers"
    catalog_path = tmp_path / "data" / "catalog" / "all.catalog.json"
    entries = []
    for idx in range(1, count + 1):
        paper_number = f"{idx:016d}"
        paper_id = f"2024_author{idx}_workflow_paper_{idx}"
        folder = papers_dir / paper_id
        (folder / "images").mkdir(parents=True)
        metadata = _metadata(idx)
        catalog = _catalog(idx)
        (folder / f"{paper_id}.metadata.json").write_text(json.dumps(metadata, ensure_ascii=False), encoding="utf-8")
        (folder / f"{paper_id}.catalog.json").write_text(json.dumps(catalog, ensure_ascii=False), encoding="utf-8")
        (folder / f"{paper_id}.md").write_text(f"# Workflow Paper {idx}\n\nbody", encoding="utf-8")
        (folder / f"{paper_id}.pdf").write_bytes(b"%PDF-test")
        entries.append({
            "paper_number": paper_number,
            "paper_id": paper_id,
            "folder_path": str(folder),
            "catalog": catalog,
            "metadata": metadata,
        })
    catalog_path.parent.mkdir(parents=True)
    catalog_path.write_text(json.dumps({"schema_version": "1.0", "papers": entries}, ensure_ascii=False), encoding="utf-8")
    write_dir = tmp_path / "write"
    return catalog_path, papers_dir, write_dir, entries


def _prepare_args(catalog_path: Path, papers_dir: Path, write_dir: Path, **kwargs) -> argparse.Namespace:
    defaults = {
        "job_id": "job_article",
        "paper_numbers": None,
        "primary_domain": None,
        "topic": None,
        "read_decision": None,
        "min_relevance_score": None,
        "limit": None,
        "apply": True,
        "dry_run": False,
        "overwrite": False,
        "all_catalog": catalog_path,
        "papers_dir": papers_dir,
        "write_dir": write_dir,
    }
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


def test_prepare_by_paper_numbers_copies_and_writes_report(tmp_path):
    catalog_path, papers_dir, write_dir, entries = _make_library(tmp_path)
    args = _prepare_args(
        catalog_path,
        papers_dir,
        write_dir,
        paper_numbers=[e["paper_number"] for e in entries],
    )

    report = prepare_workdir(args)

    assert report["selected_count"] == 3
    job_dir = write_dir / "job_article"
    assert (job_dir / "selected_catalog.json").exists()
    assert (job_dir / "reports" / "prepare_article_report.json").exists()
    for entry in entries:
        copied = job_dir / "article" / entry["paper_number"] / f"{entry['paper_id']}.metadata.json"
        assert copied.exists()


def test_prepare_by_catalog_filter(tmp_path):
    catalog_path, papers_dir, write_dir, _ = _make_library(tmp_path)
    args = _prepare_args(
        catalog_path,
        papers_dir,
        write_dir,
        job_id="filter_job",
        primary_domain="snow_model",
        topic="blowing",
        read_decision="must_read",
        min_relevance_score=2,
        limit=2,
    )

    report = prepare_workdir(args)

    assert report["selected_count"] == 2
    numbers = [p["paper_number"] for p in report["papers"]]
    assert numbers == ["0000000000000003", "0000000000000002"]


def test_prepare_missing_paper_number_does_not_create_job(tmp_path):
    catalog_path, papers_dir, write_dir, _ = _make_library(tmp_path)
    args = _prepare_args(catalog_path, papers_dir, write_dir, paper_numbers=["9999999999999999"])

    with pytest.raises(KeyError):
        prepare_workdir(args)

    assert not (write_dir / "job_article").exists()


def test_tex_article_generation_and_check_success(tmp_path):
    catalog_path, papers_dir, write_dir, entries = _make_library(tmp_path)
    prepare_workdir(_prepare_args(catalog_path, papers_dir, write_dir, paper_numbers=[e["paper_number"] for e in entries]))

    write_report = write_article(argparse.Namespace(
        job_id="job_article",
        title="Workflow Mini Article",
        language="zh",
        apply=True,
        dry_run=False,
        overwrite=False,
        write_dir=write_dir,
    ))
    check_report = check_tex_project(argparse.Namespace(job_id="job_article", compile=False, write_dir=write_dir))

    assert write_report["paper_count"] == 3
    assert (write_dir / "job_article" / "tex" / "main.tex").exists()
    assert (write_dir / "job_article" / "tex" / "references.bib").exists()
    assert check_report["valid"] is True
    assert check_report["bib_count"] == 3


def test_check_catches_missing_bib_key_data_papers_path_and_missing_doi(tmp_path):
    catalog_path, papers_dir, write_dir, entries = _make_library(tmp_path)
    prepare_workdir(_prepare_args(catalog_path, papers_dir, write_dir, paper_numbers=[e["paper_number"] for e in entries]))
    write_article(argparse.Namespace(
        job_id="job_article",
        title="Workflow Mini Article",
        language="zh",
        apply=True,
        dry_run=False,
        overwrite=False,
        write_dir=write_dir,
    ))

    tex_dir = write_dir / "job_article" / "tex"
    main_path = tex_dir / "main.tex"
    main_path.write_text(main_path.read_text(encoding="utf-8") + "\n\\cite{missingkey}\n% data/papers/bad\n", encoding="utf-8")
    bib_path = tex_dir / "references.bib"
    bib_path.write_text(
        bib_path.read_text(encoding="utf-8").replace("  doi = {10.1234/workflow.1},\n", ""),
        encoding="utf-8",
    )

    report = check_tex_project(argparse.Namespace(job_id="job_article", compile=False, write_dir=write_dir))

    assert report["valid"] is False
    assert any("missingkey" in error for error in report["errors"])
    assert any("data/papers" in error for error in report["errors"])
    assert any("missing nonempty doi" in error for error in report["errors"])
