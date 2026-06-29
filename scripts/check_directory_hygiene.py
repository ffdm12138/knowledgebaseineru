"""Report directory-boundary hygiene warnings without deleting user data."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import ALL_CATALOG_PATH, PAPER_RAW_DIR, PAPERS_DIR, PROJECT_ROOT
from src.path_utils import normalize_repo_path


WRITE_JOBS_DIR = PROJECT_ROOT / "write" / "jobs"
_REAL_ARTIFACT_SUFFIXES = {".pdf", ".md", ".png", ".jpg", ".jpeg", ".webp", ".gif", ".tex", ".bib", ".log"}
_RESTRICTED_TOKENS = ("data/papers", "data/paper_raw", "data/raw", "data/llm_work")


def _read_json(path: Path, default: Any | None = None) -> Any:
    if not path.exists():
        if default is not None:
            return default
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8"))


def _metadata_doi(metadata: dict) -> str:
    return str(((metadata.get("identifiers") or {}).get("doi")) or "").strip().lower()


def _metadata_file(folder: Path) -> Path | None:
    matches = sorted(folder.glob("*.metadata.json"))
    return matches[0] if matches else None


def _git_ignored(project_root: Path, path: Path) -> bool | None:
    git_dir = project_root / ".git"
    if not git_dir.exists():
        return None
    result = subprocess.run(
        ["git", "-C", str(project_root), "check-ignore", "-q", str(path)],
        check=False,
    )
    if result.returncode == 0:
        return True
    if result.returncode == 1:
        return False
    return None


def _contains_restricted_path(text: str) -> str | None:
    norm = text.replace("\\", "/")
    for token in _RESTRICTED_TOKENS:
        if token in norm:
            return token
    return None


def check_directory_hygiene(
    *,
    project_root: Path = PROJECT_ROOT,
    all_catalog_path: Path = ALL_CATALOG_PATH,
    papers_dir: Path = PAPERS_DIR,
    paper_raw_dir: Path = PAPER_RAW_DIR,
    write_jobs_dir: Path = WRITE_JOBS_DIR,
) -> dict:
    warnings: list[str] = []
    catalog = _read_json(all_catalog_path, {"papers": []})
    papers = catalog.get("papers") or []

    seen_numbers: dict[str, str] = {}
    formal_dois: set[str] = set()
    for entry in papers:
        number = str(entry.get("paper_number") or "")
        paper_id = str(entry.get("paper_id") or "")
        if number:
            if number in seen_numbers:
                warnings.append(f"duplicate paper_number in all.catalog: {number} ({seen_numbers[number]}, {paper_id})")
            seen_numbers[number] = paper_id
        folder = papers_dir / paper_id if paper_id else None
        if not folder or not folder.exists():
            warnings.append(f"all.catalog references missing formal paper folder: {paper_id or number}")
            continue
        meta_path = _metadata_file(folder)
        if not meta_path:
            warnings.append(f"formal paper missing metadata file: {normalize_repo_path(folder)}")
            continue
        metadata = _read_json(meta_path, {})
        doi = _metadata_doi(metadata)
        if doi:
            formal_dois.add(doi)
        else:
            warnings.append(f"formal paper metadata.identifiers.doi missing: {normalize_repo_path(meta_path)}")

    if paper_raw_dir.exists() and formal_dois:
        for meta_path in paper_raw_dir.glob("*/*.metadata.json"):
            doi = _metadata_doi(_read_json(meta_path, {}))
            if doi and doi in formal_dois:
                warnings.append(f"paper_raw appears to duplicate formal DOI {doi}: {normalize_repo_path(meta_path)}")

    if write_jobs_dir.exists():
        for path in write_jobs_dir.rglob("*"):
            if not path.is_file():
                continue
            rel = normalize_repo_path(path)
            if path.suffix.lower() in _REAL_ARTIFACT_SUFFIXES:
                ignored = _git_ignored(project_root, path)
                if ignored is False:
                    warnings.append(f"write/jobs real artifact is not gitignored: {rel}")
            if path.name == "selected_catalog.json":
                selected = _read_json(path, {})
                for item in selected.get("papers") or []:
                    source = str(item.get("source_dir") or item.get("catalog_folder_path") or "")
                    token = _contains_restricted_path(source)
                    if token and token != "data/papers":
                        warnings.append(f"{rel} article source references non-formal path {token}: {source}")
            if path.name == "main.tex":
                text = path.read_text(encoding="utf-8", errors="ignore")
                token = _contains_restricted_path(text)
                if token:
                    warnings.append(f"{rel} contains direct {token} path")

    return {
        "valid": True,
        "warning_count": len(warnings),
        "warnings": warnings,
        "checked_at": datetime.now().isoformat(timespec="seconds"),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Report directory hygiene warnings without deleting user data.")
    parser.add_argument("--project-root", type=Path, default=Path(PROJECT_ROOT))
    parser.add_argument("--all-catalog", type=Path, default=Path(ALL_CATALOG_PATH))
    parser.add_argument("--papers-dir", type=Path, default=Path(PAPERS_DIR))
    parser.add_argument("--paper-raw-dir", type=Path, default=Path(PAPER_RAW_DIR))
    parser.add_argument("--write-jobs-dir", type=Path, default=Path(WRITE_JOBS_DIR))
    return parser


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = build_parser().parse_args()
    report = check_directory_hygiene(
        project_root=args.project_root,
        all_catalog_path=args.all_catalog,
        papers_dir=args.papers_dir,
        paper_raw_dir=args.paper_raw_dir,
        write_jobs_dir=args.write_jobs_dir,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
