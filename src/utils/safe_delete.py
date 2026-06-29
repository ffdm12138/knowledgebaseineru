"""Safe deletion helpers for confirmed duplicate import artifacts."""
from __future__ import annotations

import shutil
from pathlib import Path


class SafeDeleteError(ValueError):
    pass


def _assert_inside_data_root(target: Path, data_root: Path) -> Path:
    resolved_target = target.resolve()
    resolved_root = data_root.resolve()
    if resolved_target == resolved_root:
        raise SafeDeleteError("refuse to delete data root itself")
    try:
        resolved_target.relative_to(resolved_root)
    except ValueError as exc:
        raise SafeDeleteError(f"refuse to delete outside data root: {target}") from exc
    return resolved_target


def safe_delete_duplicate_artifact(
    target: str | Path,
    *,
    data_root: str | Path,
    confirmed_duplicate: bool,
) -> dict:
    """Delete a duplicate artifact only after explicit duplicate confirmation."""
    if not confirmed_duplicate:
        raise SafeDeleteError("duplicate confirmation is required before deletion")
    target_path = _assert_inside_data_root(Path(target), Path(data_root))
    if not target_path.exists():
        return {"deleted": False, "path": str(target_path), "reason": "missing"}
    if target_path.is_dir():
        shutil.rmtree(target_path)
        return {"deleted": True, "path": str(target_path), "kind": "dir"}
    target_path.unlink()
    return {"deleted": True, "path": str(target_path), "kind": "file"}
