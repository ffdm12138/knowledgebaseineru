"""测试上传去重、覆盖保护、sha256 检测"""
import hashlib
import tempfile
from pathlib import Path
from src.manifest import PaperManifest


def test_find_by_sha256_finds_duplicate():
    """相同 sha256 应能找到已有记录"""
    sha = hashlib.sha256(b"test content").hexdigest()
    with tempfile.TemporaryDirectory() as td:
        mp = Path(td) / "test_manifest.json"
        m = PaperManifest(path=mp)
        m.upsert(
            paper_id="test1", raw_pdf="/fake/a.pdf",
            markdown="/fake/a.md", images_dir="/fake/a_images",
            status="converted", images_count=3, md_chars=100,
            raw_filename="a.pdf", sha256=sha, file_size=12,
            mtime="2025-01-01T00:00:00",
        )
        found = m.find_by_sha256(sha)
        assert found is not None
        assert found["paper_id"] == "test1"


def test_find_by_sha256_none_for_unknown():
    """不存在的 sha256 返回 None"""
    with tempfile.TemporaryDirectory() as td:
        mp = Path(td) / "test_manifest.json"
        m = PaperManifest(path=mp)
        assert m.find_by_sha256("deadbeef") is None


def test_sha256_different_content_different_hash():
    """不同内容产生不同 sha256"""
    sha1 = hashlib.sha256(b"content A").hexdigest()
    sha2 = hashlib.sha256(b"content B").hexdigest()
    assert sha1 != sha2


def test_upload_conflict_same_pid_different_sha():
    """同 paper_id 不同 sha256 应被检测"""
    with tempfile.TemporaryDirectory() as td:
        mp = Path(td) / "test_manifest.json"
        m = PaperManifest(path=mp)
        m.upsert(
            paper_id="test1", raw_pdf="/fake/a.pdf",
            markdown="/fake/a.md", images_dir="/fake/a_images",
            status="converted", images_count=3, md_chars=100,
            raw_filename="a.pdf", sha256="abc123", file_size=12,
            mtime="2025-01-01T00:00:00",
        )
        existing = m.get("test1")
        assert existing is not None
        assert existing["sha256"] == "abc123"
        # 新上传同 paper_id 但不同 sha256 → 应被识别为冲突
        assert existing["sha256"] != "def456"
