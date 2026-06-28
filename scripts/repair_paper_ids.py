"""修复已导入文献的错误 paper_id / 文件夹名。

识别"疑似错误 paper_id"（如 download / s11433_008_0106_6 / 1-s2.0-...），
根据 catalog / DOI metadata 生成规范 paper_id，并同步更新所有索引。

用法:
  # 全库扫描 dry-run
  python scripts/repair_paper_ids.py

  # 限定领域
  python scripts/repair_paper_ids.py --domain erosion_experiments

  # 限定单篇
  python scripts/repair_paper_ids.py --paper-id old_bad_folder_name

  # 导出 mapping 供人工审核
  python scripts/repair_paper_ids.py --export-mapping repair_mapping.json

  # 从 mapping 文件执行迁移
  python scripts/repair_paper_ids.py --mapping repair_mapping.json --apply

  # 直接重命名单篇
  python scripts/repair_paper_ids.py --rename old_id:new_id --apply

  # 执行（带备份）
  python scripts/repair_paper_ids.py --apply --backup
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger

from src.naming import validate_paper_id
from src.services.paper_id_migration_service import PaperIdMigrationService


def _print_table(plans) -> None:
    """Print a formatted table of migration plans."""
    if not plans:
        print("\n  (no bad paper_ids found)")
        return
    print(f"\n{'='*100}")
    print(f"{'old_paper_id':<40} {'->':>3} {'new_paper_id':<40}  {'apply':>5}")
    print(f"{'-'*100}")
    for p in plans:
        flag = "YES" if p.apply else "SKIP"
        print(f"{p.old_paper_id:<40} {'->':>3} {p.new_paper_id:<40}  {flag:>5}")
    print(f"{'='*100}")
    total = len(plans)
    to_apply = sum(1 for p in plans if p.apply)
    skipped = total - to_apply
    print(f"  Total: {total}  |  Will apply: {to_apply}  |  Skipped: {skipped}")
    print()


def main() -> int:
    parser = argparse.ArgumentParser(description="Repair bad paper_id folder names.")
    parser.add_argument("--domain", default="", help="limit to specific domain")
    parser.add_argument("--paper-id", default="", help="limit to specific paper_id")
    parser.add_argument("--apply", action="store_true", help="actually rename (default dry-run)")
    parser.add_argument("--backup", action="store_true", default=True,
                        help="backup indexes before applying (default True)")
    parser.add_argument("--no-backup", action="store_true", help="skip backup")
    parser.add_argument("--export-mapping", type=Path, default=None,
                        help="export migration plan to JSON for review")
    parser.add_argument("--mapping", type=Path, default=None,
                        help="load migration plan from JSON and apply")
    parser.add_argument("--rename", default="", help="direct rename: old_id:new_id")
    parser.add_argument("--query-crossref", action="store_true", default=False,
                        help="query Crossref for DOI metadata (may be slow, requires network)")
    args = parser.parse_args()

    service = PaperIdMigrationService()

    # ── Mode: mapping file ──────────────────────────────────────
    if args.mapping:
        mapping_path = args.mapping
        if not mapping_path.exists():
            logger.error(f"mapping file not found: {mapping_path}")
            return 1
        plans = service.load_mapping(mapping_path)
        active = [p for p in plans if p.apply]
        skipped = [p for p in plans if not p.apply]
        print(f"\nLoaded {len(plans)} migrations from {mapping_path}")
        print(f"  Active: {len(active)}  |  Skipped (apply=false): {len(skipped)}")

        if skipped:
            print("\n  Skipped migrations:")
            for p in skipped:
                print(f"    {p.old_paper_id} -> {p.new_paper_id}  reason: {p.reason}")

        _print_table(active)

        if not args.apply:
            logger.info("[dry-run] use --apply to execute migrations")
            return 0

        do_backup = args.backup and not args.no_backup
        result = service.apply_migrations(active, backup=do_backup)
        if result.get("success"):
            logger.info(f"[OK] Applied {result['applied_count']} migrations")
            logger.info(f"  Backup: {result.get('backup_dir') or 'none'}")
            logger.info(f"  Transaction: {result.get('transaction_path')}")
            logger.info("\nNext: run validation scripts")
            logger.info("  python scripts/validate_catalog.py")
            logger.info("  python scripts/validate_bib.py")
            logger.info("  python scripts/validate_domain_library.py")
        else:
            logger.error(f"Migration failed: {result.get('error', 'unknown error')}")
            if result.get("validation_errors"):
                for e in result["validation_errors"]:
                    logger.error(f"  {e}")
            logger.error(f"  Backup at: {result.get('backup_dir')}")
            logger.error(f"  Transaction log: {result.get('transaction_path')}")
            return 1
        return 0

    # ── Mode: direct rename ─────────────────────────────────────
    if args.rename:
        parts = args.rename.split(":", 1)
        if len(parts) != 2 or not parts[0] or not parts[1]:
            logger.error("--rename format: old_id:new_id")
            return 1
        old_id, new_id = parts
        try:
            validate_paper_id(old_id)
            validate_paper_id(new_id)
        except ValueError as e:
            logger.error(f"invalid paper_id: {e}")
            return 1

        from src.services.paper_id_migration_service import MigrationPlan
        plan = MigrationPlan(old_paper_id=old_id, new_paper_id=new_id, reason="manual rename")

        if not args.apply:
            logger.info(f"[dry-run] would rename: {old_id} -> {new_id}")
            return 0

        do_backup = args.backup and not args.no_backup
        result = service.apply_migrations([plan], backup=do_backup)
        if result.get("success"):
            logger.info(f"[OK] Renamed: {old_id} -> {new_id}")
            logger.info(f"  Backup: {result.get('backup_dir') or 'none'}")
            logger.info(f"  Transaction: {result.get('transaction_path')}")
        else:
            logger.error(f"Rename failed: {result}")
            return 1
        return 0

    # ── Mode: scan ──────────────────────────────────────────────
    paper_ids = [args.paper_id] if args.paper_id else None
    plans = service.plan_migrations(
        domain=args.domain,
        paper_ids=paper_ids,
        query_crossref=args.query_crossref,
    )

    if not plans:
        print("\n  No bad paper_ids found. Library looks clean!")
        return 0

    # Print detailed info
    for p in plans:
        print(f"\n{'─'*80}")
        print(f"  old:  {p.old_paper_id}")
        print(f"  new:  {p.new_paper_id}")
        print(f"  DOI:  {p.doi or '(none)'}")
        print(f"  Title: {p.title or '(none)'}")
        print(f"  Year:  {p.year or '(none)'}")
        print(f"  Authors: {', '.join(p.authors) if p.authors else '(none)'}")
        print(f"  Reason: {p.reason}")
        print(f"  Apply: {p.apply}")
        if p.warnings:
            for w in p.warnings:
                print(f"  [WARN] {w}")

    _print_table(plans)

    # Export mapping if requested
    if args.export_mapping:
        active_plans = [p for p in plans if p.apply]
        service.export_mapping(active_plans, args.export_mapping)
        logger.info(f"Mapping exported to {args.export_mapping}")
        logger.info("Review the file, set apply=true/false, then run:")
        logger.info(f"  python scripts/repair_paper_ids.py --mapping {args.export_mapping} --apply")

    if args.apply:
        do_backup = args.backup and not args.no_backup
        active_plans = [p for p in plans if p.apply]
        if not active_plans:
            logger.info("No migrations to apply (all skipped)")
            return 0
        result = service.apply_migrations(active_plans, backup=do_backup)
        if result.get("success"):
            logger.info(f"[OK] Applied {result['applied_count']} migrations")
            logger.info(f"  Backup: {result.get('backup_dir') or 'none'}")
            logger.info(f"  Transaction: {result.get('transaction_path')}")
        else:
            logger.error(f"Migration failed: {result.get('error', 'unknown error')}")
            return 1
    else:
        logger.info("\n[dry-run] use --apply to execute migrations")
        if not args.export_mapping:
            logger.info("Tip: use --export-mapping repair_mapping.json to save plan for review")

    return 0


if __name__ == "__main__":
    sys.exit(main())
