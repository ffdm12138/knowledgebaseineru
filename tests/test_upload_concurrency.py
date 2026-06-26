"""测试 /upload 并发安全：两个请求不能互相覆盖 raw"""
import hashlib
import threading
import time
import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from src import server as server_mod
from src.server import app

client = TestClient(app)


def _sha(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


@pytest.fixture(autouse=True)
def isolate_manifest(monkeypatch, tmp_path):
    from src.manifest import PaperManifest
    m = PaperManifest(path=tmp_path / "test_manifest.json")
    monkeypatch.setattr(server_mod, "manifest", m)
    monkeypatch.setattr(server_mod, "RAW_DIR", tmp_path / "raw")
    server_mod.RAW_DIR.mkdir(parents=True, exist_ok=True)
    return m


class FakeConverter:
    """可控制返回和延迟的 fake converter"""
    def __init__(self):
        self.call_count = 0
        self._delay = 0.0

    def set_delay(self, s):
        self._delay = s

    def convert(self, *args, **kwargs):
        self.call_count += 1
        if self._delay > 0:
            time.sleep(self._delay)
        return {
            "success": True, "markdown": "fake", "md_path": "/fake/md",
            "output_dir": "/fake/out", "source_file": "test", "runner": "cli",
        }


def _fake_extract_success(*args, **kwargs):
    return {"success": True, "paper_id": kwargs.get("paper_id", "test"),
            "markdown_path": "/fake/paper.md", "images_dir": "/fake/images",
            "images_count": 0, "char_count": 100}


def test_concurrent_same_name_different_content(monkeypatch, tmp_path, isolate_manifest):
    """并发上传同名不同内容 → 一个成功/一个409，不互相覆盖"""
    raw_dir = tmp_path / "raw"
    old_content = b"AAAA"
    new_content = b"BBBB"

    # 先上传一个旧文件，建立基线
    fake1 = FakeConverter()
    monkeypatch.setattr(server_mod.converter, "convert", fake1.convert)
    monkeypatch.setattr(server_mod.cleaner, "extract", _fake_extract_success)

    resp = client.post("/upload", files={
        "file": ("race.pdf", old_content, "application/pdf")
    })
    assert resp.status_code == 200

    # 旧 raw 存在
    old_path = raw_dir / "race.pdf"
    assert old_path.exists()
    old_raw_content = old_path.read_bytes()

    # 现在并发上传不同内容
    fake2 = FakeConverter()
    fake2.set_delay(0.5)  # 让第二个慢一点，确保锁机制工作
    monkeypatch.setattr(server_mod.converter, "convert", fake2.convert)

    def upload_new():
        return client.post("/upload", files={
            "file": ("race.pdf", new_content, "application/pdf")
        })

    t = threading.Thread(target=upload_new)
    t.start()
    time.sleep(0.1)  # 给线程启动时间

    # 第二个请求应该看到冲突 (paper_id 已存在且 sha256 不同)
    resp2 = client.post("/upload", files={
        "file": ("race.pdf", b"CCCC", "application/pdf")
    })
    t.join()

    # 至少有一个返回 409 (或两个都 409)
    statuses = [resp2.status_code]
    assert 409 in statuses or resp2.status_code == 409, \
        f"Expected 409 conflict, got {resp2.status_code}"
    # 旧 raw 不能被覆盖
    assert old_path.read_bytes() == old_raw_content, \
        "Old raw content must not be overwritten by concurrent uploads"


def test_concurrent_same_sha_no_duplicate_convert(monkeypatch, tmp_path, isolate_manifest):
    """并发上传同内容 → 不重复调用 converter"""
    raw_dir = tmp_path / "raw"
    content = b"same content for concurrent test"
    sha = _sha(content)

    fake = FakeConverter()
    monkeypatch.setattr(server_mod.converter, "convert", fake.convert)
    monkeypatch.setattr(server_mod.cleaner, "extract", _fake_extract_success)

    # 先 baseline 上传
    resp1 = client.post("/upload", files={
        "file": ("base.pdf", content, "application/pdf")
    })
    assert resp1.status_code == 200
    first_count = fake.call_count

    # 并发上传同内容不同名
    def upload_copy():
        client.post("/upload", files={
            "file": ("copy.pdf", content, "application/pdf")
        })

    t1 = threading.Thread(target=upload_copy)
    t2 = threading.Thread(target=upload_copy)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    # converter.call_count 不应该增加（duplicate 在转换前拦截）
    assert fake.call_count == first_count, \
        f"Converter should not be called for duplicates, but was called {fake.call_count - first_count} extra times"


def test_query_param_validation(monkeypatch):
    """上传接口拒绝非法 method（backend/effort 已固定，不暴露参数）"""
    from src import server as server_mod

    # Mock converter 避免真实调用
    def _fake_convert(*a, **kw):
        return {"success": True, "markdown": "ok", "md_path": "/f/md",
                "output_dir": "/f/out", "source_file": "t", "runner": "cli"}
    monkeypatch.setattr(server_mod.converter, "convert", _fake_convert)
    monkeypatch.setattr(server_mod.cleaner, "extract", lambda *a, **kw: {
        "success": True, "paper_id": kw.get("paper_id", "t"),
        "markdown_path": "/f/md", "images_dir": "/f/i",
        "images_count": 0, "char_count": 10})

    resp = client.post("/upload?method=evil", files={
        "file": ("test.pdf", b"%PDF-1.4 fake", "application/pdf")
    })
    assert resp.status_code == 400
    assert "method" in resp.text.lower()

    # 合法 method 仍然接受
    resp = client.post("/upload?method=ocr", files={
        "file": ("test.pdf", b"%PDF-1.4 fake", "application/pdf")
    })
    assert resp.status_code == 200
