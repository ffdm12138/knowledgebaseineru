"""全库 metadata 补全：对 catalog 中已有/缺失元数据的论文查询 Crossref 补全。

流程：
  1. 对有 DOI 的论文 → 查询 Crossref → 补全 year/authors/title/venue
  2. 对无 DOI 的论文 → 从 paper.md 正文提取 DOI → 同上
  3. 生成 proposed_paper_id
  4. 默认 dry-run，--apply 才写回 catalog

用法:
  python scripts/enrich_library_metadata.py                    # 全库 dry-run
  python scripts/enrich_library_metadata.py --domain blowing_snow_physics
  python scripts/enrich_library_metadata.py --apply            # 写入
  python scripts/enrich_library_metadata.py --apply --dry-run  # 显式 dry-run
"""
import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger

from config.settings import CATALOG_PATH, MANIFEST_PATH, LIBRARY_INDEX_PATH, PAPERS_DIR
from src.services.metadata_enrichment_service import (
    enrich_from_doi,
    extract_doi_from_paper_md,
    extract_doi_from_text,
    looks_like_bad_paper_id,
    normalize_bibliographic_metadata,
)
from src.services.paper_id import generate_paper_id
from src.utils.atomic_io import atomic_write_json

# ── DOI query cache (in-memory, per-run) ──────────────────────────────
_crossref_cache: dict[str, dict | None] = {}


def _cached_enrich_from_doi(doi: str) -> dict:
    """Query Crossref with in-memory cache."""
    from src.discovery.models import normalize_doi
    normalized = normalize_doi(doi)
    if not normalized:
        return {"success": False, "error": "invalid doi"}
    if normalized in _crossref_cache:
        return _crossref_cache[normalized]
    result = enrich_from_doi(normalized)
    _crossref_cache[normalized] = result
    return result


# ── Title quality check ───────────────────────────────────────────────

_FILENAME_STEM_LIKE = re.compile(
    r"^(\d+_|[\[\(]?\d+[\]\)]|s\d{4}|j\.\w+\.\d+|1-s2\.0|download|article|fulltext|paper|manuscript|untitled)",
    re.IGNORECASE,
)


def _title_looks_like_filename_stem(title: str) -> bool:
    """Check if title appears to be derived from a PDF filename stem."""
    if not title:
        return True
    title = title.strip()
    # Bracketed number prefix: [17]The drag on...
    if re.match(r"^\[?\d+\]?\s*_?\s*", title):
        # Has a number prefix — likely from a reference list
        return True
    if _FILENAME_STEM_LIKE.match(title):
        return True
    # snowpack_1, snowpack_2 etc
    if re.match(r"^[A-Za-z]+\d*_\d+$", title.strip()):
        return True
    return False


def _should_replace_title(old_title: str, new_title: str) -> bool:
    """Decide whether to replace old_title with new_title from DOI metadata."""
    if not new_title or not new_title.strip():
        return False
    if not old_title or not old_title.strip():
        return True
    if _title_looks_like_filename_stem(old_title):
        return True
    # Keep human-provided titles (especially Chinese ones)
    if any('一' <= c <= '鿿' for c in old_title):
        return False
    return False


# ── Main enrichment logic ─────────────────────────────────────────────

def enrich_catalog_entry(
    paper: dict,
    *,
    paper_md_text: str = "",
    dry_run: bool = True,
) -> dict:
    """Enrich a single catalog paper entry.

    Returns a dict with the changes that would be / were applied.
    """
    paper_id = paper.get("paper_id", "?")
    result = {
        "paper_id": paper_id,
        "doi": paper.get("doi", ""),
        "old_title": paper.get("title", ""),
        "old_year": paper.get("year"),
        "old_authors": paper.get("authors", []),
        "changes": {},
        "proposed_paper_id": "",
        "warnings": [],
        "enriched": False,
    }

    doi = paper.get("doi", "").strip()

    # 1. If no DOI, try extracting from paper.md
    if not doi and paper_md_text:
        doi = extract_doi_from_paper_md(paper_md_text) or ""
        if doi:
            result["doi"] = doi
            result["changes"]["doi"] = doi
            result["warnings"].append(f"DOI extracted from paper.md")

    # 2. If still no DOI, try from title/text
    if not doi and paper.get("title"):
        doi = extract_doi_from_text(paper["title"]) or ""

    # 3. Enrich from DOI
    enriched = None
    if doi:
        enriched = _cached_enrich_from_doi(doi)
        if enriched and enriched.doi:
            # Title
            new_title = enriched.title or ""
            if _should_replace_title(paper.get("title", ""), new_title):
                result["changes"]["title"] = new_title
            elif new_title and not paper.get("title"):
                result["changes"]["title"] = new_title

            # Year
            if enriched.year is not None and paper.get("year") is None:
                result["changes"]["year"] = enriched.year

            # Authors
            if enriched.authors and not paper.get("authors"):
                result["changes"]["authors"] = enriched.authors
                result["changes"]["first_author"] = enriched.first_author

            # Venue
            if enriched.venue and not paper.get("venue"):
                result["changes"]["venue"] = enriched.venue

            # Metadata source
            result["changes"]["metadata_source"] = enriched.source
            result["changes"]["metadata_confidence"] = enriched.confidence

            # Warnings from enrichment
            result["warnings"].extend(enriched.warnings)

    # 4. Generate proposed_paper_id from enriched data
    final_year = result["changes"].get("year", paper.get("year"))
    final_title = result["changes"].get("title", paper.get("title", ""))
    final_authors = result["changes"].get("authors", paper.get("authors", []))
    chinese_title = paper.get("chinese_title", "")

    if final_title and (final_year or final_authors):
        result["proposed_paper_id"] = generate_paper_id(
            year=final_year,
            title=final_title,
            authors=final_authors if final_authors else None,
            chinese_title=chinese_title,
        )

    result["enriched"] = bool(result["changes"])
    return result


def enrich_library(
    *,
    domain: str = "",
    apply: bool = False,
    catalog_path: Path = CATALOG_PATH,
    papers_dir: Path = PAPERS_DIR,
) -> dict:
    """Run enrichment across the entire library catalog."""
    cat_data = json.loads(catalog_path.read_text(encoding="utf-8"))
    papers = cat_data.get("papers", [])

    if domain:
        papers = [p for p in papers if domain in (p.get("domains") or [])]

    results = []
    total = len(papers)
    enriched_count = 0

    for i, paper in enumerate(papers):
        paper_id = paper.get("paper_id", "?")
        logger.info(f"[{i+1}/{total}] {paper_id}")

        # Read paper.md if available
        paper_md_text = ""
        paper_md_path = papers_dir / paper_id / "paper.md"
        if paper_md_path.exists():
            try:
                paper_md_text = paper_md_path.read_text(encoding="utf-8")
            except Exception:
                pass

        result = enrich_catalog_entry(paper, paper_md_text=paper_md_text, dry_run=not apply)
        results.append(result)

        if result["enriched"]:
            enriched_count += 1
            if apply:
                # Write changes back to paper dict
                for key, val in result["changes"].items():
                    paper[key] = val
                if result["proposed_paper_id"]:
                    paper.setdefault("metadata", {})
                    paper["proposed_paper_id"] = result["proposed_paper_id"]
                logger.info(f"  [ENRICHED] {list(result['changes'].keys())}")
            else:
                logger.info(f"  [WOULD ENRICH] {list(result['changes'].keys())}")
            if result["warnings"]:
                for w in result["warnings"]:
                    logger.warning(f"  [WARN] {w}")
        else:
            logger.info(f"  (no changes)")

    # Write back if apply
    if apply and enriched_count > 0:
        cat_data["papers"] = papers
        cat_data["updated_at"] = datetime.now().isoformat(timespec="seconds")
        atomic_write_json(catalog_path, cat_data, indent=2)
        logger.info(f"Catalog written: {catalog_path}")
        logger.info("Next: run 'python scripts/migrate_to_domain_library.py --apply' to rebuild domain views")

    return {
        "total": total,
        "enriched": enriched_count,
        "results": results,
        "applied": apply and enriched_count > 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Enrich library catalog metadata from DOI.")
    parser.add_argument("--domain", default="", help="limit to specific domain")
    parser.add_argument("--apply", action="store_true", help="write changes to catalog")
    args = parser.parse_args()

    summary = enrich_library(domain=args.domain, apply=args.apply)

    print(f"\n{'='*60}")
    print(f"Total papers scanned: {summary['total']}")
    print(f"Enriched: {summary['enriched']}")
    print(f"Applied: {summary['applied']}")
    print(f"Crossref API calls: {len(_crossref_cache)}")
    print(f"{'='*60}")

    if not args.apply:
        logger.info("[dry-run] use --apply to write changes")
        logger.info("After --apply, run: python scripts/migrate_to_domain_library.py --apply")

    return 0


if __name__ == "__main__":
    sys.exit(main())
