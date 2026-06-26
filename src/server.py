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
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, UploadFile, File, HTTPException, Query
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
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
from src.naming import derive_paper_id
from src.writer.job_manager import JobManager
from src.writer.topic_parser import normalize_task
from src.writer.catalog_matcher import match_catalog, confirm_selected_papers
from src.writer.deep_reader import deep_read, mark_deep_reading_filled
from src.writer.story_builder import build_story, mark_story_filled
from src.writer.tex_project import build_tex, mark_tex_content_filled
from src.writer.figure_manager import copy_figures
from src.writer.bib_manager import (validate_job_citations, portability_check,
                                    validate_catalog_citations)

# ========== 初始化 ==========

app = FastAPI(
    title="MinerU 文献资产库",
    description="文献解析 + AI 摘要目录 + 按需全文阅读 (端口 8080)",
    version="3.4.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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


class ConfirmPapersRequest(BaseModel):
    paper_ids: list[str]
    confirmed_by: str = "api"


class CopyFiguresRequest(BaseModel):
    figures: list[dict] | None = None


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
    backend: str = Query(MINERU_BACKEND, description="后端: pipeline | hybrid-engine | vlm-engine"),
    effort: str = Query(MINERU_EFFORT, description="hybrid-engine 解析强度: medium | high"),
):
    """上传文件 -> MinerU 转 tmp -> cleaner 提取 paper.md+images -> manifest 记录"""
    from config.settings import MAX_UPLOAD_SIZE
    suffix = Path(file.filename).suffix.lower()
    if suffix not in SUPPORTED_FORMATS:
        raise HTTPException(400, f"不支持的格式: {suffix}，支持: {SUPPORTED_FORMATS}")

    paper_id = derive_paper_id(file.filename)
    try:
        from src.naming import validate_paper_id
        validate_paper_id(paper_id)
    except ValueError as e:
        raise HTTPException(400, str(e))

    save_path = RAW_DIR / file.filename
    content = await file.read()
    if len(content) > MAX_UPLOAD_SIZE:
        raise HTTPException(413, f"文件过大: {len(content)} bytes > 上限 {MAX_UPLOAD_SIZE} bytes")
    save_path.write_bytes(content)

    logger.info(f"收到文件: {file.filename} ({len(content)} bytes) -> paper_id={paper_id}")

    tmp_out = MINERU_TMP_DIR / paper_id
    try:
        result = converter.convert(
            save_path, tmp_out, backend=backend, method=method,
            lang=MINERU_LANG, effort=effort,
        )
        if not result["success"]:
            raise HTTPException(500, f"转换失败: {result.get('error')}")

        # cleaner 从 tmp 提取到 papers/<paper_id>/
        clean = cleaner.extract(result["output_dir"], paper_id, overwrite=True)
        if not clean["success"]:
            raise HTTPException(500, f"清理失败: {clean.get('error')}")

        from src.file_fingerprint import compute_sha256, file_meta
        meta = file_meta(save_path)
        manifest.upsert(
            paper_id=paper_id,
            raw_pdf=str(save_path),
            markdown=clean["markdown_path"],
            images_dir=clean["images_dir"],
            status="converted",
            images_count=clean["images_count"],
            md_chars=clean["char_count"],
            raw_filename=file.filename,
            sha256=meta["sha256"], file_size=meta["file_size"], mtime=meta["mtime"],
            backend=result.get("backend", "cli"), method=method,
        )

        return {
            "status": "success",
            "paper_id": paper_id,
            "filename": file.filename,
            "markdown_path": clean["markdown_path"],
            "images_count": clean["images_count"],
            "md_chars": clean["char_count"],
            "message": f"转换完成: {paper_id} ({clean['char_count']} 字符, {clean['images_count']} 图)",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"处理失败: {e}")
        raise HTTPException(500, f"处理失败: {str(e)}")


# ========== 文献资产 ==========

@app.get("/papers")
async def list_papers():
    return {"papers": manifest.list_all(), "stats": manifest.stats()}


@app.get("/papers/{paper_id}")
async def get_paper(paper_id: str):
    entry = manifest.get(paper_id)
    if not entry:
        raise HTTPException(404, f"未找到文献: {paper_id}")
    return entry


@app.get("/papers/{paper_id}/markdown", response_class=PlainTextResponse)
async def get_paper_markdown(paper_id: str):
    md = library.read_markdown(paper_id)
    if md is None:
        raise HTTPException(404, f"未找到 paper.md: {paper_id}")
    return md


@app.get("/papers/{paper_id}/images")
async def get_paper_images(paper_id: str):
    if not library.exists(paper_id):
        raise HTTPException(404, f"未找到文献: {paper_id}")
    return {"paper_id": paper_id, "images": library.list_images(paper_id)}


@app.get("/papers/{paper_id}/images/{img_name}")
async def get_paper_image(paper_id: str, img_name: str):
    """返回单张图片文件（前端预览用）"""
    from fastapi.responses import FileResponse
    img_path = PAPERS_DIR / paper_id / "images" / img_name
    if not img_path.is_file():
        raise HTTPException(404, f"未找到图片: {paper_id}/{img_name}")
    return FileResponse(img_path)


@app.delete("/papers/{paper_id}")
async def delete_paper(paper_id: str):
    # 删除 papers 目录
    pdir = PAPERS_DIR / paper_id
    removed_files = False
    if pdir.exists():
        import shutil
        shutil.rmtree(pdir)
        removed_files = True
    # 删除 manifest 条目
    removed_manifest = manifest.delete(paper_id)
    # 删除 catalog 条目
    catalog.delete(paper_id)
    if not (removed_files or removed_manifest):
        raise HTTPException(404, f"未找到文献: {paper_id}")
    return {"status": "success", "paper_id": paper_id,
            "removed_files": removed_files, "removed_manifest": removed_manifest}


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
    out = prompt_builder.build_catalog_entry_prompt(req.paper_id)
    if not out.get("success"):
        raise HTTPException(404, out.get("error", "失败"))
    return out


@app.post("/prompt/bib-entry")
async def prompt_bib_entry(req: BibEntryRequest):
    """生成单篇文献 BibTeX 补全 prompt（不调 LLM）"""
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
    out = prompt_builder.build_fulltext_prompt(req.question.strip(), req.paper_ids)
    if not out.get("success"):
        raise HTTPException(400, out.get("error", "失败"))
    return out


# ========== 综述写作任务（不调 LLM，各步生成 prompt + 结构文件）==========

@app.post("/write/jobs")
async def create_write_job(req: CreateJobRequest):
    """创建写作任务：生成 write/<job>/ 目录 + normalized_task 骨架"""
    try:
        info = job_manager.create(topic=req.topic, input_file=req.input_file,
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
    meta = job_manager.load_meta(job_id)
    if meta is None:
        raise HTTPException(404, f"任务不存在: {job_id}")
    return meta


@app.get("/write/jobs/{job_id}/files")
async def write_job_files(job_id: str):
    if not job_manager.job_dir(job_id).exists():
        raise HTTPException(404, f"任务不存在: {job_id}")
    return {"job_id": job_id, "files": job_manager.job_files(job_id)}


@app.post("/write/jobs/{job_id}/match-catalog")
async def write_match_catalog(job_id: str):
    if not job_manager.load_meta(job_id):
        raise HTTPException(404, f"任务不存在: {job_id}")
    return match_catalog(job_id, jm=job_manager, catalog=catalog)


@app.post("/write/jobs/{job_id}/confirm-papers")
async def write_confirm_papers(job_id: str, req: ConfirmPapersRequest):
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
    if not job_manager.load_meta(job_id):
        raise HTTPException(404, f"任务不存在: {job_id}")
    try:
        return deep_read(job_id, req.paper_ids, jm=job_manager,
                         library=library, catalog=catalog)
    except RuntimeError as e:
        raise HTTPException(400, str(e))


@app.post("/write/jobs/{job_id}/mark-deep-read")
async def write_mark_deep_read(job_id: str):
    if not job_manager.load_meta(job_id):
        raise HTTPException(404, f"任务不存在: {job_id}")
    info = mark_deep_reading_filled(job_id, jm=job_manager)
    if not info["filled"]:
        raise HTTPException(400, "精读笔记校验未通过: " + "; ".join(info["errors"]))
    return info


@app.post("/write/jobs/{job_id}/build-story")
async def write_build_story(job_id: str):
    if not job_manager.load_meta(job_id):
        raise HTTPException(404, f"任务不存在: {job_id}")
    try:
        return build_story(job_id, jm=job_manager, catalog=catalog)
    except RuntimeError as e:
        raise HTTPException(400, str(e))


@app.post("/write/jobs/{job_id}/mark-story")
async def write_mark_story(job_id: str):
    if not job_manager.load_meta(job_id):
        raise HTTPException(404, f"任务不存在: {job_id}")
    info = mark_story_filled(job_id, jm=job_manager)
    if not info["filled"]:
        raise HTTPException(400, "故事线校验未通过: " + "; ".join(info["errors"]))
    return info


@app.post("/write/jobs/{job_id}/build-tex")
async def write_build_tex(job_id: str, req: BuildTexRequest):
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
    if not job_manager.load_meta(job_id):
        raise HTTPException(404, f"任务不存在: {job_id}")
    info = mark_tex_content_filled(job_id, jm=job_manager)
    if not info["filled"]:
        raise HTTPException(400, "TeX 正文校验未通过: " + "; ".join(info["errors"]))
    return info


@app.post("/write/jobs/{job_id}/copy-figures")
async def write_copy_figures(job_id: str, req: CopyFiguresRequest):
    if not job_manager.load_meta(job_id):
        raise HTTPException(404, f"任务不存在: {job_id}")
    return copy_figures(job_id, figures=req.figures, jm=job_manager, catalog=catalog)


@app.post("/write/jobs/{job_id}/validate")
async def write_validate(job_id: str):
    if not job_manager.load_meta(job_id):
        raise HTTPException(404, f"任务不存在: {job_id}")
    import importlib
    vwj = importlib.import_module("scripts.validate_write_job")
    return vwj.validate_job(job_id, jm=job_manager)


# ========== 状态 ==========

@app.get("/status")
async def status():
    from datetime import datetime
    return {
        "status": "running",
        "port": API_PORT,
        "version": "3.4.0",
        "mode": "literature_library (no vector search)",
        "mineru_backend": MINERU_BACKEND,
        "library": manifest.stats(),
        "catalog_papers": len(catalog.list_papers()),
        "timestamp": datetime.now().isoformat(),
    }


if __name__ == "__main__":
    uvicorn.run("src.server:app", host=API_HOST, port=API_PORT, reload=False, log_level="info")
