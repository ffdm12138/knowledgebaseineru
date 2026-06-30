import json
import runpy
import sys
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parent.parent


def _run_stage(argv: list[str]) -> int:
    saved = sys.argv
    sys.argv = argv
    try:
        runpy.run_path(str(_REPO_ROOT / "scripts" / "stage_raw_pdfs_to_paper_raw.py"), run_name="__main__")
        return 0
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 1
    finally:
        sys.argv = saved


def _sha(path: Path) -> str:
    import hashlib
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_stage_raw_pdfs_default_apply_copies_and_keeps_raw(tmp_path, monkeypatch):
    raw = tmp_path / "raw"
    paper_raw = tmp_path / "paper_raw"
    raw.mkdir()
    pdf = raw / "paper.pdf"
    pdf.write_bytes(b"%PDF default copy")
    report = tmp_path / "stage_report.json"
    original_sha = _sha(pdf)
    monkeypatch.syspath_prepend(str(_REPO_ROOT))

    rc = _run_stage([
        "stage_raw_pdfs_to_paper_raw.py",
        "--raw-dir", str(raw),
        "--paper-raw-dir", str(paper_raw),
        "--report", str(report),
        "--apply",
    ])

    assert rc == 0
    assert pdf.exists()
    staged_pdf = paper_raw / "000001" / "000001.pdf"
    assert staged_pdf.exists()
    assert _sha(staged_pdf) == original_sha
    manifest = json.loads((paper_raw / "000001" / "stage_manifest.json").read_text(encoding="utf-8"))
    assert manifest["operation"] == "copy"
    assert manifest["original_path"] == str(pdf)
    assert manifest["original_sha256"] == original_sha
    assert manifest["staged_sha256"] == original_sha
    report_data = json.loads(report.read_text(encoding="utf-8"))
    item = report_data[0]
    assert item["operation"] == "copy"
    assert item["original_sha256"] == original_sha
    assert item["staged_sha256"] == original_sha


def test_stage_raw_pdfs_explicit_move_removes_raw(tmp_path, monkeypatch):
    raw = tmp_path / "raw"
    paper_raw = tmp_path / "paper_raw"
    raw.mkdir()
    pdf = raw / "paper.pdf"
    pdf.write_bytes(b"%PDF explicit move")
    original_sha = _sha(pdf)
    monkeypatch.syspath_prepend(str(_REPO_ROOT))

    rc = _run_stage([
        "stage_raw_pdfs_to_paper_raw.py",
        "--raw-dir", str(raw),
        "--paper-raw-dir", str(paper_raw),
        "--apply",
        "--move",
    ])

    assert rc == 0
    assert not pdf.exists()
    manifest = json.loads((paper_raw / "000001" / "stage_manifest.json").read_text(encoding="utf-8"))
    assert manifest["operation"] == "move"
    assert manifest["original_sha256"] == original_sha
    assert manifest["staged_sha256"] == original_sha
