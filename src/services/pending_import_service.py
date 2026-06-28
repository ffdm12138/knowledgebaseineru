"""Pending PDF import service.

This module owns the import workflow. CLI scripts are thin wrappers only.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import time
from datetime import datetime
from pathlib import Path

from loguru import logger

from config.settings import (
    CATALOG_PATH,
    DOMAIN_CATALOG_DIR,
    LIBRARY_INDEX_PATH,
    MANIFEST_PATH,
    MINERU_BACKEND,
    MINERU_EFFORT,
    MINERU_LANG,
    MINERU_METHOD,
    MINERU_TMP_DIR,
    RAW_DIR,
)
from src.cleaner import MinerUOutputCleaner
from src.converter import MinerUConverter
from src.discovery.models import normalize_doi
from src.duplicate_detector import detect_all
from src.library_index import VALID_DOMAINS, LibraryIndex
from src.manifest import PaperManifest
from src.naming import safe_child, validate_paper_id
from src.services.paper_registry import PaperRegistryService
from src.services.paper_id import generate_paper_id
from src.services.conversion_ingest_pipeline import ConversionIngestPipeline
from src.utils.atomic_io import atomic_write_json
from src.utils.safe_delete import SafeDeleteError, safe_delete_duplicate_artifact


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _compute_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_sidecar(pdf_path: Path) -> dict:
    sidecar = pdf_path.with_suffix(".json")
    if sidecar.exists():
        try:
            return _load_json(sidecar)
        except Exception:
            return {}
    return {}


def _update_sidecar(
    pdf_path: Path,
    status: str,
    canonical_paper_id: str = "",
    extra: dict | None = None,
) -> None:
    sidecar = pdf_path.with_suffix(".json")
    data = _read_sidecar(pdf_path)
    data["status"] = status
    if canonical_paper_id:
        data["canonical_paper_id"] = canonical_paper_id
    data["updated_at"] = datetime.now().isoformat(timespec="seconds")
    if status == "imported":
        data["imported_at"] = data["updated_at"]
    if extra:
        data.update(extra)
    atomic_write_json(sidecar, data, indent=2)


def import_pending_pdf(
    pdf_path: str | Path,
    domain: str,
    domains: list[str] | None = None,
    title: str = "",
    doi: str = "",
    year: int | None = None,
    paper_id: str | None = None,
    apply: bool = False,
    converter: MinerUConverter | None = None,
    cleaner: MinerUOutputCleaner | None = None,
    manifest: PaperManifest | None = None,
    catalog_path: Path = CATALOG_PATH,
    index_path: Path = LIBRARY_INDEX_PATH,
    manifest_path: Path = MANIFEST_PATH,
    domain_dir: Path = DOMAIN_CATALOG_DIR,
    raw_dir: Path = RAW_DIR,
    tmp_dir: Path = MINERU_TMP_DIR,
) -> dict:
    """Import a pending PDF. Dry-run by default."""
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"pending PDF not found: {pdf_path}")
    if domain not in VALID_DOMAINS:
        raise ValueError(f"invalid primary domain: {domain}")

    all_domains = list(domains) if domains else [domain]
    if domain not in all_domains:
        all_domains.insert(0, domain)
    for d in all_domains:
        if d not in VALID_DOMAINS:
            raise ValueError(f"invalid domain: {d}")

    sidecar = _read_sidecar(pdf_path)
    doi = normalize_doi(doi or sidecar.get("doi") or "")
    title = title or sidecar.get("title") or ""
    if year is None and sidecar.get("year"):
        try:
            year = int(sidecar.get("year"))
        except (TypeError, ValueError):
            year = None
    sha256 = _compute_sha256(pdf_path)

    index = LibraryIndex(index_path)
    mfst = manifest or PaperManifest(manifest_path)
    dup = detect_all(doi=doi, sha256=sha256, title=title, year=year, index=index, manifest=mfst)

    result = {
        "pdf_path": str(pdf_path),
        "doi": doi,
        "title": title,
        "year": year,
        "sha256": sha256,
        "domains": all_domains,
        "primary_domain": domain,
        "is_duplicate": dup["is_duplicate"],
        "canonical_paper_id": dup["canonical_paper_id"],
        "needs_confirmation": dup["needs_confirmation"],
        "status": "pending",
        "applied": False,
        "renamed_pdf": False,
        "renamed_converted_dir": False,
        "duplicate_detected": dup["is_duplicate"],
        "deleted_paths": [],
        "conflict": "",
        "warnings": [],
    }

    registry = PaperRegistryService(
        manifest_path=manifest_path,
        catalog_path=catalog_path,
        index_path=index_path,
        domain_dir=domain_dir,
        raw_dir=raw_dir,
    )

    if dup["is_duplicate"]:
        existing_pid = dup["canonical_paper_id"]
        result["canonical_paper_id"] = existing_pid
        result["status"] = "duplicate"
        if not apply:
            logger.info(f"[dry-run] duplicate of {existing_pid}; would update domains membership")
            return result
        registry.update_domains(existing_pid, all_domains, primary_domain=None)
        deleted_paths, delete_warnings = _delete_duplicate_import_artifacts(
            pdf_path,
            sidecar,
            data_root=raw_dir.parent,
        )
        _update_sidecar(pdf_path, "duplicate", canonical_paper_id=existing_pid, extra={
            "domains": all_domains,
            "duplicate_reason": _duplicate_reason(dup),
            "deleted_paths": deleted_paths,
            "delete_warnings": delete_warnings,
        })
        result["applied"] = True
        result["deleted_paths"] = deleted_paths
        result["warnings"] = delete_warnings
        logger.info(f"duplicate: {existing_pid} domains updated to {all_domains}")
        return result

    if dup["needs_confirmation"]:
        logger.warning("疑似重复（title 相似），需用户确认；dry-run 下不入库")
        if not apply:
            result["status"] = "needs_confirmation"
            return result

    pid = paper_id or generate_paper_id(
        year=year,
        title=title,
        authors=sidecar.get("authors") or sidecar.get("author") or None,
        chinese_title=sidecar.get("chinese_title") or "",
    )
    validate_paper_id(pid)
    raw_target = safe_child(raw_dir, f"{pid}.pdf")

    if not apply:
        logger.info(f"[dry-run] new paper_id={pid}, would convert + register domains={all_domains}")
        result["paper_id"] = pid
        result["canonical_pdf_filename"] = raw_target.name
        result["canonical_paper_id"] = pid
        return result

    raw_target.parent.mkdir(parents=True, exist_ok=True)
    if raw_target.exists():
        existing_sha = _compute_sha256(raw_target)
        if existing_sha != sha256:
            raise FileExistsError(
                f"raw_target already exists with different content: {raw_target}. "
                f"Use a different paper_id or remove the conflicting raw file first."
            )
        # same sha256 — reuse existing raw_target, skip copy
        logger.info(f"raw_target already exists with matching sha256, reusing: {raw_target}")
    else:
        shutil.copy2(pdf_path, raw_target)

    t0 = time.time()
    pipeline = ConversionIngestPipeline(
        manifest=mfst,
        converter=converter or MinerUConverter(),
        cleaner=cleaner or MinerUOutputCleaner(),
        registry=registry,
        tmp_dir=tmp_dir,
    )
    converted = pipeline.convert_and_register(
        pdf_path=raw_target,
        paper_id=pid,
        backend=MINERU_BACKEND,
        method=MINERU_METHOD,
        lang=MINERU_LANG,
        effort=MINERU_EFFORT,
        overwrite=False,
        replace=False,
        title=title,
        doi=doi,
        year=year,
        primary_domain=domain,
        domains=all_domains,
        source_kind=sidecar.get("source_kind") or "pending_import",
        raw_filename=raw_target.name,
        raw_stem=raw_target.stem,
        sha256=sha256,
        file_size=pdf_path.stat().st_size,
        mtime=datetime.fromtimestamp(pdf_path.stat().st_mtime).isoformat(timespec="seconds"),
    )
    elapsed = time.time() - t0
    logger.info(f"[import] MinerU convert elapsed={elapsed:.1f}s paper_id={pid}")
    if not converted.get("success"):
        _update_sidecar(pdf_path, "failed", extra={"error": converted.get("error", "convert failed")})
        if converted.get("stage") == "clean":
            raise RuntimeError(f"cleaner extract failed: {converted.get('error')}")
        raise RuntimeError(f"MinerU convert failed: {converted.get('error')}")

    _update_sidecar(pdf_path, "imported", canonical_paper_id=pid, extra={
        "domains": all_domains,
        "primary_domain": domain,
        "original_filename": sidecar.get("original_filename") or pdf_path.name,
        "canonical_pdf_filename": raw_target.name,
        "canonical_paper_id": pid,
    })

    result["paper_id"] = pid
    result["canonical_paper_id"] = pid
    result["canonical_pdf_filename"] = raw_target.name
    result["renamed_pdf"] = pdf_path.name != raw_target.name
    result["renamed_converted_dir"] = False
    result["status"] = "imported"
    result["applied"] = True
    logger.info(f"imported new paper: {pid} (domains={all_domains})")
    logger.info("下一步：运行 /prompt/catalog-entry 补全文献理解条目")
    return result


def _duplicate_reason(dup: dict) -> str:
    doi_match = dup.get("doi_match")
    sha_match = dup.get("sha256_match")
    if getattr(doi_match, "matched", False):
        return "same_doi"
    if getattr(sha_match, "matched", False):
        return "same_sha256"
    return "duplicate"


def _delete_duplicate_import_artifacts(pdf_path: Path, sidecar: dict, *, data_root: Path) -> tuple[list[str], list[str]]:
    deleted_paths: list[str] = []
    warnings: list[str] = []
    candidates: list[Path] = [pdf_path]
    converted = (
        sidecar.get("duplicate_converted_dir")
        or sidecar.get("converted_dir")
        or sidecar.get("temp_converted_dir")
        or ""
    )
    if converted:
        candidates.append(Path(converted))
    for candidate in candidates:
        try:
            info = safe_delete_duplicate_artifact(
                candidate,
                data_root=data_root,
                confirmed_duplicate=True,
            )
            if info.get("deleted"):
                deleted_paths.append(info["path"])
        except SafeDeleteError as exc:
            warnings.append(str(exc))
    return deleted_paths, warnings
