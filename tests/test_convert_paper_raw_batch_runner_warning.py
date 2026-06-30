"""Tests for convert_paper_raw_batch runner warning."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def _run_batch(paper_raw: Path, runner_env: str, *extra_args: str) -> subprocess.CompletedProcess:
    """Run convert_paper_raw_batch.py via subprocess with the given env."""
    env = {
        **os.environ,
        "MINERU_RUNNER": runner_env,
        "MINERU_REQUIRE_GPU": "true",
        "MINERU_ALLOW_CPU": "",
    }
    cmd = [
        sys.executable,
        "-m", "scripts.convert_paper_raw_batch",
        "--paper-raw-dir", str(paper_raw),
        *extra_args,
    ]
    return subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=30)


def test_batch_cli_runner_warns(tmp_path):
    """When len(source_ids) > 1 and MINERU_RUNNER=cli, cold-start warning is emitted."""
    paper_raw = tmp_path / "paper_raw"
    paper_raw.mkdir(parents=True)
    for sid in ("000001", "000002"):
        (paper_raw / sid).mkdir(parents=True)

    result = _run_batch(paper_raw, "cli", "--all", "--dry-run")
    combined = result.stdout + result.stderr
    assert "WARNING" in combined, f"expected WARNING, got: {combined[:500]}"
    assert "cli_api_proxy" in combined, f"should suggest cli_api_proxy: {combined[:500]}"
    assert "MinerU runtime:" in combined
    assert "require_gpu: true" in combined
    assert "backend: hybrid-engine" in combined
    assert "method: auto" in combined
    assert "effort: medium" in combined


def test_batch_cli_api_proxy_no_warn(tmp_path):
    """When MINERU_RUNNER=cli_api_proxy, no cli cold-start warning."""
    paper_raw = tmp_path / "paper_raw"
    paper_raw.mkdir(parents=True)
    for sid in ("000001", "000002"):
        (paper_raw / sid).mkdir(parents=True)

    result = _run_batch(paper_raw, "cli_api_proxy", "--all", "--dry-run")
    combined = result.stdout + result.stderr
    assert "cold-start" not in combined.lower(), f"unexpected warning: {combined[:500]}"


def test_batch_allow_cpu_warns_and_summary_shows_debug_fallback(tmp_path):
    """--allow-cpu is explicit debug fallback and shows in runtime summary."""
    paper_raw = tmp_path / "paper_raw"
    paper_raw.mkdir(parents=True)
    (paper_raw / "000001").mkdir(parents=True)

    result = _run_batch(paper_raw, "cli_api_proxy", "--all", "--dry-run", "--allow-cpu")
    combined = result.stdout + result.stderr
    assert result.returncode == 0
    assert "--allow-cpu enables debug-only CPU/no-GPU fallback" in combined
    assert "MinerU runtime:" in combined
    assert "require_gpu: false" in combined
    assert "allow_cpu: true" in combined
