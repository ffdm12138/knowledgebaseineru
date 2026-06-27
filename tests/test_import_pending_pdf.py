"""import_pending_pdf 入库闭环测试（mock MinerU，不真实转换）。"""
import json
from pathlib import Path

from src.catalog import Catalog
from src.library_index import LibraryIndex
from src.manifest import PaperManifest
from scripts.import_pending_pdf import import_pending_pdf


class FakeConverter:
    def __init__(self):
        self.calls = 0

    def convert(self, input_path, output_dir, backend="", method="", lang="", effort="", api_url=None):
        self.calls += 1
        return {
            "success": True, "output_dir": str(output_dir), "markdown": "x",
            "md_path": str(Path(output_dir) / "x.md"), "source_file": str(input_path),
            "backend": backend, "method": method, "effort": effort, "runner": "cli", "error": "",
        }


class FakeCleaner:
    def __init__(self):
        self.calls = 0

    def extract(self, source_dir, paper_id, overwrite=False, method=None, stem=None, backend=None):
        self.calls += 1
        return {
            "success": True, "paper_id": paper_id,
            "markdown_path": f"data/papers/{paper_id}/paper.md",
            "images_dir": f"data/papers/{paper_id}/images",
            "images_count": 0, "char_count": 100, "error": "",
        }


def _setup_env(tmp_path: Path):
    root = tmp_path
    catalog_path = root / "catalog" / "literature_catalog.json"
    catalog_path.parent.mkdir(parents=True, exist_ok=True)
    catalog_path.write_text(json.dumps({"version": "0.1", "description": "", "papers": []}), encoding="utf-8")
    index_path = root / "catalog" / "library_index.json"
    manifest_path = root / "manifests" / "papers_manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps({"version": "0.1", "papers": []}), encoding="utf-8")
    domain_dir = root / "catalog" / "domains"
    raw_dir = root / "raw"
    tmp_dir = root / "tmp_mineru"
    return catalog_path, index_path, manifest_path, domain_dir, raw_dir, tmp_dir


def _make_pending(raw_dir: Path, domain: str, slug: str, doi: str, title: str, year: int):
    pending_dir = raw_dir / domain / "pending"
    pending_dir.mkdir(parents=True, exist_ok=True)
    pdf = pending_dir / f"{slug}.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")
    sidecar = pdf.with_suffix(".json")
    sidecar.write_text(json.dumps({"doi": doi, "title": title, "year": year, "status": "pending"}),
                       encoding="utf-8")
    return pdf


def test_dry_run_writes_nothing(tmp_path):
    cp, ip, mp, dd, rd, td = _setup_env(tmp_path)
    pdf = _make_pending(rd, "blowing_snow_physics", "10_1_test", "10.1/test", "Test Snow Paper", 2025)
    conv, cln = FakeConverter(), FakeCleaner()
    result = import_pending_pdf(
        pdf, domain="blowing_snow_physics", domains=["blowing_snow_physics", "aeolian_snow_transport"],
        title="Test Snow Paper", doi="10.1/test", year=2025, apply=False,
        converter=conv, cleaner=cln, manifest=PaperManifest(mp),
        catalog_path=cp, index_path=ip, manifest_path=mp, domain_dir=dd, raw_dir=rd, tmp_dir=td)
    assert result["applied"] is False
    assert conv.calls == 0
    assert cln.calls == 0
    # catalog 仍空，raw 未复制正式件
    assert json.loads(cp.read_text(encoding="utf-8"))["papers"] == []
    assert not (rd / "2025_test_snow_paper.pdf").exists()


def test_new_pdf_import_creates_all_records(tmp_path):
    cp, ip, mp, dd, rd, td = _setup_env(tmp_path)
    pdf = _make_pending(rd, "blowing_snow_physics", "10_1_test", "10.1/test", "Test Snow Paper", 2025)
    conv, cln = FakeConverter(), FakeCleaner()
    result = import_pending_pdf(
        pdf, domain="blowing_snow_physics", domains=["blowing_snow_physics", "aeolian_snow_transport"],
        title="Test Snow Paper", doi="10.1/test", year=2025, apply=True,
        converter=conv, cleaner=cln, manifest=PaperManifest(mp),
        catalog_path=cp, index_path=ip, manifest_path=mp, domain_dir=dd, raw_dir=rd, tmp_dir=td)
    assert result["status"] == "imported"
    assert result["applied"] is True
    pid = result["paper_id"]
    assert conv.calls == 1 and cln.calls == 1
    # manifest 有 converted 记录
    mfst = PaperManifest(mp)
    assert mfst.get(pid)["status"] == "converted"
    # library_index 有 canonical 记录
    idx = LibraryIndex(ip)
    entry = idx.get(pid)
    assert entry is not None
    assert set(entry["domains"]) == {"blowing_snow_physics", "aeolian_snow_transport"}
    # 全局 catalog placeholder status=unsummarized（不自动生成 AI summary）
    cat = Catalog(cp)
    paper = next(p for p in cat.list_papers() if p["paper_id"] == pid)
    assert paper["status"] == "unsummarized"
    # 两个领域 catalog 都有条目（跨领域重复索引）
    blowing = json.loads((dd / "blowing_snow_physics" / "literature_catalog.json").read_text(encoding="utf-8"))
    aeolian = json.loads((dd / "aeolian_snow_transport" / "literature_catalog.json").read_text(encoding="utf-8"))
    assert any(p["paper_id"] == pid for p in blowing["papers"])
    assert any(p["paper_id"] == pid for p in aeolian["papers"])
    # sidecar 状态更新为 imported
    sidecar = json.loads(pdf.with_suffix(".json").read_text(encoding="utf-8"))
    assert sidecar["status"] == "imported"
    assert sidecar["canonical_paper_id"] == pid


def test_duplicate_doi_updates_domains_only(tmp_path):
    cp, ip, mp, dd, rd, td = _setup_env(tmp_path)
    # 预置一篇已入库文献
    cat = Catalog(cp)
    cat.upsert({
        "paper_id": "2020_existing", "title": "Existing", "authors": [], "year": 2020,
        "venue": "", "doi": "10.1/test", "raw_pdf": "", "markdown": "", "images_dir": "",
        "status": "summarized", "primary_domain": "blowing_snow_physics",
        "domains": ["blowing_snow_physics"],
        "ai_summary": {k: "" for k in ["one_sentence", "background_problem", "research_question",
                                       "method", "data_or_experiment", "main_findings", "limitations",
                                       "relevance_to_my_work", "possible_use_in_paper"]} | {"key_equations_or_models": [], "important_figures": []},
        "tags": {"topic": [], "method": [], "material_or_region": [], "variables": [], "model_names": []},
        "selection_hints": {"read_when_question_contains": [], "do_not_use_for": [], "priority": 3},
        "notes": "", "citation": {"bib_key": "existing2020", "bibtex": "@article{existing2020, title={E}, year={2020}}",
                                  "citation_style_name": "(2020)", "source": "manual", "verified": False},
    })
    mfst = PaperManifest(mp)
    mfst.upsert("2020_existing", raw_pdf="x.pdf", markdown="m", images_dir="i", status="converted",
                sha256="oldsha", mineru_backend="hybrid-engine", method="auto", effort="medium", runner="cli")
    # 重建领域视图使 library_index 与 catalog 一致
    from scripts.migrate_to_domain_library import build_domain_library, apply_domain_library
    catalog_data = json.loads(cp.read_text(encoding="utf-8"))
    manifest_data = json.loads(mp.read_text(encoding="utf-8"))
    updated, index, dcats, dbibs, gbib = build_domain_library(catalog_data, manifest_data)
    apply_domain_library(updated, index, dcats, dbibs, gbib,
                         catalog_path=cp, index_path=ip, domain_dir=dd)

    pdf = _make_pending(rd, "blowing_snow_physics", "10_1_test", "10.1/test", "Existing", 2020)
    conv, cln = FakeConverter(), FakeCleaner()
    result = import_pending_pdf(
        pdf, domain="aeolian_snow_transport", domains=["aeolian_snow_transport"],
        title="Existing", doi="10.1/test", year=2020, apply=True,
        converter=conv, cleaner=cln, manifest=PaperManifest(mp),
        catalog_path=cp, index_path=ip, manifest_path=mp, domain_dir=dd, raw_dir=rd, tmp_dir=td)
    assert result["status"] == "duplicate"
    assert result["canonical_paper_id"] == "2020_existing"
    assert conv.calls == 0  # 不重新转换
    # domains membership 更新为包含 aeolian
    cat2 = Catalog(cp)
    paper = next(p for p in cat2.list_papers() if p["paper_id"] == "2020_existing")
    assert "aeolian_snow_transport" in paper["domains"]
    sidecar = json.loads(pdf.with_suffix(".json").read_text(encoding="utf-8"))
    assert sidecar["status"] == "duplicate"


def test_paper_stored_once_across_domains(tmp_path):
    """多 domains 入库后 paper 只存一份，但两个 domain catalog 都有 entry。"""
    cp, ip, mp, dd, rd, td = _setup_env(tmp_path)
    pdf = _make_pending(rd, "blowing_snow_physics", "10_1_multi", "10.1/multi", "Multi Domain Paper", 2024)
    conv, cln = FakeConverter(), FakeCleaner()
    result = import_pending_pdf(
        pdf, domain="blowing_snow_physics", domains=["blowing_snow_physics", "abl_pbl"],
        title="Multi Domain Paper", doi="10.1/multi", year=2024, apply=True,
        converter=conv, cleaner=cln, manifest=PaperManifest(mp),
        catalog_path=cp, index_path=ip, manifest_path=mp, domain_dir=dd, raw_dir=rd, tmp_dir=td)
    pid = result["paper_id"]
    # library_index 只有一条
    idx = LibraryIndex(ip)
    assert sum(1 for e in idx.list_all() if e["paper_id"] == pid) == 1
    # manifest 只有一条
    mfst = PaperManifest(mp)
    assert sum(1 for e in mfst.list_all() if e.get("paper_id") == pid) == 1
    # 两个 domain catalog 都有
    for d in ["blowing_snow_physics", "abl_pbl"]:
        dcat = json.loads((dd / d / "literature_catalog.json").read_text(encoding="utf-8"))
        assert any(p["paper_id"] == pid for p in dcat["papers"])
