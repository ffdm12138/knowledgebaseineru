"""多领域 catalog compact 去重 CLI。

加载指定领域 catalog，compact 去重后输出 JSON，并打印统计。
用于多领域选文进入写作前去重。
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger

from config.settings import DOMAIN_CATALOG_DIR
from src.domain_catalog import (
    compact_catalog_entries,
    compact_summary,
    load_domain_catalogs,
)
from src.library_index import VALID_DOMAINS


def main() -> int:
    parser = argparse.ArgumentParser(description="Compact and dedupe multiple domain catalogs.")
    parser.add_argument("--domains", nargs="+", required=True, help="要合并的领域 id 列表")
    parser.add_argument("--output", type=Path, default=None, help="输出 JSON 路径（默认仅打印）")
    parser.add_argument("--domain-dir", type=Path, default=None)
    args = parser.parse_args()

    for d in args.domains:
        if d not in VALID_DOMAINS:
            logger.error(f"invalid domain_id: {d}; valid: {sorted(VALID_DOMAINS)}")
            return 1

    domain_dir = args.domain_dir or DOMAIN_CATALOG_DIR
    raw_entries = load_domain_catalogs(args.domains, domain_dir=domain_dir)
    compacted = compact_catalog_entries(raw_entries)
    summary = compact_summary(raw_entries, compacted)

    logger.info(f"原始条目数: {summary['raw_count']}")
    logger.info(f"去重后条目数: {summary['compacted_count']}")
    logger.info(f"重复文献数: {summary['duplicate_count']}")
    for pid, domains in summary["per_paper_domains"].items():
        if len(domains) > 1:
            logger.info(f"  重复文献 {pid} 出现在领域: {domains}")

    output = {
        "domains": args.domains,
        "summary": summary,
        "papers": compacted,
    }
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info(f"compact catalog written: {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
