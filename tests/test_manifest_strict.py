"""测试 manifest strict 模式：损坏 JSON 时拒绝写操作"""
import json
import tempfile
import pytest
from pathlib import Path
from src.manifest import PaperManifest


def test_upsert_rejects_corrupt_manifest():
    """manifest JSON 损坏时 upsert 抛 RuntimeError"""
    with tempfile.TemporaryDirectory() as td:
        mp = Path(td) / "corrupt_manifest.json"
        # 写入损坏 JSON
        mp.write_text("{bad json", encoding="utf-8")

        m = PaperManifest(path=mp)
        # 只读可以返回空结构
        assert m.list_all() == []

        # 写操作必须抛 RuntimeError
        with pytest.raises(RuntimeError, match="损坏"):
            m.upsert(
                paper_id="test", raw_pdf="/fake/a.pdf",
                markdown="/fake/a.md", images_dir="/fake/a_images",
                status="converted", images_count=0, md_chars=0,
                raw_filename="a.pdf", sha256="abc",
                file_size=0, mtime="2025-01-01T00:00:00",
            )

        # 原坏文件仍然存在，没有被覆盖
        assert mp.read_text(encoding="utf-8") == "{bad json"


def test_delete_rejects_corrupt_manifest():
    """manifest JSON 损坏时 delete 抛 RuntimeError"""
    with tempfile.TemporaryDirectory() as td:
        mp = Path(td) / "corrupt_manifest.json"
        mp.write_text("{bad json", encoding="utf-8")

        m = PaperManifest(path=mp)
        with pytest.raises(RuntimeError, match="损坏"):
            m.delete("test_pid")

        assert mp.read_text(encoding="utf-8") == "{bad json"


def test_normal_upsert_still_works():
    """正常 manifest upsert/delete 仍然通过"""
    with tempfile.TemporaryDirectory() as td:
        mp = Path(td) / "normal_manifest.json"
        m = PaperManifest(path=mp)

        m.upsert(
            paper_id="test", raw_pdf="/fake/a.pdf",
            markdown="/fake/a.md", images_dir="/fake/a_images",
            status="converted", images_count=1, md_chars=100,
            raw_filename="a.pdf", sha256="abc123",
            file_size=12, mtime="2025-01-01T00:00:00",
        )
        assert m.has("test")
        assert m.get("test")["sha256"] == "abc123"

        m.delete("test")
        assert not m.has("test")
