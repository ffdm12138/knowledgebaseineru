import json

import scripts.doctor_ingest_pipeline as doctor


def test_doctor_writes_report_and_skips_preflight_without_sources(tmp_path, monkeypatch):
    calls: list[str] = []

    def fake_run_step(name, cmd, *, cwd):
        calls.append(name)
        return {
            "name": name,
            "command": cmd,
            "returncode": 0,
            "blocking": False,
            "stdout": "{}",
            "stderr": "",
        }

    monkeypatch.setattr(doctor, "_run_step", fake_run_step)
    report_path = tmp_path / "reports" / "doctor.json"

    rc = doctor.main([
        "--project-root", str(tmp_path),
        "--paper-raw-dir", str(tmp_path / "paper_raw"),
        "--report-path", str(report_path),
    ])

    assert rc == 0
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["valid"] is True
    assert calls == [
        "check_directory_hygiene",
        "validate_v2_library",
        "audit_metadata_quality",
        "pytest_ingest_subset",
    ]
    preflight = next(step for step in report["steps"] if step["name"] == "preflight_paper_raw_import")
    assert preflight["skipped"] is True


def test_doctor_returns_nonzero_on_blocking_step(tmp_path, monkeypatch):
    paper_raw = tmp_path / "paper_raw" / "000001"
    paper_raw.mkdir(parents=True)

    def fake_run_step(name, cmd, *, cwd):
        return {
            "name": name,
            "command": cmd,
            "returncode": 1 if name == "preflight_paper_raw_import" else 0,
            "blocking": name == "preflight_paper_raw_import",
            "stdout": "",
            "stderr": "blocked",
        }

    monkeypatch.setattr(doctor, "_run_step", fake_run_step)
    report_path = tmp_path / "doctor.json"

    rc = doctor.main([
        "--project-root", str(tmp_path),
        "--paper-raw-dir", str(tmp_path / "paper_raw"),
        "--report-path", str(report_path),
        "--skip-tests",
    ])

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert rc == 1
    assert report["valid"] is False
    assert report["blocking_count"] == 1
