"""批量注册外部 PDF 文件夹到 pending 队列。

Thin wrapper — 不写 manifest/catalog/library_index/domain catalog/bib，不调 MinerU，
不绕过 duplicate detection。每个 PDF 走现有的 PdfAcquisitionService / PendingImportService。

用法:
  conda activate mineru

  # 1. 列出 PDF + 自动推导元数据（dry-run，不写任何文件）
  python scripts/bulk_register_manual_pdfs.py ./import --domain blowing_snow_physics

  # 2. 使用 metadata CSV（filename,title,doi,year,domain）
  python scripts/bulk_register_manual_pdfs.py ./import --csv metadata.csv

  # 3. 登记到 pending（不转换，不入 catalog）
  python scripts/bulk_register_manual_pdfs.py ./import --domain blowing_snow_physics --apply

  # 4. 登记到 pending + 正式导入（需 metadata，触发 MinerU 转换）
  python scripts/bulk_register_manual_pdfs.py ./import --csv metadata.csv --apply --import
"""

import argparse
import csv
import re
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger

from config.settings import RAW_DIR
from src.library_index import VALID_DOMAINS
from src.services.pdf_acquisition_service import PdfAcquisitionService
from src.services.pending_import_service import import_pending_pdf

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

YEAR_RE = re.compile(r"(?:^|[^0-9])(1[89][0-9]{2}|20[0-9]{2})(?:[^0-9]|$)")


def _extract_year(filename: str) -> Optional[int]:
    m = YEAR_RE.search(filename)
    return int(m.group(1)) if m else None


def _guess_domain(filename: str) -> Optional[str]:
    """Best-effort domain guess from Chinese / English keywords."""
    text = filename.lower()
    # 边界层 / 大气边界层 / PBL / ABL
    if any(kw in text for kw in ("边界层", "pbl", "abl", "大气边界层", "行星边界层",
                                  "topmodel", "wep", "mike she", "prevah",
                                  "湍流边界层", "对流边界层", "超声风速")):
        return "abl_pbl"
    # 风吹雪 / 雪粒 / 跃移 / 悬移 / 升华 / blowing snow / snow drift
    if any(kw in text for kw in ("风吹雪", "雪粒", "跃移", "悬移", "吹雪", "飘雪",
                                  "blowing snow", "snow drift", "snow particle",
                                  "snow transport", "snowpack", "积雪", "雪深",
                                  "融雪", "snowmelt", "雪升华", "snow sublimation",
                                  "cryowrf", "snowmodel", "alpine3d", "crocus",
                                  "snow distribution", "snow cover", "snow accumulation",
                                  "雪飘移", "雪漂移", "风吹雪输运", "吹雪模型",
                                  "风吹雪数值", "风吹雪模拟", "mott", "vionnet")):
        return "blowing_snow_physics"
    # 风沙 / 沙尘 / 颗粒输运 / aeolian / sediment
    if any(kw in text for kw in ("风沙", "沙尘", "沙丘", "颗粒输运", "颗粒阻力",
                                  "aeolian", "sediment transport", "dune",
                                  "saltation", "suspension", "sand transport",
                                  "粒径分布", "particle", "fragmentation")):
        return "aeolian_snow_transport"
    return None


def _load_csv(csv_path: Optional[str]) -> dict[str, dict]:
    """Parse CSV with columns: filename, title, doi, year, domain.
    Returns dict keyed by basename (case-insensitive).
    """
    if not csv_path:
        return {}
    table: dict[str, dict] = {}
    with open(csv_path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            fn = (row.get("filename") or "").strip()
            if not fn:
                continue
            domain = (row.get("domain") or "").strip()
            # validate domain early
            if domain and domain not in VALID_DOMAINS:
                logger.warning(f"CSV: invalid domain {domain!r} for {fn}, skipping")
                continue
            year_str = (row.get("year") or "").strip()
            year_val: Optional[int] = None
            if year_str:
                try:
                    year_val = int(year_str)
                except ValueError:
                    pass
            table[fn.lower()] = {
                "title": (row.get("title") or "").strip(),
                "doi": (row.get("doi") or "").strip(),
                "year": year_val,
                "domain": domain,
            }
    return table


# ---------------------------------------------------------------------------
# per-file processing
# ---------------------------------------------------------------------------

def _status_label(status: str) -> str:
    return {
        "registered": "[REGISTERED]", "imported": "[IMPORTED]",
        "duplicate": "[DUPLICATE]", "needs_confirmation": "[NEEDS_CONFIRM]",
        "failed": "[FAILED]", "skipped_no_metadata": "[SKIPPED]",
        "skipped_non_pdf": "[NON_PDF]",
    }.get(status, "[UNKNOWN]")


def process_one(
    pdf: Path,
    *,
    service: PdfAcquisitionService,
    csv_meta: dict[str, dict],
    default_domain: str,
    apply: bool,
    do_import: bool,
) -> dict:
    """Register + optionally import a single PDF.  Never writes directly to
    manifest/catalog/index.  Returns status dict with outcome key."""
    name = pdf.name
    meta = csv_meta.get(name.lower(), {})

    # decide domain
    domain = meta.get("domain") or default_domain
    if domain not in VALID_DOMAINS:
        return {"filename": name, "status": "skipped_no_metadata",
                "reason": f"no valid domain (got {domain!r})"}

    # decide metadata
    title = meta.get("title") or pdf.stem
    doi = meta.get("doi") or ""
    year = meta.get("year") or _extract_year(name)

    # --- register to pending ---
    if not apply:
        logger.info(f"[dry-run] would register: {name}  domain={domain}  title={title[:60]}")
        return {"filename": name, "status": "registered", "title": title,
                "doi": doi, "year": year, "domain": domain}

    try:
        reg = service.register_local_pdf(
            pdf,
            domain_id=domain,
            doi=doi,
            title=title,
            year=year,
            source_kind="local_manual",
        )
    except Exception as exc:
        logger.error(f"register failed: {name} — {exc}")
        return {"filename": name, "status": "failed", "error": str(exc)}

    pending_path = reg["pending_pdf"]
    logger.info(f"registered: {name} -> {pending_path}")

    # --- import (optional) ---
    if not do_import:
        return {"filename": name, "status": "registered", "title": title,
                "doi": doi, "year": year, "domain": domain,
                "pending_pdf": str(pending_path)}

    # import requires at least title + year
    if not title or not year:
        logger.warning(f"skipping import (no metadata): {name} — registered as pending only")
        return {"filename": name, "status": "registered",
                "title": title, "doi": doi, "year": year, "domain": domain,
                "pending_pdf": str(pending_path),
                "reason": "insufficient metadata for import"}

    try:
        result = import_pending_pdf(
            pending_path,
            domain=domain,
            title=title,
            doi=doi,
            year=year,
            apply=True,
        )
    except Exception as exc:
        logger.error(f"import failed: {name} — {exc}")
        return {"filename": name, "status": "failed", "error": str(exc),
                "title": title, "doi": doi, "year": year, "domain": domain,
                "pending_pdf": str(pending_path)}

    return {
        "filename": name,
        "status": result.get("status", "failed"),
        "paper_id": result.get("paper_id") or result.get("canonical_paper_id", ""),
        "title": title, "doi": doi, "year": year, "domain": domain,
        "pending_pdf": str(pending_path),
    }


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="批量注册外部 PDF 到 pending 队列，可选正式导入",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # dry-run 扫描
  python scripts/bulk_register_manual_pdfs.py ./import --domain blowing_snow_physics

  # 登记到 pending
  python scripts/bulk_register_manual_pdfs.py ./import --domain blowing_snow_physics --apply

  # 登记 + 导入（需 metadata）
  python scripts/bulk_register_manual_pdfs.py ./import --csv meta.csv --apply --import
""",
    )
    parser.add_argument("input_dir", type=Path, help="包含 PDF 的外部文件夹")
    parser.add_argument("--domain", default="", help="默认领域（CSV 中有 domain 列时可选）")
    parser.add_argument("--csv", default=None, help="metadata CSV: filename,title,doi,year,domain")
    parser.add_argument("--apply", action="store_true", help="实际写入（默认 dry-run）")
    parser.add_argument("--import", dest="do_import", action="store_true",
                        help="登记后立即正式导入（需 metadata，触发 MinerU 转换）")
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    if not input_dir.is_dir():
        logger.error(f"not a directory: {input_dir}")
        return 1

    csv_meta = _load_csv(args.csv)
    if csv_meta:
        logger.info(f"loaded {len(csv_meta)} metadata entries from CSV")

    # resolve default domain
    default_domain = args.domain
    if not default_domain and not csv_meta:
        logger.error("either --domain or --csv (with domain column) is required")
        return 1

    pdfs = sorted(
        [p for p in input_dir.iterdir()
         if p.is_file() and p.suffix.lower() == ".pdf"]
    )

    if not pdfs:
        logger.warning(f"no PDF files found in {input_dir}")
        return 0

    logger.info(f"found {len(pdfs)} PDF(s) in {input_dir}")
    logger.info(f"mode: {'apply' if args.apply else 'dry-run'}"
                 f"{' + import' if args.do_import else ''}")

    service = PdfAcquisitionService(raw_dir=RAW_DIR)
    results: list[dict] = []

    for i, pdf in enumerate(pdfs, 1):
        logger.info(f"[{i}/{len(pdfs)}] {pdf.name}")
        try:
            r = process_one(
                pdf,
                service=service,
                csv_meta=csv_meta,
                default_domain=default_domain,
                apply=args.apply,
                do_import=args.do_import,
            )
        except Exception as exc:
            r = {"filename": pdf.name, "status": "failed", "error": str(exc)}
        results.append(r)

    # --- summary ---
    counts: dict[str, int] = {}
    for r in results:
        s = r.get("status", "failed")
        counts[s] = counts.get(s, 0) + 1

    print("\n" + "=" * 60)
    print("  SUMMARY")
    print("=" * 60)
    for status, label in [("imported", "[IMPORTED]"), ("registered", "[REGISTERED]"),
                           ("duplicate", "[DUPLICATE]"), ("needs_confirmation", "[NEEDS_CONFIRM]"),
                           ("failed", "[FAILED]"), ("skipped_no_metadata", "[SKIPPED]"),
                           ("skipped_non_pdf", "[NON_PDF]")]:
        if status in counts:
            print(f"  {label:20s} {counts[status]}")
    print(f"  {'─' * 35}")
    print(f"  TOTAL: {len(results)}")
    print("=" * 60)

    # detailed report
    for status in ("failed", "needs_confirmation", "skipped_no_metadata"):
        entries = [r for r in results if r.get("status") == status]
        if entries:
            print(f"\n[{status}]")
            for e in entries:
                print(f"  {e['filename']}")
                if e.get("error"):
                    print(f"    error: {e['error']}")
                if e.get("reason"):
                    print(f"    reason: {e['reason']}")

    if args.do_import:
        imported = [r for r in results if r.get("status") == "imported"]
        if imported:
            print(f"\n[imported paper_ids]")
            for e in imported:
                print(f"  {e.get('paper_id', '?')}  ← {e['filename']}")

    return 1 if counts.get("failed", 0) > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
