"""E2E structural tests: commit, dedup, numbering, rebuild, compact, copy, bibtex, destructive.

All tests use mock PDFs and in-memory temp directories — no network, no GPU.
Drives the real v2 service classes through the full chain.
"""
import json
import shutil
from pathlib import Path

import pytest

from src.services.v2_library import (
    AllCatalogBuilder,
    LlmWorkService,
    PaperNumberLedger,
    V2PaperCommitService,
    bibtex_from_metadata,
    empty_catalog,
    empty_metadata,
)
from src.catalog import build_compact_catalog_text

# Import the validate_v2_library CLI's validation function
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.validate_v2_library import validate_v2_library


def _curated_raw(root: Path, pid: str, *, doi: str = "10.1/x", year: int = 2024,
                 family: str = "Wang", tz: str = "测试论文", pdf_content: bytes = b"%PDF-X") -> Path:
    """Build a complete curated paper_raw folder ready for commit."""
    folder = root / "paper_raw" / pid
    folder.mkdir(parents=True)
    metadata = empty_metadata(pid)
    metadata["title"]["original"] = f"Paper {pid}"
    metadata["title"]["translated_zh"] = tz
    metadata["title"]["short_zh"] = tz
    metadata["year"] = year
    metadata["authors"] = [
        {"full_name": f"{family} A", "family": family, "given": "A", "orcid": "", "affiliation": ""}
    ]
    metadata["identifiers"]["doi"] = doi
    metadata["metadata_match"] = {
        "status": "matched", "source": "test", "confidence": 1.0,
        "matched_at": "2026-01-01", "warnings": [], "candidates": [],
    }
    catalog = empty_catalog()
    catalog["display"].update({
        "title_original": f"Paper {pid}", "title_zh": tz, "short_name_zh": tz,
        "year": year, "first_author": family, "authors_short": f"{family} et al.",
        "venue": "Test Journal", "doi": doi,
    })
    catalog["classification"].update({"primary_domain": "test", "topics": ["test"]})
    catalog["research_card"].update({
        "one_sentence_summary_zh": "一句话摘要",
        "method_zh": "测试方法",
        "main_conclusion_zh": "测试结论",
        "usefulness_for_project_zh": "测试用途",
    })
    catalog["screening"].update({
        "relevance_score": 5, "reading_priority": 4, "read_decision": "must_read",
        "need_fulltext": True, "best_for_sections": ["method"], "reason_zh": "测试",
    })
    (folder / f"{pid}.metadata.json").write_text(json.dumps(metadata, ensure_ascii=False), encoding="utf-8")
    (folder / f"{pid}.catalog.json").write_text(json.dumps(catalog, ensure_ascii=False), encoding="utf-8")
    (folder / f"{pid}.md").write_text(f"# {pid}\nbody content", encoding="utf-8")
    (folder / f"{pid}.pdf").write_bytes(pdf_content)
    (folder / "images").mkdir()
    return folder


def _commit(papers_dir: Path, all_catalog: Path, ledger: Path, folder: Path) -> dict:
    return V2PaperCommitService(papers_dir=papers_dir, all_catalog_path=all_catalog, ledger_path=ledger).commit_paper_raw(folder)


class TestCommit:
    def test_commit_success_assigns_paper_number(self, tmp_path):
        f = _curated_raw(tmp_path, "2024_wang_测试论文")
        r = _commit(tmp_path / "papers", tmp_path / "catalog" / "all.catalog.json",
                    tmp_path / "catalog" / "paper_number_ledger.json", f)
        assert r["status"] == "imported"
        assert r["paper_number"] == "0000000000000001"
        pdir = tmp_path / "papers" / "2024_wang_测试论文"
        for suffix in ("metadata.json", "catalog.json", "md", "pdf"):
            assert (pdir / f"2024_wang_测试论文.{suffix}").exists()
        assert (pdir / "images").is_dir()
        assert (pdir / "0000000000000001.paper.number").exists()
        assert not f.exists()  # source removed

    def test_missing_asset_rejected(self, tmp_path):
        for asset in ("pdf", "catalog.json", "md"):
            base = tmp_path / asset
            base.mkdir(parents=True, exist_ok=True)
            f = _curated_raw(base, "2024_wang_x")
            if asset == "pdf":
                (f / "2024_wang_x.pdf").unlink()
            elif asset == "catalog.json":
                (f / "2024_wang_x.catalog.json").unlink()
            elif asset == "md":
                (f / "2024_wang_x.md").unlink()
            with pytest.raises((FileNotFoundError, ValueError)):
                _commit(base / "p", base / "c" / "ac.json", base / "c" / "l.json", f)


class TestDedup:
    def test_doi_duplicate_quarantined(self, tmp_path):
        f1 = _curated_raw(tmp_path, "2024_wang_论文A", doi="10.1/same")
        f2 = _curated_raw(tmp_path, "2024_li_论文B", doi="10.1/same", pdf_content=b"%PDF-B")
        svc = V2PaperCommitService(
            papers_dir=tmp_path / "papers",
            all_catalog_path=tmp_path / "c" / "all.catalog.json",
            ledger_path=tmp_path / "c" / "l.json",
        )
        r1 = svc.commit_paper_raw(f1)
        assert r1["status"] == "imported"
        r2 = svc.commit_paper_raw(f2)
        assert r2["status"] == "possible_duplicate"
        assert Path(r2["quarantine_dir"]).exists()
        assert not (tmp_path / "papers" / "2024_li_论文B").exists()

    def test_pdf_sha_duplicate_quarantined(self, tmp_path):
        f1 = _curated_raw(tmp_path, "2024_wang_A", doi="10.1/uniq1", pdf_content=b"%PDF-same-sha")
        f2 = _curated_raw(tmp_path, "2024_wang_B", doi="10.1/uniq2", pdf_content=b"%PDF-same-sha",
                          tz="不同标题", year=2023, family="Li")
        svc = V2PaperCommitService(
            papers_dir=tmp_path / "papers",
            all_catalog_path=tmp_path / "c" / "all.json",
            ledger_path=tmp_path / "c" / "l.json",
        )
        assert svc.commit_paper_raw(f1)["status"] == "imported"
        r2 = svc.commit_paper_raw(f2)
        assert r2["status"] == "possible_duplicate"
        assert not (tmp_path / "papers" / "2024_wang_B").exists()


class TestNumberingAndRebuild:
    def test_sequential_numbering_and_rebuild(self, tmp_path):
        papers = tmp_path / "papers"
        ac = tmp_path / "c" / "all.catalog.json"
        lg = tmp_path / "c" / "paper_number_ledger.json"
        svc = V2PaperCommitService(papers_dir=papers, all_catalog_path=ac, ledger_path=lg)

        f1 = _curated_raw(tmp_path, "2024_wang_论文A")
        f2 = _curated_raw(tmp_path, "2024_li_论文B", doi="10.1/b", tz="论文B", family="Li",
                          pdf_content=b"%PDF-distinct-B")
        r1 = svc.commit_paper_raw(f1)
        r2 = svc.commit_paper_raw(f2)
        assert r1["paper_number"] == "0000000000000001"
        assert r2["paper_number"] == "0000000000000002"

    def test_deleted_paper_not_in_rebuild(self, tmp_path):
        papers = tmp_path / "papers"
        ac = tmp_path / "c" / "all.catalog.json"
        lg = tmp_path / "c" / "paper_number_ledger.json"
        svc = V2PaperCommitService(papers_dir=papers, all_catalog_path=ac, ledger_path=lg)
        f1 = _curated_raw(tmp_path, "2024_wang_论文A")
        f2 = _curated_raw(tmp_path, "2024_li_论文B", doi="10.1/b", tz="论文B", family="Li",
                          pdf_content=b"%PDF-B")
        svc.commit_paper_raw(f1)
        svc.commit_paper_raw(f2)
        # delete first paper
        shutil.rmtree(papers / "2024_wang_论文A")
        AllCatalogBuilder(papers, ac, PaperNumberLedger(lg)).build(write=True)
        data = json.loads(ac.read_text(encoding="utf-8"))
        assert len(data["papers"]) == 1
        assert data["papers"][0]["paper_id"] == "2024_li_论文B"

    def test_number_not_reused(self, tmp_path):
        papers = tmp_path / "papers"
        ac = tmp_path / "c" / "all.catalog.json"
        lg = tmp_path / "c" / "paper_number_ledger.json"
        svc = V2PaperCommitService(papers_dir=papers, all_catalog_path=ac, ledger_path=lg)
        f1 = _curated_raw(tmp_path, "2024_wang_论文A")
        f2 = _curated_raw(tmp_path, "2024_li_论文B", doi="10.1/b", tz="论文B", family="Li", pdf_content=b"%PDF-B")
        svc.commit_paper_raw(f1)
        svc.commit_paper_raw(f2)
        shutil.rmtree(papers / "2024_wang_论文A")
        AllCatalogBuilder(papers, ac, PaperNumberLedger(lg)).build(write=True)
        lg_data = json.loads(lg.read_text(encoding="utf-8"))
        assert lg_data["max_number"] == "0000000000000002"  # 1 was used, not freed


class TestCompactCatalog:
    def test_compact_includes_all_screening_fields(self, tmp_path):
        f = _curated_raw(tmp_path, "2024_wang_测试论文")
        svc = V2PaperCommitService(papers_dir=tmp_path / "papers",
                                    all_catalog_path=tmp_path / "c" / "all.json",
                                    ledger_path=tmp_path / "c" / "l.json")
        svc.commit_paper_raw(f)
        AllCatalogBuilder(tmp_path / "papers", tmp_path / "c" / "all.json",
                          PaperNumberLedger(tmp_path / "c" / "l.json")).build(write=True)
        data = json.loads((tmp_path / "c" / "all.json").read_text(encoding="utf-8"))
        txt = build_compact_catalog_text(data["papers"])
        # Each of these must appear in the compact text
        for kw in ("0000000000000001", "2024", "Wang et al.", "Test Journal", "10.1/x",
                   "must_read", "method:", "conclusion:", "usefulness:", "best_for_sections:"):
            assert kw in txt, f"compact catalog missing: {kw}"


class TestLlmWorkCopy:
    def test_copy_by_paper_number_and_guards(self, tmp_path):
        f = _curated_raw(tmp_path, "2024_wang_测试论文")
        papers = tmp_path / "papers"
        ac = tmp_path / "c" / "all.json"
        lg = tmp_path / "c" / "l.json"
        svc = V2PaperCommitService(papers_dir=papers, all_catalog_path=ac, ledger_path=lg)
        svc.commit_paper_raw(f)
        AllCatalogBuilder(papers, ac, PaperNumberLedger(lg)).build(write=True)

        lw = LlmWorkService(all_catalog_path=ac, llm_work_dir=tmp_path / "llm_work")
        number = "0000000000000001"

        # copy succeeds
        r = lw.copy_to_session(number, "session_1")
        assert r["paper_id"] == "2024_wang_测试论文"
        target = tmp_path / "llm_work" / "session_1" / number
        assert target.exists()
        assert (target / "2024_wang_测试论文.md").exists()
        assert (papers / "2024_wang_测试论文" / "2024_wang_测试论文.md").exists()  # source untouched

        # exists without overwrite
        with pytest.raises(FileExistsError):
            lw.copy_to_session(number, "session_1")

        # overwrite
        r2 = lw.copy_to_session(number, "session_1", overwrite=True)
        assert r2["paper_id"] == "2024_wang_测试论文"

        # invalid number
        with pytest.raises(ValueError):
            lw.copy_to_session("1", "x")

        # non-existent number
        with pytest.raises(KeyError):
            lw.copy_to_session("9999999999999999", "x")


class TestBibtex:
    def test_bibtex_from_metadata_only(self, tmp_path):
        f = _curated_raw(tmp_path, "2024_wang_测试论文")
        svc = V2PaperCommitService(papers_dir=tmp_path / "papers",
                                    all_catalog_path=tmp_path / "c" / "all.json",
                                    ledger_path=tmp_path / "c" / "l.json")
        svc.commit_paper_raw(f)
        meta = json.loads((tmp_path / "papers" / "2024_wang_测试论文" / "2024_wang_测试论文.metadata.json")
                          .read_text(encoding="utf-8"))
        bib = bibtex_from_metadata(meta)
        assert bib.startswith("@article{")
        for kw in ("title", "author", "year", "doi"):
            assert kw in bib, f"bibtex missing {kw}"
        # bibtex must NOT contain catalog fields
        assert "screening" not in bib
        assert "research_card" not in bib


class TestDestructive:
    def test_paper_md_rejected_by_validate(self, tmp_path):
        f = _curated_raw(tmp_path, "2024_wang_测试论文")
        papers = tmp_path / "papers"
        ac = tmp_path / "c" / "all.json"
        lg = tmp_path / "c" / "l.json"
        svc = V2PaperCommitService(papers_dir=papers, all_catalog_path=ac, ledger_path=lg)
        svc.commit_paper_raw(f)
        AllCatalogBuilder(papers, ac, PaperNumberLedger(lg)).build(write=True)

        (papers / "2024_wang_测试论文" / "paper.md").write_text("legacy", encoding="utf-8")
        errors, _ = validate_v2_library(papers_dir=papers, all_catalog_path=ac, check_paths=False)
        assert any("paper.md" in e for e in errors), f"validate should reject paper.md: {errors}"

    def test_catalog_missing_screening_rejected_by_validate(self, tmp_path):
        f = _curated_raw(tmp_path, "2024_wang_测试论文")
        papers = tmp_path / "papers"
        ac = tmp_path / "c" / "all.json"
        lg = tmp_path / "c" / "l.json"
        svc = V2PaperCommitService(papers_dir=papers, all_catalog_path=ac, ledger_path=lg)
        svc.commit_paper_raw(f)
        AllCatalogBuilder(papers, ac, PaperNumberLedger(lg)).build(write=True)

        cat_path = papers / "2024_wang_测试论文" / "2024_wang_测试论文.catalog.json"
        cat = json.loads(cat_path.read_text(encoding="utf-8"))
        saved = cat.pop("screening")
        cat_path.write_text(json.dumps(cat, ensure_ascii=False), encoding="utf-8")

        errors, _ = validate_v2_library(papers_dir=papers, all_catalog_path=ac, check_paths=False)
        assert any("screening" in e for e in errors), f"validate should reject missing screening: {errors}"

        cat_path.write_text(json.dumps({**cat, "screening": saved}, ensure_ascii=False), encoding="utf-8")

    def test_ledger_marker_conflict_reported(self, tmp_path):
        f = _curated_raw(tmp_path, "2024_wang_测试论文")
        papers = tmp_path / "papers"
        ac = tmp_path / "c" / "all.json"
        lg = tmp_path / "c" / "l.json"
        svc = V2PaperCommitService(papers_dir=papers, all_catalog_path=ac, ledger_path=lg)
        svc.commit_paper_raw(f)

        marker = papers / "2024_wang_测试论文" / "0000000000000001.paper.number"
        # overwrite marker with wrong data then rename
        marker.write_text(json.dumps({"paper_number": "0000000000000099", "folder_name": "2024_wang_测试论文"}),
                          encoding="utf-8")
        renamed = papers / "2024_wang_测试论文" / "0000000000000099.paper.number"
        marker.rename(renamed)
        errors, _ = PaperNumberLedger(lg).validate(papers)
        assert any("conflict" in e for e in errors), f"ledger should report marker conflict: {errors}"
