"""领域 catalog 视图层加载与多领域 compact 去重。

领域 catalog 是视图层，同一篇文献可跨领域重复索引。多领域选文进入写作前
必须 compact / dedupe，避免一篇文献被当成多条候选。
"""
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Iterable

from config.settings import DOMAIN_CATALOG_DIR
from src.discovery.models import normalize_title
from src.library_index import VALID_DOMAINS


def load_domain_catalog(domain_id: str, domain_dir: Path = DOMAIN_CATALOG_DIR) -> list[dict]:
    """加载单个领域 catalog 的 papers 列表。领域不存在或文件缺失返回空列表。"""
    if domain_id not in VALID_DOMAINS:
        raise ValueError(f"invalid domain_id: {domain_id}")
    path = domain_dir / domain_id / "literature_catalog.json"
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    return list(data.get("papers", []))


def load_domain_catalogs(
    domain_ids: list[str],
    include_global_fallback: bool = False,
    domain_dir: Path = DOMAIN_CATALOG_DIR,
) -> list[dict]:
    """加载多个领域 catalog 的 papers（含领域来源标记）。

    返回的每条条目附带 ``_source_domain`` 字段记录它来自哪个领域 catalog。
    若 ``include_global_fallback`` 且 ``domain_ids`` 为空，返回空列表
    （调用方应改用全局 catalog，此处不隐式加载全局）。
    """
    entries: list[dict] = []
    for domain_id in domain_ids or []:
        for p in load_domain_catalog(domain_id, domain_dir=domain_dir):
            entry = deepcopy(p)
            entry["_source_domain"] = domain_id
            entries.append(entry)
    return entries


def _entry_dedupe_key(entry: dict) -> str | None:
    """按 paper_id → doi → bib_key → (title+year) 优先级生成去重键。"""
    pid = (entry.get("paper_id") or "").strip()
    if pid:
        return f"pid:{pid}"
    doi = (entry.get("doi") or "").strip().lower()
    if doi:
        return f"doi:{doi}"
    bib_key = ((entry.get("citation") or {}).get("bib_key") or "").strip()
    if bib_key:
        return f"bib:{bib_key}"
    title = normalize_title(entry.get("title") or "")
    year = entry.get("year") or ""
    if title:
        return f"title:{title}:{year}"
    return None


def _merge_selection_hints(base: dict, other: dict) -> dict:
    """合并两条 selection_hints，列表字段取并集保序，标量取 base。"""
    b = deepcopy(base.get("selection_hints") or {})
    o = other.get("selection_hints") or {}
    for key, val in o.items():
        if isinstance(val, list):
            existing = list(b.get(key) or [])
            for item in val:
                if item not in existing:
                    existing.append(item)
            b[key] = existing
        elif key not in b:
            b[key] = val
    return b


def compact_catalog_entries(
    entries: list[dict],
    dedupe_keys: tuple[str, ...] = ("paper_id", "doi", "bib_key"),
) -> list[dict]:
    """对多领域 catalog 条目去重合并。

    去重优先级：paper_id → doi → bib_key → (normalized title + year)。
    合并后的条目增加/更新字段：
      - ``source_domains``: 该文献出现的所有领域列表（保序去重）
      - ``primary_domain``: 取首个领域的 primary_domain（若条目自身有则保留）
      - ``domains``: 所有领域的并集
      - ``selection_hints``: 列表字段并集合并
    """
    merged: dict[str, dict] = {}
    order: list[str] = []
    for entry in entries:
        key = _entry_dedupe_key(entry)
        if key is None:
            # 无法去重，直接保留并标注来源
            single = deepcopy(entry)
            src = entry.get("_source_domain")
            single["source_domains"] = [src] if src else []
            single.setdefault("primary_domain", "")
            single.setdefault("domains", [])
            merged[f"noid:{id(entry)}"] = single
            order.append(f"noid:{id(entry)}")
            continue
        if key in merged:
            base = merged[key]
            src = entry.get("_source_domain")
            if src and src not in (base.get("source_domains") or []):
                base.setdefault("source_domains", []).append(src)
            # domains 并集
            base_domains = list(base.get("domains") or [])
            for d in (entry.get("domains") or []):
                if d not in base_domains:
                    base_domains.append(d)
            base["domains"] = base_domains
            # selection_hints 合并
            base["selection_hints"] = _merge_selection_hints(base, entry)
            # raw 合并来源信息
            base.setdefault("_merged_from", []).append(src)
        else:
            new = deepcopy(entry)
            src = entry.get("_source_domain")
            new["source_domains"] = [src] if src else []
            new.setdefault("primary_domain", "")
            new.setdefault("domains", list(entry.get("domains") or []))
            new.pop("_source_domain", None)
            merged[key] = new
            order.append(key)
    return [merged[k] for k in order]


def compact_domains(
    domain_ids: list[str],
    domain_dir: Path = DOMAIN_CATALOG_DIR,
    include_global_fallback: bool = False,
) -> list[dict]:
    """加载多领域 catalog 并 compact 去重，返回去重后的条目列表。"""
    entries = load_domain_catalogs(
        domain_ids,
        include_global_fallback=include_global_fallback,
        domain_dir=domain_dir,
    )
    return compact_catalog_entries(entries)


def compact_summary(
    raw_entries: list[dict],
    compacted: list[dict],
) -> dict:
    """生成 compact 统计信息。"""
    duplicate_count = max(0, len(raw_entries) - len(compacted))
    per_paper_domains: dict[str, list[str]] = {}
    for entry in compacted:
        pid = entry.get("paper_id") or entry.get("title") or "?"
        per_paper_domains[pid] = entry.get("source_domains") or []
    return {
        "raw_count": len(raw_entries),
        "compacted_count": len(compacted),
        "duplicate_count": duplicate_count,
        "per_paper_domains": per_paper_domains,
    }
