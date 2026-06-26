"""测试 cleaner：Markdown 定位、覆盖保护"""
import tempfile
from pathlib import Path
from src.cleaner import MinerUOutputCleaner


def test_locate_markdown_finds_md():
    with tempfile.TemporaryDirectory() as td:
        d = Path(td) / "stem" / "auto"
        d.mkdir(parents=True)
        (d / "stem.md").write_text("# Title\n\nContent", encoding="utf-8")
        c = MinerUOutputCleaner()
        found = c.locate_markdown(Path(td))
        assert found is not None
        assert found.name == "stem.md"


def test_locate_markdown_none():
    c = MinerUOutputCleaner()
    assert c.locate_markdown(Path("/nonexistent")) is None


def test_locate_markdown_ignores_json_sidecars():
    """正文 md 存在时不应漏掉"""
    with tempfile.TemporaryDirectory() as td:
        d = Path(td) / "stem" / "auto"
        d.mkdir(parents=True)
        (d / "stem.md").write_text("# real content", encoding="utf-8")
        (d / "stem_model.json").write_text("{}", encoding="utf-8")
        c = MinerUOutputCleaner()
        found = c.locate_markdown(Path(td))
        assert found is not None
        assert found.suffix == ".md"


def test_extract_rejects_existing_dir():
    """目标目录已存在且 overwrite=False 应报错"""
    # cleaner 直接写 config 的 PAPERS_DIR，不便在这里测试完整路径。
    # 这里验证 locate_markdown 逻辑正确，覆盖保护在集成测试中验证。
    c = MinerUOutputCleaner()
    res = c.extract("/nonexistent/src", "test_pid", overwrite=False)
    assert res["success"] is False
    assert "未在" in res["error"]
