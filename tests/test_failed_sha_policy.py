"""Phase 4 验收：upload_service failed retry 策略——同 sha 不同 paper_id 返回 409。

避免一个 sha256 因不同 filename 生成多个 paper_id。
"""
import hashlib
import pytest
from fastapi.testclient import TestClient
from src.manifest import PaperManifest
from src import server as server_mod
from src.server import app

client = TestClient(app)


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _fake_convert_success(*a, **kw):
    return {"success": True, "markdown": "fake", "md_path": "/f/md",
            "output_dir": "/f/out", "source_file": "t",
            "backend": "hybrid-engine", "method": "auto",
            "effort": "medium", "runner": "cli"}


def _fake_extract_success(*a, **kw):
    return {"success": True, "paper_id": kw.get("paper_id", "t"),
            "markdown_path": "/f/paper.md", "images_dir": "/f/images",
            "images_count": 0, "char_count": 100}


@pytest.fixture
def isolated(monkeypatch, tmp_path):
    m = PaperManifest(path=tmp_path / "test_manifest.json")
    monkeypatch.setattr(server_mod, "manifest", m)
    monkeypatch.setattr(server_mod, "RAW_DIR", tmp_path / "raw")
    server_mod.RAW_DIR.mkdir(parents=True, exist_ok=True)
    return m


def test_failed_same_sha_different_paper_id_rejected(monkeypatch, isolated):
    """A. failed original.pdf 后上传 copy.pdf 同 sha → 409, 不出现 copy"""
    m = isolated
    content = b"failed content for sha policy"
    sha = _sha(content)
    # original.pdf 失败记录：derive_paper_id("original.pdf") = "original"
    m.upsert("original", raw_pdf="r/original.pdf", markdown="", images_dir="",
             status="failed", sha256=sha, file_size=len(content),
             mtime="2025-01-01T00:00:00", raw_filename="original.pdf",
             mineru_backend="hybrid-engine", method="auto")

    monkeypatch.setattr(server_mod.converter, "convert", _fake_convert_success)
    monkeypatch.setattr(server_mod.cleaner, "extract", _fake_extract_success)

    resp = client.post("/upload", files={
        "file": ("copy.pdf", content, "application/pdf")
    })
    assert resp.status_code == 409, f"expected 409, got {resp.status_code}: {resp.text}"
    assert "失败记录" in resp.text or "paper_id" in resp.text
    # manifest 里不出现 copy
    assert m.get("copy") is None
    # original 仍是 failed
    assert m.get("original")["status"] == "failed"


def test_failed_same_sha_same_paper_id_allows_retry(monkeypatch, isolated):
    """B. failed original.pdf 后重传 original.pdf 同 sha → 允许重试, 单条记录"""
    m = isolated
    content = b"retry same paper id"
    sha = _sha(content)
    m.upsert("original", raw_pdf="r/original.pdf", markdown="", images_dir="",
             status="failed", sha256=sha, file_size=len(content),
             mtime="2025-01-01T00:00:00", raw_filename="original.pdf",
             mineru_backend="hybrid-engine", method="auto")

    monkeypatch.setattr(server_mod.converter, "convert", _fake_convert_success)
    monkeypatch.setattr(server_mod.cleaner, "extract", _fake_extract_success)

    resp = client.post("/upload", files={
        "file": ("original.pdf", content, "application/pdf")
    })
    assert resp.status_code == 200
    assert resp.json()["status"] == "success"
    # 仍只有 original 一条
    assert m.get("original")["status"] == "converted"


def test_find_by_sha256_prefers_converted_over_failed(isolated):
    """C. failed + converted 同 sha → 返回 converted"""
    m = isolated
    sha = "abc"
    m.upsert("a", raw_pdf="r/a", markdown="", images_dir="",
             status="failed", sha256=sha, file_size=1,
             mtime="2025-01-01T00:00:00", mineru_backend="hybrid-engine", method="auto")
    m.upsert("b", raw_pdf="r/b", markdown="md", images_dir="i",
             status="converted", sha256=sha, file_size=1,
             mtime="2025-01-01T00:00:00", mineru_backend="hybrid-engine", method="auto")
    assert m.find_by_sha256(sha)["status"] == "converted"


def test_find_by_sha256_prefers_converting_over_failed(isolated):
    """D. failed + converting 同 sha → 返回 converting"""
    m = isolated
    sha = "def"
    m.upsert("a", raw_pdf="r/a", markdown="", images_dir="",
             status="failed", sha256=sha, file_size=1,
             mtime="2025-01-01T00:00:00", mineru_backend="hybrid-engine", method="auto")
    m.upsert("b", raw_pdf="r/b", markdown="", images_dir="",
             status="converting", sha256=sha, file_size=1,
             mtime="2025-01-01T00:00:00", mineru_backend="hybrid-engine", method="auto")
    assert m.find_by_sha256(sha)["status"] == "converting"
