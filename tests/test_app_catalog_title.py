"""app.list_papers 标题读取测试：catalog v2 content-only 条目无 metadata 字段，
标题必须从 content_identity.content_title 读取。不访问网络。"""
import app


class FakeCatalog:
    def __init__(self, papers):
        self._papers = papers

    def list_papers(self):
        return list(self._papers)


def test_list_papers_reads_content_title(monkeypatch):
    """content-only 条目（无 metadata 字段）能从 content_identity.content_title 取到标题。"""
    monkeypatch.setattr(app, "catalog", FakeCatalog([{
        "paper_number": "0000000000000001",
        "paper_id": "2024_wang_测试",
        "content_identity": {"content_title": "内容标题示例"},
    }]))
    out = app.list_papers()
    assert "内容标题示例" in out
    assert "0000000000000001" in out
    assert "2024_wang_测试" in out


def test_list_papers_does_not_assume_metadata_field(monkeypatch):
    """条目不含 metadata 字段时不报错，标题仍来自 content_identity。"""
    monkeypatch.setattr(app, "catalog", FakeCatalog([{
        "paper_number": "0000000000000002",
        "paper_id": "2024_li_另一篇",
        "content_identity": {"content_title": "另一篇标题"},
    }]))
    out = app.list_papers()
    assert "另一篇标题" in out


def test_list_papers_empty_catalog(monkeypatch):
    monkeypatch.setattr(app, "catalog", FakeCatalog([]))
    out = app.list_papers()
    assert "为空" in out
