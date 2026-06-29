"""任务级 BibTeX：catalog citation 校验 + job bib 导出 + \\cite 一致性。

v2 不再有全局 references.bib；每篇 BibTeX 由 bibtex_from_metadata 从 metadata.json
生成，写作时抽取选中论文写入 job 内 tex/references.bib。bib_key = metadata.citation_key or paper_id。
"""
import re
from pathlib import Path

from src.writer.job_manager import JobManager
from src.writer.catalog_matcher import load_selected
from src.catalog import Catalog
from src import bib as bibmod


def _bib_map(papers: list[dict]) -> dict[str, str]:
    """paper_id -> bib_key (metadata.citation_key or paper_id)。"""
    return {p.get("paper_id", ""): bibmod.bib_key_for_entry(p) for p in papers}


def validate_catalog_citations(catalog_data: dict | None = None) -> list[str]:
    """校验 catalog 中每篇可生成的 BibTeX。返回错误列表（空=通过）。

    v2：bib_key = metadata.citation_key or paper_id，必须非空且唯一；
    bibtex_from_metadata 生成的条目以 @ 开头、entry key == bib_key、含 title/author/year；
    metadata.identifiers.doi 有值时 bibtex 应含 doi。
    """
    cat = catalog_data or Catalog().load()
    errors = []
    seen = set()
    for p in cat.get("papers", []):
        ctx = f"paper_id={p.get('paper_id', '?')}"
        bk = bibmod.bib_key_for_entry(p)
        if not bk:
            errors.append(f"{ctx} bib_key 为空")
        elif bk in seen:
            errors.append(f"{ctx} bib_key 重复: {bk}")
        else:
            seen.add(bk)
        bt = bibmod.bibtex_for_entry(p).strip()
        if not bt or not bt.startswith("@"):
            errors.append(f"{ctx} bibtex 生成失败或不以 @ 开头")
            continue
        m = re.match(r"@\w+\s*\{\s*([^,\s]+)", bt)
        if m and m.group(1) != bk:
            errors.append(f"{ctx} bibtex entry key({m.group(1)}) != bib_key({bk})")
        for field in ("title", "author", "year"):
            if not re.search(rf"\b{field}\s*=", bt, re.IGNORECASE):
                errors.append(f"{ctx} bibtex 缺少 {field} 字段")
        meta = p.get("metadata") or {}
        doi = ((meta.get("identifiers") or {}).get("doi") or "").strip()
        if doi and "doi" not in bt.lower():
            errors.append(f"{ctx} metadata 有 doi 但 bibtex 未写 doi")
    return errors


def export_job_bib(job_id: str, bib_keys: list[str] | None = None,
                   jm: JobManager | None = None) -> dict:
    """为 job 抽取 selected_papers 对应的 BibTeX，逐篇生成写入 job 的 tex/references.bib。

    bib_keys 为 None 时从 selected_papers.json（必须 confirmed）取。
    v2 直接由 bibtex_from_metadata 生成，不再依赖全局 references.bib。
    """
    jm = jm or JobManager()
    jdir = jm.job_dir(job_id)
    papers = Catalog().list_papers()
    by_id = {p.get("paper_id"): p for p in papers}

    if bib_keys is None:
        sel = load_selected(job_id, jm)
        if sel.get("selection_status") != "confirmed":
            raise RuntimeError("selected_papers.json is not confirmed，拒绝导出 references.bib")
        bib_map = _bib_map(papers)
        entries: list[dict] = []
        for it in sel.get("selected_papers", []):
            pid = it.get("paper_id", "")
            entry = by_id.get(pid)
            bk = it.get("bib_key") or bib_map.get(pid, "")
            if entry and bk:
                entries.append(entry)
        bib_keys = [bibmod.bib_key_for_entry(e) for e in entries]
    else:
        wanted = set(bib_keys)
        entries = [p for p in papers if bibmod.bib_key_for_entry(p) in wanted]

    blocks = [bibmod.bibtex_for_entry(e) for e in entries]
    out = jdir / "tex" / "references.bib"
    out.parent.mkdir(parents=True, exist_ok=True)
    header = f"% write/{job_id} 引用库，由 {len(blocks)} 条 BibTeX 从 metadata 生成。\n\n"
    out.write_text(header + "\n\n".join(blocks) + "\n", encoding="utf-8")
    return {"references_bib": str(out), "count": len(blocks)}


def validate_job_bib(job_id: str, jm: JobManager | None = None) -> list[str]:
    """校验 job 的 references.bib：entry key 不重复、与 selected 对应。返回错误列表。"""
    jm = jm or JobManager()
    jdir = jm.job_dir(job_id)
    bib_path = jdir / "tex" / "references.bib"
    errors = []
    if not bib_path.exists():
        return ["缺少 tex/references.bib"]
    blocks = bibmod.parse_blocks(bib_path.read_text(encoding="utf-8"))
    raw = bib_path.read_text(encoding="utf-8")
    keys = re.findall(r"@\w+\s*\{\s*([^,\s]+)", raw)
    if len(keys) != len(set(keys)):
        errors.append("references.bib 中存在重复 entry key")
    sel = load_selected(job_id, jm)
    if sel.get("selection_status") == "confirmed":
        bib_map = _bib_map(Catalog().list_papers())
        sel_keys = set()
        for it in sel.get("selected_papers", []):
            bk = it.get("bib_key") or bib_map.get(it.get("paper_id", ""), "")
            if bk:
                sel_keys.add(bk)
        extra = set(blocks.keys()) - sel_keys
        if extra:
            errors.append(f"references.bib 含 selected_papers 之外的条目: {sorted(extra)}")
    return errors


def _extract_cite_keys(tex_text: str) -> set[str]:
    """从 TeX 文本提取所有 \\cite{...} 中的 key（支持多 key 与 cite变体）。
    跳过 % 注释行，避免模板里的占位 \\cite{bib_key} 被误判。"""
    keys = set()
    for line in tex_text.splitlines():
        code = line.split("%", 1)[0] if line.lstrip().startswith("%") else line
        if line.lstrip().startswith("%"):
            continue
        for m in re.finditer(r"\\cite[a-zA-Z]*\s*\{([^}]*)\}", code):
            for k in m.group(1).split(","):
                k = k.strip()
                if k:
                    keys.add(k)
    return keys


def validate_job_citations(job_id: str, jm: JobManager | None = None) -> dict:
    """校验 job 的 TeX 引用与 references.bib 一致性"""
    jm = jm or JobManager()
    jdir = jm.job_dir(job_id)
    bib_path = jdir / "tex" / "references.bib"
    bib_keys = set(bibmod.parse_blocks(bib_path.read_text(encoding="utf-8")).keys()) if bib_path.exists() else set()

    cited = set()
    for tex in jdir.rglob("*.tex"):
        cited |= _extract_cite_keys(tex.read_text(encoding="utf-8"))

    missing = cited - bib_keys
    unused = bib_keys - cited
    return {
        "cited_keys": sorted(cited),
        "bib_keys": sorted(bib_keys),
        "missing_in_bib": sorted(missing),
        "unused_in_bib": sorted(unused),
        "valid": len(missing) == 0,
    }


def portability_check(job_id: str, jm: JobManager | None = None) -> dict:
    """检查 job 的 tex 项目是否完全自包含、可整体挪走。

    确认所有引用资源都能在 job 目录内解析：
    - \\bibliography{...} 指向的 .bib 在 tex/ 内
    - \\input{...}/\\include{...} 指向的 .tex 存在
    - \\includegraphics{...} 指向的图在 job 内
    - 不依赖 data/ 等外部绝对路径
    """
    jm = jm or JobManager()
    jdir = jm.job_dir(job_id)
    tex_dir = jdir / "tex"
    errors = []

    def _resolve(base: Path, ref: str) -> Path:
        p = (base / ref).resolve()
        return p

    for tex in tex_dir.rglob("*.tex"):
        text = tex.read_text(encoding="utf-8")
        for line in text.splitlines():
            if line.lstrip().startswith("%"):
                continue
            for m in re.finditer(r"\\(?:bibliography|addbibresource)\s*\{([^}]*)\}", line):
                ref = m.group(1).strip()
                cand = _resolve(tex.parent, ref)
                if not cand.exists() and not cand.with_suffix(".bib").exists():
                    errors.append(f"{tex.name}: \\bibliography{{{ref}}} 在 tex/ 内找不到")
            for m in re.finditer(r"\\(?:input|include)\s*\{([^}]*)\}", line):
                ref = m.group(1).strip()
                cand = _resolve(tex.parent, ref)
                if not (cand.exists() or cand.with_suffix(".tex").exists()):
                    errors.append(f"{tex.name}: \\input{{{ref}}} 找不到")
            for m in re.finditer(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]*)\}", line):
                ref = m.group(1).strip()
                resolved = _resolve(tex.parent, ref)
                try:
                    resolved.relative_to(jdir.resolve())
                except ValueError:
                    errors.append(f"{tex.name}: \\includegraphics{{{ref}}} 指向 job 目录外，不可移植")
                    continue
                if not resolved.exists():
                    errors.append(f"{tex.name}: \\includegraphics{{{ref}}} 文件不存在（在 job 内但缺失）")

    return {
        "portable": len(errors) == 0,
        "errors": errors,
        "note": "job 目录可整体复制/挪走，所有引用资源均自包含" if not errors else "存在外部依赖，不可直接挪走",
    }
