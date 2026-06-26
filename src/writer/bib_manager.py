"""任务级 BibTeX：catalog citation 校验 + 全局库原子同步 + job bib 导出 + \\cite 一致性"""
import re
from datetime import datetime
from pathlib import Path

from src.writer.job_manager import JobManager
from src.writer.catalog_matcher import load_selected
from src.catalog import Catalog
from src import bib as bibmod
from config.settings import CATALOG_PATH


def validate_catalog_citations(catalog_data: dict | None = None) -> list[str]:
    """校验 catalog 中每篇的 citation 字段。返回错误列表（空=通过）。

    检查：有 citation；bib_key 非空且唯一；bibtex 非空且以 @ 开头；
    bibtex entry key == citation.bib_key；bibtex 含 title/author/year；
    DOI 有则 warning（不计入 fatal）。
    """
    cat = catalog_data or Catalog().load()
    errors = []
    warnings = []
    seen = set()
    for p in cat.get("papers", []):
        ctx = f"paper_id={p.get('paper_id', '?')}"
        cit = p.get("citation", {}) or {}
        if not cit:
            errors.append(f"{ctx} 无 citation")
            continue
        bk = cit.get("bib_key")
        if not bk:
            errors.append(f"{ctx} citation.bib_key 为空")
        elif bk in seen:
            errors.append(f"{ctx} bib_key 重复: {bk}")
        else:
            seen.add(bk)
        bt = (cit.get("bibtex") or "").strip()
        if not bt:
            errors.append(f"{ctx} citation.bibtex 为空")
            continue
        if not bt.startswith("@"):
            errors.append(f"{ctx} bibtex 应以 @ 开头")
            continue
        # entry key == bib_key
        m = re.match(r"@\w+\s*\{\s*([^,\s]+)", bt)
        if m and m.group(1) != bk:
            errors.append(f"{ctx} bibtex entry key({m.group(1)}) != bib_key({bk})")
        for field in ["title", "author", "year"]:
            if not re.search(rf"\b{field}\s*=", bt, re.IGNORECASE):
                errors.append(f"{ctx} bibtex 缺少 {field} 字段")
        doi = p.get("doi")
        if doi and "doi" not in bt.lower():
            warnings.append(f"{ctx} catalog 有 doi 但 bibtex 未写 doi")
    return errors  # 仅 fatal；warnings 由调用方按需处理


def sync_from_catalog(backup: bool = True) -> Path:
    """同步生成 data/catalog/references.bib，带校验 + 备份 + 原子写入。

    流程：validate → 备份旧文件 → 写 tmp → 校验 tmp 非空 → 原子替换。
    """
    cat = Catalog().load()
    errors = validate_catalog_citations(cat)
    if errors:
        raise RuntimeError(f"catalog citation 校验未通过，拒绝同步 references.bib:\n"
                           + "\n".join(errors))

    blocks = []
    for p in cat.get("papers", []):
        bt = ((p.get("citation") or {}).get("bibtex") or "").strip()
        if bt:
            blocks.append(bt)
    text = ("% 由 literature_catalog.json 自动同步生成，请勿手动编辑。\n\n"
            + "\n\n".join(blocks) + "\n")

    dest = bibmod.GLOBAL_BIB_PATH
    dest.parent.mkdir(parents=True, exist_ok=True)

    # 备份
    if backup and dest.exists():
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        bak = dest.with_name(dest.name + f".bak_{ts}")
        bak.write_text(dest.read_text(encoding="utf-8"), encoding="utf-8")

    # 原子写入：tmp → replace
    tmp = dest.with_name(dest.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    if not tmp.read_text(encoding="utf-8").strip():
        raise RuntimeError("写入 references.bib.tmp 为空，中止")
    # 解析 tmp 确认条目数一致
    parsed = bibmod.parse_blocks(tmp.read_text(encoding="utf-8"))
    if len(parsed) != len(blocks):
        raise RuntimeError(f"tmp 解析条目数({len(parsed)}) != 预期({len(blocks)})，中止")
    tmp.replace(dest)
    return dest


def export_job_bib(job_id: str, bib_keys: list[str] | None = None,
                   jm: JobManager | None = None) -> dict:
    """从全局 references.bib 抽取 selected_papers 对应条目写入 job 的 tex/references.bib。

    bib_keys 为 None 时从 selected_papers.json（必须 confirmed）取。
    selected 未确认时 raise RuntimeError。
    """
    jm = jm or JobManager()
    jdir = jm.job_dir(job_id)

    if bib_keys is None:
        sel = load_selected(job_id, jm)
        if sel.get("selection_status") != "confirmed":
            raise RuntimeError("selected_papers.json is not confirmed，拒绝导出 references.bib")
        bib_map = {p["paper_id"]: (p.get("citation") or {}).get("bib_key", "")
                   for p in Catalog().list_papers()}
        bib_keys = []
        for it in sel.get("selected_papers", []):
            bk = it.get("bib_key") or bib_map.get(it.get("paper_id", ""), "")
            if bk:
                bib_keys.append(bk)

    # 确认所有请求的 key 都能导出（缺失则报错，不静默丢 key）
    all_blocks = bibmod.load_global_bib()
    missing = [k for k in bib_keys if k not in all_blocks]
    if missing:
        raise ValueError(f"全局 references.bib 中缺少以下 bib key，拒绝导出: {missing}")
    text = bibmod.get_entries_for_keys(bib_keys)
    out = jdir / "tex" / "references.bib"
    out.parent.mkdir(parents=True, exist_ok=True)
    header = f"% write/{job_id} 引用库，由 {len(bib_keys)} 条 BibTeX 抽取生成。\n\n"
    out.write_text(header + text, encoding="utf-8")
    return {"references_bib": str(out), "count": len(bib_keys)}


def validate_job_bib(job_id: str, jm: JobManager | None = None) -> list[str]:
    """校验 job 的 references.bib：entry key 不重复、与 selected 对应。返回错误列表。"""
    jm = jm or JobManager()
    jdir = jm.job_dir(job_id)
    bib_path = jdir / "tex" / "references.bib"
    errors = []
    if not bib_path.exists():
        return ["缺少 tex/references.bib"]
    blocks = bibmod.parse_blocks(bib_path.read_text(encoding="utf-8"))
    # entry key 不重复（parse_blocks 已天然去重，这里再校验原始文本）
    raw = bib_path.read_text(encoding="utf-8")
    keys = re.findall(r"@\w+\s*\{\s*([^,\s]+)", raw)
    if len(keys) != len(set(keys)):
        errors.append("references.bib 中存在重复 entry key")
    # 与 selected 对应
    sel = load_selected(job_id, jm)
    if sel.get("selection_status") == "confirmed":
        sel_keys = set()
        bib_map = {p["paper_id"]: (p.get("citation") or {}).get("bib_key", "")
                   for p in Catalog().list_papers()}
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
        # 去掉行内注释（% 后内容，但 \% 转义除外——此处简化处理行首/整行注释）
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

    # 收集所有 .tex 中的 \cite{}
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
        # 处理无扩展名与相对路径
        p = (base / ref).resolve()
        return p

    for tex in tex_dir.rglob("*.tex"):
        text = tex.read_text(encoding="utf-8")
        for line in text.splitlines():
            if line.lstrip().startswith("%"):
                continue
            # \bibliography{refs} 或 \addbibresource{refs.bib}
            for m in re.finditer(r"\\(?:bibliography|addbibresource)\s*\{([^}]*)\}", line):
                ref = m.group(1).strip()
                cand = _resolve(tex.parent, ref)
                if not cand.exists() and not cand.with_suffix(".bib").exists():
                    errors.append(f"{tex.name}: \\bibliography{{{ref}}} 在 tex/ 内找不到")
            # \input{...} / \include{...}
            for m in re.finditer(r"\\(?:input|include)\s*\{([^}]*)\}", line):
                ref = m.group(1).strip()
                cand = _resolve(tex.parent, ref)
                if not (cand.exists() or cand.with_suffix(".tex").exists()):
                    errors.append(f"{tex.name}: \\input{{{ref}}} 找不到")
            # \includegraphics{...}
            for m in re.finditer(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]*)\}", line):
                ref = m.group(1).strip()
                # 必须落在 job 目录内（禁止指向 data/papers 等外部）
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
