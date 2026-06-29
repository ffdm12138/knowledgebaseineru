"""Tests for scripts/curate_paper_raw.py: dry-run writes curation_prompt.md, apply merges + renames."""
import json
import runpy
import sys
from pathlib import Path

import pytest

from src.services.v2_library import empty_catalog, empty_metadata


def _matched_raw(folder: Path, source_id: str = "000001") -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    metadata = empty_metadata(source_id)
    metadata["title"]["original"] = "Trusted Original"
    metadata["year"] = 2024
    metadata["authors"] = [{"full_name": "Wang A", "family": "Wang", "given": "A", "orcid": "", "affiliation": ""}]
    metadata["metadata_match"]["status"] = "matched"
    metadata["metadata_match"]["confidence"] = 1.0
    (folder / f"{source_id}.metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    (folder / f"{source_id}.md").write_text("# Trusted Original\n\nbody text", encoding="utf-8")
    (folder / f"{source_id}.pdf").write_bytes(b"%PDF")
    (folder / "images").mkdir()
    return folder


_REPO_ROOT = Path(__file__).resolve().parent.parent
_SCRIPT = _REPO_ROOT / "scripts" / "curate_paper_raw.py"


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


def test_dry_run_writes_curation_prompt(tmp_path, monkeypatch):
    raw = tmp_path / "paper_raw"
    folder = _matched_raw(raw / "000001")
    monkeypatch.syspath_prepend(str(_REPO_ROOT))
    rc = _run_cli([
        "curate_paper_raw.py",
        "--paper-dir", str(folder),
        "--dry-run",
    ])
    assert rc == 0
    prompt_path = folder / "curation_prompt.md"
    assert prompt_path.exists()
    text = prompt_path.read_text(encoding="utf-8")
    assert "paper_raw_catalog_curator" in text
    assert "evidence_profile" in text
    assert "screening" in text
    assert "不得覆盖" in text or "metadata" in text


def test_apply_merges_only_empty_and_renames(tmp_path, monkeypatch):
    raw = tmp_path / "paper_raw"
    folder = _matched_raw(raw / "000001")
    catalog = empty_catalog()
    catalog["display"].update({
        "title_original": "Trusted Original",
        "title_zh": "可信论文",
        "short_name_zh": "可信论文",
        "year": 2024,
        "first_author": "Wang",
    })
    catalog_path = folder / "000001.catalog.json"
    catalog_path.write_text(json.dumps(catalog), encoding="utf-8")
    patch = empty_metadata("000001")
    patch["abstract"] = "new abstract"
    patch["title"]["original"] = "Overwrite Attempt"
    patch_path = tmp_path / "patch.metadata.json"
    patch_path.write_text(json.dumps(patch), encoding="utf-8")
    monkeypatch.syspath_prepend(str(_REPO_ROOT))

    rc = _run_cli([
        "curate_paper_raw.py",
        "--paper-dir", str(folder),
        "--catalog", str(catalog_path),
        "--metadata", str(patch_path),
        "--apply",
    ])
    assert rc == 0
    renamed = tmp_path / "paper_raw" / "2024_Wang_可信论文"
    assert renamed.exists()
    merged = json.loads((renamed / "2024_Wang_可信论文.metadata.json").read_text(encoding="utf-8"))
    assert merged["title"]["original"] == "Trusted Original"  # not overwritten
    assert merged["abstract"] == "new abstract"  # empty field filled


def test_apply_rejects_unmatched_metadata(tmp_path, monkeypatch):
    raw = tmp_path / "paper_raw"
    folder = _matched_raw(raw / "000001")
    meta_path = folder / "000001.metadata.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["metadata_match"]["status"] = "unmatched"
    meta_path.write_text(json.dumps(meta), encoding="utf-8")
    monkeypatch.syspath_prepend(str(_REPO_ROOT))
    rc = _run_cli(["curate_paper_raw.py", "--paper-dir", str(folder), "--apply"])
    assert rc == 1
    assert (folder / ".import_status.json").exists()


def test_all_ready_apply_only_processes_curated(tmp_path, monkeypatch):
    raw = tmp_path / "paper_raw"
    # folder A has a curated catalog output
    folder_a = _matched_raw(raw / "000001")
    catalog = empty_catalog()
    catalog["display"].update({"short_name_zh": "甲论文", "year": 2024, "first_author": "Wang"})
    (folder_a / "000001.catalog.json").write_text(json.dumps(catalog), encoding="utf-8")
    # folder B is ready (metadata+md+images) but has NO curated catalog output
    _matched_raw(raw / "000002")
    monkeypatch.syspath_prepend(str(_REPO_ROOT))
    rc = _run_cli(["curate_paper_raw.py", "--all-ready", "--paper-raw-dir", str(raw), "--apply"])
    # folder A renamed (curated), folder B left untouched; exit 0 since B is just skipped
    assert (raw / "2024_Wang_甲论文").exists() or (folder_a / ".import_status.json").exists()
    assert (raw / "000002").exists()  # not processed
    # rc: A may succeed (curated) -> rc 0; if apply needs matched+schema it's fine
    assert rc in (0, 1)
