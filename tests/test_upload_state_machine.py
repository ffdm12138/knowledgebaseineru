"""结构收敛验收：upload 状态机——状态驱动行为，非仅记录。

验收点（计划 Phase 4）：
  1. find_by_sha256 命中多条时按 converted > converting > failed 优先级返回。
  2. converting 状态：同 sha256 命中 converting → upload 返回 in_progress，不调 converter。
  3. converted 状态：命中 converted → duplicate，不调 converter。
  4. failed 状态：允许重试，进入转换流程。
"""
import hashlib
import tempfile
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from src.manifest import PaperManifest
from src import server as server_mod
from src.server import app

client = TestClient(app)


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _fake_convert_success(*args, **kwargs):
    return {"success": True, "markdown": "fake", "md_path": "/f/md",
            "output_dir": "/f/out", "source_file": "t", "runner": "cli"}


def _fake_extract_success(*args, **kwargs):
    return {"success": True, "paper_id": kwargs.get("paper_id", "t"),
            "markdown_path": "/f/paper.md", "images_dir": "/f/images",
            "images_count": 0, "char_count": 100}


@pytest.fixture
def isolated(monkeypatch, tmp_path):
    """独立 manifest + raw 目录，隔离真实 data/。"""
    m = PaperManifest(path=tmp_path / "test_manifest.json")
    monkeypatch.setattr(server_mod, "manifest", m)
    monkeypatch.setattr(server_mod, "RAW_DIR", tmp_path / "raw")
    server_mod.RAW_DIR.mkdir(parents=True, exist_ok=True)
    return m


# ---- find_by_sha256 优先级 ----

def test_find_by_sha256_prefers_converted_over_failed(isolated):
    """同一 sha256 有 converted 和 failed 两条 → 返回 converted。"""
    m = isolated
    sha = "deadbeef"
    m.upsert("failed_pid", raw_pdf="r/a.pdf", markdown="", images_dir="",
             status="failed", sha256=sha, file_size=1,
             mtime="2025-01-01T00:00:00", mineru_backend="hybrid-engine",
             method="auto")
    m.upsert("ok_pid", raw_pdf="r/b.pdf", markdown="md/b.md", images_dir="i",
             status="converted", sha256=sha, file_size=1,
             mtime="2025-01-01T00:00:00", mineru_backend="hybrid-engine",
             method="auto")
    found = m.find_by_sha256(sha)
    assert found["paper_id"] == "ok_pid"
    assert found["status"] == "converted"


def test_find_by_sha256_prefers_converting_over_failed(isolated):
    """同一 sha256 converting 与 failed 并存 → 返回 converting。"""
    m = isolated
    sha = "cafef00d"
    m.upsert("failed_pid", raw_pdf="r/a.pdf", markdown="", images_dir="",
             status="failed", sha256=sha, file_size=1,
             mtime="2025-01-01T00:00:00", mineru_backend="hybrid-engine",
             method="auto")
    m.upsert("conv_pid", raw_pdf="r/b.pdf", markdown="", images_dir="",
             status="converting", sha256=sha, file_size=1,
             mtime="2025-01-01T00:00:00", mineru_backend="hybrid-engine",
             method="auto")
    found = m.find_by_sha256(sha)
    assert found["status"] == "converting"


# ---- converting 阻止重复转换 ----

def test_converting_status_blocks_duplicate_conversion(monkeypatch, isolated):
    """同 sha256 命中 converting → in_progress，不调 converter。"""
    m = isolated
    content = b"content being converted"
    sha = _sha(content)
    m.upsert("inflight", raw_pdf="r/x.pdf", markdown="", images_dir="",
             status="converting", sha256=sha, file_size=len(content),
             mtime="2025-01-01T00:00:00", raw_filename="x.pdf",
             mineru_backend="hybrid-engine", method="auto")

    call_count = {"n": 0}

    def _spy_convert(*a, **kw):
        call_count["n"] += 1
        return _fake_convert_success(*a, **kw)

    monkeypatch.setattr(server_mod.converter, "convert", _spy_convert)
    monkeypatch.setattr(server_mod.cleaner, "extract", _fake_extract_success)

    resp = client.post("/upload", files={
        "file": ("x.pdf", content, "application/pdf")
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "in_progress"
    assert call_count["n"] == 0, "converting 状态下不得调用 converter"


# ---- converted 命中 → duplicate ----

def test_converted_status_returns_duplicate(monkeypatch, isolated):
    """同 sha256 命中 converted → duplicate，不调 converter。"""
    m = isolated
    content = b"already converted content"
    sha = _sha(content)
    m.upsert("done_pid", raw_pdf="r/x.pdf", markdown="md/x.md", images_dir="i",
             status="converted", sha256=sha, file_size=len(content),
             mtime="2025-01-01T00:00:00", raw_filename="x.pdf",
             mineru_backend="hybrid-engine", method="auto")

    call_count = {"n": 0}

    def _spy_convert(*a, **kw):
        call_count["n"] += 1
        return _fake_convert_success(*a, **kw)

    monkeypatch.setattr(server_mod.converter, "convert", _spy_convert)
    monkeypatch.setattr(server_mod.cleaner, "extract", _fake_extract_success)

    resp = client.post("/upload", files={
        "file": ("copy.pdf", content, "application/pdf")
    })
    assert resp.status_code == 200
    assert resp.json()["status"] == "duplicate"
    assert call_count["n"] == 0


# ---- failed 允许重试 ----

def test_failed_status_allows_retry(monkeypatch, isolated):
    """同 sha256 命中 failed → 进入转换流程（重试），调 converter。"""
    m = isolated
    content = b"previously failed content"
    sha = _sha(content)
    m.upsert("failed_pid", raw_pdf="r/x.pdf", markdown="", images_dir="",
             status="failed", sha256=sha, file_size=len(content),
             mtime="2025-01-01T00:00:00", raw_filename="x.pdf",
             mineru_backend="hybrid-engine", method="auto")

    call_count = {"n": 0}

    def _spy_convert(*a, **kw):
        call_count["n"] += 1
        return _fake_convert_success(*a, **kw)

    monkeypatch.setattr(server_mod.converter, "convert", _spy_convert)
    monkeypatch.setattr(server_mod.cleaner, "extract", _fake_extract_success)

    resp = client.post("/upload", files={
        "file": ("x.pdf", content, "application/pdf")
    })
    assert resp.status_code == 200
    assert resp.json()["status"] == "success"
    assert call_count["n"] == 1, "failed 状态应允许重试并调用 converter"
    # 重试后该 sha256 对应的最新记录应为 converted（优先级高于 failed）
    assert m.find_by_sha256(sha)["status"] == "converted"
