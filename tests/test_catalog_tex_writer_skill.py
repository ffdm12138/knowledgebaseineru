from pathlib import Path


def test_catalog_tex_writer_skill_files_exist():
    root = Path(__file__).resolve().parent.parent / "skills" / "catalog_tex_writer"
    for name in ["SKILL.md", "README.md", "CLAUDE.md", "article_plan_schema.json", "examples/mini_article_plan.json"]:
        assert (root / name).exists()


def test_catalog_tex_writer_skill_documents_boundaries():
    root = Path(__file__).resolve().parent.parent / "skills" / "catalog_tex_writer"
    text = (root / "SKILL.md").read_text(encoding="utf-8")

    assert "selected_catalog.json" in text
    assert "Do not read `data/papers` directly" in text
    assert "metadata" in text
    assert "write/jobs/<job_id>/tex/" in text
