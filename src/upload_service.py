"""上传单一管道（Single Pipeline）——系统结构收敛的核心

本模块是全系统**唯一**写入 data/raw/ 并驱动 converter → cleaner → manifest
完整转换流程的入口。FastAPI /upload、Gradio app.py、（必要时）CLI 一律调用它。

设计目标（收敛阶段）：
  1. 单一事实源：raw 写入 + sha256 + 去重 + converting 状态机 + 转换 + 清理 +
     manifest 记录，全部在这里完成，调用方不再触碰 RAW_DIR / converter / cleaner
     / manifest 的写接口。
  2. 依赖注入：converter / cleaner / manifest 由调用方传入实例，便于测试用
     monkeypatch 替换 server 模块级单例（server.py 顶部初始化一次后传入）。
  3. 状态驱动行为：
       - converting 状态阻止重复转换（同 sha256 命中 converting → in_progress）
       - converted 状态命中 → duplicate，不再进 converter
       - failed 状态 → 允许显式重试
  4. 不做隐式副作用：除显式给定的 raw_dir / tmp_dir 外不写其它路径。

本模块不调 LLM、不做向量检索。所有 IO 通过注入的实例完成。
"""
import os
import asyncio
import hashlib
import tempfile
from datetime import datetime
from pathlib import Path

from filelock import FileLock
from loguru import logger

from config.settings import (
    RAW_DIR, MINERU_TMP_DIR, MAX_UPLOAD_SIZE,
    MINERU_BACKEND, MINERU_EFFORT, MINERU_METHOD, MINERU_LANG,
    SUPPORTED_FORMATS,
)
from src.naming import derive_paper_id, validate_paper_id, safe_child
from src.services.conversion_ingest_pipeline import ConversionIngestPipeline
from src.services.paper_registry import PaperRegistryService


class UploadError(Exception):
    """上传/转换管道内已知错误，携带 HTTP 状态码与可读信息。

    调用方（FastAPI / Gradio）据此映射为 HTTP 响应或 UI 提示，
    不应让本模块直接抛 HTTPException（保持框架无关、可复用于 CLI）。
    """

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class _BytesSource:
    """把内存 bytes 适配成 upload_core 期望的 async read(n) 接口（Gradio 路径用）。"""

    def __init__(self, data: bytes):
        self._buf = data
        self._pos = 0

    async def read(self, n: int = -1) -> bytes:
        if n is None or n < 0:
            chunk = self._buf[self._pos:]
        else:
            chunk = self._buf[self._pos:self._pos + n]
        self._pos += len(chunk)
        return chunk


def sanitize_filename(filename: str, raw_dir: Path) -> str:
    """净化上传文件名：仅取 basename，并经 safe_child 二次校验在 RAW_DIR 内。"""
    safe_filename = Path(filename).name
    if safe_filename != filename:
        raise UploadError(f"非法文件名（含路径）: {filename}", status_code=400)
    try:
        safe_child(raw_dir, safe_filename)
    except ValueError:
        raise UploadError(f"非法文件名: {filename}", status_code=400)
    return safe_filename


async def _stream_to_temp(source, raw_dir: Path,
                          max_size: int = MAX_UPLOAD_SIZE) -> tuple[str, int, str]:
    """异步流式写入临时文件：防内存尖峰、防超限、边写边算 sha256。

    返回 (tmp_path, size, sha256_hex)。超限或异常时清理 tmp 并抛 UploadError。
    """
    sha = hashlib.sha256()
    total_size = 0
    chunk_size = 1024 * 1024  # 1MB
    tmp_fd, tmp_path = tempfile.mkstemp(
        dir=str(raw_dir), prefix=".upload_", suffix=".tmp")
    try:
        with os.fdopen(tmp_fd, "wb") as tmpf:
            while True:
                chunk = await source.read(chunk_size)
                if not chunk:
                    break
                total_size += len(chunk)
                if total_size > max_size:
                    raise UploadError(
                        f"文件过大: > {max_size} bytes (当前 {total_size} bytes)",
                        status_code=413)
                sha.update(chunk)
                tmpf.write(chunk)
    except UploadError:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise
    except Exception as e:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        logger.error(f"上传写入失败: {e}")
        raise UploadError(f"上传失败: {e}", status_code=500) from e
    return tmp_path, total_size, sha.hexdigest()


def _mark_failed(registry, paper_id, save_path, filename,
                 file_sha256, file_size, backend, method, effort,
                 error, runner="cli") -> None:
    """转换/清理失败时标记 failed（复用 converting 已写入的指纹信息）。"""
    registry.mark_conversion_failed(
        paper_id=paper_id,
        raw_pdf=save_path,
        error=error,
        sha256=file_sha256,
        mineru_backend=backend, method=method, effort=effort,
        runner=runner,
    )


async def upload_core(
    *,
    filename: str,
    source,
    converter,
    cleaner,
    manifest,
    registry=None,
    raw_dir: Path = RAW_DIR,
    tmp_dir: Path = MINERU_TMP_DIR,
    method: str = MINERU_METHOD,
    backend: str = MINERU_BACKEND,
    effort: str = MINERU_EFFORT,
    lang: str = MINERU_LANG,
) -> dict:
    """上传单一管道：写 raw → 去重 → converting → convert → clean → manifest(converted)

    Args:
        filename: 原始文件名（用于推导 paper_id 与净化）。
        source: 异步可读对象（FastAPI UploadFile，或 _BytesSource）。
        converter/cleaner/manifest: 注入的实例（由 server 顶部单例传入）。
        raw_dir/tmp_dir: 受控目录，默认全局配置。
        method/backend/effort/lang: MinerU 解析参数。

    Returns:
        dict，含 status / paper_id / 统计信息 / message。status 取值：
          "success" | "duplicate" | "in_progress"

    Raises:
        UploadError: 任何校验/IO/转换失败，携带 status_code。
    """
    registry = registry or PaperRegistryService(manifest_path=manifest.path)

    # 0. method 枚举校验
    if method not in ("auto", "ocr", "txt"):
        raise UploadError(f"非法 method: {method}，允许: auto, ocr, txt",
                          status_code=400)

    # 1. 后缀校验
    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED_FORMATS:
        raise UploadError(f"不支持的格式: {suffix}，支持: {SUPPORTED_FORMATS}",
                          status_code=400)

    # 2. paper_id 推导 + 校验
    paper_id = derive_paper_id(filename)
    try:
        validate_paper_id(paper_id)
    except ValueError as e:
        raise UploadError(str(e), status_code=400)

    # 3. 文件名净化
    safe_filename = sanitize_filename(filename, raw_dir)
    save_path = raw_dir / safe_filename

    # 4. 流式写 tmp（防内存尖峰）+ sha256 + 大小
    tmp_path, file_size, file_sha256 = await _stream_to_temp(
        source, raw_dir, MAX_UPLOAD_SIZE)

    logger.info(
        f"收到文件: {filename} ({file_size} bytes, "
        f"sha256={file_sha256[:12]}…) -> paper_id={paper_id}")

    # 5. 上传事务锁：防并发 TOCTOU + converting 状态机
    upload_lock = FileLock(str(raw_dir / ".upload.lock"))
    with upload_lock:
        existing = manifest.find_by_sha256(file_sha256)
        if existing:
            status = existing.get("status", "")
            if status == "converting":
                os.unlink(tmp_path)
                return {
                    "status": "in_progress",
                    "paper_id": existing.get("paper_id"),
                    "message": "相同文件正在转换中，请稍后查看",
                }
            if status in {"converted", "unregistered_converted"}:
                os.unlink(tmp_path)
                return {
                    "status": "duplicate",
                    "paper_id": existing.get("paper_id"),
                    "message": f"相同文件已存在 (paper_id={existing.get('paper_id')})，未重复转换",
                }
            if status == "failed":
                # failed 重试策略：同 sha 不同 paper_id 拒绝（避免一个 sha256
                # 对应多个 paper_id）；同 paper_id 才允许重试，覆盖原失败记录
                if existing.get("paper_id") != paper_id:
                    os.unlink(tmp_path)
                    raise UploadError(
                        f"相同文件已有失败记录 (paper_id={existing.get('paper_id')})，"
                        f"请重试原 paper_id 或先删除该失败记录，不允许创建新 paper_id。",
                        status_code=409)
                logger.info(f"上次转换失败 ({paper_id})，允许重试")

        # paper_id 已存在但 sha256 不同（非 failed）
        existing_by_pid = manifest.get(paper_id)
        if existing_by_pid and existing_by_pid.get("sha256") != file_sha256 \
                and existing_by_pid.get("status") not in ("failed", None):
            os.unlink(tmp_path)
            raise UploadError(
                f"paper_id={paper_id} 已存在但内容不同，不允许覆盖。"
                f"若需替换请先手动删除旧文献。",
                status_code=409)

        # final_path 冲突检查
        if save_path.exists():
            from src.file_fingerprint import compute_sha256
            existing_raw_sha = compute_sha256(save_path)
            if existing_raw_sha != file_sha256:
                os.unlink(tmp_path)
                raise UploadError(
                    f"同名文件 {safe_filename} 已存在且内容不同，不允许覆盖。"
                    f"请改名后重新上传。",
                    status_code=409)
            os.unlink(tmp_path)
            logger.info(f"同名同内容文件已存在，复用: {save_path}")
        else:
            os.replace(tmp_path, str(save_path))

        # 写入 converting 状态，防止并发重复转换
        registry.mark_converting(
            paper_id=paper_id,
            raw_pdf=save_path,
            raw_filename=filename,
            sha256=file_sha256, file_size=file_size,
            mtime=datetime.now().isoformat(timespec="seconds"),
            mineru_backend=backend, method=method, effort=effort,
            runner="cli",
        )
    # 锁释放

    # 6. 转换 → 清理 → manifest(converted)
    try:
        file_mtime = datetime.fromtimestamp(
            os.path.getmtime(str(save_path))).isoformat(timespec="seconds")
        pipeline = ConversionIngestPipeline(
            manifest=manifest,
            converter=converter,
            cleaner=cleaner,
            registry=registry,
            tmp_dir=tmp_dir,
        )
        converted = pipeline.convert_and_register(
            paper_id=paper_id,
            pdf_path=save_path,
            raw_filename=filename,
            sha256=file_sha256, file_size=file_size, mtime=file_mtime,
            backend=backend, method=method, effort=effort, lang=lang,
            source_kind="upload",
            already_marked_converting=True,
            replace=True,
        )
        if not converted.get("success"):
            prefix = "转换失败" if converted.get("stage") == "convert" else "清理失败"
            raise UploadError(f"{prefix}: {converted.get('error')}",
                              status_code=500)

        return {
            "status": "success",
            "paper_id": paper_id,
            "filename": filename,
            "markdown_path": converted["markdown_path"],
            "images_count": converted["images_count"],
            "md_chars": converted["char_count"],
            "message": f"转换完成: {paper_id} ({converted['char_count']} 字符, {converted['images_count']} 图)",
        }
    except UploadError:
        raise
    except Exception as e:
        logger.error(f"处理失败: {e}")
        raise UploadError(f"处理失败: {str(e)}", status_code=500) from e


def upload_from_bytes(
    *,
    filename: str,
    data: bytes,
    converter,
    cleaner,
    manifest,
    registry=None,
    raw_dir: Path = RAW_DIR,
    tmp_dir: Path = MINERU_TMP_DIR,
    method: str = MINERU_METHOD,
    backend: str = MINERU_BACKEND,
    effort: str = MINERU_EFFORT,
    lang: str = MINERU_LANG,
) -> dict:
    """Gradio / 同步调用方入口：bytes → 单一管道。

    与 upload_core 共享同一套校验、去重、converting 状态机、转换流程；
    仅以 _BytesSource 把内存 bytes 适配成 async read(n) 接口后复用 upload_core。
    """
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(
            upload_core(
                filename=filename, source=_BytesSource(data),
                converter=converter, cleaner=cleaner, manifest=manifest,
                registry=registry,
                raw_dir=raw_dir, tmp_dir=tmp_dir,
                method=method, backend=backend, effort=effort, lang=lang,
            ))
    finally:
        loop.close()


class _FileSource:
    """把磁盘文件适配成 upload_core 期望的 async read(n) 接口。

    分块读取，避免 Gradio 大 PDF 一次性 read_bytes 造成内存尖峰。
    read 是 async def（满足 upload_core 的 await 约定），内部同步读文件。
    """

    def __init__(self, path: Path):
        self._path = Path(path)
        self._fh = None

    async def read(self, n: int = -1) -> bytes:
        if self._fh is None:
            self._fh = self._path.open("rb")
        return self._fh.read(n)

    def close(self) -> None:
        if self._fh is not None:
            self._fh.close()
            self._fh = None


def upload_from_path(
    *,
    src_path: str | Path,
    converter,
    cleaner,
    manifest,
    registry=None,
    filename: str | None = None,
    raw_dir: Path = RAW_DIR,
    tmp_dir: Path = MINERU_TMP_DIR,
    method: str = MINERU_METHOD,
    backend: str = MINERU_BACKEND,
    effort: str = MINERU_EFFORT,
    lang: str = MINERU_LANG,
) -> dict:
    """Gradio / 同步调用方入口：文件路径 → 单一管道（流式，不一次性读入内存）。

    与 upload_core 共享同一套校验、去重、converting 状态机、转换流程；
    以 _FileSource 分块读文件，避免大 PDF 内存尖峰。
    filename 缺省取 src_path 的 basename。
    """
    src_path = Path(src_path)
    if filename is None:
        filename = src_path.name
    source = _FileSource(src_path)
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(
            upload_core(
                filename=filename, source=source,
                converter=converter, cleaner=cleaner, manifest=manifest,
                registry=registry,
                raw_dir=raw_dir, tmp_dir=tmp_dir,
                method=method, backend=backend, effort=effort, lang=lang,
            ))
    finally:
        source.close()
        loop.close()
