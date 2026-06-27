"""pending OA PDF 正式入库 CLI。

流程：读取 pending PDF + sidecar → 规范化 DOI → 计算 sha256 → 本地查重 →
（重复）只更新 domains membership；或（新文献）转换+清理+manifest+library_index+
全局 catalog placeholder+领域 catalog → 更新 sidecar 状态。

默认 dry-run，传 --apply 才写入。不自动生成 AI summary（只生成待补全 placeholder 与
catalog-entry prompt）。MinerU 转换/清理通过 MinerUConverter/MinerUOutputCleaner，
测试可 monkeypatch 其方法，不真实调用 MinerU。
"""
import argparse
import hashlib
import json
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

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
from src.catalog import Catalog
from src.cleaner import MinerUOutputCleaner
from src.discovery.models import normalize_doi
from src.duplicate_detector import detect_all
from src.library_index import VALID_DOMAINS, LibraryIndex
from src.manifest import PaperManifest
from src.naming import safe_child, validate_paper_id
from src.converter import MinerUConverter
from scripts.migrate_to_domain_library import apply_domain_library, build_domain_library


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _compute_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _make_slug(text: str, max_len: int = 50) -> str:
    """将标题转为 paper_id 可用 slug。

    规则（符合项目命名规范）：
    - 保留中文（\\u4e00-\\u9fff）、拉丁字母、数字
    - 其余非字母数字字符替换为 _
    - 首尾 _ 修剪
    - 截断至 max_len 字符

    注：slug 主要用于 auto-fallback；推荐通过 --paper-id 传入中文名称。
    """
    if not text:
        return "untitled"
    slug = re.sub(r"[^一-鿿A-Za-z0-9]+", "_", text).strip("_").lower()
    if len(slug) > max_len:
        slug = slug[:max_len].rstrip("_")
    return slug or "untitled"


def _build_placeholder_entry(
    paper_id: str,
    title: str,
    year: int | None,
    doi: str,
    raw_pdf: str,
    markdown: str,
    images_dir: str,
    primary_domain: str,
    domains: list[str],
    existing_bib_keys: set[str],
) -> dict:
    """构建待补全 catalog placeholder（status=unsummarized，所有必填字段齐备）。"""
    base = f"{year}_{_make_slug(title)}" if year else _make_slug(title)
    bib_key = base
    suffix = 2
    while bib_key in existing_bib_keys:
        bib_key = f"{base}_{suffix}"
        suffix += 1
    bibtex = "@misc{" + bib_key + ",\n"
    bibtex += f"  title = {{{title}}},\n"
    if year:
        bibtex += f"  year = {{{year}}},\n"
    if doi:
        bibtex += f"  doi = {{{doi}}},\n"
    bibtex += "}\n"
    return {
        "paper_id": paper_id,
        "title": title or "(待补全标题)",
        "authors": [],
        "year": year,
        "venue": "",
        "doi": doi,
        "raw_pdf": raw_pdf,
        "markdown": markdown,
        "images_dir": images_dir,
        "status": "unsummarized",
        "primary_domain": primary_domain,
        "domains": list(domains),
        "ai_summary": {
            "one_sentence": "",
            "background_problem": "",
            "research_question": "",
            "method": "",
            "data_or_experiment": "",
            "main_findings": "",
            "key_equations_or_models": [],
            "important_figures": [],
            "limitations": "",
            "relevance_to_my_work": "",
            "possible_use_in_paper": "",
        },
        "tags": {
            "topic": [],
            "method": [],
            "material_or_region": [],
            "variables": [],
            "model_names": [],
        },
        "selection_hints": {
            "read_when_question_contains": [],
            "do_not_use_for": [],
            "priority": 3,
        },
        "notes": "pending PDF import placeholder — run /prompt/catalog-entry to complete",
        "citation": {
            "bib_key": bib_key,
            "bibtex": bibtex,
            "citation_style_name": f"({year})" if year else "(n.d.)",
            "source": "pending_import",
            "verified": False,
        },
    }


def _read_sidecar(pdf_path: Path) -> dict:
    sidecar = pdf_path.with_suffix(".json")
    if sidecar.exists():
        try:
            return _load_json(sidecar)
        except Exception:
            return {}
    return {}


def _update_sidecar(pdf_path: Path, status: str, canonical_paper_id: str = "",
                    extra: dict | None = None) -> None:
    sidecar = pdf_path.with_suffix(".json")
    data = _read_sidecar(pdf_path)
    data["status"] = status
    if canonical_paper_id:
        data["canonical_paper_id"] = canonical_paper_id
    data["imported_at"] = datetime.now().isoformat(timespec="seconds")
    if extra:
        data.update(extra)
    sidecar.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _regenerate_domain_views(catalog_path: Path, manifest_path: Path,
                             index_path: Path, domain_dir: Path) -> None:
    """从全局 catalog + manifest 重建 library_index / 领域 catalog / bibs。"""
    catalog_data = _load_json(catalog_path)
    manifest_data = _load_json(manifest_path)
    updated_catalog, index, domain_catalogs, domain_bibs, global_bib = build_domain_library(
        catalog_data, manifest_data
    )
    apply_domain_library(
        updated_catalog, index, domain_catalogs, domain_bibs, global_bib,
        catalog_path=catalog_path, index_path=index_path, domain_dir=domain_dir,
    )


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
    """导入一个 pending PDF。返回结果 dict（dry-run 不写入）。"""
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
    }

    # --- 重复：只更新 domains membership，不重新转换 ---
    if dup["is_duplicate"]:
        existing_pid = dup["canonical_paper_id"]
        result["canonical_paper_id"] = existing_pid
        result["status"] = "duplicate"
        if not apply:
            logger.info(f"[dry-run] duplicate of {existing_pid}; would update domains membership")
            return result
        catalog = Catalog(catalog_path)
        data = catalog.load()
        for p in data.get("papers", []):
            if p.get("paper_id") == existing_pid:
                cur_domains = list(p.get("domains") or [])
                for d in all_domains:
                    if d not in cur_domains:
                        cur_domains.append(d)
                p["domains"] = cur_domains
                break
        catalog.save(data)
        _regenerate_domain_views(catalog_path, manifest_path, index_path, domain_dir)
        _update_sidecar(pdf_path, "duplicate", canonical_paper_id=existing_pid,
                        extra={"domains": all_domains})
        result["applied"] = True
        logger.info(f"duplicate: {existing_pid} domains updated to {all_domains}")
        return result

    if dup["needs_confirmation"]:
        logger.warning("疑似重复（title 相似），需用户确认；dry-run 下不入库")
        if not apply:
            result["status"] = "needs_confirmation"
            return result
        # apply 模式下仍允许入库（用户已确认），继续

    # --- 新文献入库 ---
    # 生成 canonical paper_id
    if paper_id:
        pid = paper_id
    else:
        slug = _make_slug(title)
        pid = f"{year}_{slug}" if year else slug
    validate_paper_id(pid)

    # raw PDF 目标位置：data/raw/<pid>.pdf
    raw_target = safe_child(raw_dir, f"{pid}.pdf")
    markdown_rel = f"data/papers/{pid}/paper.md"
    images_rel = f"data/papers/{pid}/images"

    if not apply:
        logger.info(f"[dry-run] new paper_id={pid}, would convert + register domains={all_domains}")
        result["paper_id"] = pid
        result["status"] = "pending"
        return result

    # 复制 PDF 到正式 raw 位置
    raw_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(pdf_path, raw_target)

    # 转换 + 清理
    converter = converter or MinerUConverter()
    cleaner = cleaner or MinerUOutputCleaner()
    out_dir = tmp_dir / pid
    conv = converter.convert(
        str(raw_target), out_dir,
        backend=MINERU_BACKEND, method=MINERU_METHOD, lang=MINERU_LANG, effort=MINERU_EFFORT,
    )
    if not conv.get("success"):
        mfst.upsert(pid, raw_pdf=str(raw_target), markdown="", images_dir="",
                    status="failed", sha256=sha256, error=conv.get("error", "convert failed"),
                    mineru_backend=MINERU_BACKEND, method=MINERU_METHOD, effort=MINERU_EFFORT,
                    runner=conv.get("runner", "cli"))
        raise RuntimeError(f"MinerU convert failed: {conv.get('error')}")
    clean = cleaner.extract(
        conv["output_dir"], pid, overwrite=False,
        method=MINERU_METHOD, stem=raw_target.stem, backend=MINERU_BACKEND,
    )
    if not clean.get("success"):
        mfst.upsert(pid, raw_pdf=str(raw_target), markdown="", images_dir="",
                    status="failed", sha256=sha256, error=clean.get("error", "clean failed"),
                    mineru_backend=MINERU_BACKEND, method=MINERU_METHOD, effort=MINERU_EFFORT,
                    runner=conv.get("runner", "cli"))
        raise RuntimeError(f"cleaner extract failed: {clean.get('error')}")

    # manifest
    mfst.upsert(
        pid, raw_pdf=str(raw_target), markdown=clean["markdown_path"],
        images_dir=clean["images_dir"], status="converted",
        images_count=clean["images_count"], md_chars=clean["char_count"],
        sha256=sha256, raw_filename=raw_target.name, raw_stem=raw_target.stem,
        mineru_backend=MINERU_BACKEND, method=MINERU_METHOD, effort=MINERU_EFFORT,
        runner=conv.get("runner", "cli"),
    )

    # 全局 catalog placeholder
    catalog = Catalog(catalog_path)
    data = catalog.load()
    existing_bib_keys = {
        ((p.get("citation") or {}).get("bib_key") or "") for p in data.get("papers", [])
    }
    entry = _build_placeholder_entry(
        pid, title, year, doi, str(raw_target), clean["markdown_path"],
        clean["images_dir"], domain, all_domains, existing_bib_keys,
    )
    catalog.upsert(entry)

    # 重建 library_index / 领域 catalog / bibs
    _regenerate_domain_views(catalog_path, manifest_path, index_path, domain_dir)

    # sidecar
    _update_sidecar(pdf_path, "imported", canonical_paper_id=pid,
                    extra={"domains": all_domains, "primary_domain": domain})

    result["paper_id"] = pid
    result["status"] = "imported"
    result["applied"] = True
    logger.info(f"imported new paper: {pid} (domains={all_domains})")
    logger.info("下一步：运行 /prompt/catalog-entry 补全文献理解条目")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Import a pending OA PDF into the library.")
    parser.add_argument("pdf_path", type=Path, help="pending PDF 路径")
    parser.add_argument("--domain", required=True, choices=sorted(VALID_DOMAINS),
                        help="主领域 (primary domain)")
    parser.add_argument("--domains", nargs="+", default=None, help="全部领域 membership（含主领域）")
    parser.add_argument("--title", default="", help="标题（缺省从 sidecar 读）")
    parser.add_argument("--doi", default="", help="DOI（缺省从 sidecar 读）")
    parser.add_argument("--year", type=int, default=None, help="年份")
    parser.add_argument("--paper-id", default=None, help="显式 canonical paper_id（缺省自动生成）")
    parser.add_argument("--apply", action="store_true", help="实际写入（默认 dry-run）")
    args = parser.parse_args()

    try:
        result = import_pending_pdf(
            args.pdf_path, domain=args.domain, domains=args.domains,
            title=args.title, doi=args.doi, year=args.year, paper_id=args.paper_id,
            apply=args.apply,
        )
    except Exception as e:
        logger.error(f"import failed: {e}")
        return 1
    logger.info(f"status={result['status']} applied={result['applied']} "
                f"is_duplicate={result['is_duplicate']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
