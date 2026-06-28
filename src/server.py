"""FastAPI 文献资产库服务 (MinerU 3.4)

重构后定位：文献资产库 + AI 摘要目录 + 按需全文阅读。
不再做语义检索 / RAG。所有 /prompt/* 只生成可复制 prompt，不调用 LLM。

接口：
- POST   /upload                       上传并转换：raw -> MinerU tmp -> cleaner -> papers -> manifest
- GET    /papers                        列出已转换文献
- GET    /papers/{paper_id}             单篇文献信息
- GET    /papers/{paper_id}/markdown    读取全文 Markdown
- GET    /papers/{paper_id}/images      列出图片
- DELETE /papers/{paper_id}             删除文献（manifest + papers 目录）
- GET    /catalog                       读取 literature_catalog.json
- POST   /catalog/validate              校验目录结构
- GET    /catalog/unsummarized          列出未总结文献
- POST   /prompt/catalog-entry          生成单篇目录条目补全 prompt
- POST   /prompt/plan-reading           生成目录规划阅读 prompt
- POST   /prompt/read-fulltext          生成基于全文的写作 prompt
- GET    /status                        系统状态
"""
import sys
import os
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, UploadFile, File, HTTPException, Query, Body
from fastapi.responses import HTMLResponse, PlainTextResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.concurrency import run_in_threadpool
from pydantic import BaseModel
import uvicorn
from loguru import logger

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import (
    API_HOST, API_PORT, RAW_DIR, MINERU_TMP_DIR, PAPERS_DIR,
    MINERU_BACKEND, MINERU_EFFORT, MINERU_METHOD, MINERU_LANG,
    SUPPORTED_FORMATS,
)

from src.converter import MinerUConverter
from src.cleaner import MinerUOutputCleaner
from src.manifest import PaperManifest
from src.library import PaperLibrary
from src.catalog import Catalog
from src.prompt_builder import PromptBuilder
from src.writer.job_manager import JobManager
from src.writer.topic_parser import normalize_task
from src.writer.catalog_matcher import match_catalog, confirm_selected_papers
from src.writer.deep_reader import deep_read, mark_deep_reading_filled
from src.writer.story_builder import build_story, mark_story_filled
from src.writer.tex_project import build_tex, mark_tex_content_filled
from src.writer.figure_manager import copy_figures
from src.writer.bib_manager import (validate_job_citations, portability_check,
                                    validate_catalog_citations)
from src.writer.job_validator import validate_job
from src.services.upload_job_service import (
    UploadJobRunner,
    UploadJobStore,
    new_upload_job_id,
    stage_upload_file,
)

# ========== 初始化 ==========

app = FastAPI(
    title="MinerU 文献资产库",
    description="文献解析 + AI 摘要目录 + 按需全文阅读 (端口 8080)",
    version="3.4.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:8080",
        "http://localhost:8080",
        "http://127.0.0.1:7860",
        "http://localhost:7860",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

converter = MinerUConverter()
cleaner = MinerUOutputCleaner()
manifest = PaperManifest()
library = PaperLibrary(manifest=manifest)
catalog = Catalog()
prompt_builder = PromptBuilder(catalog=catalog, library=library)
job_manager = JobManager()
upload_job_store = UploadJobStore()
upload_job_runner = UploadJobRunner(upload_job_store)

# 启动时迁移旧 manifest 记录到 SSOT 字段结构（幂等）
manifest.migrate()

logger.info(f"服务初始化完成，监听 {API_HOST}:{API_PORT}")


# ========== 请求模型 ==========

class PlanRequest(BaseModel):
    question: str


class FulltextRequest(BaseModel):
    question: str
    paper_ids: list[str]


class CatalogEntryRequest(BaseModel):
    paper_id: str


class BibEntryRequest(BaseModel):
    paper_id: str


class CreateJobRequest(BaseModel):
    topic: str | None = None
    input_file: str | None = None
    language: str = "zh"
    target: str = "phd_thesis"


class DeepReadRequest(BaseModel):
    paper_ids: list[str] | None = None
    force: bool = False


class ConfirmPapersRequest(BaseModel):
    paper_ids: list[str]
    confirmed_by: str = "api"


class MatchCatalogRequest(BaseModel):
    domain_ids: list[str] | None = None


class CopyFiguresRequest(BaseModel):
    figures: list[dict] | None = None


class BuildStoryRequest(BaseModel):
    force: bool = False


class BuildTexRequest(BaseModel):
    title: str | None = None
    force: bool = False
    template_only: bool = False


# ========== 首页 ==========

@app.get("/", response_class=HTMLResponse)
async def index():
    html_path = PROJECT_ROOT / "web" / "index.html"
    if html_path.exists():
        return HTMLResponse(html_path.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>MinerU 文献资产库</h1><p>访问 <a href='/docs'>/docs</a> 查看API文档</p>")


# ========== 上传 / 转换 ==========

@app.post("/upload")
async def upload(
    file: UploadFile = File(...),
    method: str = Query(MINERU_METHOD, description="解析方法: auto | ocr | txt"),
    wait: bool = Query(False, description="true 时等待转换完成并返回旧版响应"),

):
    """上传文件 -> MinerU 转 tmp -> cleaner 提取 paper.md+images -> manifest 记录
    固定使用 hybrid-engine + medium + auto，不暴露 backend/effort 选择。

    系统唯一上传管道：实现在 src/upload_service.upload_core，本端点只做 HTTP 适配。
    Gradio / CLI 同样调用 upload_service，确保 raw 写入、去重、converting 状态机
    全系统单入口。
    """
    from src.upload_service import UploadError, sanitize_filename, upload_from_path
    try:
        filename = file.filename or "upload.pdf"
        if method not in ("auto", "ocr", "txt"):
            raise UploadError(f"非法 method: {method}，允许: auto, ocr, txt", status_code=400)
        if Path(filename).suffix.lower() not in SUPPORTED_FORMATS:
            raise UploadError(f"不支持的格式: {Path(filename).suffix.lower()}，支持: {SUPPORTED_FORMATS}", status_code=400)
        sanitize_filename(filename, RAW_DIR)
        staged_path = await stage_upload_file(file, filename)

        def _run_upload():
            return upload_from_path(
                src_path=staged_path,
                filename=filename,
                converter=converter,
                cleaner=cleaner,
                manifest=manifest,
                raw_dir=RAW_DIR,
                tmp_dir=MINERU_TMP_DIR,
                method=method,
                backend=MINERU_BACKEND,
                effort=MINERU_EFFORT,
                lang=MINERU_LANG,
            )

        if wait:
            try:
                return await run_in_threadpool(_run_upload)
            finally:
                try:
                    staged_path.unlink(missing_ok=True)
                except OSError:
                    pass

        job_id = new_upload_job_id()
        upload_job_store.create(
            job_id=job_id,
            filename=filename,
            method=method,
            staged_path=staged_path,
        )
        upload_job_runner.submit(
            job_id=job_id,
            staged_path=staged_path,
            run_upload=_run_upload,
        )
        return JSONResponse(
            status_code=202,
            content={
                "job_id": job_id,
                "status": "queued",
                "filename": filename,
                "status_url": f"/upload/jobs/{job_id}",
            },
        )
    except UploadError as e:
        raise HTTPException(e.status_code, e.message)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/upload/jobs/{job_id}")
async def get_upload_job(job_id: str):
    try:
        from src.naming import validate_job_id
        validate_job_id(job_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    job = upload_job_store.get(job_id)
    if not job:
        raise HTTPException(404, f"upload job not found: {job_id}")
    return job


# ========== 文献资产 ==========

@app.get("/papers")
async def list_papers():
    return {"papers": manifest.list_all(), "stats": manifest.stats()}


@app.get("/papers/{paper_id}")
async def get_paper(paper_id: str):
    try:
        from src.naming import validate_paper_id
        validate_paper_id(paper_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    entry = manifest.get(paper_id)
    if not entry:
        raise HTTPException(404, f"未找到文献: {paper_id}")
    return entry


@app.get("/papers/{paper_id}/markdown", response_class=PlainTextResponse)
async def get_paper_markdown(paper_id: str):
    try:
        from src.naming import validate_paper_id
        validate_paper_id(paper_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    md = library.read_markdown(paper_id)
    if md is None:
        raise HTTPException(404, f"未找到 paper.md: {paper_id}")
    return md


@app.get("/papers/{paper_id}/images")
async def get_paper_images(paper_id: str):
    try:
        from src.naming import validate_paper_id
        validate_paper_id(paper_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    if not library.exists(paper_id):
        raise HTTPException(404, f"未找到文献: {paper_id}")
    return {"paper_id": paper_id, "images": library.list_images(paper_id)}


@app.get("/papers/{paper_id}/images/{img_name}")
async def get_paper_image(paper_id: str, img_name: str):
    """返回单张图片文件（前端预览用）"""
    from fastapi.responses import FileResponse
    try:
        from src.naming import safe_child, validate_paper_id, validate_image_name
        validate_paper_id(paper_id)
        validate_image_name(img_name)
        img_path = safe_child(library.images_dir(paper_id), img_name)
    except ValueError as e:
        raise HTTPException(400, str(e))
    if not img_path.is_file():
        raise HTTPException(404, f"未找到图片: {paper_id}/{img_name}")
    return FileResponse(img_path)


@app.delete("/papers/{paper_id}")
async def delete_paper(paper_id: str):
    # 校验 paper_id 防止路径穿越
    try:
        from src.naming import validate_paper_id
        validate_paper_id(paper_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    from src.services.paper_registry import PaperRegistryService
    svc = PaperRegistryService()
    result = svc.delete_paper(paper_id, remove_raw=False, remove_assets=True)
    if not result.get("success"):
        raise HTTPException(404, f"未找到文献: {paper_id}")
    return {"status": "success", "paper_id": paper_id,
            "deleted_paper_dir": result["deleted_paper_dir"],
            "removed_manifest": result["manifest"]}


# ========== 目录 ==========

@app.get("/catalog")
async def get_catalog():
    return catalog.load()


@app.post("/catalog/validate")
async def validate_catalog():
    errors = catalog.validate()
    return {"valid": len(errors) == 0, "errors": errors}


@app.get("/catalog/unsummarized")
async def unsummarized():
    ids = [p["paper_id"] for p in manifest.list_all()]
    return {"unsummarized": catalog.unsummarized(ids)}


# ========== Prompt 生成（不调 LLM）==========

@app.post("/prompt/catalog-entry")
async def prompt_catalog_entry(req: CatalogEntryRequest):
    try:
        from src.naming import validate_paper_id
        validate_paper_id(req.paper_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    out = prompt_builder.build_catalog_entry_prompt(req.paper_id)
    if not out.get("success"):
        raise HTTPException(404, out.get("error", "失败"))
    return out


@app.post("/prompt/bib-entry")
async def prompt_bib_entry(req: BibEntryRequest):
    """生成单篇文献 BibTeX 补全 prompt（不调 LLM）"""
    try:
        from src.naming import validate_paper_id
        validate_paper_id(req.paper_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    out = prompt_builder.build_bib_completion_prompt(req.paper_id)
    if not out.get("success"):
        raise HTTPException(404, out.get("error", "失败"))
    return out


@app.post("/prompt/plan-reading")
async def prompt_plan_reading(req: PlanRequest):
    if not req.question.strip():
        raise HTTPException(400, "问题不能为空")
    out = prompt_builder.build_catalog_planning_prompt(req.question.strip())
    if not out.get("success"):
        raise HTTPException(400, out.get("error", "失败"))
    return out


@app.post("/prompt/read-fulltext")
async def prompt_read_fulltext(req: FulltextRequest):
    if not req.question.strip():
        raise HTTPException(400, "问题不能为空")
    if not req.paper_ids:
        raise HTTPException(400, "paper_ids 不能为空")
    try:
        from src.naming import validate_paper_id
        for pid in req.paper_ids:
            validate_paper_id(pid)
    except ValueError as e:
        raise HTTPException(400, str(e))
    out = prompt_builder.build_fulltext_prompt(req.question.strip(), req.paper_ids)
    if not out.get("success"):
        raise HTTPException(400, out.get("error", "失败"))
    return out


# ========== 综述写作任务（不调 LLM，各步生成 prompt + 结构文件）==========


def _check_job_id(job_id: str) -> None:
    """校验 job_id 防路径穿越，非法时抛 HTTPException(400)"""
    from src.naming import validate_job_id
    try:
        validate_job_id(job_id)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/write/jobs")
async def create_write_job(req: CreateJobRequest):
    """创建写作任务：生成 write/<job>/ 目录 + normalized_task 骨架"""
    # API 不接受 input_file 路径（防本地任意文件读取）
    if req.input_file:
        raise HTTPException(
            400,
            "HTTP API 不接受本地 input_file 路径；请通过 topic 参数传入研究文本。"
            "CLI 写作用 input_file 请用 scripts/write_review.py。")
    try:
        info = job_manager.create(topic=req.topic, input_file=None,
                                  target=req.target, language=req.language)
    except (ValueError, FileNotFoundError) as e:
        raise HTTPException(400, str(e))
    norm = normalize_task(info["job_id"], job_manager)
    info["normalized_task"] = norm["normalized_path"]
    return info


@app.get("/write/jobs")
async def list_write_jobs():
    return {"jobs": job_manager.list_jobs()}


@app.get("/write/jobs/{job_id}")
async def get_write_job(job_id: str):
    _check_job_id(job_id)
    meta = job_manager.load_meta(job_id)
    if meta is None:
        raise HTTPException(404, f"任务不存在: {job_id}")
    return meta


@app.get("/write/jobs/{job_id}/files")
async def write_job_files(job_id: str):
    _check_job_id(job_id)
    if not job_manager.job_dir(job_id).exists():
        raise HTTPException(404, f"任务不存在: {job_id}")
    return {"job_id": job_id, "files": job_manager.job_files(job_id)}


@app.post("/write/jobs/{job_id}/match-catalog")
async def write_match_catalog(job_id: str, req: MatchCatalogRequest = Body(default_factory=MatchCatalogRequest)):
    _check_job_id(job_id)
    if not job_manager.load_meta(job_id):
        raise HTTPException(404, f"任务不存在: {job_id}")
    return match_catalog(job_id, jm=job_manager, catalog=catalog, domain_ids=req.domain_ids)


@app.post("/write/jobs/{job_id}/confirm-papers")
async def write_confirm_papers(job_id: str, req: ConfirmPapersRequest):
    _check_job_id(job_id)
    if not job_manager.load_meta(job_id):
        raise HTTPException(404, f"任务不存在: {job_id}")
    if not req.paper_ids:
        raise HTTPException(400, "paper_ids 不能为空")
    selected = [{"paper_id": pid, "reason": "", "expected_use": "", "priority": 3}
                for pid in req.paper_ids]
    try:
        return confirm_selected_papers(job_id, selected,
                                       confirmed_by=req.confirmed_by,
                                       jm=job_manager, catalog=catalog)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/write/jobs/{job_id}/deep-read")
async def write_deep_read(job_id: str, req: DeepReadRequest):
    _check_job_id(job_id)
    if not job_manager.load_meta(job_id):
        raise HTTPException(404, f"任务不存在: {job_id}")
    try:
        return deep_read(job_id, req.paper_ids, force=req.force, jm=job_manager,
                         library=library, catalog=catalog)
    except RuntimeError as e:
        raise HTTPException(400, str(e))


@app.post("/write/jobs/{job_id}/mark-deep-read")
async def write_mark_deep_read(job_id: str):
    _check_job_id(job_id)
    if not job_manager.load_meta(job_id):
        raise HTTPException(404, f"任务不存在: {job_id}")
    info = mark_deep_reading_filled(job_id, jm=job_manager)
    if not info["filled"]:
        raise HTTPException(400, "精读笔记校验未通过: " + "; ".join(info["errors"]))
    return info


@app.post("/write/jobs/{job_id}/build-story")
async def write_build_story(job_id: str, req: BuildStoryRequest = Body(default_factory=BuildStoryRequest)):
    _check_job_id(job_id)
    if not job_manager.load_meta(job_id):
        raise HTTPException(404, f"任务不存在: {job_id}")
    try:
        return build_story(job_id, force=req.force, jm=job_manager, catalog=catalog)
    except RuntimeError as e:
        raise HTTPException(400, str(e))


@app.post("/write/jobs/{job_id}/mark-story")
async def write_mark_story(job_id: str):
    _check_job_id(job_id)
    if not job_manager.load_meta(job_id):
        raise HTTPException(404, f"任务不存在: {job_id}")
    info = mark_story_filled(job_id, jm=job_manager)
    if not info["filled"]:
        raise HTTPException(400, "故事线校验未通过: " + "; ".join(info["errors"]))
    return info


@app.post("/write/jobs/{job_id}/build-tex")
async def write_build_tex(job_id: str, req: BuildTexRequest):
    _check_job_id(job_id)
    if not job_manager.load_meta(job_id):
        raise HTTPException(404, f"任务不存在: {job_id}")
    try:
        return build_tex(job_id, title=req.title, force=req.force,
                         template_only=req.template_only,
                         jm=job_manager, catalog=catalog, library=library)
    except RuntimeError as e:
        raise HTTPException(400, str(e))


@app.post("/write/jobs/{job_id}/mark-tex")
async def write_mark_tex(job_id: str):
    _check_job_id(job_id)
    if not job_manager.load_meta(job_id):
        raise HTTPException(404, f"任务不存在: {job_id}")
    info = mark_tex_content_filled(job_id, jm=job_manager)
    if not info["filled"]:
        raise HTTPException(400, "TeX 正文校验未通过: " + "; ".join(info["errors"]))
    return info


@app.post("/write/jobs/{job_id}/copy-figures")
async def write_copy_figures(job_id: str, req: CopyFiguresRequest):
    _check_job_id(job_id)
    if not job_manager.load_meta(job_id):
        raise HTTPException(404, f"任务不存在: {job_id}")
    return copy_figures(job_id, figures=req.figures, jm=job_manager, catalog=catalog)


@app.post("/write/jobs/{job_id}/validate")
async def write_validate(job_id: str):
    _check_job_id(job_id)
    if not job_manager.load_meta(job_id):
        raise HTTPException(404, f"任务不存在: {job_id}")
    return validate_job(job_id, jm=job_manager)


# ========== 状态 ==========

@app.get("/status")
async def status():
    import os
    from datetime import datetime
    from src.converter import MINERU_EXE, mineru_available
    return {
        "status": "running",
        "port": API_PORT,
        "version": "3.4.0",
        "mode": "literature_library (no vector search)",
        "mineru_backend": MINERU_BACKEND,
        "mineru_cli": MINERU_EXE,
        "mineru_available": mineru_available(),
        "raw_dir_writable": os.access(RAW_DIR, os.W_OK),
        "papers_dir_writable": os.access(PAPERS_DIR, os.W_OK),
        "manifest_writable": os.access(manifest.path.parent, os.W_OK),
        "library": manifest.stats(),
        "catalog_papers": len(catalog.list_papers()),
        "timestamp": datetime.now().isoformat(),
    }


@app.get("/status/runtime")
async def status_runtime():
    from src.converter import MINERU_EXE
    from src.mineru_runtime import (
        describe_runtime,
        list_gpu_processes,
        preflight_gpu,
        preflight_mineru_api,
        preflight_mineru_cli,
        runtime_config_from_env,
        snapshot_nvidia_smi,
    )
    from src.mineru_lock import read_mineru_lock_status

    config = runtime_config_from_env()
    gpu = preflight_gpu()
    cli = preflight_mineru_cli(MINERU_EXE)
    api = preflight_mineru_api(config.api_url)

    # GPU snapshot (memory/util summary)
    gpu_snapshot = snapshot_nvidia_smi()
    gpu_summary = {"available": gpu_snapshot.get("available", False)}
    if gpu_snapshot.get("gpus"):
        g = gpu_snapshot["gpus"][0]
        gpu_summary.update({
            "name": g.get("name", "?"),
            "memory_used_mb": g.get("memory_used_mb", 0),
            "memory_total_mb": g.get("memory_total_mb", 0),
            "gpu_util_pct": g.get("gpu_util_pct", 0),
            "memory_util_pct": g.get("memory_util_pct", 0),
        })

    # GPU compute processes (real process list from nvidia-smi)
    gpu_procs = list_gpu_processes()
    gpu_processes = gpu_procs.get("processes", []) if gpu_procs.get("available") else []

    # MinerU lock status
    lock_status = read_mineru_lock_status()

    return {
        "runtime": describe_runtime(config),
        "gpu": {
            "nvidia_smi_available": gpu.nvidia_smi,
            "preflight_ok": gpu.ok,
            "preflight_message": gpu.message,
            "summary": gpu_summary,
        },
        "gpu_processes": gpu_processes,
        "mineru_lock": lock_status,
        "cli": cli.__dict__,
        "api": api.__dict__,
    }


if __name__ == "__main__":
    uvicorn.run("src.server:app", host=API_HOST, port=API_PORT, reload=False, log_level="info")
