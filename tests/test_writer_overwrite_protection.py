import json

import pytest

from src.writer.deep_reader import deep_read
from src.writer.job_manager import JobManager
from src.writer.story_builder import build_story


class FakeLibrary:
    def exists(self, pid):
        return True

    def list_images(self, pid):
        return []

    def read_multiple(self, paper_ids, max_chars_each=0):
        return {pid: "full text" for pid in paper_ids}


class FakeCatalog:
    def list_papers(self):
        return [{"paper_id": "2024_wang_测试论文", "metadata": {"citation_key": "wang2024"}}]


def _job(tmp_path):
    jm = JobManager(write_dir=tmp_path / "write")
    info = jm.create(topic="测试任务")
    jdir = jm.job_dir(info["job_id"])
    (jdir / "planning" / "selected_papers.json").write_text(json.dumps({
        "selected_papers": [{"paper_id": "2024_wang_测试论文"}],
        "selection_status": "confirmed",
    }, ensure_ascii=False), encoding="utf-8")
    jm.set_step(info["job_id"], "catalog_selection_confirmed", True)
    return jm, info["job_id"], jdir


def test_deep_read_refuses_user_filled_note(tmp_path):
    jm, job_id, jdir = _job(tmp_path)
    note = jdir / "reading" / "paper_notes" / "2024_wang_测试论文.md"
    note.write_text("# Note\n\nThis is carefully filled human content with enough substance.", encoding="utf-8")

    with pytest.raises(RuntimeError, match="refuse to overwrite"):
        deep_read(job_id, jm=jm, library=FakeLibrary(), catalog=FakeCatalog(), from_papers=True)

    assert "human content" in note.read_text(encoding="utf-8")


def test_deep_read_force_creates_backup(tmp_path):
    jm, job_id, jdir = _job(tmp_path)
    note = jdir / "reading" / "paper_notes" / "2024_wang_测试论文.md"
    note.write_text("# Note\n\nThis is carefully filled human content with enough substance.", encoding="utf-8")

    result = deep_read(job_id, force=True, jm=jm, library=FakeLibrary(), catalog=FakeCatalog(), from_papers=True)

    assert result["writes"][0]["backup"]
    assert any((jdir / "reading" / "paper_notes").glob("*.bak_*"))


def test_story_refuses_when_marked_filled(tmp_path):
    jm, job_id, jdir = _job(tmp_path)
    jm.set_step(job_id, "deep_read_notes_filled", True)
    jm.set_step(job_id, "story_plan_filled", True)
    story = jdir / "planning" / "story_plan.md"
    story.write_text("# Story\n\nHuman-written story plan with real content.", encoding="utf-8")

    with pytest.raises(RuntimeError, match="already marked filled"):
        build_story(job_id, jm=jm, catalog=FakeCatalog())


def test_story_refreshes_empty_template(tmp_path):
    jm, job_id, jdir = _job(tmp_path)
    jm.set_step(job_id, "deep_read_notes_filled", True)
    story = jdir / "planning" / "story_plan.md"
    story.write_text("> STATUS: TEMPLATE_ONLY\n\n（待填）", encoding="utf-8")

    result = build_story(job_id, jm=jm, catalog=FakeCatalog())

    assert result["writes"][0]["action"] == "refreshed_template"
