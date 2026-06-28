"""测试 /upload 去重与冲突检测：tmp 不应在检查前覆盖已有 raw。

所有测试 monkeypatch converter.convert 和 cleaner.extract 避免真实 MinerU。
"""
import hashlib
import tempfile
import pytest
from pathlib import Path
from fastapi.testclient import TestClient

from src.server import app
from src import server as server_mod

client = TestClient(app)


def _sha(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _fake_convert_success(*args, **kwargs):
    return {"success": True, "markdown": "fake", "md_path": "/fake/md",
            "output_dir": "/fake/out", "source_file": "test", "runner": "cli"}


def _fake_extract_success(*args, **kwargs):
    return {"success": True, "paper_id": kwargs.get("paper_id", "test"),
            "markdown_path": "/fake/paper.md", "images_dir": "/fake/images",
            "images_count": 0, "char_count": 100}


@pytest.fixture(autouse=True)
def isolate_manifest(monkeypatch, tmp_path):
    """每个测试用独立 manifest，不污染真实 data/"""
    from src.manifest import PaperManifest
    m = PaperManifest(path=tmp_path / "test_manifest.json")
    monkeypatch.setattr(server_mod, "manifest", m)
    monkeypatch.setattr(server_mod, "RAW_DIR", tmp_path / "raw")
    server_mod.RAW_DIR.mkdir(parents=True, exist_ok=True)
    yield m


def test_duplicate_sha256_does_not_delete_existing_raw(monkeypatch, tmp_path, isolate_manifest):
    """重复上传同内容文件 → duplicate，不删已有 raw，不调用 converter"""
    m = isolate_manifest
    raw_dir = tmp_path / "raw"
    content = b"unique content for dedup test"
    sha = _sha(content)

    # 模拟已有文献：raw 文件已存在 + manifest 有记录
    existing_raw = raw_dir / "existing.pdf"
    existing_raw.write_bytes(content)
    m.upsert(
        paper_id="existing_pid", raw_pdf=str(existing_raw),
        markdown="/fake/md", images_dir="/fake/img",
        status="converted", images_count=0, md_chars=100,
        raw_filename="existing.pdf", sha256=sha, file_size=len(content),
        mtime="2025-01-01T00:00:00",
    )

    monkeypatch.setattr(server_mod.converter, "convert", _fake_convert_success)
    monkeypatch.setattr(server_mod.cleaner, "extract", _fake_extract_success)

    resp = client.post("/upload?wait=true", files={
        "file": ("existing.pdf", content, "application/pdf")
    })

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["status"] == "duplicate"
    # 已有 raw 文件仍在
    assert existing_raw.exists(), "existing raw file should NOT be deleted"
    assert existing_raw.read_bytes() == content, "existing raw content should be unchanged"


def test_same_name_different_content_does_not_overwrite_raw(monkeypatch, tmp_path, isolate_manifest):
    """同名不同内容上传 → 409，旧 raw 不变"""
    m = isolate_manifest
    raw_dir = tmp_path / "raw"
    old_content = b"old content for conflict test"
    old_sha = _sha(old_content)

    existing_raw = raw_dir / "paper.pdf"
    existing_raw.write_bytes(old_content)
    m.upsert(
        paper_id="paper_2020", raw_pdf=str(existing_raw),
        markdown="/fake/md", images_dir="/fake/img",
        status="converted", images_count=0, md_chars=100,
        raw_filename="paper.pdf", sha256=old_sha, file_size=len(old_content),
        mtime="2025-01-01T00:00:00",
    )

    monkeypatch.setattr(server_mod.converter, "convert", _fake_convert_success)
    monkeypatch.setattr(server_mod.cleaner, "extract", _fake_extract_success)

    resp = client.post("/upload?wait=true", files={
        "file": ("paper.pdf", b"new different content - conflict!", "application/pdf")
    })

    assert resp.status_code == 409, f"Expected 409, got {resp.status_code}: {resp.text}"
    # 旧 raw 文件仍在且内容不变
    assert existing_raw.exists(), "old raw file should NOT be overwritten"
    assert existing_raw.read_bytes() == old_content, "old raw content should be unchanged"


def test_same_sha_different_filename_no_touch_original_raw(monkeypatch, tmp_path, isolate_manifest):
    """相同内容不同文件名 → duplicate，原 raw 不受影响"""
    m = isolate_manifest
    raw_dir = tmp_path / "raw"
    content = b"same content, different filenames"
    sha = _sha(content)

    original_raw = raw_dir / "original.pdf"
    original_raw.write_bytes(content)
    m.upsert(
        paper_id="original_pid", raw_pdf=str(original_raw),
        markdown="/fake/md", images_dir="/fake/img",
        status="converted", images_count=0, md_chars=100,
        raw_filename="original.pdf", sha256=sha, file_size=len(content),
        mtime="2025-01-01T00:00:00",
    )

    monkeypatch.setattr(server_mod.converter, "convert", _fake_convert_success)
    monkeypatch.setattr(server_mod.cleaner, "extract", _fake_extract_success)

    resp = client.post("/upload?wait=true", files={
        "file": ("copy.pdf", content, "application/pdf")
    })

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "duplicate"
    assert original_raw.exists(), "original raw file should NOT be deleted"
    # copy.pdf 不应被创建（os.replace 未执行）
    copy_path = raw_dir / "copy.pdf"
    assert not copy_path.exists(), "copy.pdf should NOT exist (never moved)"


def test_conversion_failure_does_not_leave_tmp(monkeypatch, tmp_path, isolate_manifest):
    """转换失败时 tmp 应被清理"""
    _ = isolate_manifest  # just init
    raw_dir = tmp_path / "raw"

    def _fail_convert(*args, **kwargs):
        return {"success": False, "error": "simulated failure", "runner": "cli"}

    monkeypatch.setattr(server_mod.converter, "convert", _fail_convert)

    resp = client.post("/upload?wait=true", files={
        "file": ("fail.pdf", b"content that will fail conversion", "application/pdf")
    })

    assert resp.status_code == 500
    # 不应有 .upload_*.tmp 残留
    tmp_files = list(raw_dir.glob(".upload_*.tmp"))
    assert len(tmp_files) == 0, f"tmp files should be cleaned: {tmp_files}"
