"""批量转换文档目录 (MinerU 3.4)

重构后流程：raw -> MinerU tmp -> cleaner -> papers/<paper_id>/ -> manifest
不再做 chunk / embedding / 入库。可走 mineru-api(8000) 加速。

用法:
  conda activate mineru

  # 终端1：启动API服务 (端口8000，避开代理7890)
  mineru-api --port 8000

  # 终端2：批量转换
  python batch_convert.py data/raw --api-url http://127.0.0.1:8000

  # 可选参数
  --backend pipeline|hybrid-engine    默认从config读取
  --method auto|ocr|txt               默认auto
  --effort medium|high                仅hybrid-engine生效
"""
import os
import sys
import subprocess
import argparse
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from loguru import logger
from config.settings import (
    MINERU_TMP_DIR, SUPPORTED_FORMATS, MINERU_TIMEOUT,
    MINERU_BACKEND, MINERU_EFFORT, MINERU_METHOD, MINERU_LANG,
)
from src.cleaner import MinerUOutputCleaner
from src.manifest import PaperManifest
from src.naming import derive_paper_id

_PYTHON_DIR = Path(os.sys.executable).parent
MINERU_EXE = str(_PYTHON_DIR / "Scripts" / "mineru.exe")
if not os.path.exists(MINERU_EXE):
    MINERU_EXE = str(_PYTHON_DIR / "mineru.exe")

cleaner = MinerUOutputCleaner()
manifest = PaperManifest()


def run_mineru(input_path: str, output_dir: str, backend: str, method: str,
               effort: str, lang: str, api_url: str) -> bool:
    cmd = [MINERU_EXE, "-p", input_path, "-o", output_dir,
           "-b", backend, "-m", method, "-l", lang]
    if backend == "hybrid-engine":
        cmd.extend(["--effort", effort])
    if api_url:
        cmd.extend(["--api-url", api_url])
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                            errors="replace", env={**os.environ}, timeout=MINERU_TIMEOUT)
    if result.returncode != 0:
        logger.error(f"  转换失败: {result.stderr[-300:] if result.stderr else '未知'}")
        return False
    return True


def main():
    parser = argparse.ArgumentParser(description="批量转换文档目录")
    parser.add_argument("input_dir", help="文档所在目录 (如 data/raw)")
    parser.add_argument("--backend", default=MINERU_BACKEND, choices=["pipeline", "vlm-engine", "hybrid-engine"])
    parser.add_argument("--method", default=MINERU_METHOD, choices=["auto", "ocr", "txt"])
    parser.add_argument("--effort", default=MINERU_EFFORT, choices=["medium", "high"])
    parser.add_argument("--api-url", default=None, help="mineru-api 服务地址")
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    if not input_dir.exists():
        logger.error(f"目录不存在: {input_dir}")
        sys.exit(1)

    files = sorted([f for f in input_dir.iterdir() if f.suffix.lower() in SUPPORTED_FORMATS])
    if not files:
        logger.error(f"没有支持的文件: {input_dir}")
        sys.exit(1)

    logger.info(f"找到 {len(files)} 个文件")
    if args.api_url:
        logger.info(f"使用API服务: {args.api_url} (模型已预加载，速度快)")

    for i, f in enumerate(files, 1):
        paper_id = derive_paper_id(f.name)

        # sha256 去重（与 watcher 一致）
        from src.file_fingerprint import compute_sha256
        sha = compute_sha256(f)
        existing_by_sha = manifest.find_by_sha256(sha)
        if existing_by_sha and existing_by_sha.get("status") == "converted":
            logger.info(f"[{i}/{len(files)}] 跳过 (sha256 已转换): {f.name} = {existing_by_sha['paper_id']}")
            continue
        # paper_id 冲突：同名但不同内容 → 加后缀
        if manifest.has(paper_id):
            existing = manifest.get(paper_id)
            if existing.get("sha256") and existing["sha256"] != sha:
                paper_id = f"{paper_id}_{sha[:8]}"
                logger.warning(f"  paper_id 冲突且 sha256 不同 → {paper_id}")

        if manifest.has(paper_id) and Path(manifest.get(paper_id)["markdown"]).exists() \
                and manifest.get(paper_id).get("sha256") == sha:
            logger.info(f"[{i}/{len(files)}] 跳过 (已转换): {f.name} -> {paper_id}")
            continue

        logger.info(f"[{i}/{len(files)}] 处理: {f.name} -> {paper_id} | sha256={sha[:12]} | backend={'api' if args.api_url else 'cli'}")
        tmp_out = MINERU_TMP_DIR / paper_id
        t0 = time.time()
        ok = run_mineru(str(f), str(tmp_out), args.backend, args.method,
                        args.effort, MINERU_LANG, args.api_url)
        if not ok:
            continue
        # MinerU 输出在 tmp_out/<stem>/<method>/，cleaner 递归定位
        clean = cleaner.extract(tmp_out, paper_id, overwrite=True,
                                method=args.method, stem=f.stem,
                                backend=args.backend)
        if not clean["success"]:
            logger.error(f"  清理失败: {clean.get('error')}")
            continue
        from src.file_fingerprint import compute_sha256, file_meta
        meta = file_meta(f)
        manifest.upsert(paper_id=paper_id, raw_pdf=str(f),
                        markdown=clean["markdown_path"], images_dir=clean["images_dir"],
                        status="converted", images_count=clean["images_count"],
                        md_chars=clean["char_count"],
                        raw_filename=f.name, raw_stem=f.stem,
                        sha256=meta["sha256"], file_size=meta["file_size"],
                        mtime=meta["mtime"],
                        backend="api" if args.api_url else "cli", method=args.method)
        logger.info(f"  完成 ({time.time()-t0:.0f}s): {paper_id}")

    stats = manifest.stats()
    logger.info(f"\n批量转换完成！文献库: {stats['total_papers']} 篇, "
                f"{stats['total_md_chars']} 字符, {stats['total_images']} 图")


if __name__ == "__main__":
    main()
