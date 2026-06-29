import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.check_directory_hygiene import check_directory_hygiene


def _write_json(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def test_directory_hygiene_reports_warnings_without_deleting_files(tmp_path):
    papers_dir = tmp_path / "data" / "papers"
    paper_raw_dir = tmp_path / "data" / "paper_raw"
    write_jobs_dir = tmp_path / "write" / "jobs"
    all_catalog = tmp_path / "data" / "catalog" / "all.catalog.json"

    paper = papers_dir / "2024_author_missing_doi"
    paper.mkdir(parents=True)
    _write_json(paper / "2024_author_missing_doi.metadata.json", {"identifiers": {"doi": ""}})
    _write_json(all_catalog, {
        "papers": [
            {"paper_number": "0000000000000001", "paper_id": "2024_author_missing_doi"},
            {"paper_number": "0000000000000001", "paper_id": "missing_folder"},
        ]
    })
    _write_json(paper_raw_dir / "000001" / "000001.metadata.json", {"identifiers": {"doi": "10.1/duplicate"}})

    job = write_jobs_dir / "job"
    (job / "tex").mkdir(parents=True)
    (job / "tex" / "main.tex").write_text("% data/paper_raw/000001\n", encoding="utf-8")
    _write_json(job / "selected_catalog.json", {
        "papers": [{"source_dir": "data/paper_raw/000001", "paper_number": "0000000000000001"}]
    })

    report = check_directory_hygiene(
        project_root=tmp_path,
        all_catalog_path=all_catalog,
        papers_dir=papers_dir,
        paper_raw_dir=paper_raw_dir,
        write_jobs_dir=write_jobs_dir,
    )

    assert report["valid"] is True
    assert report["warning_count"] >= 4
    assert (job / "tex" / "main.tex").exists()
    assert any("duplicate paper_number" in warning for warning in report["warnings"])
    assert any("metadata.identifiers.doi missing" in warning for warning in report["warnings"])
    assert any("missing formal paper folder" in warning for warning in report["warnings"])
    assert any("data/paper_raw" in warning for warning in report["warnings"])
