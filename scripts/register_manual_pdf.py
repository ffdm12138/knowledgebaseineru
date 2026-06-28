"""手动本地 PDF 注册：复制到 pending 目录 + 写 sidecar。

不转换、不入 catalog。后续由 import_pending_pdf.py --apply 正式入库。

增强功能：
  --auto-metadata：自动提取 DOI + 查询 Crossref 元数据 → sidecar
  --chinese-title：中文标题，参与 proposed_paper_id 生成
  --paper-id：显式 canonical paper_id
  --doi / --title / --year / --authors：手动指定元数据
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger

from config.settings import RAW_DIR
from src.library_index import VALID_DOMAINS
from src.services.metadata_enrichment_service import (
    enrich_from_pdf,
    extract_doi_from_filename,
)
from src.services.pdf_acquisition_service import PdfAcquisitionService
from src.services.paper_id import resolve_paper_id
from src.naming import validate_paper_id


def main() -> int:
    parser = argparse.ArgumentParser(description="Register a local PDF as pending.")
    parser.add_argument("pdf_path", type=Path, help="path to the local PDF file")
    parser.add_argument("--domain", choices=sorted(VALID_DOMAINS), required=True,
                        help="主领域 (primary domain)")
    parser.add_argument("--domains", nargs="+", default=None, help="全部领域 membership")
    parser.add_argument("--doi", default="", help="DOI")
    parser.add_argument("--title", default="", help="paper title")
    parser.add_argument("--year", type=int, default=None, help="publication year")
    parser.add_argument("--authors", nargs="+", default=None, help="author names (space-separated)")
    parser.add_argument("--chinese-title", default="", help="中文标题（用于 paper_id 生成）")
    parser.add_argument("--paper-id", default="", help="显式 canonical paper_id（最高优先级）")
    parser.add_argument("--auto-metadata", action="store_true", default=False,
                        help="自动提取 DOI + 查询 Crossref 元数据")
    parser.add_argument("--no-auto-metadata", action="store_true", default=False,
                        help="禁用自动元数据（默认行为）")
    args = parser.parse_args()

    if not args.pdf_path.exists():
        logger.error(f"file not found: {args.pdf_path}")
        return 1

    # Validate paper_id if provided
    if args.paper_id:
        try:
            validate_paper_id(args.paper_id)
        except ValueError as e:
            logger.error(f"invalid --paper-id: {e}")
            return 1

    all_domains = list(args.domains or [args.domain])
    if args.domain not in all_domains:
        all_domains.insert(0, args.domain)
    for d in all_domains:
        if d not in VALID_DOMAINS:
            logger.error(f"invalid domain: {d}")
            return 1

    # Build sidecar metadata
    doi = args.doi
    title = args.title
    year = args.year
    authors = list(args.authors) if args.authors else None
    chinese_title = args.chinese_title
    enrichment_result = None
    proposed_paper_id = ""
    warnings: list[str] = []

    if args.auto_metadata and not args.no_auto_metadata:
        logger.info("running auto-metadata enrichment...")
        enrichment_result = enrich_from_pdf(
            args.pdf_path,
            chinese_title=chinese_title,
        )
        # Fill gaps from enrichment
        if enrichment_result.doi and not doi:
            doi = enrichment_result.doi
        if enrichment_result.title and not title:
            title = enrichment_result.title
        if enrichment_result.year is not None and year is None:
            year = enrichment_result.year
        if enrichment_result.authors and not authors:
            authors = enrichment_result.authors
        if enrichment_result.first_author:
            pass  # first_author tracked in sidecar
        proposed_paper_id = enrichment_result.proposed_paper_id
        warnings = enrichment_result.warnings
        logger.info(f"  DOI: {doi or '(not found)'}")
        logger.info(f"  Title: {title or '(not found)'}")
        logger.info(f"  Year: {year or '(not found)'}")
        logger.info(f"  Authors: {authors or '(not found)'}")
        logger.info(f"  Proposed paper_id: {proposed_paper_id}")
        if warnings:
            for w in warnings:
                logger.warning(f"  [WARN] {w}")
    elif not doi and not title:
        # Try basic DOI extraction from filename
        doi = extract_doi_from_filename(args.pdf_path.name) or ""
        if doi:
            logger.info(f"DOI extracted from filename: {doi}")

    # Resolve final paper_id for sidecar
    canonical_paper_id = args.paper_id or ""
    if not canonical_paper_id and proposed_paper_id:
        canonical_paper_id = proposed_paper_id

    # Register PDF via PdfAcquisitionService
    service = PdfAcquisitionService(raw_dir=RAW_DIR)
    extra = {}
    if authors:
        extra["authors"] = authors
        extra["first_author"] = authors[0] if authors else ""
    if chinese_title:
        extra["chinese_title"] = chinese_title
    if proposed_paper_id:
        extra["proposed_paper_id"] = proposed_paper_id
    if canonical_paper_id:
        extra["canonical_paper_id"] = canonical_paper_id
    if enrichment_result:
        extra["metadata_source"] = enrichment_result.source
        extra["metadata_confidence"] = enrichment_result.confidence
        if enrichment_result.venue:
            extra["venue"] = enrichment_result.venue
    if warnings:
        extra["warnings"] = warnings

    result = service.register_local_pdf(
        args.pdf_path,
        domain_id=args.domain,
        domains=all_domains,
        doi=doi,
        title=title or args.pdf_path.stem,
        year=year,
        source_kind="local_manual",
    )

    # Re-write sidecar with enriched metadata
    if extra:
        import json
        from src.utils.atomic_io import atomic_write_json
        sidecar_path = Path(result["sidecar_path"])
        if sidecar_path.exists():
            sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
            sidecar.update(extra)
            atomic_write_json(sidecar_path, sidecar, indent=2)

    logger.info(f"registered: {result['pending_pdf']}")
    logger.info(f"  doi: {doi or '(none)'}")
    logger.info(f"  sha256: {result['sidecar']['sha256']}")
    logger.info(f"  sidecar: {result['sidecar_path']}")
    if canonical_paper_id:
        logger.info(f"  canonical_paper_id: {canonical_paper_id}")
    if proposed_paper_id and proposed_paper_id != canonical_paper_id:
        logger.info(f"  proposed_paper_id: {proposed_paper_id}")
    logger.info("next: use scripts/import_pending_pdf.py --apply to import")
    return 0


if __name__ == "__main__":
    sys.exit(main())
