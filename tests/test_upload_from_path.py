"""Phase 7 验收：upload_from_path 流式上传 + app.py 不 read_bytes。

Gradio 大 PDF 不再一次性读入内存，改用文件流式分块。
"""
import ast
import hashlib
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

from src.upload_service import upload_from_path, UploadError


def _fake_convert_success(*a, **kw):
    return {"success": True, "markdown": "fake", "md_path": "/f/md",
            "output_dir": "/f/out", "source_file": "t",
            "backend": "hybrid-engine", "method": "auto",
            "effort": "medium", "runner": "cli"}


def _fake_extract_success(*a, **kw):
    return {"success": True, "paper_id": kw.get("paper_id", "t"),
            "markdown_path": "/f/paper.md", "images_dir": "/f/images",
            "images_count": 0, "char_count": 100}


def test_upload_from_path_success(tmp_path):
    """upload_from_path 处理文件成功，不一次性 read_bytes"""
    from src.manifest import PaperManifest
    m = PaperManifest(path=tmp_path / "m.json")
    raw = tmp_path / "raw"; raw.mkdir()
    src = tmp_path / "src.pdf"
    content = b"%PDF-1.4 fake content for path upload"
    src.write_bytes(content)

    result = upload_from_path(
        src_path=src, converter=MagicMock(convert=_fake_convert_success),
        cleaner=MagicMock(extract=_fake_extract_success), manifest=m, raw_dir=raw)
    assert result["status"] == "success"
    assert result["paper_id"]
    # manifest 落地
    sha = hashlib.sha256(content).hexdigest()
    assert m.find_by_sha256(sha)["status"] == "unregistered_converted"


def test_upload_from_path_oversize_rejected(tmp_path, monkeypatch):
    """超过 MAX_UPLOAD_SIZE 时不一次性读入内存，返回 UploadError(413)"""
    from src.manifest import PaperManifest
    import src.upload_service as us
    m = PaperManifest(path=tmp_path / "m.json")
    raw = tmp_path / "raw"; raw.mkdir()
    src = tmp_path / "big.pdf"
    src.write_bytes(b"x" * 10)

    # 把 MAX_UPLOAD_SIZE 在 _stream_to_temp 内压到极小
    monkeypatch.setattr(us, "MAX_UPLOAD_SIZE", 4)
    try:
        upload_from_path(
            src_path=src, converter=MagicMock(), cleaner=MagicMock(),
            manifest=m, raw_dir=raw)
    except UploadError as e:
        assert e.status_code == 413
    else:
        raise AssertionError("expected UploadError 413")


def test_app_does_not_call_read_bytes():
    """app.py 不得出现 read_bytes（大文件内存尖峰）"""
    app_src = (Path(__file__).resolve().parent.parent / "app.py").read_text(encoding="utf-8")
    tree = ast.parse(app_src)
    body = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "upload_and_convert":
            body = ast.get_source_segment(app_src, node)
            break
    assert body is not None
    assert "read_bytes" not in body, "upload_and_convert 不得 read_bytes，改用 upload_from_path 流式"


def test_app_uses_upload_from_path():
    """app.py 必须用 upload_from_path"""
    app_src = (Path(__file__).resolve().parent.parent / "app.py").read_text(encoding="utf-8")
    assert "upload_from_path" in app_src
