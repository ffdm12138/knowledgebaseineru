"""Validate the domain-aware library files.

契约：领域 catalog 是视图层，允许同一篇文献跨领域重复索引；
但物理存储层（library_index / manifest / 全局 catalog / references.bib）
必须保持一篇文献一份 canonical 记录。
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger

from config.settings import (
    CATALOG_PATH,
    DOMAIN_CATALOG_DIR,
    LIBRARY_INDEX_PATH,
    MANIFEST_PATH,
)
from src import bib as bibmod
from src.library_index import DOMAIN_REGISTRY, LibraryIndex
from src.path_utils import resolve_stored_path


def _load_json(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8"))


def validate_domain_library(
    catalog_path: Path = CATALOG_PATH,
    index_path: Path = LIBRARY_INDEX_PATH,
    domain_dir: Path = DOMAIN_CATALOG_DIR,
    manifest_path: Path = MANIFEST_PATH,
    check_paths: bool = False,
) -> tuple[list[str], list[str]]:
    """返回 (errors, warnings)。

    errors 违反核心契约；warnings 为快照友好的软提示（缺失物理文件等）。
    """
    errors: list[str] = []
    warnings: list[str] = []

    try:
        catalog = _load_json(catalog_path)
    except Exception as e:
        return [f"failed to load catalog: {e}"], warnings

    index = LibraryIndex(index_path)
    try:
        errors.extend(index.validate(check_paths=check_paths))
        index_data = index.load()
    except Exception as e:
        errors.append(f"failed to validate library_index: {e}")
        index_data = {"papers": []}

    root_by_id = {p.get("paper_id"): p for p in catalog.get("papers", [])}
    index_by_id = {p.get("paper_id"): p for p in index_data.get("papers", [])}
    if set(root_by_id) != set(index_by_id):
        errors.append("root catalog paper_ids differ from library_index paper_ids")

    # --- 物理存储层唯一性：禁止重复 ---
    # library_index 内 paper_id 唯一（index.validate 已查），这里查 DOI/bib_key 多义性
    doi_to_pids: dict[str, list[str]] = {}
    bib_to_pids: dict[str, list[str]] = {}
    seen_doi = set()
    seen_bib = set()
    for pid, paper in root_by_id.items():
        idx = index_by_id.get(pid)
        if idx:
            if paper.get("primary_domain") != idx.get("primary_domain"):
                errors.append(f"{pid} primary_domain differs between catalog and index")
            if list(paper.get("domains") or []) != list(idx.get("domains") or []):
                errors.append(f"{pid} domains differs between catalog and index")
        doi = (paper.get("doi") or "").strip().lower()
        if doi:
            doi_to_pids.setdefault(doi, []).append(pid)
            if doi in seen_doi:
                errors.append(f"duplicate DOI in root catalog: {doi}")
            seen_doi.add(doi)
        bib_key = ((paper.get("citation") or {}).get("bib_key") or "").strip()
        if not bib_key:
            errors.append(f"{pid} missing citation.bib_key")
        else:
            bib_to_pids.setdefault(bib_key, []).append(pid)
            if bib_key in seen_bib:
                errors.append(f"duplicate bib_key in root catalog: {bib_key}")
            seen_bib.add(bib_key)

    # 同一 DOI 对应多个 paper_id（物理重复）
    for doi, pids in doi_to_pids.items():
        if len(set(pids)) > 1:
            errors.append(f"DOI {doi} maps to multiple paper_ids: {sorted(set(pids))}")
    # 同一 bib_key 对应多个 paper_id
    for bib_key, pids in bib_to_pids.items():
        if len(set(pids)) > 1:
            errors.append(f"bib_key {bib_key} maps to multiple paper_ids: {sorted(set(pids))}")

    # manifest sha256 唯一性：同一 sha256 不能对应多个 converted canonical paper
    try:
        manifest = _load_json(manifest_path)
        sha_to_pids: dict[str, list[str]] = {}
        for entry in manifest.get("papers", []):
            sha = (entry.get("sha256") or "").strip().lower()
            if not sha:
                continue
            sha_to_pids.setdefault(sha, []).append(entry.get("paper_id", ""))
        for sha, pids in sha_to_pids.items():
            converted = [p for p in pids if p]
            if len(set(converted)) > 1:
                errors.append(f"sha256 {sha} maps to multiple manifest papers: {sorted(set(converted))}")
    except Exception as e:
        warnings.append(f"could not check manifest sha256 uniqueness: {e}")

    # --- 领域视图层：允许跨领域重复，校验 membership 一致性 ---
    # 每个 domain catalog 的期望成员 = root catalog 中 domains 声明该领域的所有 paper
    expected_ids_by_domain: dict[str, set[str]] = {}
    for domain_id in DOMAIN_REGISTRY:
        expected_ids_by_domain[domain_id] = {
            pid for pid, p in root_by_id.items() if domain_id in (p.get("domains") or [])
        }

    domain_actual: dict[str, set[str]] = {}
    for domain_id in DOMAIN_REGISTRY:
        catalog_file = domain_dir / domain_id / "literature_catalog.json"
        bib_file = domain_dir / domain_id / "references.bib"
        try:
            domain_catalog = _load_json(catalog_file)
        except Exception as e:
            errors.append(f"failed to load {catalog_file}: {e}")
            continue
        domain_papers = domain_catalog.get("papers", [])
        actual_ids = set()
        seen_in_domain: set[str] = set()
        for p in domain_papers:
            pid = p.get("paper_id")
            # 同一领域 catalog 内部不应重复
            if pid in seen_in_domain:
                errors.append(f"{domain_id} catalog has duplicate paper_id: {pid}")
            seen_in_domain.add(pid)
            actual_ids.add(pid)
            # domain catalog 中的 paper_id 必须在 library_index 有 canonical 记录
            if pid and pid not in index_by_id:
                errors.append(f"{domain_id} catalog paper_id {pid} not in library_index")
            # domain catalog 中的 paper_id 必须在全局 catalog 有 canonical 条目
            if pid and pid not in root_by_id:
                errors.append(f"{domain_id} catalog paper_id {pid} not in global catalog")
            # domain_view.domain_id 必须与所在文件夹一致
            view = p.get("domain_view") or {}
            view_domain = view.get("domain_id")
            if view_domain and view_domain != domain_id:
                errors.append(
                    f"{domain_id} catalog entry {pid} domain_view.domain_id={view_domain} mismatch"
                )
        domain_actual[domain_id] = actual_ids
        expected_ids = expected_ids_by_domain[domain_id]
        if actual_ids != expected_ids:
            errors.append(
                f"{domain_id} catalog paper_ids do not match root catalog domains membership"
            )

        if not bib_file.exists():
            errors.append(f"missing {bib_file}")
            continue
        bib_blocks = set(bibmod.parse_blocks(bib_file.read_text(encoding="utf-8")))
        expected_bib = {
            (root_by_id[pid].get("citation") or {}).get("bib_key")
            for pid in expected_ids
            if (root_by_id[pid].get("citation") or {}).get("bib_key")
        }
        if bib_blocks != expected_bib:
            errors.append(f"{domain_id} references.bib keys do not match domain catalog")

    # 双向 membership 一致性：paper domains 声明 vs domain catalog 实际收录
    for domain_id in DOMAIN_REGISTRY:
        expected = expected_ids_by_domain[domain_id]
        actual = domain_actual.get(domain_id, set())
        missing = expected - actual  # 声明了但 domain catalog 没有
        extra = actual - expected    # domain catalog 有但 domains 没声明
        for pid in sorted(missing):
            errors.append(f"{pid} declares domain {domain_id} but missing from its catalog")
        for pid in sorted(extra):
            errors.append(f"{pid} in {domain_id} catalog but domains does not declare it")

    # --- warnings：快照友好的软提示 ---
    for pid, idx in index_by_id.items():
        md = (idx.get("markdown_path") or "").strip()
        if md and not resolve_stored_path(md).exists():
            warnings.append(f"{pid} markdown_path not found: {md}")
        imgs = (idx.get("images_dir") or "").strip()
        if imgs and not resolve_stored_path(imgs).exists():
            warnings.append(f"{pid} images_dir not found: {imgs}")
        raw = (idx.get("raw_pdf") or "").strip()
        if raw and not resolve_stored_path(raw).exists():
            warnings.append(f"{pid} raw_pdf not found: {raw}")
    for domain_id in DOMAIN_REGISTRY:
        if not expected_ids_by_domain.get(domain_id):
            warnings.append(f"domain {domain_id} has no papers")

    return errors, warnings


def main() -> int:
    errors, warnings = validate_domain_library()
    if not errors:
        for w in warnings:
            logger.warning(w)
        logger.info("domain library validation passed")
        return 0
    logger.error(f"domain library validation failed: {len(errors)} errors")
    for e in errors:
        logger.error(f"  - {e}")
    for w in warnings:
        logger.warning(w)
    return 1


if __name__ == "__main__":
    sys.exit(main())
