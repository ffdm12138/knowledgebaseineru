"""校验写作任务产物完整性

检查：main.tex / introduction.tex / method.tex / references.bib 是否存在；
所有 \cite{} 能在 references.bib 找到；所有 \includegraphics 文件存在；
使用的图片有 source README；run_meta 状态完整。
退出码 0 通过，1 有错误。
用法: python scripts/validate_write_job.py --job 001_xxx
"""
import re
import sys
import json
import argparse
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from loguru import logger
from src.writer.job_manager import JobManager
from src.writer.bib_manager import validate_job_citations, portability_check


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--job", required=True)
    args = ap.parse_args()
    jm = JobManager()
    jdir = jm.job_dir(args.job)
    if not jdir.exists():
        logger.error(f"任务不存在: {args.job}")
        return 1

    errors = []
    # 必备文件
    must = {
        "tex/main.tex": jdir / "tex" / "main.tex",
        "tex/sections/introduction.tex": jdir / "tex" / "sections" / "introduction.tex",
        "tex/sections/method.tex": jdir / "tex" / "sections" / "method.tex",
        "tex/references.bib": jdir / "tex" / "references.bib",
        "logs/run_meta.json": jdir / "logs" / "run_meta.json",
    }
    for name, p in must.items():
        if not p.exists():
            errors.append(f"缺少 {name}")

    # \cite 一致性
    cite = validate_job_citations(args.job, jm=jm)
    warnings = []
    for k in cite["missing_in_bib"]:
        errors.append(f"\\cite{{{k}}} 在 references.bib 中找不到")
    for k in cite["unused_in_bib"]:
        warnings.append(f"references.bib 中 {k} 尚未被引用（待 LLM 填正文后引用）")

    # 可移植性：tex 项目是否自包含、可整体挪走
    port = portability_check(args.job, jm=jm)
    for e in port["errors"]:
        errors.append(e)

    # \includegraphics 文件存在
    for tex in jdir.rglob("*.tex"):
        text = tex.read_text(encoding="utf-8")
        for m in re.finditer(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]*)\}", text):
            gpath = m.group(1)
            # 相对 tex 文件解析
            resolved = (tex.parent / gpath).resolve()
            if not resolved.exists():
                errors.append(f"{tex.name}: \\includegraphics{{{gpath}}} 文件不存在")

    # 图片有 source README
    figdir = jdir / "figures"
    if figdir.exists():
        for pd in figdir.iterdir():
            if pd.is_dir() and not (pd / "README.md").exists():
                errors.append(f"figures/{pd.name}/ 缺少 README.md（图源记录）")

    # run_meta 状态
    meta_p = jdir / "logs" / "run_meta.json"
    if meta_p.exists():
        meta = json.loads(meta_p.read_text(encoding="utf-8"))
        if not meta.get("steps", {}).get("tex_generated"):
            errors.append("run_meta: tex_generated 未完成")

    if not errors:
        logger.info(f"✅ 写作任务 {args.job} 校验通过（可移植：{port['portable']}）")
        for w in warnings:
            logger.warning(f"  ⚠ {w}")
        return 0
    logger.error(f"❌ {args.job} 发现 {len(errors)} 个问题：")
    for e in errors:
        logger.error(f"  - {e}")
    for w in warnings:
        logger.warning(f"  ⚠ {w}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
