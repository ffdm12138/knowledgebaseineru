"""综述写作 CLI

子命令: create / match / deep-read / story / tex / figures / validate

用法示例:
  python scripts/write_review.py create --topic "风吹雪升华参数化的发展脉络"
  python scripts/write_review.py match --job 001_xxx
  python scripts/write_review.py deep-read --job 001_xxx --papers 1999_dery_吹雪体相模型 2025_huang_雪粒破碎促进升华
  python scripts/write_review.py story --job 001_xxx
  python scripts/write_review.py tex --job 001_xxx
  python scripts/write_review.py figures --job 001_xxx
  python scripts/write_review.py validate --job 001_xxx

所有 LLM 步骤只生成 prompt 文本（写到 logs/prompts/），不内置 LLM。
"""
import sys
import argparse
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from loguru import logger
from src.writer.job_manager import JobManager
from src.writer.topic_parser import normalize_task
from src.writer.catalog_matcher import match_catalog
from src.writer.deep_reader import deep_read
from src.writer.story_builder import build_story
from src.writer.tex_project import build_tex
from src.writer.figure_manager import copy_figures


def cmd_create(args):
    jm = JobManager()
    info = jm.create(topic=args.topic, input_file=args.input,
                     target=args.target, language=args.language)
    # 顺带生成 normalized_task
    norm = normalize_task(info["job_id"], jm)
    logger.info(f"任务创建: {info['job_id']}")
    logger.info(f"  目录: {info['job_dir']}")
    logger.info(f"  normalized_task: {norm['normalized_path']}")
    logger.info(f"  下一步: python scripts/write_review.py match --job {info['job_id']}")
    print(info["job_id"])


def cmd_match(args):
    info = match_catalog(args.job)
    logger.info(f"目录匹配完成: {args.job}")
    logger.info(f"  prompt: {info['prompt_path']}")
    logger.info(f"  candidates: {info['candidates_path']}")
    logger.info(f"  selected: {info['selected_path']}")
    logger.info("  下一步：用大模型跑匹配 prompt，把结果回填 selected_papers.json，再 deep-read")


def cmd_deep_read(args):
    info = deep_read(args.job, args.papers)
    logger.info(f"精读完成: {args.job}，{len(info['notes'])} 篇笔记")
    logger.info(f"  prompt: {info['prompt_path']}")
    logger.info(f"  evidence: {info['evidence_table']}")
    logger.info(f"  figures: {info['figure_candidates']}")


def cmd_story(args):
    info = build_story(args.job)
    logger.info(f"故事线生成: {args.job}")
    logger.info(f"  prompt: {info['prompt_path']}")
    logger.info(f"  story_plan: {info['story_plan']}")


def cmd_tex(args):
    info = build_tex(args.job, title=args.title)
    logger.info(f"TeX 项目生成: {args.job}")
    logger.info(f"  main: {info['main_tex']}")
    logger.info(f"  intro: {info['introduction_tex']}")
    logger.info(f"  method: {info['method_tex']}")
    logger.info(f"  references.bib: {info['references_bib']} ({info['bib_count']} 条)")
    logger.info(f"  写作 prompt: {info['prompt_path']}")


def cmd_figures(args):
    info = copy_figures(args.job)
    logger.info(f"图片复制: {len(info['copied'])} 张")


def cmd_validate(args):
    from scripts.validate_write_job import main as vmain
    sys.argv = ["validate", "--job", args.job]
    sys.exit(vmain())


def main():
    ap = argparse.ArgumentParser(description="综述写作 CLI")
    sub = ap.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("create")
    c.add_argument("--topic", default=None)
    c.add_argument("--input", default=None)
    c.add_argument("--target", default="phd_thesis")
    c.add_argument("--language", default="zh")
    c.set_defaults(func=cmd_create)

    m = sub.add_parser("match"); m.add_argument("--job", required=True); m.set_defaults(func=cmd_match)
    d = sub.add_parser("deep-read"); d.add_argument("--job", required=True)
    d.add_argument("--papers", nargs="+", required=True); d.set_defaults(func=cmd_deep_read)
    s = sub.add_parser("story"); s.add_argument("--job", required=True); s.set_defaults(func=cmd_story)
    t = sub.add_parser("tex"); t.add_argument("--job", required=True)
    t.add_argument("--title", default=None); t.set_defaults(func=cmd_tex)
    f = sub.add_parser("figures"); f.add_argument("--job", required=True); f.set_defaults(func=cmd_figures)
    v = sub.add_parser("validate"); v.add_argument("--job", required=True); v.set_defaults(func=cmd_validate)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
