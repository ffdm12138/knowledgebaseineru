"""Rebuild v2 data/catalog/all.catalog.json from data/papers."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.services.v2_library import AllCatalogBuilder


def main() -> int:
    parser = argparse.ArgumentParser(description="Rebuild v2 all.catalog.json.")
    parser.add_argument("--apply", action="store_true", help="write all.catalog.json; default is dry-run")
    parser.add_argument("--dry-run", action="store_true", help="print summary without writing")
    args = parser.parse_args()
    write = args.apply and not args.dry_run
    data = AllCatalogBuilder().build(write=write)
    print(f"papers={len(data.get('papers', []))} written={write}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
