import json
import subprocess
import tempfile
from pathlib import Path

from scripts.migrate_to_domain_library import (
    apply_domain_library,
    build_domain_library,
)
from scripts.validate_domain_library import validate_domain_library
from scripts import pack_repo


def _paper(pid: str, bib_key: str, primary: str = "") -> dict:
    domains = [primary] if primary else []
    return {
        "paper_id": pid,
        "title": "Test Paper",
        "authors": ["A"],
        "year": 2020,
        "venue": "Journal",
        "doi": "",
        "raw_pdf": "data/raw/test.pdf",
        "markdown": f"data/papers/{pid}/paper.md",
        "images_dir": f"data/papers/{pid}/images",
        "status": "summarized",
        "primary_domain": primary,
        "domains": domains,
        "ai_summary": {
            "one_sentence": "One.",
            "background_problem": "",
            "research_question": "",
            "method": "",
            "data_or_experiment": "",
            "main_findings": "",
            "key_equations_or_models": [],
            "important_figures": [],
            "limitations": "",
            "relevance_to_my_work": "",
            "possible_use_in_paper": "",
        },
        "tags": {
            "topic": [],
            "method": [],
            "material_or_region": [],
            "variables": [],
            "model_names": [],
        },
        "selection_hints": {
            "read_when_question_contains": [],
            "do_not_use_for": [],
            "priority": 3,
        },
        "notes": "",
        "citation": {
            "bib_key": bib_key,
            "bibtex": f"@article{{{bib_key}, title={{Test}}, author={{A}}, year={{2020}}}}",
            "citation_style_name": "A (2020)",
            "source": "manual",
            "verified": False,
        },
    }


def test_build_domain_library_all_domains_membership():
    """领域 catalog 收录所有 domains 声明该领域的文献（跨领域重复索引）。"""
    catalog = {
        "version": "0.1",
        "description": "",
        "papers": [
            _paper("2000_sugiura_test", "sugiura2020_test"),
            _paper("2026_viaro_test", "viaro2020_test"),
        ],
    }
    manifest = {"papers": []}
    updated, index, domain_catalogs, domain_bibs, global_bib = build_domain_library(catalog, manifest)

    sugiura = next(p for p in updated["papers"] if p["paper_id"].startswith("2000_sugiura"))
    assert sugiura["primary_domain"] == "aeolian_snow_transport"
    assert sugiura["domains"] == ["aeolian_snow_transport", "blowing_snow_physics"]
    # sugiura 同时出现在两个领域 catalog（跨领域重复索引合法）
    aeolian_ids = {p["paper_id"] for p in domain_catalogs["aeolian_snow_transport"]["papers"]}
    blowing_ids = {p["paper_id"] for p in domain_catalogs["blowing_snow_physics"]["papers"]}
    assert aeolian_ids == {"2000_sugiura_test"}
    assert "2000_sugiura_test" in blowing_ids  # secondary domain
    assert "2026_viaro_test" in blowing_ids    # primary domain
    # domain_view 字段：is_primary_domain 正确
    sugiura_in_blowing = next(p for p in domain_catalogs["blowing_snow_physics"]["papers"]
                              if p["paper_id"] == "2000_sugiura_test")
    assert sugiura_in_blowing["domain_view"]["domain_id"] == "blowing_snow_physics"
    assert sugiura_in_blowing["domain_view"]["is_primary_domain"] is False
    assert sugiura_in_blowing["domain_view"]["canonical_paper_id"] == "2000_sugiura_test"
    assert "sugiura2020_test" in domain_bibs["aeolian_snow_transport"]
    assert "sugiura2020_test" in domain_bibs["blowing_snow_physics"]  # 跨领域 bib 重复合法
    assert "viaro2020_test" in global_bib
    assert index["papers"][0]["markdown_path"].startswith("data/papers/")


def test_apply_and_validate_domain_library_without_paper_files():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        catalog = {
            "version": "0.1",
            "description": "",
            "papers": [_paper("1999_shao_test", "shao2020_test")],
        }
        manifest = {"version": "0.1", "papers": []}
        updated, index, domain_catalogs, domain_bibs, global_bib = build_domain_library(catalog, manifest)
        catalog_path = root / "catalog" / "literature_catalog.json"
        index_path = root / "catalog" / "library_index.json"
        domain_dir = root / "catalog" / "domains"
        manifest_path = root / "manifests" / "papers_manifest.json"
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        apply_domain_library(
            updated,
            index,
            domain_catalogs,
            domain_bibs,
            global_bib,
            catalog_path=catalog_path,
            index_path=index_path,
            domain_dir=domain_dir,
        )

        errors, warnings = validate_domain_library(
            catalog_path=catalog_path,
            index_path=index_path,
            domain_dir=domain_dir,
            manifest_path=manifest_path,
            check_paths=False,
        )
        assert errors == []
        # 缺失物理文件只产生 warning，不报错（快照友好）
        assert any("markdown_path not found" in w for w in warnings)
        assert (domain_dir / "aeolian_snow_transport" / "literature_catalog.json").exists()
        assert (domain_dir / "aeolian_snow_transport" / "references.bib").exists()


def test_migration_dry_run_builds_data_without_writing():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        catalog = {"version": "0.1", "description": "", "papers": [_paper("1999_shao_test", "k")]}
        manifest = {"version": "0.1", "papers": []}
        build_domain_library(catalog, manifest)
        assert not (root / "catalog" / "library_index.json").exists()


def test_pack_repo_file_list_includes_new_untracked_files():
    files = set(pack_repo.git_tracked_files())
    assert "src/library_index.py" in files
    assert "scripts/migrate_to_domain_library.py" in files


def test_pack_repo_fallback_scans_filesystem_and_excludes_noise(monkeypatch, tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "scripts").mkdir()
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / ".pytest_cache").mkdir()
    (tmp_path / ".git").mkdir()
    (tmp_path / "src" / "library_index.py").write_text("# ok", encoding="utf-8")
    (tmp_path / "scripts" / "migrate_to_domain_library.py").write_text("# ok", encoding="utf-8")
    (tmp_path / "__pycache__" / "x.pyc").write_bytes(b"x")
    (tmp_path / ".pytest_cache" / "x").write_text("x", encoding="utf-8")
    (tmp_path / ".git" / "HEAD").write_text("x", encoding="utf-8")
    (tmp_path / "temp.tmp").write_text("x", encoding="utf-8")
    (tmp_path / "file.lock").write_text("x", encoding="utf-8")
    (tmp_path / "mineru_snapshot.zip").write_bytes(b"x")

    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(args[0], 1, "", "no git")

    monkeypatch.setattr(pack_repo, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(pack_repo.subprocess, "run", fake_run)

    files = set(pack_repo.git_tracked_files())
    assert "src/library_index.py" in files
    assert "scripts/migrate_to_domain_library.py" in files
    assert "__pycache__/x.pyc" not in files
    assert ".pytest_cache/x" not in files
    assert ".git/HEAD" not in files
    assert "temp.tmp" not in files
    assert "file.lock" not in files
    assert "mineru_snapshot.zip" not in files
