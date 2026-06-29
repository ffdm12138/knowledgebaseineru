"""Overwrite-protected text writes for writing workflow artifacts."""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path


TODO_MARKERS = ["TODO", "待填", "（待填）", "TEMPLATE_ONLY", "由大模型补全", "待补全"]


def text_is_empty_or_template(text: str) -> bool:
    """Return True when existing text has no user-filled substance."""
    if not text.strip():
        return True
    body = text
    for marker in TODO_MARKERS:
        body = body.replace(marker, "")
    body = re.sub(r"^#.*$", "", body, flags=re.MULTILINE)
    body = re.sub(r"^%.*$", "", body, flags=re.MULTILINE)
    body = re.sub(r"^\|[-:| ]+\|$", "", body, flags=re.MULTILINE)
    return len(re.sub(r"\s+", "", body)) < 20


def write_text_safely(
    path: Path,
    text: str,
    force: bool = False,
    backup: bool = True,
) -> dict:
    """Write text without clobbering user-filled files by default."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        old_text = path.read_text(encoding="utf-8")
        if not force and not text_is_empty_or_template(old_text):
            return {"written": False, "path": str(path), "action": "skipped", "backup": None}
        bak = None
        action = "refreshed_template"
        if force:
            action = "overwritten"
            if backup:
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                bak = str(path.with_suffix(path.suffix + f".bak_{ts}"))
                Path(bak).write_text(old_text, encoding="utf-8")
        path.write_text(text, encoding="utf-8")
        return {"written": True, "path": str(path), "action": action, "backup": bak}
    path.write_text(text, encoding="utf-8")
    return {"written": True, "path": str(path), "action": "created", "backup": None}
