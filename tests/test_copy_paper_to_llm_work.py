"""Tests for scripts/copy_paper_to_llm_work.py: copy by paper_number, dry-run, overwrite, errors."""
import json
import runpy
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SCRIPT = _REPO_ROOT / "scripts" / "copy_paper_to_llm_work.py"

from src.services.v2_library import V2PaperCommitService, empty_catalog, empty_metadata


def _commit_one(tmp_path: Path) -> tuple[Path, Path, str]:
    pid = "2024_wang_测试论文"
    raw = tmp_path / "paper_raw" / pid
    raw.mkdir(parents=True)
    metadata = empty_metadata(pid)
    metadata["title"]["original"] = "Test Paper"
    metadata["title"]["translated_zh"] = "测试论文"
    metadata["year"] = 2024
    metadata["authors"] = [{"full_name": "Wang A", "family": "Wang", "given": "A", "orcid": "", "affiliation": ""}]
    metadata["identifiers"]["doi"] = "10.1/test"
    metadata["metadata_match"] = {"status": "matched", "source": "test", "confidence": 1.0,
                                  "matched_at": "2026-01-01", "warnings": [], "candidates": []}
    catalog = empty_catalog()
    catalog["display"].update({"short_name_zh": "测试论文", "year": 2024, "first_author": "Wang"})
    (raw / f"{pid}.metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    (raw / f"{pid}.catalog.json").write_text(json.dumps(catalog), encoding="utf-8")
    (raw / f"{pid}.md").write_text("# Test", encoding="utf-8")
    (raw / f"{pid}.pdf").write_bytes(b"%PDF")
    (raw / "images").mkdir()
    papers = tmp_path / "papers"
    all_catalog = tmp_path / "catalog" / "all.catalog.json"
    ledger = tmp_path / "catalog" / "paper_number_ledger.json"
    V2PaperCommitService(papers_dir=papers, all_catalog_path=all_catalog, ledger_path=ledger).commit_paper_raw(raw)
    return papers, all_catalog, "0000000000000001"


def _run_cli(argv: list[str]) -> int:
    saved = sys.argv
    sys.argv = argv
    try:
        runpy.run_path(str(_SCRIPT), run_name="__main__")
        return 0
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 1
    finally:
        sys.argv = saved


def test_cli_dry_run_writes_nothing(tmp_path, monkeypatch):
    papers, all_catalog, number = _commit_one(tmp_path)
    llm_work = tmp_path / "llm_work"
    monkeypatch.syspath_prepend(str(_REPO_ROOT))
    rc = _run_cli([
        "copy_paper_to_llm_work.py",
        "--paper-number", number,
        "--session-id", "review_001",
        "--all-catalog", str(all_catalog),
        "--llm-work-dir", str(llm_work),
        "--dry-run",
    ])
    assert rc == 0
    assert not llm_work.exists() or not any(llm_work.iterdir())


def test_cli_apply_copies_and_does_not_modify_papers(tmp_path, monkeypatch):
    papers, all_catalog, number = _commit_one(tmp_path)
    llm_work = tmp_path / "llm_work"
    paper_dir = papers / "2024_wang_测试论文"
    md_before = (paper_dir / "2024_wang_测试论文.md").read_bytes()
    monkeypatch.syspath_prepend(str(_REPO_ROOT))
    rc = _run_cli([
        "copy_paper_to_llm_work.py",
        "--paper-number", number,
        "--session-id", "review_001",
        "--all-catalog", str(all_catalog),
        "--llm-work-dir", str(llm_work),
        "--apply",
    ])
    assert rc == 0
    target = llm_work / "review_001" / number
    assert target.exists()
    assert (target / "2024_wang_测试论文.md").exists()
    # data/papers untouched
    assert (paper_dir / "2024_wang_测试论文.md").read_bytes() == md_before


def test_cli_invalid_number_errors(tmp_path, monkeypatch):
    papers, all_catalog, _ = _commit_one(tmp_path)
    llm_work = tmp_path / "llm_work"
    monkeypatch.syspath_prepend(str(_REPO_ROOT))
    rc = _run_cli([
        "copy_paper_to_llm_work.py",
        "--paper-number", "1",  # not 16 digits
        "--session-id", "review_001",
        "--all-catalog", str(all_catalog),
        "--llm-work-dir", str(llm_work),
        "--apply",
    ])
    assert rc == 1


def test_cli_exists_without_overwrite_errors(tmp_path, monkeypatch):
    papers, all_catalog, number = _commit_one(tmp_path)
    llm_work = tmp_path / "llm_work"
    monkeypatch.syspath_prepend(str(_REPO_ROOT))
    common = ["copy_paper_to_llm_work.py", "--paper-number", number, "--session-id", "review_001",
              "--all-catalog", str(all_catalog), "--llm-work-dir", str(llm_work), "--apply"]
    assert _run_cli(common) == 0
    # second time without --overwrite -> error
    assert _run_cli(common) == 1
    # with --overwrite -> success
    assert _run_cli(common + ["--overwrite"]) == 0
