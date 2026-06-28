"""PDF fetch pipeline with access policy and pluggable resolvers.

入口：
  fetch_oa_pdf()          — 旧接口，仅 OA，向后兼容
  fetch_pdf()             — 新接口，支持 access policy + resolver chain

代理：若 ``config.settings.FETCH_PROXY`` 非空，自动设置 HTTPS_PROXY 等。
"""
import hashlib
import json
import os
import re
import shutil
from datetime import datetime
from pathlib import Path

import requests
from loguru import logger

from config.settings import FETCH_PROXY, MINERU_FETCH_MAX_BYTES, RAW_DIR
from src.discovery.models import normalize_doi
from src.fetch.access_policy import AccessMode, AccessPolicy
from src.fetch.fetch_arxiv import resolve_arxiv_pdf
from src.fetch.fetch_openalex import resolve_openalex_pdf
from src.fetch.fetch_publisher import resolve_publisher_pdf
from src.fetch.fetch_scihub import resolve_scihub
from src.fetch.fetch_semantic_scholar import resolve_semantic_scholar_pdf
from src.fetch.fetch_unpaywall import resolve_unpaywall
from src.fetch.models import FetchResult
from src.fetch.resolver_registry import build_resolvers
from src.fetch.resolvers.base import ResolveContext
from src.services.pdf_acquisition_service import PdfAcquisitionService, _atomic_write_json
from src.services.metadata_enrichment_service import normalize_bibliographic_metadata
from src.utils.file_allocation import allocate_unique_path


# Re-export for test monkeypatch (test_fetch_pipeline patches at module level)
_build_resolvers = build_resolvers

if FETCH_PROXY:
    os.environ.setdefault("HTTP_PROXY", FETCH_PROXY)
    os.environ.setdefault("HTTPS_PROXY", FETCH_PROXY)
    logger.info(f"fetch proxy enabled: {FETCH_PROXY}")


def safe_doi_slug(doi: str) -> str:
    normalized = normalize_doi(doi)
    return re.sub(r"[^A-Za-z0-9._-]+", "_", normalized).strip("_") or "unknown_doi"


def _safe_write_pending(src_content: bytes, target: Path) -> tuple[Path, str]:
    """Write bytes to a pending PDF target without silently overwriting.

    Returns (final_path, sha256_hex).
    - target does not exist → write and return target.
    - target exists, same sha256 → reuse existing, skip write.
    - target exists, different sha256 → auto-rename with sha8 suffix.
    """
    digest = hashlib.sha256(src_content)
    src_sha256 = digest.hexdigest()
    if len(src_content) > MINERU_FETCH_MAX_BYTES:
        raise ValueError(f"PDF exceeds MINERU_FETCH_MAX_BYTES={MINERU_FETCH_MAX_BYTES}")

    target.parent.mkdir(parents=True, exist_ok=True)
    final, reused = allocate_unique_path(target, src_sha256)
    if reused:
        logger.info(f"pending PDF already exists with matching sha256, reusing: {final}")
        return final, src_sha256
    tmp = final.with_suffix(final.suffix + ".tmp")
    try:
        tmp.write_bytes(src_content)
        os.replace(tmp, final)
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)
    return final, src_sha256


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _move_pending_file(src_path: Path, target: Path, sha256: str | None = None) -> tuple[Path, str]:
    """Atomically move a prepared PDF into pending with conflict protection."""
    src_sha256 = sha256 or _sha256_file(src_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    final, reused = allocate_unique_path(target, src_sha256)
    if reused:
        logger.info(f"pending PDF already exists with matching sha256, reusing: {final}")
        src_path.unlink(missing_ok=True)
        return final, src_sha256
    os.replace(src_path, final)
    return final, src_sha256


def _copy_pending(src_path: Path, target: Path) -> tuple[Path, str]:
    """Stream-copy a file to pending target with sha256 conflict protection.

    Returns (final_path, sha256_hex).
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".copy.tmp")
    digest = hashlib.sha256()
    try:
        with src_path.open("rb") as src, tmp.open("wb") as dst:
            total = 0
            for chunk in iter(lambda: src.read(1024 * 1024), b""):
                total += len(chunk)
                if total > MINERU_FETCH_MAX_BYTES:
                    raise ValueError(f"PDF exceeds MINERU_FETCH_MAX_BYTES={MINERU_FETCH_MAX_BYTES}")
                digest.update(chunk)
                dst.write(chunk)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
    return _move_pending_file(tmp, target, digest.hexdigest())


def _looks_like_pdf(response: requests.Response, url: str) -> bool:
    content_type = response.headers.get("content-type", "").lower()
    return "pdf" in content_type or url.lower().split("?")[0].endswith(".pdf")


def _download_pdf(url: str, tmp_path: Path) -> tuple[Path, str]:
    """Stream-download PDF to *tmp_path*, return (tmp_path, sha256_hex).

    Caller is responsible for atomically moving the temp file to the final
    pending target.
    """
    with requests.get(url, stream=True, timeout=60) as response:
        response.raise_for_status()
        if not _looks_like_pdf(response, response.url or url):
            raise ValueError(f"response is not a PDF: {response.headers.get('content-type', '')}")
        tmp_path.parent.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256()
        total = 0
        with tmp_path.open("wb") as fh:
            for chunk in response.iter_content(chunk_size=1024 * 64):
                if not chunk:
                    continue
                total += len(chunk)
                if total > MINERU_FETCH_MAX_BYTES:
                    tmp_path.unlink(missing_ok=True)
                    raise ValueError(f"PDF exceeds MINERU_FETCH_MAX_BYTES={MINERU_FETCH_MAX_BYTES}")
                digest.update(chunk)
                fh.write(chunk)
        return tmp_path, digest.hexdigest()


def _write_sidecar(result: FetchResult, sidecar_path: Path) -> None:
    pdf_path = Path(result.output_path) if result.output_path else sidecar_path.with_suffix(".pdf")
    domain_id = ""
    if sidecar_path.parent.name == "pending":
        domain_id = sidecar_path.parent.parent.name
        if domain_id == "unknown":
            domain_id = ""
    stat = pdf_path.stat() if pdf_path.exists() else None
    service = PdfAcquisitionService(raw_dir=sidecar_path.parents[2] if len(sidecar_path.parents) > 2 else RAW_DIR)
    policy_mode = result.access_mode or AccessMode.OA_ONLY.value
    resolver_access_mode = (result.metadata or {}).get("resolver_access_mode") or policy_mode
    source_kind = _source_kind_for_result(result, policy_mode, resolver_access_mode)

    # ── Normalize bibliographic metadata from resolver result ──────────
    raw_meta = dict(result.metadata or {})
    # Determine source for normalization
    source_hint = ""
    resolver_name = (result.resolver or "").lower()
    source_name = (result.source or "").lower()
    if "openalex" in resolver_name or "openalex" in source_name:
        source_hint = "openalex"
    elif "semantic_scholar" in resolver_name or "semantic" in source_name:
        source_hint = "semantic_scholar"
    elif "unpaywall" in resolver_name or "unpaywall" in source_name:
        source_hint = "unpaywall"
    elif "crossref" in resolver_name:
        source_hint = "crossref"

    normalized = normalize_bibliographic_metadata(raw_meta, source=source_hint)
    normalized_title = normalized.get("title") or (result.metadata or {}).get("title", "")
    normalized_year = normalized.get("year") or (result.metadata or {}).get("year")
    normalized_authors = normalized.get("authors") or []
    normalized_first_author = normalized.get("first_author") or ""

    # Generate proposed_paper_id
    proposed_paper_id = ""
    if normalized_title or normalized_year:
        from src.services.paper_id import generate_paper_id
        proposed_paper_id = generate_paper_id(
            year=normalized_year,
            title=normalized_title,
            authors=normalized_authors if normalized_authors else None,
        )

    unified = service.build_sidecar(
        source_kind=source_kind,
        access_mode=policy_mode,
        resolver=result.resolver,
        doi=result.doi,
        title=normalized_title,
        year=normalized_year,
        original_filename=pdf_path.name,
        pending_pdf=pdf_path,
        sha256=result.sha256,
        file_size=stat.st_size if stat else 0,
        mtime=datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds") if stat else "",
        domain_id=domain_id,
        domains=[domain_id] if domain_id else [],
        status="pending" if result.success else "failed",
        error=result.error,
        extra={
            **result.to_dict(),
            "policy_mode": policy_mode,
            "resolver_name": result.resolver,
            "resolver_access_mode": resolver_access_mode,
            "source_kind": source_kind,
            "authors": normalized_authors,
            "first_author": normalized_first_author,
            "venue": normalized.get("venue", ""),
            "metadata_source": normalized.get("source", source_kind),
            "proposed_paper_id": proposed_paper_id,
        },
    )
    _atomic_write_json(sidecar_path, unified)


def _source_kind_for_result(result: FetchResult, policy_mode: str, resolver_access_mode: str) -> str:
    source = (result.source or result.resolver or "").lower()
    resolver = (result.resolver or "").lower()
    if "scihub" in {source, resolver}:
        return "scihub"
    if "custom" in {source, resolver} or resolver_access_mode == AccessMode.CUSTOM.value:
        return "custom"
    if "local" in {source, resolver} or resolver_access_mode == AccessMode.LOCAL_MANUAL.value:
        return "local_manual"
    if "browser" in {source, resolver} or resolver_access_mode == AccessMode.BROWSER_ASSISTED.value:
        return "browser_assisted"
    if resolver_access_mode == AccessMode.OA_ONLY.value or result.access_status == "open_access":
        return "open_access"
    if policy_mode == AccessMode.INSTITUTIONAL.value or resolver_access_mode == AccessMode.INSTITUTIONAL.value:
        return "institutional"
    return policy_mode or "open_access"




def fetch_pdf(
    doi: str,
    domain_id: str | None = None,
    output_root: Path = RAW_DIR,
    dry_run: bool = False,
    access_policy: AccessPolicy | None = None,
    title: str = "",
    year: int | None = None,
    metadata: dict | None = None,
) -> FetchResult:
    """按 access policy 使用 resolver chain 获取 PDF。

    返回的 FetchResult 包含：
      - resolver_chain（已尝试过的 resolver）
      - 若 requires_user_action=True，只返回 action_hint + landing_url
      - 若成功，写入 pending 目录 + sidecar
    """
    normalized = normalize_doi(doi)
    if not normalized:
        return FetchResult(doi=doi, error="doi is required")

    policy = access_policy or AccessPolicy()
    resolvers = _build_resolvers(policy)
    ctx = ResolveContext(
        doi=normalized,
        title=title,
        year=year,
        domain_id=domain_id,
        metadata=(metadata or {}),
        access_policy=policy,
    )

    last_error = ""
    chain: list[str] = []
    for resolver in resolvers:
        chain.append(resolver.name)
        result = resolver.resolve(ctx)

        # 更新 resolver_chain（不管成功失败）
        result.resolver_chain = list(chain)
        result.resolver = resolver.name
        resolver_access_mode = result.access_mode or policy.mode.value
        result.metadata = dict(result.metadata or {})
        result.metadata.setdefault("resolver_access_mode", resolver_access_mode)
        result.access_mode = policy.mode.value

        if not result.success:
            last_error = result.error or last_error
            continue

        # 需要用户手动操作
        if result.requires_user_action:
            if dry_run:
                result.output_path = ""
                result.sidecar_path = ""
            return result

        # OA 模式：下载 PDF
        if result.pdf_url:
            if dry_run:
                result.output_path = ""
                result.sidecar_path = ""
                return result
            try:
                pending_dir = Path(output_root) / (domain_id or "unknown") / "pending"
                pending_dir.mkdir(parents=True, exist_ok=True)
                candidate = pending_dir / f"{safe_doi_slug(normalized)}.pdf"
                tmp = candidate.with_suffix(candidate.suffix + ".tmp")
                tmp_path, sha256 = _download_pdf(result.pdf_url, tmp)
                pdf_path, sha256 = _move_pending_file(tmp_path, candidate, sha256)
                result.sha256 = sha256
                sidecar_path = pdf_path.with_suffix(".json")
                result.output_path = pdf_path.as_posix()
                result.sidecar_path = sidecar_path.as_posix()
                _write_sidecar(result, sidecar_path)
                return result
            except Exception as exc:
                logger.warning(f"download failed from {resolver.name} for {doi!r}: {exc}")
                last_error = str(exc)
                continue

        # publisher_tdm / local_manual / springer_direct / wiley_tdm：已有本地文件或内存内容
        if result.output_path:
            src_path = Path(result.output_path)
            if src_path.exists():
                if dry_run:
                    return result
                pending_dir = Path(output_root) / (domain_id or "unknown") / "pending"
                pending_dir.mkdir(parents=True, exist_ok=True)
                candidate = pending_dir / f"{safe_doi_slug(normalized)}.pdf"
                pdf_path, sha256 = _copy_pending(src_path, candidate)
                result.sha256 = sha256
                sidecar_path = pdf_path.with_suffix(".json")
                result.output_path = pdf_path.as_posix()
                result.sidecar_path = sidecar_path.as_posix()
                _write_sidecar(result, sidecar_path)
                return result

        # TDM resolver: content already in memory, save with conflict protection
        if result.raw and result.raw.get("content"):
            if dry_run:
                result.output_path = ""
                result.sidecar_path = ""
                return result
            pending_dir = Path(output_root) / (domain_id or "unknown") / "pending"
            pending_dir.mkdir(parents=True, exist_ok=True)
            candidate = pending_dir / f"{safe_doi_slug(normalized)}.pdf"
            content = result.raw["content"]
            pdf_path, sha256 = _safe_write_pending(content, candidate)
            result.sha256 = sha256
            sidecar_path = pdf_path.with_suffix(".json")
            result.output_path = pdf_path.as_posix()
            result.sidecar_path = sidecar_path.as_posix()
            # 清除 raw/metadata 中的大字节内容，sidecar 只需元数据
            result.raw.pop("content", None)
            if result.metadata:
                result.metadata.pop("content", None)
            _write_sidecar(result, sidecar_path)
            return result

    return FetchResult(
        doi=normalized,
        error=last_error or "no PDF found",
        resolver_chain=chain,
        access_mode=policy.mode.value,
    )


def fetch_oa_pdf(
    doi: str,
    domain_id: str | None = None,
    output_root: Path = RAW_DIR,
    dry_run: bool = False,
) -> FetchResult:
    """向后兼容：仅 OA 模式。"""
    return fetch_pdf(
        doi,
        domain_id=domain_id,
        output_root=output_root,
        dry_run=dry_run,
        access_policy=AccessPolicy(mode=AccessMode.OA_ONLY),
    )

