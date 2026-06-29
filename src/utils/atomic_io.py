"""Atomic JSON write helpers."""
from __future__ import annotations

import json
import os
from pathlib import Path

from filelock import FileLock


def atomic_write_json(
    path: str | Path,
    data: dict,
    *,
    indent: int = 2,
    sort_keys: bool = False,
) -> None:
    """Write JSON with filelock + tmp + os.replace."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = FileLock(str(path.with_suffix(path.suffix + ".lock")))
    with lock:
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(
            json.dumps(data, ensure_ascii=False, indent=indent, sort_keys=sort_keys),
            encoding="utf-8",
        )
        json.loads(tmp.read_text(encoding="utf-8"))
        os.replace(tmp, path)
