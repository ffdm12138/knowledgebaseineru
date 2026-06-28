from pathlib import Path

from src.converter import MinerUConverter


def test_cli_command_includes_hybrid_engine_and_effort(monkeypatch, tmp_path):
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"%PDF")
    output = tmp_path / "out"
    captured = {}

    class Result:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        stem_dir = output / "a" / "hybrid_auto"
        stem_dir.mkdir(parents=True, exist_ok=True)
        (stem_dir / "a.md").write_text("ok", encoding="utf-8")
        return Result()

    monkeypatch.setattr("src.converter.subprocess.run", fake_run)
    monkeypatch.setattr("src.converter.preflight_gpu", lambda: type("Health", (), {"ok": True, "message": "ok"})())
    monkeypatch.setattr("src.converter.snapshot_nvidia_smi", lambda: {"available": False})
    monkeypatch.setattr("src.converter.MinerULock.acquire", lambda self, timeout=None: True)
    monkeypatch.setattr("src.converter.MinerULock.release", lambda self: None)
    converter = MinerUConverter(timeout=1)

    result = converter.convert_via_cli(
        pdf,
        output,
        backend="hybrid-engine",
        method="auto",
        effort="medium",
    )

    assert result["success"] is True
    assert "-b" in captured["cmd"]
    assert "hybrid-engine" in captured["cmd"]
    assert "--effort" in captured["cmd"]
    assert "medium" in captured["cmd"]


def test_api_url_returns_structured_failure_not_notimplemented(monkeypatch, tmp_path):
    """runner=api + api_url → convert_via_api 返回结构化失败（未实现）。"""
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"%PDF")
    monkeypatch.setenv("MINERU_RUNNER", "api")

    class Health:
        api_available = False
        message = "down"

    monkeypatch.setattr("src.converter.preflight_mineru_api", lambda api_url: Health())
    result = MinerUConverter(timeout=1).convert(
        pdf,
        tmp_path / "out",
        api_url="http://127.0.0.1:8000",
    )

    assert result["success"] is False
    assert result["runner"] == "api"
    assert "unavailable" in result["error"]


def test_env_api_runner_uses_api_without_explicit_url(monkeypatch, tmp_path):
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"%PDF")
    captured = {}

    def fake_api(self, input_path, output_dir, backend, method, lang, effort, api_url):
        captured["api_url"] = api_url
        return {"success": False, "runner": "api", "error": "adapter missing"}

    monkeypatch.setenv("MINERU_RUNNER", "api")
    monkeypatch.setenv("MINERU_API_URL", "http://127.0.0.1:9000")
    monkeypatch.setattr(MinerUConverter, "convert_via_api", fake_api)

    result = MinerUConverter(timeout=1).convert(pdf, tmp_path / "out")

    assert result["runner"] == "api"
    assert captured["api_url"] == "http://127.0.0.1:9000"


def test_cli_runner_returns_gpu_preflight_failure(monkeypatch, tmp_path):
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"%PDF")

    class Health:
        ok = False
        message = "gpu missing"

    monkeypatch.setattr("src.converter.preflight_gpu", lambda: Health())
    result = MinerUConverter(timeout=1).convert_via_cli(pdf, tmp_path / "out")

    assert result["success"] is False
    assert "GPU preflight failed" in result["error"]


def test_cli_runner_rejects_explicit_api_url(monkeypatch, tmp_path):
    """runner=cli + 显式 api_url → 结构化错误，不进入 convert_via_api。"""
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"%PDF")
    monkeypatch.setenv("MINERU_RUNNER", "cli")
    monkeypatch.delenv("MINERU_API_URL", raising=False)

    result = MinerUConverter(timeout=1).convert(
        pdf, tmp_path / "out", api_url="http://127.0.0.1:8000")

    assert result["success"] is False
    assert result["runner"] == "cli"
    assert "cli_api_proxy" in result["error"]


def test_cli_api_proxy_command_includes_api_url(monkeypatch, tmp_path):
    """runner=cli_api_proxy + api_url → 命令包含 --api-url。"""
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"%PDF")
    output = tmp_path / "out"
    captured = {}

    class Result:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        stem_dir = output / "a" / "hybrid_auto"
        stem_dir.mkdir(parents=True, exist_ok=True)
        (stem_dir / "a.md").write_text("ok", encoding="utf-8")
        return Result()

    monkeypatch.setenv("MINERU_RUNNER", "cli_api_proxy")
    monkeypatch.setenv("MINERU_API_URL", "http://127.0.0.1:9000")
    monkeypatch.setattr("src.converter.subprocess.run", fake_run)
    monkeypatch.setattr("src.converter.preflight_gpu", lambda: type("Health", (), {"ok": True, "message": "ok"})())
    monkeypatch.setattr("src.converter.snapshot_nvidia_smi", lambda: {"available": False})
    monkeypatch.setattr("src.converter.MinerULock.acquire", lambda self, timeout=None: True)
    monkeypatch.setattr("src.converter.MinerULock.release", lambda self: None)

    result = MinerUConverter(timeout=1).convert_via_cli(
        pdf, output, backend="hybrid-engine", method="auto", effort="medium",
        api_url="http://127.0.0.1:8000",
    )

    assert result["success"] is True
    assert result["runner"] == "cli_api_proxy"
    assert "--api-url" in captured["cmd"]
    assert "http://127.0.0.1:8000" in captured["cmd"]


def test_cli_api_proxy_with_env_api_url(monkeypatch, tmp_path):
    """runner=cli_api_proxy + env MINERU_API_URL → 命令自动包含 --api-url。"""
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"%PDF")
    output = tmp_path / "out"
    captured = {}

    class Result:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        stem_dir = output / "a" / "hybrid_auto"
        stem_dir.mkdir(parents=True, exist_ok=True)
        (stem_dir / "a.md").write_text("ok", encoding="utf-8")
        return Result()

    monkeypatch.setenv("MINERU_RUNNER", "cli_api_proxy")
    monkeypatch.setenv("MINERU_API_URL", "http://127.0.0.1:9000")
    monkeypatch.setattr("src.converter.subprocess.run", fake_run)
    monkeypatch.setattr("src.converter.preflight_gpu", lambda: type("Health", (), {"ok": True, "message": "ok"})())
    monkeypatch.setattr("src.converter.snapshot_nvidia_smi", lambda: {"available": False})
    monkeypatch.setattr("src.converter.MinerULock.acquire", lambda self, timeout=None: True)
    monkeypatch.setattr("src.converter.MinerULock.release", lambda self: None)

    # 不传 api_url → 应该用 env MINERU_API_URL
    result = MinerUConverter(timeout=1).convert(
        pdf, output, backend="hybrid-engine", method="auto", effort="medium")

    assert result["success"] is True
    assert result["runner"] == "cli_api_proxy"
    assert "--api-url" in captured["cmd"]


def test_cli_runner_no_api_url(monkeypatch, tmp_path):
    """runner=cli 不带 api_url → 命令不含 --api-url。"""
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"%PDF")
    output = tmp_path / "out"
    captured = {}

    class Result:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        stem_dir = output / "a" / "hybrid_auto"
        stem_dir.mkdir(parents=True, exist_ok=True)
        (stem_dir / "a.md").write_text("ok", encoding="utf-8")
        return Result()

    monkeypatch.setenv("MINERU_RUNNER", "cli")
    monkeypatch.delenv("MINERU_API_URL", raising=False)
    monkeypatch.setattr("src.converter.subprocess.run", fake_run)
    monkeypatch.setattr("src.converter.preflight_gpu", lambda: type("Health", (), {"ok": True, "message": "ok"})())
    monkeypatch.setattr("src.converter.snapshot_nvidia_smi", lambda: {"available": False})
    monkeypatch.setattr("src.converter.MinerULock.acquire", lambda self, timeout=None: True)
    monkeypatch.setattr("src.converter.MinerULock.release", lambda self: None)

    result = MinerUConverter(timeout=1).convert(
        pdf, output, backend="hybrid-engine", method="auto", effort="medium")

    assert result["success"] is True
    assert result["runner"] == "cli"
    assert "--api-url" not in captured["cmd"]
