"""监控 raw 文件夹，自动转换新增文件 (MinerU 3.4)

稳定性重构后流程：
  raw 文件 → 稳定性检测 → sha256 → duplicate 检查 → MinerU(CLI) → cleaner → papers → manifest(原子写)

去重逻辑：
  - 已知重复 stem（DUPLICATE_RAW_STEMS）：跳过并记录日志
  - sha256 已存在且 converted：跳过（同名不同内容不被误跳过，按 sha256 判定）
  - paper_id 已存在但 sha256 不同：自动加 sha256 前8位后缀，避免静默覆盖

用法:
  conda activate mineru
  python watcher.py                     # 走 CLI（默认）
  python watcher.py --once              # 跑一轮就退出
  python watcher.py --api-url http://127.0.0.1:8000   # 走 API（暂未实现，会报错）
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
from src.naming import derive_paper_id, is_known_duplicate, validate_paper_id
from src.file_fingerprint import compute_sha256, file_meta
from src.watcher_utils import is_file_stable, is_uploading_temp

converter = MinerUConverter()
cleaner = MinerUOutputCleaner()
manifest = PaperManifest()
manifest.migrate()


def resolve_paper_id(filename: str, sha256: str) -> str:
    """解析 paper_id；若已存在但 sha256 不同，加 sha256 前8位后缀防覆盖。"""
    pid = derive_paper_id(filename)
    validate_paper_id(pid)
    existing = manifest.get(pid)
    if existing and existing.get("sha256") and existing["sha256"] != sha256:
        new_pid = f"{pid}_{sha256[:8]}"
        validate_paper_id(new_pid)
        logger.warning(f"paper_id 冲突且 sha256 不同: {pid} -> {new_pid}")
        return new_pid
    return pid


def process_file(f: Path, backend: str, method: str, effort: str,
                 lang: str, api_url: str | None) -> bool:
    """转换单个文件：稳定性 → sha256 → duplicate → 转换 → 清理 → manifest"""
    # 0. 临时上传文件跳过
    if is_uploading_temp(f):
        logger.info(f"  跳过临时文件: {f.name}")
        return False

    # 1. 文件稳定性检测
    if not is_file_stable(f, wait_seconds=1.0):
        logger.info(f"  文件未稳定，本轮跳过: {f.name}")
        return False

    # 2. 已知重复 stem
    if is_known_duplicate(f.name):
        logger.info(f"  跳过已知重复上传: {f.name}")
        return False

    # 3. sha256 去重
    logger.info(f"  计算 sha256: {f.name}")
    sha = compute_sha256(f)
    existing_by_sha = manifest.find_by_sha256(sha)
    if existing_by_sha and existing_by_sha.get("status") == "converted":
        logger.info(f"  跳过 (sha256 已转换): {f.name} = {existing_by_sha['paper_id']}")
        return False

    # 4. 解析 paper_id（含冲突后缀）
    paper_id = resolve_paper_id(f.name, sha)
    if manifest.has(paper_id) and manifest.get(paper_id).get("sha256") == sha \
            and Path(manifest.get(paper_id)["markdown"]).exists():
        logger.info(f"  跳过 (已转换): {f.name} -> {paper_id}")
        return False

    # 5. 转换
    logger.info(f"  转换: {f.name} -> {paper_id} | sha256={sha[:12]} | runner={'api' if api_url else 'cli'}")
    tmp_out = MINERU_TMP_DIR / paper_id
    result = converter.convert(f, tmp_out, backend=backend, method=method,
                               lang=lang, effort=effort, api_url=api_url)
    if not result["success"]:
        logger.error(f"  转换失败: {result.get('error')}")
        return False

    # 6. 清理
    clean = cleaner.extract(result["output_dir"], paper_id, overwrite=False,
                            method=method, stem=f.stem, backend=backend)
    if not clean["success"]:
        logger.error(f"  清理失败: {clean.get('error')}")
        return False

    # 7. manifest（含指纹 + 后端）
    meta = file_meta(f)
    manifest.upsert(
        paper_id=paper_id, raw_pdf=str(f),
        markdown=clean["markdown_path"], images_dir=clean["images_dir"],
        status="converted", images_count=clean["images_count"],
        md_chars=clean["char_count"],
        raw_filename=f.name, raw_stem=f.stem,
        sha256=sha, file_size=meta["file_size"], mtime=meta["mtime"],
        mineru_backend=backend, effort=effort, method=method,
        runner=result.get("runner", "cli"),
    )
    logger.info(f"  完成: {paper_id} ({clean['char_count']} 字符, {clean['images_count']} 图)")
    return True


def scan_and_convert(api_url: str | None, backend: str, method: str, effort: str, lang: str) -> int:
    files = sorted([f for f in RAW_DIR.iterdir()
                    if f.suffix.lower() in SUPPORTED_FORMATS and f.is_file()])
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
    parser.add_argument("--api-url", default=None,
                        help="mineru-api 地址。留空走 CLI（默认）。注意：API HTTP 上传暂未实现，传值会报错")
    parser.add_argument("--backend", default=MINERU_BACKEND, choices=["pipeline", "vlm-engine", "hybrid-engine"])
    parser.add_argument("--method", default=MINERU_METHOD, choices=["auto", "ocr", "txt"])
    parser.add_argument("--effort", default=MINERU_EFFORT, choices=["medium", "high"])
    parser.add_argument("--interval", type=int, default=30, help="检查间隔(秒)")
    parser.add_argument("--once", action="store_true", help="跑一轮就退出")
    args = parser.parse_args()

    backend_mode = "api" if args.api_url else "cli"
    logger.info(f"监控启动: {RAW_DIR}")
    logger.info(f"[converter] runner = {backend_mode}" +
                (f" ({args.api_url})" if args.api_url else " (CLI 子进程)"))
    logger.info(f"解析后端: {args.backend} | 方法: {args.method} | 强度: {args.effort} | 间隔: {args.interval}s")

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
