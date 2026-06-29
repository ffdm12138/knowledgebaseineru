"""Copy formal paper folders to the LLM writing workspace by 16-digit paper_number.

Resolves each paper_number via data/catalog/all.catalog.json and copies the whole
data/papers/<paper_id>/ folder to data/llm_work/<session_id>/<paper_number>/.
Never moves or modifies data/papers/.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import ALL_CATALOG_PATH, LLM_WORK_DIR
from src.services.v2_library import LlmWorkService
from src.path_utils import resolve_stored_path


def _collect_numbers(args) -> list[str]:
    numbers: list[str] = []
    if args.paper_number:
        numbers.append(args.paper_number)
    if args.paper_numbers:
        numbers.extend(args.paper_numbers)
    # de-dup preserve order
    seen: set[str] = set()
    out: list[str] = []
    for n in numbers:
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Copy paper folders to data/llm_work by paper_number.")
    parser.add_argument("--paper-number", default=None, help="single 16-digit paper_number")
    parser.add_argument("--paper-numbers", nargs="+", default=None, help="multiple 16-digit paper_numbers")
    parser.add_argument("--session-id", required=True, help="writing session id (target subfolder)")
    parser.add_argument("--apply", action="store_true", help="perform the copy; default is dry-run")
    parser.add_argument("--dry-run", action="store_true", help="resolve and report only, write nothing")
    parser.add_argument("--overwrite", action="store_true", help="overwrite an existing target folder")
    parser.add_argument("--all-catalog", type=Path, default=Path(ALL_CATALOG_PATH))
    parser.add_argument("--llm-work-dir", type=Path, default=Path(LLM_WORK_DIR))
    parser.add_argument("--report", type=Path, default=None)
    args = parser.parse_args()

    numbers = _collect_numbers(args)
    if not numbers:
        raise SystemExit("--paper-number or --paper-numbers is required")
    write = args.apply and not args.dry_run
    service = LlmWorkService(all_catalog_path=args.all_catalog, llm_work_dir=args.llm_work_dir)
    report = []
    for number in numbers:
        item = {"paper_number": number, "session_id": args.session_id, "status": "planned"}
        try:
            entry = service.resolve_paper_number(number)
            item["paper_id"] = entry.get("paper_id")
            source = resolve_stored_path(entry["folder_path"])
            item["source_dir"] = str(source)
            target = args.llm_work_dir / args.session_id / number
            item["target_dir"] = str(target)
            if write:
                result = service.copy_to_session(number, args.session_id, overwrite=args.overwrite)
                item["work_dir"] = result.get("work_dir")
                item["status"] = "copied"
            else:
                item["status"] = "planned"
        except FileExistsError as exc:
            item.update({"status": "exists", "error": str(exc)})
        except (KeyError, ValueError) as exc:
            item.update({"status": "failed", "error": str(exc)})
        except Exception as exc:  # pragma: no cover - defensive
            item.update({"status": "failed", "error": str(exc)})
        report.append(item)

    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps({"applied": write, "session_id": args.session_id, "items": report}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"applied": write, "session_id": args.session_id, "items": report}, ensure_ascii=False, indent=2))
    return 1 if any(i["status"] not in {"planned", "copied"} for i in report) else 0


if __name__ == "__main__":
    raise SystemExit(main())
