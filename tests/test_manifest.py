"""测试 manifest 原子写入、sha256 查找、filelock"""
import json
import tempfile
from pathlib import Path
from src.manifest import PaperManifest


def test_upsert_and_get():
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "manifest.json"
        m = PaperManifest(p)
        m.upsert("test_pid", raw_pdf="raw/x.pdf", markdown="md/x.md",
                 images_dir="md/images", sha256="abc123", file_size=1000,
                 mtime="2026-01-01T00:00:00", backend="cli", method="auto")
        entry = m.get("test_pid")
        assert entry is not None
        assert entry["paper_id"] == "test_pid"
        assert entry["sha256"] == "abc123"
        assert entry["status"] == "converted"


def test_find_by_sha256():
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "manifest.json"
        m = PaperManifest(p)
        m.upsert("a", raw_pdf="raw/a.pdf", markdown="md/a.md",
                 images_dir="md/images", sha256="aaa", file_size=100,
                 mtime="2026-01-01T00:00:00", backend="cli", method="auto")
        m.upsert("b", raw_pdf="raw/b.pdf", markdown="md/b.md",
                 images_dir="md/images", sha256="bbb", file_size=200,
                 mtime="2026-01-01T00:00:00", backend="cli", method="auto")
        assert m.find_by_sha256("aaa") is not None
        assert m.find_by_sha256("aaa")["paper_id"] == "a"
        assert m.find_by_sha256("bbb")["paper_id"] == "b"
        assert m.find_by_sha256("ccc") is None


def test_delete():
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "manifest.json"
        m = PaperManifest(p)
        m.upsert("x", raw_pdf="raw/x.pdf", markdown="md/x.md",
                 images_dir="md/images", sha256="xxx", file_size=10,
                 mtime="2026-01-01T00:00:00", backend="cli", method="auto")
        assert m.has("x")
        assert m.delete("x")
        assert not m.has("x")
        assert not m.delete("x")  # 第二次删返回 False


def test_atomic_write_not_corrupted():
    """写入后读回 JSON 必须可解析"""
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "manifest.json"
        m = PaperManifest(p)
        m.upsert("x", raw_pdf="raw/x.pdf", markdown="md/x.md",
                 images_dir="md/images", sha256="xxx", file_size=10,
                 mtime="2026-01-01T00:00:00", backend="cli", method="auto")
        # 直接读文件确认是合法 JSON
        data = json.loads(p.read_text(encoding="utf-8"))
        assert len(data["papers"]) == 1


def test_list_all():
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "manifest.json"
        m = PaperManifest(p)
        assert m.list_all() == []
        m.upsert("x", raw_pdf="raw/x.pdf", markdown="md/x.md",
                 images_dir="md/images", sha256="x", file_size=1,
                 mtime="2026-01-01T00:00:00", backend="cli", method="auto")
        assert len(m.list_all()) == 1


def test_stats():
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "manifest.json"
        m = PaperManifest(p)
        m.upsert("a", raw_pdf="raw/a.pdf", markdown="md/a.md",
                 images_dir="md/images", sha256="a", file_size=1,
                 images_count=3, md_chars=100,
                 mtime="2026-01-01T00:00:00", backend="cli", method="auto")
        m.upsert("b", raw_pdf="raw/b.pdf", markdown="md/b.md",
                 images_dir="md/images", sha256="b", file_size=1,
                 images_count=5, md_chars=200,
                 mtime="2026-01-01T00:00:00", backend="cli", method="auto")
        s = m.stats()
        assert s["total_papers"] == 2
        assert s["total_images"] == 8
        assert s["total_md_chars"] == 300
