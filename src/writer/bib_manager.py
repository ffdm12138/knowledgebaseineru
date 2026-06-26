"""任务级 BibTeX：从全局 references.bib 抽取 + 校验 \cite{} 一致性"""
import re
from pathlib import Path

from src.writer.job_manager import JobManager
from src import bib as bibmod


def export_job_bib(job_id: str, bib_keys: list[str],
                   jm: JobManager | None = None) -> dict:
    """从全局 references.bib 抽取指定 key 写入 job 的 tex/references.bib"""
    jm = jm or JobManager()
    text = bibmod.get_entries_for_keys(bib_keys)
    out = jm.job_dir(job_id) / "tex" / "references.bib"
    out.parent.mkdir(parents=True, exist_ok=True)
    header = f"% write/{job_id} 引用库，由 {len(bib_keys)} 条 BibTeX 抽取生成。\n\n"
    out.write_text(header + text, encoding="utf-8")
    return {"references_bib": str(out), "count": len(bib_keys)}


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
