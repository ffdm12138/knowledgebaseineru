"""批量转换文档目录 (MinerU 3.4)

重构后流程：raw -> MinerU tmp -> cleaner -> papers/<paper_id>/ -> registry
不再做 chunk / embedding / 入库。默认 CLI runner。

用法:
  conda activate mineru

  # 批量转换（CLI runner，日常推荐）
  python batch_convert.py data/raw

  # 可选参数
  --backend pipeline|hybrid-engine    默认从config读取
  --method auto|ocr|txt               默认auto
  --effort medium|high                仅hybrid-engine生效
  --api-url URL                       实验性接口（HTTP upload adapter 未实现，不推荐日常使用）
"""
import sys
import argparse
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from loguru import logger
from config.settings import (
    MINERU_TMP_DIR, SUPPORTED_FORMATS,
    MINERU_BACKEND, MINERU_EFFORT, MINERU_METHOD, MINERU_LANG,
)
from src.cleaner import MinerUOutputCleaner
from src.manifest import PaperManifest
from src.naming import derive_paper_id

cleaner = MinerUOutputCleaner()
manifest = PaperManifest()
manifest.migrate()


def main():
    parser = argparse.ArgumentParser(description="批量转换文档目录")
    parser.add_argument("input_dir", help="文档所在目录 (如 data/raw)")
    parser.add_argument("--backend", default=MINERU_BACKEND, choices=["pipeline", "vlm-engine", "hybrid-engine"])
    parser.add_argument("--method", default=MINERU_METHOD, choices=["auto", "ocr", "txt"])
    parser.add_argument("--effort", default=MINERU_EFFORT, choices=["medium", "high"])
    parser.add_argument("--api-url", default=None, help="mineru-api 服务地址")
    args = parser.parse_args()
    # 普通模式禁止 backend/effort 覆盖（产品固定 hybrid-engine + medium）
    from config.settings import enforce_backend_effort_override
    enforce_backend_effort_override(parser, args)

    input_dir = Path(args.input_dir)
    if not input_dir.exists():
        logger.error(f"目录不存在: {input_dir}")
        sys.exit(1)

    files = sorted([f for f in input_dir.iterdir() if f.suffix.lower() in SUPPORTED_FORMATS])
    if not files:
        logger.error(f"没有支持的文件: {input_dir}")
        sys.exit(1)

    logger.info(f"找到 {len(files)} 个文件")
    if args.api_url:
        logger.warning(
            f"使用 API runner: {args.api_url}; HTTP upload adapter 未实现时会结构化失败，不会静默回退 CLI"
        )

    import time as _time
    elapsed_records = []  # (filename, paper_id, elapsed_sec, success)
    skipped_count = 0
    failed_count = 0

    for i, f in enumerate(files, 1):
        paper_id = derive_paper_id(f.name)

        # sha256 去重（与 watcher 一致）
        from src.file_fingerprint import compute_sha256
        sha = compute_sha256(f)
        existing_by_sha = manifest.find_by_sha256(sha)
        if existing_by_sha and existing_by_sha.get("status") in {"converted", "unregistered_converted"}:
            logger.info(f"[{i}/{len(files)}] 跳过 (sha256 已转换): {f.name} = {existing_by_sha['paper_id']}")
            skipped_count += 1
            continue
        # paper_id 冲突：同名但不同内容 → 加后缀
        if manifest.has(paper_id):
            existing = manifest.get(paper_id)
            if existing.get("sha256") and existing["sha256"] != sha:
                paper_id = f"{paper_id}_{sha[:8]}"
                logger.warning(f"  paper_id 冲突且 sha256 不同 → {paper_id}")

        if manifest.has(paper_id) and Path(manifest.get(paper_id)["markdown"]).exists() \
                and manifest.get(paper_id).get("sha256") == sha:
            logger.info(f"[{i}/{len(files)}] 跳过 (已转换): {f.name} -> {paper_id}")
            skipped_count += 1
            continue

        logger.info(f"[{i}/{len(files)}] 处理: {f.name} -> {paper_id} | sha256={sha[:12]} | runner={'api' if args.api_url else 'cli'}")
        t0 = _time.time()
        from src.services.ingest_service import IngestService
        ing = IngestService(manifest=manifest)
        conv = ing.convert_file(
            pdf_path=f, paper_id=paper_id, backend=args.backend,
            method=args.method, lang=MINERU_LANG,
            effort=args.effort, api_url=args.api_url, overwrite=True,
        )
        elapsed = _time.time() - t0
        if not conv["success"]:
            logger.error(f"  转换失败 ({elapsed:.0f}s): {conv.get('error')}")
            elapsed_records.append((f.name, paper_id, elapsed, False))
            failed_count += 1
            continue
        logger.info(f"  完成 ({elapsed:.0f}s): {paper_id}")
        elapsed_records.append((f.name, paper_id, elapsed, True))

    # ── 批量转换汇总 ──
    success_times = [e[2] for e in elapsed_records if e[3]]
    if success_times:
        sorted_times = sorted(success_times)
        n = len(sorted_times)
        total_elapsed = sum(sorted_times)
        avg_elapsed = total_elapsed / n
        median_elapsed = sorted_times[n // 2]
        max_elapsed = sorted_times[-1]
        success_records = [e for e in elapsed_records if e[3]]
        slowest_file = max(success_records, key=lambda e: e[2])[0]
        logger.info(
            f"\n[批量转换汇总] total_files={len(files)} converted={n} "
            f"skipped={skipped_count} failed={failed_count}"
        )
        logger.info(
            f"[批量转换汇总] total_elapsed={total_elapsed:.1f}s "
            f"avg={avg_elapsed:.1f}s median={median_elapsed:.1f}s "
            f"max={max_elapsed:.1f}s slowest={slowest_file}"
        )
        if failed_count > 0:
            failed_names = [e[0] for e in elapsed_records if not e[3]]
            logger.info(f"[批量转换汇总] failed_files: {', '.join(failed_names)}")
    elif elapsed_records:
        failed_names = [e[0] for e in elapsed_records if not e[3]]
        logger.info(
            f"\n[批量转换汇总] total_files={len(files)} all_failed "
            f"skipped={skipped_count} failed={failed_count} "
            f"failed_files: {', '.join(failed_names)}"
        )

    stats = manifest.stats()
    logger.info(f"\n批量转换完成！文献库: {stats['total_papers']} 篇, "
                f"{stats['total_md_chars']} 字符, {stats['total_images']} 图")


if __name__ == "__main__":
    main()
