"""手动本地 PDF 注册：复制到 pending 目录 + 写 sidecar。

不转换、不入 catalog。后续由 import_pending_pdf.py --apply 正式入库。
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger

from config.settings import RAW_DIR
from src.library_index import VALID_DOMAINS
from src.services.pdf_acquisition_service import PdfAcquisitionService


def main() -> int:
    parser = argparse.ArgumentParser(description="Register a local PDF as pending.")
    parser.add_argument("pdf_path", type=Path, help="path to the local PDF file")
    parser.add_argument("--doi", default="", help="DOI")
    parser.add_argument("--title", default="", help="paper title")
    parser.add_argument("--year", type=int, default=None, help="publication year")
    parser.add_argument("--domain", choices=sorted(VALID_DOMAINS), required=True)
    parser.add_argument("--domains", nargs="+", default=None, help="all domains membership")
    args = parser.parse_args()

    if not args.pdf_path.exists():
        logger.error(f"file not found: {args.pdf_path}")
        return 1

    service = PdfAcquisitionService(raw_dir=RAW_DIR)
    result = service.register_local_pdf(
        args.pdf_path,
        domain_id=args.domain,
        domains=args.domains,
        doi=args.doi,
        title=args.title,
        year=args.year,
        source_kind="local_manual",
    )

    logger.info(f"registered: {result['pending_pdf']}")
    logger.info(f"  doi: {args.doi or '(none)'}")
    logger.info(f"  sha256: {result['sidecar']['sha256']}")
    logger.info(f"  sidecar: {result['sidecar_path']}")
    logger.info("next: use scripts/import_pending_pdf.py --apply to import")
    return 0


if __name__ == "__main__":
    sys.exit(main())
