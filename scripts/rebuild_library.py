"""从 data/raw/ 重建 data/papers/

两种来源：
  1. 若 data/parsed/<stem>/ 已有旧版 MinerU 输出（hybrid_engine 默认），直接用 cleaner 提取，免重新转换。
  2. 否则调用 MinerU 重新转换到 tmp 再提取。

paper_id 映射：
  - 现有 13 篇用 config/paper_ids.py 的 RAW_STEM_TO_PAPER_ID 固定映射（年份_首位作者_中文标题）。
  - 重复上传的两篇（DUPLICATE_RAW_STEMS）跳过。
  - 新文件用 derive_paper_id() 自动推导。

用法:
  conda activate mineru
  python scripts/rebuild_library.py                  # 优先复用 data/parsed 旧输出
  python scripts/rebuild_library.py --reconvert      # 强制重新走 MinerU 转换（慢）
  python scripts/rebuild_library.py --api-url http://127.0.0.1:8000
"""
import os
import sys
import subprocess
import argparse
import time
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger
from config.settings import (
    RAW_DIR, LEGACY_PARSED_DIR, MINERU_TMP_DIR, SUPPORTED_FORMATS,
    MINERU_BACKEND, MINERU_EFFORT, MINERU_METHOD, MINERU_LANG,
    MINERU_TIMEOUT,
)
from config.paper_ids import RAW_STEM_TO_PAPER_ID, DUPLICATE_RAW_STEMS
from src.cleaner import MinerUOutputCleaner
from src.manifest import PaperManifest
from src.naming import derive_paper_id
from src.converter import MinerUConverter

cleaner = MinerUOutputCleaner()
manifest = PaperManifest()
manifest.migrate()
converter = MinerUConverter()

# 旧版 MinerU 输出可能的 method 目录（按优先级：hybrid_auto 优先于其它）
# 复用 cleaner 的反向映射，避免重复维护目录名→(method,backend) 表
from src.cleaner import MinerUOutputCleaner as _CleanerForMap

# 优先级顺序：hybrid_auto > hybrid_txt > hybrid_ocr > vlm_auto > vlm_txt > vlm_ocr
# > auto > txt > ocr。固定顺序，不依赖 os.listdir。
_METHOD_DIR_PRIORITY = [
    "hybrid_auto", "hybrid_txt", "hybrid_ocr",
    "vlm_auto", "vlm_txt", "vlm_ocr",
    "auto", "txt", "ocr",
]


@dataclass
class LegacyOutput:
    """旧版 MinerU 输出目录及其检测到的 method/backend。

    detected_method/detected_backend 由目录名反向推导（复用 cleaner 映射），
    传给 cleaner.extract 时确保 method 与目录一致，避免 method=auto 误吃 hybrid_ocr。
    """
    source_dir: Path
    detected_method: str | None
    detected_backend: str | None
    method_dir: str | None


def find_legacy_output(stem: str) -> LegacyOutput | None:
    """在 data/parsed/<stem>/ 下找到含 .md 的输出目录，并检测其 method/backend。

    返回 LegacyOutput（含检测到的 method/backend），找不到返回 None。
    多个 method 目录并存时按固定优先级取第一个，不依赖 os.listdir 顺序。
    """
    base = LEGACY_PARSED_DIR / stem
    if not base.exists():
        return None
    for d in _METHOD_DIR_PRIORITY:
        p = base / d
        if p.is_dir() and any(p.glob("*.md")):
            method, backend = _CleanerForMap._method_from_dirname(d)
            return LegacyOutput(source_dir=p, detected_method=method,
                                detected_backend=backend, method_dir=d)
    # 直接在 base 下（无 method 子目录）：method/backend 无法检测，交给调用方默认
    if any(base.glob("*.md")):
        return LegacyOutput(source_dir=base, detected_method=None,
                            detected_backend=None, method_dir=None)
    return None


def reconvert(f: Path, paper_id: str, backend: str, method: str, effort: str,
              lang: str, api_url: str | None) -> Path | None:
    """调用 MinerU 重新转换，返回输出目录"""
    tmp_out = MINERU_TMP_DIR / paper_id
    # 直接用 subprocess（converter.convert 不支持 api_url）
    from src.converter import MINERU_EXE
    cmd = [MINERU_EXE, "-p", str(f), "-o", str(tmp_out), "-b", backend, "-m", method, "-l", lang]
    if backend == "hybrid-engine":
        cmd.extend(["--effort", effort])
    if api_url:
        cmd.extend(["--api-url", api_url])
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                            errors="replace", env={**os.environ}, timeout=MINERU_TIMEOUT)
    if result.returncode != 0:
        logger.error(f"  转换失败: {result.stderr[-300:]}")
        return None
    return tmp_out


def process_one(f: Path, reconvert_flag: bool, backend: str, method: str,
                effort: str, lang: str, api_url: str | None) -> bool:
    stem = f.stem
    # 重复上传的跳过
    if stem in DUPLICATE_RAW_STEMS:
        logger.info(f"跳过重复文件: {f.name}")
        return False

    paper_id = RAW_STEM_TO_PAPER_ID.get(stem) or derive_paper_id(f.name)

    if manifest.has(paper_id) and Path(manifest.get(paper_id)["markdown"]).exists():
        logger.info(f"跳过 (已存在): {f.name} -> {paper_id}")
        return False

    logger.info(f"处理: {f.name} -> {paper_id}")

    legacy = None
    if not reconvert_flag:
        legacy = find_legacy_output(stem)
        if legacy:
            logger.info(f"  复用旧输出: {legacy.source_dir} "
                        f"(method={legacy.detected_method}, backend={legacy.detected_backend})")

    # 复用 legacy 时以检测到的 method/backend 为准（避免 method=auto 误吃 hybrid_ocr）；
    # 否则用命令行参数重新转换。
    if legacy is not None:
        source_dir = legacy.source_dir
        eff_method = legacy.detected_method or method
        eff_backend = legacy.detected_backend or backend
        eff_effort = ""  # legacy 输出无 effort 信息
        eff_runner = "legacy"
    else:
        t0 = time.time()
        source_dir = reconvert(f, paper_id, backend, method, effort, lang, api_url)
        if source_dir is None:
            return False
        logger.info(f"  重新转换完成 ({time.time()-t0:.0f}s): {source_dir}")
        eff_method, eff_backend, eff_effort, eff_runner = method, backend, effort, "cli"

    clean = cleaner.extract(source_dir, paper_id, overwrite=True,
                            method=eff_method, stem=stem, backend=eff_backend)
    if not clean["success"]:
        logger.error(f"  清理失败: {clean.get('error')}")
        return False

    from src.file_fingerprint import compute_sha256, file_meta
    meta = file_meta(f)
    manifest.upsert(paper_id=paper_id, raw_pdf=str(f),
                    markdown=clean["markdown_path"], images_dir=clean["images_dir"],
                    status="converted", images_count=clean["images_count"],
                    md_chars=clean["char_count"],
                    raw_filename=f.name, raw_stem=f.stem,
                    sha256=meta["sha256"], file_size=meta["file_size"],
                    mtime=meta["mtime"], mineru_backend=eff_backend, effort=eff_effort,
                    method=eff_method, runner=eff_runner)
    logger.info(f"  入库: {paper_id} ({clean['char_count']} 字符, {clean['images_count']} 图)")
    return True


def main():
    parser = argparse.ArgumentParser(description="从 data/raw/ 重建 data/papers/")
    parser.add_argument("--reconvert", action="store_true", help="强制重新走 MinerU 转换")
    parser.add_argument("--backend", default=MINERU_BACKEND)
    parser.add_argument("--method", default=MINERU_METHOD)
    parser.add_argument("--effort", default=MINERU_EFFORT)
    parser.add_argument("--api-url", default=None)
    args = parser.parse_args()
    # 普通模式禁止 backend/effort 覆盖（产品固定 hybrid-engine + medium）
    from config.settings import enforce_backend_effort_override
    enforce_backend_effort_override(parser, args)

    files = sorted([f for f in RAW_DIR.iterdir() if f.suffix.lower() in SUPPORTED_FORMATS])
    logger.info(f"发现 {len(files)} 个 raw 文件")
    logger.info(f"模式: {'重新转换' if args.reconvert else '优先复用旧输出'}")

    n = 0
    for i, f in enumerate(files, 1):
        logger.info(f"[{i}/{len(files)}]")
        if process_one(f, args.reconvert, args.backend, args.method,
                        args.effort, MINERU_LANG, args.api_url):
            n += 1

    stats = manifest.stats()
    logger.info(f"\n迁移完成：本次新增 {n} 篇。文献库共 {stats['total_papers']} 篇, "
                f"{stats['total_md_chars']} 字符, {stats['total_images']} 图。")


if __name__ == "__main__":
    main()
