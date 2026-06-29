import json
import runpy
import sys
from pathlib import Path

from scripts.validate_v2_library import validate_v2_library
from src.services.v2_library import empty_catalog, empty_metadata


_REPO_ROOT = Path(__file__).resolve().parent.parent


def _run_script(script: str, argv: list[str]) -> int:
    saved = sys.argv
    sys.argv = argv
    try:
        runpy.run_path(str(_REPO_ROOT / "scripts" / script), run_name="__main__")
        return 0
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 1
    finally:
        sys.argv = saved


def test_network_metadata_requires_doi(tmp_path, monkeypatch):
    input_path = tmp_path / "candidates.jsonl"
    input_path.write_text(json.dumps({"title": "No DOI Paper", "year": 2024}) + "\n", encoding="utf-8")
    paper_raw = tmp_path / "paper_raw"
    report = tmp_path / "report.json"
    monkeypatch.syspath_prepend(str(_REPO_ROOT))

    rc = _run_script(
        "stage_network_metadata_to_paper_raw.py",
        [
            "stage_network_metadata_to_paper_raw.py",
            "--input", str(input_path),
            "--paper-raw-dir", str(paper_raw),
            "--report", str(report),
            "--apply",
        ],
    )

    assert rc == 1
    assert not paper_raw.exists() or not any(paper_raw.iterdir())
    data = json.loads(report.read_text(encoding="utf-8"))
    assert data[0]["error"] == "network/search metadata import requires metadata.identifiers.doi"


def test_network_metadata_maps_publication_fields(tmp_path, monkeypatch):
    input_path = tmp_path / "candidates.jsonl"
    input_path.write_text(json.dumps({
        "title": "Network Paper",
        "year": 2024,
        "doi": "https://doi.org/10.1000/example",
        "venue": "Test Journal",
        "volume": "12",
        "issue": "3",
        "page": "45-56",
    }) + "\n", encoding="utf-8")
    paper_raw = tmp_path / "paper_raw"
    monkeypatch.syspath_prepend(str(_REPO_ROOT))

    rc = _run_script(
        "stage_network_metadata_to_paper_raw.py",
        [
            "stage_network_metadata_to_paper_raw.py",
            "--input", str(input_path),
            "--paper-raw-dir", str(paper_raw),
            "--apply",
        ],
    )

    assert rc == 0
    metadata = json.loads((paper_raw / "000001" / "000001.metadata.json").read_text(encoding="utf-8"))
    assert metadata["identifiers"]["doi"] == "10.1000/example"
    assert metadata["publication"]["volume"] == "12"
    assert metadata["publication"]["number"] == "3"
    assert metadata["publication"]["issue"] == "3"
    assert metadata["publication"]["pages"] == "45-56"


def test_validate_formal_library_requires_doi(tmp_path):
    pid = "2024_wang_测试论文"
    folder = tmp_path / "papers" / pid
    folder.mkdir(parents=True)
    metadata = empty_metadata(pid)
    metadata["title"]["original"] = "Test Paper"
    metadata["year"] = 2024
    metadata["authors"] = [{"full_name": "Wang A", "family": "Wang", "given": "A", "orcid": "", "affiliation": ""}]
    metadata["container"]["journal"] = "Test Journal"
    metadata["metadata_match"]["status"] = "matched"
    metadata["pdf"]["sha256"] = "abc"
    metadata["pdf"]["file_size"] = 4
    catalog = empty_catalog()
    catalog["display"].update({"title_original": "Test Paper", "short_name_zh": "测试论文", "year": 2024, "first_author": "Wang"})
    (folder / f"{pid}.metadata.json").write_text(json.dumps(metadata, ensure_ascii=False), encoding="utf-8")
    (folder / f"{pid}.catalog.json").write_text(json.dumps(catalog, ensure_ascii=False), encoding="utf-8")
    (folder / f"{pid}.md").write_text("# Test", encoding="utf-8")
    (folder / f"{pid}.pdf").write_bytes(b"%PDF")
    (folder / "images").mkdir()
    all_catalog = tmp_path / "catalog" / "all.catalog.json"
    all_catalog.parent.mkdir()
    all_catalog.write_text(json.dumps({"schema_version": "1.0", "papers": []}), encoding="utf-8")

    errors, _ = validate_v2_library(papers_dir=tmp_path / "papers", all_catalog_path=all_catalog, check_paths=False)

    assert any(f"{pid} metadata.identifiers.doi is required in formal library" in err for err in errors)
