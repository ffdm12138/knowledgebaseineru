"""Create a domain-aware library index and per-domain catalogs.

Default mode is dry-run. Use --apply to write files.
"""
import argparse
import json
import os
import sys
from copy import deepcopy
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger

from config.settings import (
    CATALOG_PATH,
    DOMAIN_CATALOG_DIR,
    LIBRARY_INDEX_PATH,
    MANIFEST_PATH,
)
from src.library_index import DOMAIN_REGISTRY, LibraryIndex


PRIMARY_BY_PREFIX = {
    "1982_schmidt": "blowing_snow_physics",
    "1988_dery": "blowing_snow_physics",
    "1999_dery": "blowing_snow_physics",
    "2000_nishimura": "blowing_snow_physics",
    "2010_gordon": "blowing_snow_physics",
    "2017_comola": "blowing_snow_physics",
    "2025_huang": "blowing_snow_physics",
    "2026_viaro": "blowing_snow_physics",
    "1999_shao": "aeolian_snow_transport",
    "2000_sugiura": "aeolian_snow_transport",
    "2008_wang": "aeolian_snow_transport",
    "2021_zheng": "aeolian_snow_transport",
    "2023_wang": "aeolian_snow_transport",
}

SECONDARY_BY_PREFIX = {
    "2000_sugiura": ["blowing_snow_physics"],
    "2023_wang": ["abl_pbl"],
    "2026_viaro": ["abl_pbl"],
}


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _atomic_write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    json.loads(tmp.read_text(encoding="utf-8"))
    os.replace(tmp, path)


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    if not tmp.read_text(encoding="utf-8").strip():
        raise RuntimeError(f"refusing to write empty file: {path}")
    os.replace(tmp, path)


def _domains_for_paper_id(paper_id: str) -> tuple[str, list[str]]:
    primary = ""
    secondary = []
    for prefix, domain in PRIMARY_BY_PREFIX.items():
        if paper_id.startswith(prefix):
            primary = domain
            break
    for prefix, domains in SECONDARY_BY_PREFIX.items():
        if paper_id.startswith(prefix):
            secondary = domains
            break
    if not primary:
        primary = "blowing_snow_physics"
    domains = [primary]
    for d in secondary:
        if d not in domains:
            domains.append(d)
    return primary, domains


def _bib_text(papers: list[dict]) -> str:
    blocks = []
    for p in papers:
        bibtex = ((p.get("citation") or {}).get("bibtex") or "").strip()
        if bibtex:
            blocks.append(bibtex)
    return "% Generated from domain-aware literature catalog. Do not edit by hand.\n\n" + "\n\n".join(blocks) + "\n"


def build_domain_library(
    catalog_data: dict,
    manifest_data: dict,
) -> tuple[dict, dict, dict[str, dict], dict[str, str], str]:
    """Return updated catalog, index, per-domain catalogs, bib texts, global bib."""
    updated_catalog = deepcopy(catalog_data)
    updated_papers = []

    for paper in updated_catalog.get("papers", []):
        p = deepcopy(paper)
        paper_id = p.get("paper_id", "")
        # 优先沿用 catalog 条目已有的 primary_domain/domains（新入库文献由 import 流程写入）；
        # 仅当缺失时回退到 legacy 前缀映射（13 篇历史文献）。
        existing_primary = (p.get("primary_domain") or "").strip()
        existing_domains = list(p.get("domains") or [])
        if existing_primary and existing_domains:
            primary, domains = existing_primary, existing_domains
        else:
            primary, domains = _domains_for_paper_id(paper_id)
        p["primary_domain"] = primary
        p["domains"] = domains
        updated_papers.append(p)

    updated_catalog["papers"] = updated_papers
    library_index = LibraryIndex.build_from_catalog_and_manifest(updated_catalog, manifest_data)

    domain_catalogs = {}
    domain_bibs = {}
    for domain_id, info in DOMAIN_REGISTRY.items():
        label = info["label"]
        # 领域视图层：收录所有 domains 中声明该领域的文献（可跨领域重复索引）
        papers = []
        for p in updated_papers:
            if domain_id in (p.get("domains") or []):
                view_entry = deepcopy(p)
                view_entry["domain_view"] = {
                    "domain_id": domain_id,
                    "is_primary_domain": p.get("primary_domain") == domain_id,
                    "canonical_paper_id": p.get("paper_id", ""),
                }
                papers.append(view_entry)
        domain_catalogs[domain_id] = {
            "version": updated_catalog.get("version", "0.1"),
            "description": f"Domain catalog: {label}",
            "domain_id": domain_id,
            "domain_name": label,
            "papers": papers,
        }
        domain_bibs[domain_id] = _bib_text(papers)

    global_bib = _bib_text(updated_papers)
    return updated_catalog, library_index, domain_catalogs, domain_bibs, global_bib


def apply_domain_library(
    updated_catalog: dict,
    library_index: dict,
    domain_catalogs: dict[str, dict],
    domain_bibs: dict[str, str],
    global_bib: str,
    catalog_path: Path = CATALOG_PATH,
    index_path: Path = LIBRARY_INDEX_PATH,
    domain_dir: Path = DOMAIN_CATALOG_DIR,
) -> None:
    _atomic_write_json(catalog_path, updated_catalog)
    _atomic_write_json(index_path, library_index)
    for domain_id, catalog in domain_catalogs.items():
        base = domain_dir / domain_id
        _atomic_write_json(base / "literature_catalog.json", catalog)
        _atomic_write_text(base / "references.bib", domain_bibs[domain_id])
    _atomic_write_text(catalog_path.parent / "references.bib", global_bib)


def main() -> int:
    parser = argparse.ArgumentParser(description="Create domain-aware literature library files.")
    parser.add_argument("--apply", action="store_true", help="write generated files")
    parser.add_argument("--catalog", type=Path, default=CATALOG_PATH)
    parser.add_argument("--manifest", type=Path, default=MANIFEST_PATH)
    parser.add_argument("--index", type=Path, default=LIBRARY_INDEX_PATH)
    parser.add_argument("--domain-dir", type=Path, default=DOMAIN_CATALOG_DIR)
    args = parser.parse_args()

    catalog_data = _load_json(args.catalog)
    manifest_data = _load_json(args.manifest)
    updated_catalog, index, domain_catalogs, domain_bibs, global_bib = build_domain_library(
        catalog_data, manifest_data
    )

    logger.info(f"papers: {len(updated_catalog.get('papers', []))}")
    for domain_id, catalog in domain_catalogs.items():
        logger.info(f"{domain_id}: {len(catalog.get('papers', []))} papers")
    logger.info(f"will write: {args.catalog}")
    logger.info(f"will write: {args.index}")
    for domain_id in DOMAIN_REGISTRY:
        logger.info(f"will write: {args.domain_dir / domain_id / 'literature_catalog.json'}")
        logger.info(f"will write: {args.domain_dir / domain_id / 'references.bib'}")
    logger.info(f"will write: {args.catalog.parent / 'references.bib'}")

    if not args.apply:
        logger.info("dry-run only; pass --apply to write files")
        return 0

    apply_domain_library(
        updated_catalog,
        index,
        domain_catalogs,
        domain_bibs,
        global_bib,
        catalog_path=args.catalog,
        index_path=args.index,
        domain_dir=args.domain_dir,
    )
    logger.info("domain library migration written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
