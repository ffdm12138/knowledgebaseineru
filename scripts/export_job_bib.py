"""从全局 references.bib 抽取指定文献生成 write/<job>/tex/references.bib

用法:
  python scripts/export_job_bib.py --job 001_xxx --keys dery1999_bulk_blowing_snow huang2025_fragmentation_sublimation
  python scripts/export_job_bib.py --job 001_xxx --from-selected   # 用 selected_papers.json 的 bib_key
"""
import sys
import json
import argparse
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from loguru import logger
from src.writer.job_manager import JobManager
from src.writer.bib_manager import export_job_bib


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--job", required=True)
    ap.add_argument("--keys", nargs="*", default=[])
    ap.add_argument("--from-selected", action="store_true")
    args = ap.parse_args()

    jm = JobManager()
    keys = args.keys
    if args.from_selected or not keys:
        sel = jm.job_dir(args.job) / "planning" / "selected_papers.json"
        if sel.exists():
            for it in json.loads(sel.read_text(encoding="utf-8")):
                if it.get("bib_key"):
                    keys.append(it["bib_key"])
    if not keys:
        logger.error("未提供 --keys 也无法从 selected_papers.json 读取")
        return 1
    info = export_job_bib(args.job, keys, jm=jm)
    logger.info(f"导出 {info['count']} 条到 {info['references_bib']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
