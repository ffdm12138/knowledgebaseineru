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
from pathlib import Path

import requests
from loguru import logger

from config.settings import FETCH_PROXY, RAW_DIR
from src.discovery.models import normalize_doi
from src.fetch.access_policy import AccessMode, AccessPolicy
from src.fetch.fetch_arxiv import resolve_arxiv_pdf
from src.fetch.fetch_openalex import resolve_openalex_pdf
from src.fetch.fetch_publisher import resolve_publisher_pdf
from src.fetch.fetch_scihub import resolve_scihub
from src.fetch.fetch_semantic_scholar import resolve_semantic_scholar_pdf
from src.fetch.fetch_unpaywall import resolve_unpaywall
from src.fetch.models import FetchResult
from src.fetch.resolvers.base import ResolveContext
from src.fetch.resolvers.oa_resolvers import (
    ArxivResolver,
    OpenAlexResolver,
    PublisherOAResolver,
    SemanticScholarResolver,
    UnpaywallResolver,
)
from src.fetch.resolvers.tdm_resolvers import (
    ElsevierTdmResolver,
    SpringerDirectResolver,
    WileyTdmResolver,
)

if FETCH_PROXY:
    os.environ.setdefault("HTTP_PROXY", FETCH_PROXY)
    os.environ.setdefault("HTTPS_PROXY", FETCH_PROXY)
    logger.info(f"fetch proxy enabled: {FETCH_PROXY}")


def safe_doi_slug(doi: str) -> str:
    normalized = normalize_doi(doi)
    return re.sub(r"[^A-Za-z0-9._-]+", "_", normalized).strip("_") or "unknown_doi"


def _looks_like_pdf(response: requests.Response, url: str) -> bool:
    content_type = response.headers.get("content-type", "").lower()
    return "pdf" in content_type or url.lower().split("?")[0].endswith(".pdf")


def _download_pdf(url: str, output_path: Path) -> str:
    with requests.get(url, stream=True, timeout=60) as response:
        response.raise_for_status()
        if not _looks_like_pdf(response, response.url or url):
            raise ValueError(f"response is not a PDF: {response.headers.get('content-type', '')}")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = output_path.with_suffix(output_path.suffix + ".tmp")
        digest = hashlib.sha256()
        with tmp.open("wb") as fh:
            for chunk in response.iter_content(chunk_size=1024 * 64):
                if not chunk:
                    continue
                digest.update(chunk)
                fh.write(chunk)
        tmp.replace(output_path)
        return digest.hexdigest()


def _write_sidecar(result: FetchResult, sidecar_path: Path) -> None:
    sidecar_path.write_text(json.dumps(result.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")


def _build_resolvers(policy: AccessPolicy) -> list:
    """根据 access policy 构建 resolver 列表。"""
    name_map = {
        "unpaywall": UnpaywallResolver,
        "openalex": OpenAlexResolver,
        "semantic_scholar": SemanticScholarResolver,
        "arxiv": ArxivResolver,
        "publisher_oa": PublisherOAResolver,
        "wiley_tdm": WileyTdmResolver,
        "springer_direct": SpringerDirectResolver,
        "elsevier_tdm": ElsevierTdmResolver,
        "publisher_tdm": _TdmResolver,
        "institutional_browser": _InstBrowserResolver,
        "browser_assisted": _BrowserResolver,
        "local_manual": _LocalResolver,
        "scihub": _SciHubResolver,
        "biorxiv": _BiorxivBridge,
        "pmc_oa": _PmcOaBridge,
        "ref_downloader": _RefDownloaderBridge,
    }
    resolvers = []
    for name in policy.enabled_resolver_names():
        if name in name_map:
            resolvers.append(name_map[name]())
    return resolvers


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
                pdf_path = pending_dir / f"{safe_doi_slug(normalized)}.pdf"
                sidecar_path = pdf_path.with_suffix(".json")
                sha256 = _download_pdf(result.pdf_url, pdf_path)
                result.sha256 = sha256
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
                pdf_path = pending_dir / f"{safe_doi_slug(normalized)}.pdf"
                sidecar_path = pdf_path.with_suffix(".json")
                import shutil
                shutil.copy2(src_path, pdf_path)
                digest = hashlib.sha256()
                digest.update(pdf_path.read_bytes())
                result.sha256 = digest.hexdigest()
                result.output_path = pdf_path.as_posix()
                result.sidecar_path = sidecar_path.as_posix()
                _write_sidecar(result, sidecar_path)
                return result

        # TDM resolver: content already in raw, save directly
        if result.raw and result.raw.get("content"):
            if dry_run:
                result.output_path = ""
                result.sidecar_path = ""
                return result
            pending_dir = Path(output_root) / (domain_id or "unknown") / "pending"
            pending_dir.mkdir(parents=True, exist_ok=True)
            pdf_path = pending_dir / f"{safe_doi_slug(normalized)}.pdf"
            sidecar_path = pdf_path.with_suffix(".json")
            content = result.raw["content"]
            pdf_path.write_bytes(content)
            result.sha256 = hashlib.sha256(content).hexdigest()
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


# ── 行内辅助 resolver（待 resolver 重构完整后移到独立模块）──

class _TdmResolver:
    name = "publisher_tdm"
    def resolve(self, ctx):
        from .resolvers.institutional_resolvers import PublisherTDMResolver
        return PublisherTDMResolver().resolve(ctx)


class _InstBrowserResolver:
    name = "institutional_browser"
    def resolve(self, ctx):
        from .resolvers.institutional_resolvers import InstitutionalBrowserResolver
        return InstitutionalBrowserResolver().resolve(ctx)


class _BrowserResolver:
    name = "browser_assisted"
    def resolve(self, ctx):
        from .resolvers.browser_resolvers import BrowserAssistedResolver
        return BrowserAssistedResolver().resolve(ctx)


class _LocalResolver:
    name = "local_manual"
    def resolve(self, ctx):
        from .resolvers.local_resolvers import LocalManualResolver
        return LocalManualResolver().resolve(ctx)


class _SciHubResolver:
    name = "scihub"
    def resolve(self, ctx):
        from .fetch_scihub import resolve_scihub
        return resolve_scihub(ctx.doi)


class _RefDownloaderBridge:
    name = "ref_downloader"
    def resolve(self, ctx):
        from .resolvers.ref_downloader_bridge import RefDownloaderResolver
        return RefDownloaderResolver().resolve(ctx)


class _BiorxivBridge:
    name = "biorxiv"
    def resolve(self, ctx):
        from .resolvers.preprint_resolvers import BiorxivResolver
        return BiorxivResolver().resolve(ctx)


class _PmcOaBridge:
    name = "pmc_oa"
    def resolve(self, ctx):
        from .resolvers.preprint_resolvers import PmcOaResolver
        return PmcOaResolver().resolve(ctx)
