"""监控 raw 文件夹，自动转换新增文件 (MinerU 3.4)

重构后流程：raw -> MinerU tmp -> cleaner -> papers/<paper_id>/ -> manifest
不再做 chunk / embedding / 入库。

用法:
  conda activate mineru

  # 前提：mineru-api 已在端口8000运行（可选，加速）
  python watcher.py

  # 可选参数
  --interval 30       检查间隔(秒)，默认30
  --once              跑一轮就退出(不循环监控)
  --api-url URL       走 mineru-api 服务加速
"""
import os
import sys
import argparse
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from loguru import logger
from config.settings import (
    RAW_DIR, MINERU_TMP_DIR, SUPPORTED_FORMATS,
    MINERU_BACKEND, MINERU_EFFORT, MINERU_METHOD, MINERU_LANG,
)
from src.converter import MinerUConverter
from src.cleaner import MinerUOutputCleaner
from src.manifest import PaperManifest
from src.naming import derive_paper_id

converter = MinerUConverter()
cleaner = MinerUOutputCleaner()
manifest = PaperManifest()


def process_file(f: Path, backend: str, method: str, effort: str,
                 lang: str, api_url: str) -> bool:
    """转换单个文件：raw -> tmp -> clean -> manifest"""
    paper_id = derive_paper_id(f.name)
    if manifest.has(paper_id) and (Path(manifest.get(paper_id)["markdown"])).exists():
        logger.info(f"  跳过 (已转换): {f.name} -> {paper_id}")
        return False

    logger.info(f"  转换: {f.name} -> {paper_id}")
    tmp_out = MINERU_TMP_DIR / paper_id
    # converter 不传 api_url；如需走 8000 服务，用 batch_convert.py
    result = converter.convert(f, tmp_out, backend=backend, method=method,
                               lang=lang, effort=effort)
    if not result["success"]:
        logger.error(f"  转换失败: {result.get('error')}")
        return False

    clean = cleaner.extract(result["output_dir"], paper_id)
    if not clean["success"]:
        logger.error(f"  清理失败: {clean.get('error')}")
        return False

    manifest.upsert(
        paper_id=paper_id, raw_pdf=str(f),
        markdown=clean["markdown_path"], images_dir=clean["images_dir"],
        status="converted", images_count=clean["images_count"],
        md_chars=clean["char_count"],
    )
    logger.info(f"  完成: {paper_id} ({clean['char_count']} 字符, {clean['images_count']} 图)")
    return True


def scan_and_convert(api_url: str, backend: str, method: str, effort: str, lang: str) -> int:
    files = sorted([f for f in RAW_DIR.iterdir() if f.suffix.lower() in SUPPORTED_FORMATS])
    if not files:
        return 0
    converted = 0
    for i, f in enumerate(files, 1):
        logger.info(f"[{i}/{len(files)}] {f.name}")
        t0 = time.time()
        if process_file(f, backend, method, effort, lang, api_url):
            converted += 1
            logger.info(f"  耗时 {time.time()-t0:.0f}s")
    return converted


def main():
    parser = argparse.ArgumentParser(description="监控 raw 文件夹，自动转换新增文件")
    parser.add_argument("--api-url", default="", help="mineru-api 地址（watcher 直走 CLI，一般留空）")
    parser.add_argument("--backend", default=MINERU_BACKEND, choices=["pipeline", "vlm-engine", "hybrid-engine"])
    parser.add_argument("--method", default=MINERU_METHOD, choices=["auto", "ocr", "txt"])
    parser.add_argument("--effort", default=MINERU_EFFORT, choices=["medium", "high"])
    parser.add_argument("--interval", type=int, default=30, help="检查间隔(秒)")
    parser.add_argument("--once", action="store_true", help="跑一轮就退出")
    args = parser.parse_args()

    logger.info(f"监控启动: {RAW_DIR}")
    logger.info(f"后端: {args.backend} | 方法: {args.method} | 强度: {args.effort} | 间隔: {args.interval}s")

    total = 0
    while True:
        count = scan_and_convert(args.api_url, args.backend, args.method, args.effort, MINERU_LANG)
        total += count
        if count > 0:
            logger.info(f"本轮处理 {count} 个文件，累计 {total} 个")
        else:
            logger.debug("本轮无新文件")
        if args.once:
            break
        logger.debug(f"等待 {args.interval}s ...")
        time.sleep(args.interval)

    logger.info(f"完成，共处理 {total} 个文件")


if __name__ == "__main__":
    main()
