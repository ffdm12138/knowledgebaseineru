"""Phase 3 验收：manifest error/updated_at 字段 + converted_at 语义。

converted_at 仅 status=converted 时写入；converting/failed 保留旧值或空，不新建。
"""
import tempfile
from pathlib import Path
from unittest.mock import MagicMock
from src.manifest import PaperManifest


def _new(td):
    return PaperManifest(path=Path(td) / "m.json")


def test_failed_writes_error_and_no_new_converted_at():
    """A. upsert(status=failed, error=boom): error 写入, 无新建 converted_at, updated_at 非空"""
    with tempfile.TemporaryDirectory() as td:
        m = _new(td)
        m.upsert("p", raw_pdf="r", markdown="", images_dir="",
                 status="failed", error="boom", sha256="a", file_size=1,
                 mtime="2026-01-01T00:00:00", mineru_backend="hybrid-engine",
                 method="auto")
        e = m.get("p")
        assert e["status"] == "failed"
        assert e["error"] == "boom"
        assert e["converted_at"] == ""  # 不新建
        assert e["updated_at"] != ""


def test_converting_no_new_converted_at():
    """B. upsert(status=converting): 无新建 converted_at, updated_at 非空"""
    with tempfile.TemporaryDirectory() as td:
        m = _new(td)
        m.upsert("p", raw_pdf="r", markdown="", images_dir="",
                 status="converting", sha256="a", file_size=1,
                 mtime="2026-01-01T00:00:00", mineru_backend="hybrid-engine",
                 method="auto")
        e = m.get("p")
        assert e["status"] == "converting"
        assert e["converted_at"] == ""
        assert e["updated_at"] != ""


def test_converted_writes_converted_at():
    """C. upsert(status=converted): converted_at 非空, updated_at 非空"""
    with tempfile.TemporaryDirectory() as td:
        m = _new(td)
        m.upsert("p", raw_pdf="r", markdown="md", images_dir="i",
                 status="converted", sha256="a", file_size=1,
                 mtime="2026-01-01T00:00:00", mineru_backend="hybrid-engine",
                 method="auto")
        e = m.get("p")
        assert e["converted_at"] != ""
        assert e["updated_at"] != ""


def test_converted_to_failed_preserves_converted_at():
    """D. converted -> failed: 旧 converted_at 保留, error 非空, updated_at 更新"""
    with tempfile.TemporaryDirectory() as td:
        m = _new(td)
        m.upsert("p", raw_pdf="r", markdown="md", images_dir="i",
                 status="converted", sha256="a", file_size=1,
                 mtime="2026-01-01T00:00:00", mineru_backend="hybrid-engine",
                 method="auto")
        first = m.get("p")
        old_cat = first["converted_at"]
        old_uat = first["updated_at"]

        # 翻转为 failed
        m.upsert("p", raw_pdf="r", markdown="", images_dir="",
                 status="failed", error="boom2", sha256="a", file_size=1,
                 mtime="2026-01-01T00:00:00", mineru_backend="hybrid-engine",
                 method="auto")
        e = m.get("p")
        assert e["status"] == "failed"
        assert e["error"] == "boom2"
        assert e["converted_at"] == old_cat  # 保留
        assert e["updated_at"] >= old_uat  # 更新


def test_upload_service_converter_failure_writes_error(monkeypatch, tmp_path):
    """E. upload_service converter 失败后 manifest 中 error 非空"""
    import hashlib
    from src.manifest import PaperManifest
    from src.upload_service import upload_from_bytes, UploadError

    m = PaperManifest(path=tmp_path / "m.json")
    raw = tmp_path / "raw"; raw.mkdir()

    class _FailConv:
        def convert(self, *a, **kw):
            return {"success": False, "error": "simulated boom",
                    "backend": "hybrid-engine", "method": "auto",
                    "effort": "medium", "runner": "cli"}

    content = b"will fail"
    sha = hashlib.sha256(content).hexdigest()
    try:
        upload_from_bytes(filename="x.pdf", data=content,
                          converter=_FailConv(), cleaner=MagicMock(),
                          manifest=m, raw_dir=raw)
    except UploadError:
        pass

    entry = m.find_by_sha256(sha)
    assert entry is not None
    assert entry["status"] == "failed"
    assert "simulated boom" in entry["error"]
    assert entry["converted_at"] == ""
