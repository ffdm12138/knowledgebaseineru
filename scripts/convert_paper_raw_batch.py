"""Batch convert v2 data/paper_raw sources with guarded MinerU input paths."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger

from config.settings import PAPER_RAW_DIR
from config.settings import MINERU_BACKEND, MINERU_EFFORT, MINERU_METHOD
from src.services.v2_library import PaperRawConverter


def _source_ids(root: Path, args) -> list[str]:
    if args.source_id:
        return [args.source_id]
    if args.source_ids:
        return args.source_ids
    if args.all:
        return sorted(p.name for p in root.iterdir() if p.is_dir() and p.name.isdigit() and len(p.name) == 6)
    raise ValueError("--source-id, --source-ids, or --all is required")


def _preflight_status(root: Path, source_id: str) -> str:
    path = root / source_id / ".import_status.json"
    if not path.exists():
        return ""
    try:
        return str((json.loads(path.read_text(encoding="utf-8")) or {}).get("status") or "")
    except Exception:
        return ""


def _print_runtime_summary(cfg) -> None:
    cuda_devices = cfg.cuda_visible_devices or "unset"
    print(
        "MinerU runtime:\n"
        f"  runner: {cfg.runner.value}\n"
        f"  backend: {MINERU_BACKEND}\n"
        f"  method: {MINERU_METHOD}\n"
        f"  effort: {MINERU_EFFORT}\n"
        f"  require_gpu: {str(cfg.require_gpu).lower()}\n"
        f"  allow_cpu: {str(cfg.allow_cpu).lower()}\n"
        f"  cuda_visible_devices: {cuda_devices}",
        file=sys.stderr,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert v2 paper_raw PDFs into md/images.")
    parser.add_argument("--source-id", default=None)
    parser.add_argument("--source-ids", nargs="+", default=None)
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--paper-raw-dir", type=Path, default=PAPER_RAW_DIR)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--allow-cpu", action="store_true",
                        help="debug only: set MINERU_ALLOW_CPU=true for this process")
    parser.add_argument("--only-preflight-ready", action="store_true",
                        help="only convert paper_raw folders whose .import_status.json status is ready_for_convert")
    parser.add_argument("--report", type=Path, default=None)
    args = parser.parse_args()

    if args.allow_cpu:
        os.environ["MINERU_ALLOW_CPU"] = "true"
        os.environ["MINERU_REQUIRE_GPU"] = "false"
        print(
            "WARNING: --allow-cpu enables debug-only CPU/no-GPU fallback. "
            "This is not formal MinerU ingest SOP.",
            file=sys.stderr,
        )

    write = args.apply and not args.dry_run
    source_ids = _source_ids(args.paper_raw_dir, args)

    from src.mineru_runtime import runtime_config_from_env, MinerURunner
    cfg = runtime_config_from_env()
    _print_runtime_summary(cfg)
    if write and not cfg.require_gpu:
        print(
            "WARNING: MINERU_REQUIRE_GPU is false. Normal ingest conversion requires GPU. "
            "Use this only for debugging. Set MINERU_REQUIRE_GPU=true for formal ingestion.",
            file=sys.stderr,
        )

    # warn when batch-converting >1 PDF with cold-start CLI runner
    if len(source_ids) > 1:
        try:
            if cfg.runner == MinerURunner.CLI:
                print(
                    f"  ** WARNING: Batch conversion is using MINERU_RUNNER=cli on"
                    f" {len(source_ids)} sources; this may cold-start MinerU per PDF."
                    f" Prefer MINERU_RUNNER=cli_api_proxy with a persistent mineru-api"
                    f" service for large batches.",
                    file=sys.stderr,
                )
        except Exception:
            pass  # never let a warning break conversion

    converter = PaperRawConverter(args.paper_raw_dir)
    report = []
    for source_id in source_ids:
        item = {"source_id": source_id, "status": "planned"}
        if args.only_preflight_ready:
            preflight_status = _preflight_status(args.paper_raw_dir, source_id)
            item["preflight_status"] = preflight_status
            if preflight_status != "ready_for_convert":
                item["status"] = "skipped"
                item["reason"] = "preflight status is not ready_for_convert"
                report.append(item)
                continue
        logger.info("{} convert paper_raw/{}", "CONVERT" if write else "DRY-RUN", source_id)
        if write:
            try:
                result = converter.convert(source_id)
                item.update(result)
                item["status"] = "converted" if result.get("success") else "failed"
            except Exception as exc:
                item.update({"status": "failed", "error": str(exc)})
                logger.error("convert failed for {}: {}", source_id, exc)
        report.append(item)

    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"applied": write, "items": report}, ensure_ascii=False, indent=2))
    return 1 if any(i["status"] == "failed" for i in report) else 0


if __name__ == "__main__":
    raise SystemExit(main())
