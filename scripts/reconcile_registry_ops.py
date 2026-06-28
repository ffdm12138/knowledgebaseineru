"""Reconcile incomplete PaperRegistryService operation markers."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import REGISTRY_OPS_DIR
from src.services.paper_registry import PaperRegistryService


def _load_ops(ops_dir: Path) -> list[dict]:
    out = []
    for path in sorted(ops_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            out.append({"op_id": path.stem, "status": "unreadable", "error": str(exc), "path": str(path)})
            continue
        data["path"] = str(path)
        out.append(data)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Reconcile incomplete registry operation markers.")
    parser.add_argument("--apply", action="store_true", help="rebuild domain views for incomplete register ops")
    parser.add_argument("--ops-dir", type=Path, default=REGISTRY_OPS_DIR)
    args = parser.parse_args()

    ops = _load_ops(args.ops_dir)
    incomplete = [op for op in ops if op.get("status") not in {"complete"}]
    print(f"registry ops: total={len(ops)} incomplete={len(incomplete)}")
    for op in incomplete:
        print(
            f"- {op.get('op_id')} status={op.get('status')} "
            f"phase={op.get('phase')} paper_id={op.get('paper_id')} "
            f"error={op.get('error', '')}"
        )

    if args.apply and incomplete:
        svc = PaperRegistryService(ops_dir=args.ops_dir)
        svc._rebuild_domain_views()
        print("[OK] rebuilt domain views from current manifest/catalog")
    elif incomplete:
        print("Run with --apply to rebuild domain views from current facts.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
