"""Build or apply a safe repair plan for manifest/catalog/library_index drift."""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from collections import Counter
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import (
    CATALOG_PATH,
    DOMAIN_CATALOG_DIR,
    LIBRARY_INDEX_PATH,
    MANIFEST_PATH,
    PAPERS_DIR,
)
from scripts.audit_library import audit_library
from src.services.paper_registry import PaperRegistryService


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {"papers": []}
    return json.loads(path.read_text(encoding="utf-8"))


def _by_id(data: dict) -> dict[str, dict]:
    return {p.get("paper_id", ""): p for p in data.get("papers", []) if p.get("paper_id")}


def _norm(value: str) -> str:
    return re.sub(r"[\W_]+", "", (value or "").strip().lower(), flags=re.UNICODE)


def _year_from_pid(pid: str) -> str:
    m = re.match(r"^(\d{4})_", pid or "")
    return m.group(1) if m else ""


def _semantic_suffix(pid: str) -> str:
    parts = (pid or "").split("_")
    if parts and re.fullmatch(r"\d{4}", parts[0]):
        parts = parts[1:]
    if parts and re.fullmatch(r"[A-Za-z][A-Za-z0-9-]*", parts[0]):
        parts = parts[1:]
    return _norm("_".join(parts))


def _basename_stem(entry: dict) -> str:
    raw = entry.get("raw_pdf") or entry.get("raw_filename") or ""
    if not raw:
        return ""
    return _norm(Path(str(raw).replace("\\", "/")).stem)


def _title_key(entry: dict) -> str:
    title = _norm(entry.get("title", ""))
    year = entry.get("year") or _year_from_pid(entry.get("paper_id", ""))
    return f"{year}::{title}" if title and year else ""


def _paper_md_exists(paper_id: str, papers_dir: Path = PAPERS_DIR) -> bool:
    return (papers_dir / paper_id / "paper.md").exists()


def _score_pair(manifest_pid: str, manifest_entry: dict, catalog_pid: str, catalog_entry: dict) -> tuple[float, str]:
    m_doi = (manifest_entry.get("doi") or "").strip().lower()
    c_doi = (catalog_entry.get("doi") or "").strip().lower()
    if m_doi and c_doi and m_doi == c_doi:
        return 1.0, "doi"
    m_sha = (manifest_entry.get("sha256") or "").strip().lower()
    c_sha = (catalog_entry.get("sha256") or "").strip().lower()
    if m_sha and c_sha and m_sha == c_sha:
        return 1.0, "sha256"
    if _title_key(manifest_entry) and _title_key(manifest_entry) == _title_key(catalog_entry):
        return 0.9, "title_year"

    m_year = str(manifest_entry.get("year") or _year_from_pid(manifest_pid) or "")
    c_year = str(catalog_entry.get("year") or _year_from_pid(catalog_pid) or "")
    m_suffix = _semantic_suffix(manifest_pid)
    c_suffix = _semantic_suffix(catalog_pid)
    if m_year and m_year == c_year and m_suffix and c_suffix:
        if m_suffix == c_suffix or m_suffix in c_suffix or c_suffix in m_suffix:
            return 0.85, "year_shared_suffix"
        ratio = SequenceMatcher(None, m_suffix, c_suffix).ratio()
        if ratio >= 0.72:
            return 0.8, "year_keyword_similarity"

    m_base = _basename_stem(manifest_entry)
    c_base = _basename_stem(catalog_entry)
    if m_base and c_base:
        ratio = SequenceMatcher(None, m_base, c_base).ratio()
        if ratio >= 0.85:
            return 0.85, "raw_pdf_basename"

    m_title = _norm(manifest_entry.get("title", "") or manifest_entry.get("raw_stem", ""))
    c_title = _norm(catalog_entry.get("title", ""))
    if m_year and m_year == c_year and m_title and c_title:
        ratio = SequenceMatcher(None, m_title, c_title).ratio()
        if ratio >= 0.72:
            return 0.8, "year_title_similarity"

    if manifest_pid in catalog_pid or catalog_pid in manifest_pid:
        return 0.6, "paper_id_substring"
    return 0.0, ""


def _best_candidates(manifest_only: set[str], catalog_only: set[str], manifest: dict, catalog: dict) -> list[dict]:
    candidates = []
    for catalog_pid in sorted(catalog_only):
        scored = []
        for manifest_pid in sorted(manifest_only):
            confidence, reason = _score_pair(
                manifest_pid, manifest.get(manifest_pid, {}),
                catalog_pid, catalog.get(catalog_pid, {}),
            )
            if confidence >= 0.6:
                scored.append({
                    "action": "merge_manifest_catalog_ids",
                    "manifest_paper_id": manifest_pid,
                    "catalog_paper_id": catalog_pid,
                    "reason": reason,
                    "confidence": confidence,
                })
        scored.sort(key=lambda x: (-x["confidence"], x["manifest_paper_id"]))
        candidates.extend(scored[:3])
    return candidates


def _split_auto_matches(candidates: list[dict]) -> tuple[list[dict], list[dict]]:
    high = [c for c in candidates if c["confidence"] >= 0.8]
    by_manifest = Counter(c["manifest_paper_id"] for c in high)
    by_catalog = Counter(c["catalog_paper_id"] for c in high)
    matches = []
    manual = []
    for c in high:
        if by_manifest[c["manifest_paper_id"]] == 1 and by_catalog[c["catalog_paper_id"]] == 1:
            matches.append(c)
        else:
            c = dict(c)
            c["manual_review_reason"] = "non_one_to_one_high_confidence_match"
            manual.append(c)
    for c in candidates:
        if c["confidence"] < 0.8:
            c = dict(c)
            c["manual_review_reason"] = "low_confidence"
            manual.append(c)
    matches.sort(key=lambda x: (x["catalog_paper_id"], x["manifest_paper_id"]))
    manual.sort(key=lambda x: (-x["confidence"], x["catalog_paper_id"], x["manifest_paper_id"]))
    return matches, manual


def _backup_fact_sources(manifest_path: Path, catalog_path: Path, index_path: Path, domain_dir: Path) -> list[str]:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    paths = [manifest_path, catalog_path, index_path, catalog_path.parent / "references.bib"]
    if domain_dir.exists():
        paths.extend(sorted(domain_dir.glob("*/literature_catalog.json")))
        paths.extend(sorted(domain_dir.glob("*/references.bib")))
    backups = []
    for path in paths:
        if not path.exists():
            continue
        backup = path.with_name(f"{path.name}.bak_{stamp}")
        shutil.copy2(path, backup)
        backups.append(str(backup))
    return backups


def build_reconcile_plan(
    manifest_path: Path = MANIFEST_PATH,
    catalog_path: Path = CATALOG_PATH,
    index_path: Path = LIBRARY_INDEX_PATH,
    papers_dir: Path = PAPERS_DIR,
) -> dict:
    report = audit_library(manifest_path, catalog_path, index_path, strict=True)
    manifest = _by_id(_load_json(manifest_path))
    catalog = _by_id(_load_json(catalog_path))

    manifest_only = set(report["manifest_only_paper_ids"]) | set(report["manifest_converted_without_catalog"])
    catalog_only = set(report["catalog_entries_without_manifest"])
    candidates = _best_candidates(manifest_only, catalog_only, manifest, catalog)
    matches, manual_review = _split_auto_matches(candidates)

    matched_manifest = {m["manifest_paper_id"] for m in matches}
    matched_catalog = {m["catalog_paper_id"] for m in matches}
    unmatched_catalog_only = []
    for catalog_pid in sorted(catalog_only - matched_catalog):
        c = catalog.get(catalog_pid, {})
        unmatched_catalog_only.append({
            "paper_id": catalog_pid,
            "paper_md_exists": _paper_md_exists(catalog_pid, papers_dir),
            "suggested_action": "rebuild_manifest_converted" if _paper_md_exists(catalog_pid, papers_dir)
            else "catalog_orphan",
            "raw_pdf": c.get("raw_pdf", ""),
            "markdown": c.get("markdown", ""),
            "images_dir": c.get("images_dir", ""),
        })

    unmatched_manifest_only = []
    for manifest_pid in sorted(manifest_only - matched_manifest):
        entry = manifest.get(manifest_pid, {})
        if entry.get("status") == "converted":
            suggested = "mark_unregistered_converted"
        else:
            suggested = "keep_non_converted_out_of_catalog"
        unmatched_manifest_only.append({
            "paper_id": manifest_pid,
            "status": entry.get("status", ""),
            "suggested_action": suggested,
        })

    failed_catalog = []
    for pid in report["manifest_failed_with_existing_catalog"]:
        failed_catalog.append({
            "paper_id": pid,
            "paper_md_exists": _paper_md_exists(pid, papers_dir),
            "suggested_action": "restore_manifest_converted" if _paper_md_exists(pid, papers_dir)
            else "conversion_failed_with_catalog",
        })

    return {
        "apply_supported": True,
        "audit_ok": report["ok"],
        "matches": matches,
        "candidates": candidates,
        "manual_review": manual_review,
        "unmatched_catalog_only": unmatched_catalog_only,
        "unmatched_manifest_only": unmatched_manifest_only,
        "manifest_failed_with_existing_catalog": failed_catalog,
        "summary": {
            "matches": len(matches),
            "candidates": len(candidates),
            "manual_review": len(manual_review),
            "unmatched_catalog_only": len(unmatched_catalog_only),
            "unmatched_manifest_only": len(unmatched_manifest_only),
            "manifest_failed_with_existing_catalog": len(failed_catalog),
        },
    }


def apply_reconcile_plan(
    plan: dict,
    manifest_path: Path = MANIFEST_PATH,
    catalog_path: Path = CATALOG_PATH,
    index_path: Path = LIBRARY_INDEX_PATH,
    domain_dir: Path = DOMAIN_CATALOG_DIR,
    papers_dir: Path = PAPERS_DIR,
) -> dict:
    backups = _backup_fact_sources(manifest_path, catalog_path, index_path, domain_dir)
    registry = PaperRegistryService(
        manifest_path=manifest_path,
        catalog_path=catalog_path,
        index_path=index_path,
        domain_dir=domain_dir,
        papers_dir=papers_dir,
    )
    manifest = _by_id(_load_json(manifest_path))
    catalog = _by_id(_load_json(catalog_path))
    applied = []

    for match in plan["matches"]:
        applied.append(registry.merge_manifest_catalog_ids(
            match["manifest_paper_id"],
            match["catalog_paper_id"],
        ))

    for item in plan["unmatched_manifest_only"]:
        pid = item["paper_id"]
        entry = manifest.get(pid, {})
        if item["suggested_action"] != "mark_unregistered_converted":
            continue
        applied.append(registry.register_converted_paper(
            paper_id=pid,
            raw_pdf=entry.get("raw_pdf", ""),
            markdown=entry.get("markdown", ""),
            images_dir=entry.get("images_dir", ""),
            sha256=entry.get("sha256", ""),
            file_size=entry.get("file_size", 0),
            mtime=entry.get("mtime", ""),
            raw_filename=entry.get("raw_filename", ""),
            raw_stem=entry.get("raw_stem", ""),
            mineru_backend=entry.get("mineru_backend", "hybrid-engine"),
            method=entry.get("method", "auto"),
            effort=entry.get("effort", "medium"),
            runner=entry.get("runner", "cli"),
            source_kind="reconcile_unregistered",
            images_count=entry.get("images_count", 0),
            md_chars=entry.get("md_chars", 0),
            replace=True,
        ))

    for item in plan["unmatched_catalog_only"]:
        if item["suggested_action"] != "catalog_orphan":
            continue
        applied.append(registry.mark_catalog_asset_problem(
            paper_id=item["paper_id"],
            status="asset_missing",
            raw_pdf=item.get("raw_pdf", ""),
            markdown=item.get("markdown", ""),
            images_dir=item.get("images_dir", ""),
            error="catalog entry has no matching manifest; manual review required",
        ))

    for item in plan["manifest_failed_with_existing_catalog"]:
        pid = item["paper_id"]
        c = catalog.get(pid, {})
        if item["suggested_action"] == "restore_manifest_converted":
            entry = manifest.get(pid, {})
            md = entry.get("markdown") or c.get("markdown") or str(papers_dir / pid / "paper.md")
            images = entry.get("images_dir") or c.get("images_dir") or str(papers_dir / pid / "images")
            raw = entry.get("raw_pdf") or c.get("raw_pdf", "")
            applied.append(registry.register_converted_paper(
                paper_id=pid,
                raw_pdf=raw,
                markdown=md,
                images_dir=images,
                sha256=entry.get("sha256", ""),
                title=c.get("title", ""),
                doi=c.get("doi", ""),
                year=c.get("year"),
                primary_domain=c.get("primary_domain", ""),
                domains=list(c.get("domains") or []),
                source_kind="reconcile_restore",
                replace=True,
            ))
        else:
            applied.append(registry.mark_catalog_asset_problem(
                paper_id=pid,
                status="conversion_failed_with_catalog",
                raw_pdf=c.get("raw_pdf", ""),
                markdown=c.get("markdown", ""),
                images_dir=c.get("images_dir", ""),
                error="catalog exists but conversion failed and paper.md is missing",
            ))

    registry._rebuild_domain_views()
    return {"backups": backups, "applied": applied}


def main() -> int:
    parser = argparse.ArgumentParser(description="Build or apply a library reconciliation plan.")
    parser.add_argument("--manifest", type=Path, default=MANIFEST_PATH)
    parser.add_argument("--catalog", type=Path, default=CATALOG_PATH)
    parser.add_argument("--index", type=Path, default=LIBRARY_INDEX_PATH)
    parser.add_argument("--domain-dir", type=Path, default=DOMAIN_CATALOG_DIR)
    parser.add_argument("--papers-dir", type=Path, default=PAPERS_DIR)
    parser.add_argument("--apply", action="store_true", help="apply safe one-to-one repairs")
    args = parser.parse_args()

    plan = build_reconcile_plan(args.manifest, args.catalog, args.index, args.papers_dir)
    if args.apply:
        result = apply_reconcile_plan(
            plan,
            manifest_path=args.manifest,
            catalog_path=args.catalog,
            index_path=args.index,
            domain_dir=args.domain_dir,
            papers_dir=args.papers_dir,
        )
        plan["apply_result"] = result
        plan["post_apply_audit"] = audit_library(args.manifest, args.catalog, args.index, strict=True)
    print(json.dumps(plan, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
