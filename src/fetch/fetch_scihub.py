"""Sci-Hub PDF lookup - 最后后备渠道（OA 获取失败时使用）。

优先尝试多个 Sci-Hub 镜像，依次：
  sci-hub.se → sci-hub.ru → sci-hub.st

依赖代理配置 ``config.settings.FETCH_PROXY``（默认空=直连）。
"""
import re

import requests
from loguru import logger

from config.settings import FETCH_PROXY
from src.discovery.models import normalize_doi
from src.fetch.models import FetchResult

SCI_HUB_DOMAINS = ["https://sci-hub.se", "https://sci-hub.ru", "https://sci-hub.st"]

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"


def _get_proxies() -> dict | None:
    if FETCH_PROXY:
        return {"http": FETCH_PROXY, "https": FETCH_PROXY}
    return None


def resolve_scihub(doi: str) -> FetchResult:
    """按 DOI 通过 Sci-Hub 查找 PDF URL。

    Sci-Hub 返回 HTML 页面内含嵌 PDF iframe 或直链。
    解析策略：
      1. Content-Type 直接是 PDF → 返回直链
      2. HTML 中含 ``<iframe id="pdf" src="...">`` → 提取 PDF URL
      3. HTML 中含 ``<a href="...pdf">`` 下载链接 → 提取
    """
    normalized = normalize_doi(doi)
    if not normalized:
        return FetchResult(doi=doi, error="empty doi")

    proxies = _get_proxies()
    headers = {"User-Agent": USER_AGENT}

    for base in SCI_HUB_DOMAINS:
        url = f"{base}/{normalized}"
        try:
            resp = requests.get(url, proxies=proxies, headers=headers, timeout=30)
            resp.raise_for_status()

            # 情况 1：直接返回 PDF
            content_type = resp.headers.get("content-type", "").lower()
            if "pdf" in content_type:
                return FetchResult(
                    doi=normalized, success=True, source="scihub",
                    pdf_url=resp.url, oa_status="scihub",
                    metadata={"scihub_url": url, "direct_pdf": True},
                )

            html = resp.text

            # 情况 2：iframe 内嵌 PDF
            m = re.search(r'<iframe[^>]+(?:id|name)=["\']pdf["\'][^>]+src=["\']([^"\']+)["\']', html)
            if m:
                pdf_url = m.group(1)
                if pdf_url.startswith("//"):
                    pdf_url = "https:" + pdf_url
                elif pdf_url.startswith("/"):
                    pdf_url = f"{base}{pdf_url}"
                return FetchResult(
                    doi=normalized, success=True, source="scihub",
                    pdf_url=pdf_url, oa_status="scihub",
                    metadata={"scihub_url": url, "direct_pdf": False},
                )

            # 情况 3：直接 a 标签 PDF 链接
            m = re.search(r'<a[^>]+href=["\']([^"\']+\.pdf[^"\']*)["\']', html)
            if m:
                pdf_url = m.group(1)
                if pdf_url.startswith("//"):
                    pdf_url = "https:" + pdf_url
                elif pdf_url.startswith("/"):
                    pdf_url = f"{base}{pdf_url}"
                return FetchResult(
                    doi=normalized, success=True, source="scihub",
                    pdf_url=pdf_url, oa_status="scihub",
                    metadata={"scihub_url": url, "direct_pdf": False},
                )

        except requests.RequestException as exc:
            logger.debug(f"Sci-Hub lookup failed for {doi!r} via {base}: {exc}")
            continue
        except Exception as exc:
            logger.debug(f"Sci-Hub parse failed for {doi!r} via {base}: {exc}")
            continue

    return FetchResult(doi=normalized, error="Sci-Hub: no PDF found across all mirrors")
