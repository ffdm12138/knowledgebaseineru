"""入库前本地查重检测。

不允许联网查询，所有判断必须本地可测。匹配优先级：
  DOI 完全一致 → confidence 1.0
  PDF sha256 一致 → confidence 1.0
  title normalized + year 一致 → confidence >= 0.85
  title 相似但 year 差距 <= 1 → confidence 0.6-0.8（仅 warning，需用户确认）
"""
from __future__ import annotations

from dataclasses import dataclass, field
from difflib import SequenceMatcher

from src.discovery.models import normalize_doi, normalize_title
from src.library_index import LibraryIndex
from src.manifest import PaperManifest


@dataclass
class DuplicateResult:
    matched: bool
    reason: str = ""
    canonical_paper_id: str | None = None
    confidence: float = 0.0
    matched_fields: list[str] = field(default_factory=list)


def detect_duplicate_by_doi(
    doi: str, index: LibraryIndex | None = None
) -> DuplicateResult:
    """按 DOI 在 library_index 中查重。"""
    index = index or LibraryIndex()
    normalized = normalize_doi(doi)
    if not normalized:
        return DuplicateResult(matched=False, reason="empty doi")
    entry = index.find_by_doi(normalized)
    if entry:
        return DuplicateResult(
            matched=True,
            reason="doi already in library_index",
            canonical_paper_id=entry.get("paper_id"),
            confidence=1.0,
            matched_fields=["doi"],
        )
    return DuplicateResult(matched=False, reason="doi not found", confidence=0.0)


def detect_duplicate_by_sha256(
    sha256: str, manifest: PaperManifest | None = None
) -> DuplicateResult:
    """按 PDF sha256 在 manifest 中查重（仅 converted/duplicate 视为已入库）。"""
    manifest = manifest or PaperManifest()
    sha = (sha256 or "").strip().lower()
    if not sha:
        return DuplicateResult(matched=False, reason="empty sha256")
    entry = manifest.find_by_sha256(sha)
    if not entry:
        return DuplicateResult(matched=False, reason="sha256 not found")
    # failed 记录不算 canonical 已入库（允许同 paper_id 重试，跨 paper_id 由调用方处理）
    status = (entry.get("status") or "").strip()
    if status in {"converted", "unregistered_converted", "duplicate"}:
        return DuplicateResult(
            matched=True,
            reason=f"sha256 already converted (status={status})",
            canonical_paper_id=entry.get("paper_id"),
            confidence=1.0,
            matched_fields=["sha256"],
        )
    return DuplicateResult(
        matched=False,
        reason=f"sha256 found but status={status} (not canonical)",
        canonical_paper_id=entry.get("paper_id"),
        confidence=0.0,
    )


def detect_possible_duplicate_by_title(
    title: str,
    year: int | None,
    index: LibraryIndex | None = None,
) -> list[DuplicateResult]:
    """按 title 相似度 + year 接近度查找疑似重复。

    返回所有疑似结果（confidence >= 0.6），按 confidence 降序。
    """
    index = index or LibraryIndex()
    title_norm = normalize_title(title)
    if not title_norm:
        return []
    results: list[DuplicateResult] = []
    for entry in index.list_all():
        cand_title = normalize_title(entry.get("title") or "")
        if not cand_title:
            continue
        ratio = SequenceMatcher(None, title_norm, cand_title).ratio()
        cand_year = entry.get("year")
        year_match = year is not None and cand_year == year
        year_close = (
            year is not None
            and cand_year is not None
            and abs(int(cand_year) - int(year)) <= 1
        )
        if year_match and ratio >= 0.85:
            confidence = max(0.85, ratio)
            reason = "title + year exact match"
        elif year_close and ratio >= 0.6:
            # 相似度 0.6→confidence 0.6，0.85→confidence 0.8 线性映射
            confidence = min(0.8, 0.6 + 0.2 * (ratio - 0.6) / 0.25)
            reason = "title similar + year close (needs confirmation)"
        elif ratio >= 0.9:
            confidence = max(0.6, ratio)
            reason = "title highly similar (needs confirmation)"
        else:
            continue
        results.append(DuplicateResult(
            matched=confidence >= 0.85,
            reason=reason,
            canonical_paper_id=entry.get("paper_id"),
            confidence=round(confidence, 4),
            matched_fields=["title", "year"] if year_match or year_close else ["title"],
        ))
    results.sort(key=lambda r: r.confidence, reverse=True)
    return results


def detect_all(
    doi: str = "",
    sha256: str = "",
    title: str = "",
    year: int | None = None,
    index: LibraryIndex | None = None,
    manifest: PaperManifest | None = None,
) -> dict:
    """综合查重，返回汇总 dict。

    返回:
      {
        "is_duplicate": bool,            # DOI 或 sha256 确定重复（confidence 1.0）
        "canonical_paper_id": str|None,
        "doi_match": DuplicateResult,
        "sha256_match": DuplicateResult,
        "title_matches": list[DuplicateResult],
        "needs_confirmation": bool,      # 仅有疑似 title 重复
      }
    """
    doi_res = detect_duplicate_by_doi(doi, index=index) if doi else DuplicateResult(matched=False, reason="no doi")
    sha_res = detect_duplicate_by_sha256(sha256, manifest=manifest) if sha256 else DuplicateResult(matched=False, reason="no sha256")
    title_res = detect_possible_duplicate_by_title(title, year, index=index) if title else []

    canonical = None
    is_duplicate = False
    if doi_res.matched:
        canonical = doi_res.canonical_paper_id
        is_duplicate = True
    elif sha_res.matched:
        canonical = sha_res.canonical_paper_id
        is_duplicate = True

    needs_confirmation = (not is_duplicate) and any(r.confidence >= 0.6 for r in title_res)

    return {
        "is_duplicate": is_duplicate,
        "canonical_paper_id": canonical,
        "doi_match": doi_res,
        "sha256_match": sha_res,
        "title_matches": title_res,
        "needs_confirmation": needs_confirmation,
    }
