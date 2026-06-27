"""领域 catalog 视图层：跨领域重复索引合法、物理重复非法。"""
import json
from pathlib import Path

from scripts.migrate_to_domain_library import apply_domain_library, build_domain_library
from scripts.validate_domain_library import validate_domain_library


def _paper(pid: str, bib_key: str, primary: str, domains: list[str]) -> dict:
    return {
        "paper_id": pid,
        "title": pid,
        "authors": ["A"],
        "year": 2020,
        "venue": "J",
        "doi": "",
        "raw_pdf": f"data/raw/{pid}.pdf",
        "markdown": f"data/papers/{pid}/paper.md",
        "images_dir": f"data/papers/{pid}/images",
        "status": "summarized",
        "primary_domain": primary,
        "domains": domains,
        "ai_summary": {
            "one_sentence": "x", "background_problem": "", "research_question": "",
            "method": "", "data_or_experiment": "", "main_findings": "",
            "key_equations_or_models": [], "important_figures": [],
            "limitations": "", "relevance_to_my_work": "", "possible_use_in_paper": "",
        },
        "tags": {"topic": [], "method": [], "material_or_region": [], "variables": [], "model_names": []},
        "selection_hints": {"read_when_question_contains": [], "do_not_use_for": [], "priority": 3},
        "notes": "",
        "citation": {
            "bib_key": bib_key,
            "bibtex": f"@article{{{bib_key}, title={{T}}, author={{A}}, year={{2020}}}}",
            "citation_style_name": "A (2020)", "source": "manual", "verified": False,
        },
    }


def _build(tmp_path: Path, papers: list[dict]):
    catalog = {"version": "0.1", "description": "", "papers": papers}
    manifest = {"version": "0.1", "papers": []}
    updated, index, dcats, dbibs, gbib = build_domain_library(catalog, manifest)
    catalog_path = tmp_path / "catalog" / "literature_catalog.json"
    index_path = tmp_path / "catalog" / "library_index.json"
    domain_dir = tmp_path / "catalog" / "domains"
    manifest_path = tmp_path / "manifests" / "papers_manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    apply_domain_library(updated, index, dcats, dbibs, gbib,
                         catalog_path=catalog_path, index_path=index_path, domain_dir=domain_dir)
    return catalog_path, index_path, domain_dir, manifest_path


def test_cross_domain_repeat_is_legal(tmp_path):
    """同一 paper 出现在两个 domain catalog 合法。"""
    papers = [_paper("2026_viaro_test", "viaro2020", "blowing_snow_physics",
                     ["blowing_snow_physics", "abl_pbl"])]
    cp, ip, dd, mp = _build(tmp_path, papers)
    errors, warnings = validate_domain_library(
        catalog_path=cp, index_path=ip, domain_dir=dd, manifest_path=mp, check_paths=False)
    assert errors == []
    # 两个领域 catalog 都收录
    blowing = json.loads((dd / "blowing_snow_physics" / "literature_catalog.json").read_text(encoding="utf-8"))
    abl = json.loads((dd / "abl_pbl" / "literature_catalog.json").read_text(encoding="utf-8"))
    assert len(blowing["papers"]) == 1
    assert len(abl["papers"]) == 1
    # secondary domain 条目 is_primary_domain=False
    assert abl["papers"][0]["domain_view"]["is_primary_domain"] is False
    assert abl["papers"][0]["domain_view"]["canonical_paper_id"] == "2026_viaro_test"


def test_same_domain_internal_duplicate_is_illegal(tmp_path):
    """同一领域 catalog 内部重复 paper_id 非法。"""
    papers = [_paper("2026_viaro_test", "viaro2020", "blowing_snow_physics", ["blowing_snow_physics"])]
    cp, ip, dd, mp = _build(tmp_path, papers)
    # 手动注入重复条目
    cat_path = dd / "blowing_snow_physics" / "literature_catalog.json"
    data = json.loads(cat_path.read_text(encoding="utf-8"))
    data["papers"].append(dict(data["papers"][0]))
    cat_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    errors, _ = validate_domain_library(
        catalog_path=cp, index_path=ip, domain_dir=dd, manifest_path=mp, check_paths=False)
    assert any("duplicate paper_id" in e for e in errors)


def test_domain_view_mismatch_is_illegal(tmp_path):
    """domain_view.domain_id 与所在文件夹不一致非法。"""
    papers = [_paper("2026_viaro_test", "viaro2020", "blowing_snow_physics", ["blowing_snow_physics"])]
    cp, ip, dd, mp = _build(tmp_path, papers)
    cat_path = dd / "blowing_snow_physics" / "literature_catalog.json"
    data = json.loads(cat_path.read_text(encoding="utf-8"))
    data["papers"][0]["domain_view"]["domain_id"] = "abl_pbl"
    cat_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    errors, _ = validate_domain_library(
        catalog_path=cp, index_path=ip, domain_dir=dd, manifest_path=mp, check_paths=False)
    assert any("domain_view.domain_id" in e for e in errors)


def test_physical_doi_duplicate_is_illegal(tmp_path):
    """library_index / 全局 catalog 中同一 DOI 对应多个 paper_id 非法。"""
    papers = [
        _paper("2026_a_test", "a2020", "blowing_snow_physics", ["blowing_snow_physics"]),
        _paper("2026_b_test", "b2020", "aeolian_snow_transport", ["aeolian_snow_transport"]),
    ]
    papers[0]["doi"] = "10.1/x"
    papers[1]["doi"] = "10.1/x"
    cp, ip, dd, mp = _build(tmp_path, papers)
    errors, _ = validate_domain_library(
        catalog_path=cp, index_path=ip, domain_dir=dd, manifest_path=mp, check_paths=False)
    assert any("maps to multiple paper_ids" in e for e in errors)
