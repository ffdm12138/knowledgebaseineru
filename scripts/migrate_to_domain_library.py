"""Create a domain-aware library index and per-domain catalogs.

Thin CLI wrapper around src.services.domain_library_service.
Default mode is dry-run. Use --apply to write files.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger

from config.settings import CATALOG_PATH, DOMAIN_CATALOG_DIR, LIBRARY_INDEX_PATH, MANIFEST_PATH
from src.library_index import DOMAIN_REGISTRY
from src.services.domain_library_service import (
    _load_json,
    apply_domain_library,
    build_domain_library,
)


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
