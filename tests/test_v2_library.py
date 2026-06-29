import json
from pathlib import Path

import pytest

from src.services.v2_library import (
    AllCatalogBuilder,
    LlmWorkService,
    PaperCurationService,
    PaperNumberLedger,
    PaperRawAllocator,
    PaperRawConverter,
    V2PaperCommitService,
    empty_catalog,
    empty_metadata,
    migrate_catalog_to_v2_0,
    validate_catalog_schema,
)


def _curated_raw(root: Path, pid: str = "2024_wang_测试论文") -> Path:
    folder = root / "paper_raw" / pid
    folder.mkdir(parents=True)
    metadata = empty_metadata(pid)
    metadata["title"]["original"] = "Test Paper"
    metadata["title"]["translated_zh"] = "测试论文"
    metadata["year"] = 2024
    metadata["authors"] = [{"full_name": "Wang A", "family": "Wang", "given": "A", "orcid": "", "affiliation": ""}]
    metadata["container"]["journal"] = "Test Journal"
    metadata["identifiers"]["doi"] = "10.1/test"
    metadata["metadata_match"] = {
        "status": "matched",
        "source": "test",
        "confidence": 1.0,
        "matched_at": "2026-01-01T00:00:00",
        "warnings": [],
        "candidates": [],
    }
    catalog = empty_catalog()
    catalog["content_identity"]["content_title"] = "Test Paper"
    catalog["classification"].update({
        "primary_domain": "blowing_snow_physics",
        "secondary_domains": ["blowing_snow_physics"],
        "topic_tags": ["blowing_snow"],
    })
    catalog["research_card"]["research_problem"] = "测试论文摘要"
    catalog["content_notes"]["short_summary"] = "测试论文摘要"
    (folder / f"{pid}.metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    (folder / f"{pid}.catalog.json").write_text(json.dumps(catalog), encoding="utf-8")
    (folder / f"{pid}.md").write_text("# Test Paper", encoding="utf-8")
    (folder / f"{pid}.pdf").write_bytes(b"%PDF")
    (folder / "images").mkdir()
    return folder


def test_paper_raw_allocator_uses_monotonic_six_digit_ids(tmp_path):
    raw = tmp_path / "data" / "raw"
    raw.mkdir(parents=True)
    pdf = raw / "a.pdf"
    pdf.write_bytes(b"%PDF")
    paper_raw = tmp_path / "data" / "paper_raw"
    (paper_raw / "000003").mkdir(parents=True)

    result = PaperRawAllocator(paper_raw).allocate_from_pdf(pdf)

    assert result["source_id"] == "000004"
    assert (paper_raw / "000004" / "000004.pdf").exists()
    metadata = json.loads((paper_raw / "000004" / "000004.metadata.json").read_text(encoding="utf-8"))
    assert metadata["pdf"]["sha256"]


def test_v2_commit_assigns_number_and_builds_all_catalog(tmp_path):
    raw_folder = _curated_raw(tmp_path)
    papers = tmp_path / "papers"
    all_catalog = tmp_path / "catalog" / "all.catalog.json"
    ledger = tmp_path / "catalog" / "paper_number_ledger.json"

    result = V2PaperCommitService(
        papers_dir=papers,
        all_catalog_path=all_catalog,
        ledger_path=ledger,
    ).commit_paper_raw(raw_folder)

    pid = "2024_wang_测试论文"
    assert result["status"] == "imported"
    assert result["paper_number"] == "0000000000000001"
    assert (papers / pid / f"{pid}.pdf").exists()
    assert (papers / pid / f"{pid}.md").exists()
    assert (papers / pid / "0000000000000001.paper.number").exists()
    data = json.loads(all_catalog.read_text(encoding="utf-8"))
    assert data["papers"][0]["paper_id"] == pid
    assert data["papers"][0]["paper_number"] == "0000000000000001"
    assert not raw_folder.exists()


def test_all_catalog_rebuild_drops_deleted_folders_without_reusing_number(tmp_path):
    raw_folder = _curated_raw(tmp_path)
    papers = tmp_path / "papers"
    all_catalog = tmp_path / "catalog" / "all.catalog.json"
    ledger = tmp_path / "catalog" / "paper_number_ledger.json"
    svc = V2PaperCommitService(papers_dir=papers, all_catalog_path=all_catalog, ledger_path=ledger)
    svc.commit_paper_raw(raw_folder)
    for child in papers.iterdir():
        if child.is_dir():
            import shutil
            shutil.rmtree(child)

    rebuilt = AllCatalogBuilder(papers, all_catalog, PaperNumberLedger(ledger)).build(write=True)

    assert rebuilt["papers"] == []
    ledger_data = json.loads(ledger.read_text(encoding="utf-8"))
    assert ledger_data["max_number"] == "0000000000000001"


def test_llm_work_copy_by_paper_number(tmp_path):
    raw_folder = _curated_raw(tmp_path)
    papers = tmp_path / "papers"
    all_catalog = tmp_path / "catalog" / "all.catalog.json"
    ledger = tmp_path / "catalog" / "paper_number_ledger.json"
    V2PaperCommitService(papers_dir=papers, all_catalog_path=all_catalog, ledger_path=ledger).commit_paper_raw(raw_folder)

    result = LlmWorkService(all_catalog_path=all_catalog, llm_work_dir=tmp_path / "llm_work").copy_to_session(
        "0000000000000001",
        "session_1",
    )

    assert result["paper_id"] == "2024_wang_测试论文"
    assert (tmp_path / "llm_work" / "session_1" / "0000000000000001" / "2024_wang_测试论文.md").exists()


def test_v2_commit_quarantines_duplicate_doi(tmp_path):
    first = _curated_raw(tmp_path, "2024_wang_测试论文")
    papers = tmp_path / "papers"
    all_catalog = tmp_path / "catalog" / "all.catalog.json"
    ledger = tmp_path / "catalog" / "paper_number_ledger.json"
    svc = V2PaperCommitService(papers_dir=papers, all_catalog_path=all_catalog, ledger_path=ledger)
    svc.commit_paper_raw(first)
    second = _curated_raw(tmp_path, "2024_li_重复论文")
    meta_path = second / "2024_li_重复论文.metadata.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["identifiers"]["doi"] = "10.1/test"
    meta_path.write_text(json.dumps(meta), encoding="utf-8")

    result = svc.commit_paper_raw(second)

    assert result["status"] == "possible_duplicate"
    assert Path(result["quarantine_dir"]).exists()
    assert not (papers / "2024_li_重复论文").exists()


def test_ledgers_reports_marker_conflict(tmp_path):
    folder = tmp_path / "papers" / "pid"
    folder.mkdir(parents=True)
    (folder / "0000000000000002.paper.number").write_text("{}", encoding="utf-8")
    ledger = PaperNumberLedger(tmp_path / "catalog" / "paper_number_ledger.json")
    ledger.save({
        "schema_version": "1.0",
        "max_number": "0000000000000001",
        "items": {
            "0000000000000001": {
                "folder_name": "pid",
                "folder_path": str(folder),
                "created_at": "",
            }
        },
    })

    errors, _ = ledger.validate(tmp_path / "papers")

    assert any("conflict" in err for err in errors)


def test_v2_commit_blocks_unmatched_metadata(tmp_path):
    raw_folder = _curated_raw(tmp_path, "2024_wang_未匹配论文")
    meta_path = raw_folder / "2024_wang_未匹配论文.metadata.json"
    metadata = json.loads(meta_path.read_text(encoding="utf-8"))
    metadata["metadata_match"]["status"] = "unmatched"
    meta_path.write_text(json.dumps(metadata), encoding="utf-8")

    result = V2PaperCommitService(
        papers_dir=tmp_path / "papers",
        all_catalog_path=tmp_path / "catalog" / "all.catalog.json",
        ledger_path=tmp_path / "catalog" / "paper_number_ledger.json",
    ).commit_paper_raw(raw_folder)

    assert result["status"] == "metadata_unmatched"
    assert not (tmp_path / "papers" / "2024_wang_未匹配论文").exists()
    assert (raw_folder / ".import_status.json").exists()


def test_pdf_metadata_without_doi_cannot_commit(tmp_path):
    raw_folder = _curated_raw(tmp_path, "2024_wang_无doi论文")
    meta_path = raw_folder / "2024_wang_无doi论文.metadata.json"
    metadata = json.loads(meta_path.read_text(encoding="utf-8"))
    metadata["identifiers"]["doi"] = ""
    meta_path.write_text(json.dumps(metadata), encoding="utf-8")
    papers = tmp_path / "papers"
    all_catalog = tmp_path / "catalog" / "all.catalog.json"
    ledger = tmp_path / "catalog" / "paper_number_ledger.json"

    result = V2PaperCommitService(
        papers_dir=papers,
        all_catalog_path=all_catalog,
        ledger_path=ledger,
    ).commit_paper_raw(raw_folder)

    assert result == {
        "success": False,
        "status": "metadata_incomplete",
        "errors": ["metadata.identifiers.doi is required for formal commit"],
    }
    assert not (papers / "2024_wang_无doi论文").exists()
    assert not ledger.exists()
    assert not all_catalog.exists()
    assert (raw_folder / ".import_status.json").exists()


def test_commit_normalizes_doi_into_formal_metadata(tmp_path):
    raw_folder = _curated_raw(tmp_path, "2024_wang_doi标准化")
    meta_path = raw_folder / "2024_wang_doi标准化.metadata.json"
    metadata = json.loads(meta_path.read_text(encoding="utf-8"))
    metadata["identifiers"]["doi"] = "https://doi.org/10.1038/s41586-023-06185-3"
    meta_path.write_text(json.dumps(metadata), encoding="utf-8")
    papers = tmp_path / "papers"

    result = V2PaperCommitService(
        papers_dir=papers,
        all_catalog_path=tmp_path / "catalog" / "all.catalog.json",
        ledger_path=tmp_path / "catalog" / "paper_number_ledger.json",
    ).commit_paper_raw(raw_folder)

    assert result["status"] == "imported"
    formal = json.loads(
        (papers / "2024_wang_doi标准化" / "2024_wang_doi标准化.metadata.json").read_text(encoding="utf-8")
    )
    assert formal["identifiers"]["doi"] == "10.1038/s41586-023-06185-3"


class _FakeRawConverter:
    def convert(self, input_path, output_dir, **kwargs):
        source_id = Path(input_path).stem
        out = Path(output_dir) / source_id / "hybrid_auto"
        out.mkdir(parents=True)
        (out / f"{source_id}.md").write_text("![x](./images/a.png)\n\ntext", encoding="utf-8")
        (out / "images").mkdir()
        (out / "images" / "a.png").write_bytes(b"png")
        return {"success": True, "output_dir": str(Path(output_dir) / source_id), "runner": "cli"}


def test_paper_raw_converter_guards_input_and_extracts_images(tmp_path):
    paper_raw = tmp_path / "paper_raw"
    src = paper_raw / "000001"
    src.mkdir(parents=True)
    (src / "000001.pdf").write_bytes(b"%PDF")
    metadata = empty_metadata("000001")
    (src / "000001.metadata.json").write_text(json.dumps(metadata), encoding="utf-8")

    converter = PaperRawConverter(paper_raw_dir=paper_raw, converter=_FakeRawConverter())
    result = converter.convert("000001")

    assert result["success"]
    assert (src / "000001.md").read_text(encoding="utf-8").startswith("![x](images/a.png)")
    assert (src / "images" / "a.png").exists()
    with pytest.raises(ValueError):
        converter.convert(tmp_path / "raw" / "000001")


def test_curation_merges_only_empty_metadata_and_renames(tmp_path):
    folder = tmp_path / "paper_raw" / "000001"
    folder.mkdir(parents=True)
    metadata = empty_metadata("000001")
    metadata["title"]["original"] = "Trusted Original"
    metadata["title"]["short_zh"] = "可信论文"
    metadata["year"] = 2024
    metadata["authors"] = [{"full_name": "Wang A", "family": "Wang", "given": "A", "orcid": "", "affiliation": ""}]
    metadata["container"]["journal"] = "Test Journal"
    metadata["identifiers"]["doi"] = "10.1/test"
    metadata["metadata_match"]["status"] = "matched"
    metadata["metadata_match"]["confidence"] = 1.0
    catalog = empty_catalog()
    catalog["content_identity"]["content_title"] = "Trusted Original"
    catalog["classification"]["primary_domain"] = "blowing_snow"
    (folder / "000001.metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    (folder / "000001.catalog.json").write_text(json.dumps(catalog), encoding="utf-8")
    (folder / "000001.md").write_text("# Trusted", encoding="utf-8")
    (folder / "000001.pdf").write_bytes(b"%PDF")
    (folder / "images").mkdir()
    patch = empty_metadata("000001")
    patch["title"]["original"] = "Overwrite Attempt"
    patch["abstract"] = "new abstract"
    patch_path = tmp_path / "patch.metadata.json"
    patch_path.write_text(json.dumps(patch), encoding="utf-8")

    result = PaperCurationService().apply_curated_files(folder, curated_metadata_path=patch_path)

    assert result["success"]
    renamed = Path(result["folder"])
    assert renamed.name == "2024_Wang_可信论文"
    merged = json.loads((renamed / f"{renamed.name}.metadata.json").read_text(encoding="utf-8"))
    assert merged["title"]["original"] == "Trusted Original"
    assert merged["abstract"] == "new abstract"
    assert (renamed / f"{renamed.name}.catalog.json").exists()


def test_v2_commit_does_not_write_pdf_mirror(tmp_path):
    raw_folder = _curated_raw(tmp_path)
    papers = tmp_path / "papers"
    mirror_dir = tmp_path / "pdf_mirror"
    result = V2PaperCommitService(
        papers_dir=papers,
        all_catalog_path=tmp_path / "catalog" / "all.catalog.json",
        ledger_path=tmp_path / "catalog" / "paper_number_ledger.json",
    ).commit_paper_raw(raw_folder)

    assert result["status"] == "imported"
    assert not mirror_dir.exists()


def test_empty_catalog_is_v2_0_with_content_groups():
    cat = empty_catalog()
    assert cat["schema_version"] == "2.0"
    assert "display" not in cat  # display removed in v2.0
    for key in ("content_identity", "classification", "screening", "research_card", "evidence_profile", "content_notes", "provenance", "asset_refs"):
        assert key in cat
    for key in ("read_decision", "relevance_score", "reason"):
        assert key in cat["screening"]
    for key in ("research_problem", "main_findings", "usefulness_for_user"):
        assert key in cat["research_card"]


def test_validate_catalog_schema_rejects_missing_v2_0_groups():
    cat = empty_catalog()
    del cat["evidence_profile"]
    del cat["screening"]
    errors = validate_catalog_schema(cat)
    assert any("evidence_profile" in e for e in errors)
    assert any("screening" in e for e in errors)


def test_validate_catalog_schema_accepts_v2_0():
    assert validate_catalog_schema(empty_catalog()) == []


def test_validate_catalog_schema_rejects_forbidden_metadata_keys():
    cat = empty_catalog()
    cat["doi"] = "10.1/x"  # forbidden at top level
    errors = validate_catalog_schema(cat)
    assert any("forbidden bibliographic key: doi" in e for e in errors)
    cat2 = empty_catalog()
    cat2["content_identity"]["identifiers"] = {"doi": "10.1/x"}  # forbidden nested
    errors2 = validate_catalog_schema(cat2)
    assert any("forbidden bibliographic key: content_identity.identifiers" in e for e in errors2)


def test_migrate_catalog_to_v2_0_strips_forbidden_and_preserves_content():
    old = {
        "schema_version": "1.1",
        "display": {"title_original": "Keep", "title_zh": "", "short_name_zh": "", "year": 2020, "first_author": "X", "doi": "10.1/x"},
        "classification": {"primary_domain": "snow", "domains": ["snow"], "topics": ["drift"], "keywords_en": [], "keywords_zh": []},
        "research_card": {"one_sentence_summary_zh": "kept summary", "research_question_zh": "", "object_zh": "",
                          "method_zh": "", "data_or_experiment_zh": "", "key_variables": [], "main_conclusion_zh": "",
                          "usefulness_for_project_zh": "", "recommended_use_cases_zh": []},
    }
    migrated, removed = migrate_catalog_to_v2_0(old)
    assert migrated["schema_version"] == "2.0"
    assert "display" not in migrated
    assert migrated["content_identity"]["content_title"] == "Keep"
    assert migrated["content_notes"]["short_summary"] == "kept summary"
    assert validate_catalog_schema(migrated) == []
    assert any("doi" in r for r in removed)
    assert any("year" in r for r in removed)


def test_paper_id_folds_accented_author_family_to_ascii():
    """Accented family names (Déry, Müller) must produce an ASCII-safe paper_id, not crash."""
    from src.services.v2_library import first_author_family, paper_id_from_metadata_catalog
    from src.naming import validate_paper_id
    m = empty_metadata("000001")
    m["year"] = 1999
    m["title"]["short_zh"] = "体相吹雪模型"
    m["authors"] = [{"full_name": "Stephen J. Déry", "family": "Déry", "given": "Stephen J.", "orcid": "", "affiliation": ""}]
    c = empty_catalog()
    assert first_author_family(m) == "Dery"
    pid = paper_id_from_metadata_catalog(m, c)
    validate_paper_id(pid)  # must not raise
    assert pid == "1999_Dery_体相吹雪模型"


def test_accented_author_apply_curated_files_completes_rename(tmp_path):
    """apply_curated_files must not crash and must produce correct ASCII paper_id for accented names."""
    folder = tmp_path / "paper_raw" / "000001"
    folder.mkdir(parents=True)
    metadata = empty_metadata("000001")
    metadata["title"]["original"] = "A Bulk Blowing-Snow Model"
    metadata["title"]["short_zh"] = "体相吹雪模型"
    metadata["year"] = 1999
    metadata["authors"] = [{"full_name": "Stephen J. Déry", "family": "Déry", "given": "Stephen J.", "orcid": "", "affiliation": ""}]
    metadata["container"]["journal"] = "Test Journal"
    metadata["identifiers"]["doi"] = "10.1/dery"
    metadata["metadata_match"]["status"] = "matched"
    metadata["metadata_match"]["confidence"] = 1.0
    catalog = empty_catalog()
    catalog["content_identity"]["content_title"] = "A Bulk Blowing-Snow Model"
    catalog["classification"]["primary_domain"] = "blowing_snow"
    (folder / "000001.metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    (folder / "000001.catalog.json").write_text(json.dumps(catalog), encoding="utf-8")
    (folder / "000001.md").write_text("# test", encoding="utf-8")
    (folder / "000001.pdf").write_bytes(b"%PDF")
    (folder / "images").mkdir()
    result = PaperCurationService().apply_curated_files(folder, curated_catalog_path=folder / "000001.catalog.json")
    assert result["success"], f"apply_curated_files failed: {result.get('errors', [])}"
    assert result["paper_id"] == "1999_Dery_体相吹雪模型"
    renamed = Path(result["folder"])
    assert renamed.exists()
    assert renamed.name == "1999_Dery_体相吹雪模型"


def test_apply_rejects_catalog_missing_screening_group(tmp_path):
    """apply_curated_files must reject a curator catalog missing the critical screening group."""
    folder = tmp_path / "paper_raw" / "000001"
    folder.mkdir(parents=True)
    metadata = empty_metadata("000001")
    metadata["title"]["original"] = "T"
    metadata["year"] = 2024
    metadata["authors"] = [{"full_name": "Wang A", "family": "Wang", "given": "A", "orcid": "", "affiliation": ""}]
    metadata["container"]["journal"] = "Test Journal"
    metadata["identifiers"]["doi"] = "10.1/test"
    metadata["metadata_match"]["status"] = "matched"
    metadata["metadata_match"]["confidence"] = 1.0
    (folder / "000001.metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    catalog = empty_catalog()
    del catalog["screening"]
    catalog_path = folder / "000001.catalog.json"
    catalog_path.write_text(json.dumps(catalog), encoding="utf-8")
    (folder / "000001.md").write_text("# T", encoding="utf-8")
    (folder / "000001.pdf").write_bytes(b"%PDF")
    (folder / "images").mkdir()
    result = PaperCurationService().apply_curated_files(folder, curated_catalog_path=catalog_path)
    assert not result["success"]
    assert any("screening" in e for e in result["errors"])
    assert (folder / ".import_status.json").exists(), ".import_status.json must be written on failure"
    assert folder.exists(), "folder must NOT be renamed on failure"
