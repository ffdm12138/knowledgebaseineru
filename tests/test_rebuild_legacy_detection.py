"""Phase 5 验收：rebuild_library legacy method/backend 检测。

find_legacy_output 返回 LegacyOutput（含 detected_method/detected_backend），
复用 legacy 输出时 cleaner.extract 收到与目录一致的 method。
"""
import tempfile
from pathlib import Path

import scripts.rebuild_library as rb
from scripts.rebuild_library import find_legacy_output, LegacyOutput


def _make_legacy(parsed_root: Path, stem: str, dirname: str, content: str = "# md"):
    d = parsed_root / stem / dirname
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{stem}.md").write_text(content, encoding="utf-8")


def test_hybrid_ocr_detected_as_ocr(tmp_path, monkeypatch):
    """hybrid_ocr -> detected_method=ocr, detected_backend=hybrid-engine"""
    monkeypatch.setattr(rb, "LEGACY_PARSED_DIR", tmp_path / "parsed")
    _make_legacy(tmp_path / "parsed", "paper", "hybrid_ocr")
    lo = find_legacy_output("paper")
    assert lo is not None
    assert isinstance(lo, LegacyOutput)
    assert lo.detected_method == "ocr"
    assert lo.detected_backend == "hybrid-engine"
    assert lo.method_dir == "hybrid_ocr"


def test_hybrid_auto_detected_as_auto(tmp_path, monkeypatch):
    monkeypatch.setattr(rb, "LEGACY_PARSED_DIR", tmp_path / "parsed")
    _make_legacy(tmp_path / "parsed", "paper", "hybrid_auto")
    lo = find_legacy_output("paper")
    assert lo.detected_method == "auto"
    assert lo.detected_backend == "hybrid-engine"


def test_hybrid_txt_detected_as_txt(tmp_path, monkeypatch):
    monkeypatch.setattr(rb, "LEGACY_PARSED_DIR", tmp_path / "parsed")
    _make_legacy(tmp_path / "parsed", "paper", "hybrid_txt")
    lo = find_legacy_output("paper")
    assert lo.detected_method == "txt"
    assert lo.detected_backend == "hybrid-engine"


def test_priority_hybrid_auto_over_ocr(tmp_path, monkeypatch):
    """多 method 目录并存时按固定优先级取 hybrid_auto，不靠 listdir 顺序"""
    monkeypatch.setattr(rb, "LEGACY_PARSED_DIR", tmp_path / "parsed")
    base = tmp_path / "parsed" / "paper"
    for d in ("hybrid_ocr", "hybrid_auto", "hybrid_txt"):
        dd = base / d
        dd.mkdir(parents=True)
        (dd / "paper.md").write_text(f"# {d}", encoding="utf-8")
    lo = find_legacy_output("paper")
    assert lo.method_dir == "hybrid_auto"


def test_reuse_legacy_passes_detected_method_to_cleaner(tmp_path, monkeypatch):
    """复用 legacy hybrid_ocr 时 cleaner.extract 收到 method=ocr（不是 auto）"""
    monkeypatch.setattr(rb, "LEGACY_PARSED_DIR", tmp_path / "parsed")
    _make_legacy(tmp_path / "parsed", "paper", "hybrid_ocr")

    # 隔离 manifest / cleaner
    from src.manifest import PaperManifest
    monkeypatch.setattr(rb, "manifest", PaperManifest(path=tmp_path / "m.json"))
    monkeypatch.setattr(rb, "PAPERS_DIR", tmp_path / "papers", raising=False)

    captured = {}

    class _FakeCleaner:
        def extract(self, source_dir, paper_id, overwrite=False,
                    method=None, stem=None, backend=None):
            captured["method"] = method
            captured["backend"] = backend
            return {"success": True, "paper_id": paper_id,
                    "markdown_path": str(tmp_path / "p.md"),
                    "images_dir": "", "images_count": 0, "char_count": 5}
    monkeypatch.setattr(rb, "cleaner", _FakeCleaner())

    # raw 文件
    raw = tmp_path / "raw"
    raw.mkdir()
    f = raw / "paper.pdf"
    f.write_bytes(b"%PDF-1.4 fake")

    # 不在 DUPLICATE_RAW_STEMS，且 manifest 无记录 → 走 legacy 复用
    monkeypatch.setattr(rb, "DUPLICATE_RAW_STEMS", set(), raising=False)
    monkeypatch.setattr(rb, "RAW_STEM_TO_PAPER_ID", {}, raising=False)

    ok = rb.process_one(f, reconvert_flag=False, backend="hybrid-engine",
                        method="auto", effort="medium", lang="ch", api_url=None)
    assert ok is True
    # cleaner 收到的是检测到的 ocr，不是命令行默认 auto
    assert captured["method"] == "ocr"
    assert captured["backend"] == "hybrid-engine"
    # manifest 写入 mineru_backend=hybrid-engine, method=ocr, runner=legacy
    entry = rb.manifest.list_all()[0]
    assert entry["mineru_backend"] == "hybrid-engine"
    assert entry["method"] == "ocr"
    assert entry["runner"] == "legacy"


def test_no_dead_code_reconvert_env_call():
    """reconvert 不再含 converter._get_env() 死代码"""
    import inspect
    src = inspect.getsource(rb.reconvert)
    assert "_get_env" not in src, "reconvert 不得残留 _get_env 死代码"
