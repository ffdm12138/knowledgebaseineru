"""结构收敛验收：manifest 字段 SSOT——backend=cli 不得出现，mineru_backend 必须是 MinerU 后端。

旧设计把 converter 返回的 runner(cli/api) 错误地写入 manifest.backend，与
config.MINERU_BACKEND(hybrid-engine) 语义冲突。收敛后：
  - manifest.mineru_backend : MinerU 解析后端（hybrid-engine 等），来自 config
  - manifest.runner         : 调用通道 cli/api，来自 converter 返回
  - manifest.backend        : 不再存在
"""
import json
import tempfile
from pathlib import Path
import pytest
from src.manifest import PaperManifest, VALID_STATUSES


def _new_manifest(td):
    return PaperManifest(path=Path(td) / "m.json")


def test_upsert_uses_mineru_backend_not_backend():
    """upsert 写入 mineru_backend，不再有 backend 字段。"""
    with tempfile.TemporaryDirectory() as td:
        m = _new_manifest(td)
        m.upsert("p1", raw_pdf="raw/x.pdf", markdown="md/x.md",
                 images_dir="md/images", sha256="a", file_size=1,
                 mtime="2026-01-01T00:00:00",
                 mineru_backend="hybrid-engine", effort="medium",
                 method="auto", runner="cli")
        entry = m.get("p1")
        assert entry["mineru_backend"] == "hybrid-engine"
        assert entry["runner"] == "cli"
        assert entry["effort"] == "medium"
        assert "backend" not in entry, "旧 backend 字段必须不存在"


def test_upsert_rejects_legacy_backend_kwarg():
    """upsert 不再接受 backend 关键字参数（SSOT 改名）。"""
    with tempfile.TemporaryDirectory() as td:
        m = _new_manifest(td)
        with pytest.raises(TypeError):
            m.upsert("p", raw_pdf="r", markdown="md", images_dir="i",
                     backend="cli", method="auto")


def test_mineru_backend_not_cli():
    """mineru_backend 不得是 cli/api（那是 runner 语义）。"""
    with tempfile.TemporaryDirectory() as td:
        m = _new_manifest(td)
        m.upsert("p1", raw_pdf="r", markdown="md", images_dir="i",
                 sha256="a", file_size=1, mtime="2026-01-01T00:00:00",
                 mineru_backend="hybrid-engine", runner="cli", method="auto")
        entry = m.get("p1")
        assert entry["mineru_backend"] != "cli"
        assert entry["mineru_backend"] != "api"
        assert entry["runner"] == "cli"


def test_upsert_rejects_invalid_status():
    """非法 status 必须拒绝（状态机词表）。"""
    with tempfile.TemporaryDirectory() as td:
        m = _new_manifest(td)
        with pytest.raises(ValueError, match="非法 status"):
            m.upsert("p", raw_pdf="r", markdown="md", images_dir="i",
                     status="bogus_status")


def test_valid_statuses_complete():
    """状态机词表覆盖完整。"""
    assert VALID_STATUSES == {"queued", "converting", "converted", "failed", "duplicate"}


def test_migrate_legacy_record():
    """旧记录（含 backend=cli、缺 mineru_backend）迁移到 SSOT 字段。"""
    with tempfile.TemporaryDirectory() as td:
        mp = Path(td) / "m.json"
        legacy = {
            "version": "0.1",
            "description": "...",
            "papers": [{
                "paper_id": "old_pid",
                "raw_pdf": "raw/old.pdf",
                "raw_filename": "old.pdf",
                "raw_stem": "old",
                "sha256": "deadbeef",
                "file_size": 100,
                "mtime": "2025-01-01T00:00:00",
                "markdown": "md/old.md",
                "images_dir": "md/images",
                "status": "converted",
                "backend": "cli",
                "method": "auto",
                "images_count": 0,
                "md_chars": 0,
                "converted_at": "2025-01-01T00:00:00",
            }],
        }
        mp.write_text(json.dumps(legacy, ensure_ascii=False), encoding="utf-8")
        m = PaperManifest(path=mp)
        n = m.migrate()
        assert n == 1
        entry = m.get("old_pid")
        assert "backend" not in entry
        assert entry["mineru_backend"] == "hybrid-engine"
        assert entry["effort"] == "medium"
        assert entry["runner"] == "cli"


def test_migrate_idempotent():
    """迁移幂等：已迁移记录再次 migrate 不重复计数。"""
    with tempfile.TemporaryDirectory() as td:
        m = _new_manifest(td)
        m.upsert("p", raw_pdf="r", markdown="md", images_dir="i",
                 sha256="a", file_size=1, mtime="2026-01-01T00:00:00",
                 mineru_backend="hybrid-engine", effort="medium",
                 method="auto", runner="cli")
        assert m.migrate() == 0
