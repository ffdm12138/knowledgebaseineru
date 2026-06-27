"""手动本地 PDF 注册：复制到 pending 目录 + 写 sidecar。

不转换、不入 catalog。后续由 import_pending_pdf.py --apply 正式入库。
"""
import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger

from config.settings import RAW_DIR
from src.library_index import VALID_DOMAINS


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

    # compute sha256
    sha256 = hashlib.sha256()
    sha256.update(args.pdf_path.read_bytes())
    sha256_hex = sha256.hexdigest()

    # copy to pending
    pending_dir = RAW_DIR / args.domain / "pending"
    pending_dir.mkdir(parents=True, exist_ok=True)
    safe_name = args.pdf_path.name
    target = pending_dir / safe_name
    shutil.copy2(args.pdf_path, target)

    # write sidecar
    sidecar = {
        "doi": args.doi,
        "title": args.title or args.pdf_path.stem,
        "year": args.year,
        "domain_id": args.domain,
        "domains": args.domains or [args.domain],
        "pdf_url": "",
        "sha256": sha256_hex,
        "status": "pending",
        "source": "manual_import",
        "access_mode": "local_manual",
        "access_status": "manual",
        "registered_at": datetime.now().isoformat(timespec="seconds"),
    }
    sidecar_path = target.with_suffix(".json")
    sidecar_path.write_text(json.dumps(sidecar, ensure_ascii=False, indent=2), encoding="utf-8")

    logger.info(f"registered: {target}")
    logger.info(f"  doi: {args.doi or '(none)'}")
    logger.info(f"  sha256: {sha256_hex}")
    logger.info(f"  sidecar: {sidecar_path}")
    logger.info("next: use scripts/import_pending_pdf.py --apply to import")
    return 0


if __name__ == "__main__":
    sys.exit(main())
