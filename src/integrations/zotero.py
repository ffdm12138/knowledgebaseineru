"""Zotero 集成预留存根。

不依赖 pyzotero 库，定义数据结构和接口占位。后续可扩展：
  - 从 Zotero 导出 BibTeX/BetterBibTeX 读取 DOI
  - 检查 Zotero 是否已有 PDF
  - 把 pending/imported PDF 与 Zotero item 对齐
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ZoteroAttachmentCandidate:
    doi: str = ""
    title: str = ""
    pdf_path: str = ""
    item_key: str = ""
    collection: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


def export_doi_list(items: list[dict]) -> list[str]:
    """从 Zotero API items 提取 DOI 列表（占位，不真实调用 API）。"""
    dois = []
    for item in items:
        doi = (item.get("data") or {}).get("DOI", "")
        if doi:
            dois.append(doi)
    return dois
