"""项目配置

重构后定位：文献资产库 + AI 摘要目录 + 按需全文阅读。
不再做 chunk / embedding / ChromaDB 语义检索。

所有配置项均可通过环境变量覆盖（保留默认值），支持 .env 文件。
"""
import os
import warnings
from pathlib import Path


def _env_str(name: str, default: str) -> str:
    """读取字符串环境变量，空字符串视为未设置"""
    val = os.environ.get(name, "").strip()
    return val if val else default


def _env_int(name: str, default: int, min_val: int | None = None,
             max_val: int | None = None) -> int:
    """读取整数环境变量，非法值时 warning 后回退默认值"""
    val = os.environ.get(name, "").strip()
    if not val:
        return default
    try:
        v = int(val)
    except ValueError:
        warnings.warn(f"{name}={val!r} 非法整数，回退默认 {default}")
        return default
    if min_val is not None and v < min_val:
        warnings.warn(f"{name}={v} < {min_val}，回退默认 {default}")
        return default
    if max_val is not None and v > max_val:
        warnings.warn(f"{name}={v} > {max_val}，回退默认 {default}")
        return default
    return v


def _env_path(name: str, default: Path) -> Path:
    """读取路径环境变量"""
    val = os.environ.get(name, "").strip()
    return Path(val) if val else Path(default)

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent

# 数据目录
DATA_DIR = _env_path("MINERU_DATA_DIR", PROJECT_ROOT / "data")
RAW_DIR = DATA_DIR / "raw"                  # PDF 原文（投放/上传目标，不在 papers 中复制 PDF）
PAPERS_DIR = DATA_DIR / "papers"            # MinerU 清理后的 AI 可读资产：<paper_id>/paper.md + images/
MINERU_TMP_DIR = DATA_DIR / "tmp" / "mineru_raw_output"  # MinerU 原始输出临时目录，处理完可清空
LEGACY_PARSED_DIR = DATA_DIR / "parsed"     # 旧版 MinerU 输出（仅迁移时读取，新流程不再写入）

# 目录与账本
CATALOG_DIR = DATA_DIR / "catalog"          # AI 维护的文献理解目录
MANIFESTS_DIR = DATA_DIR / "manifests"      # 系统维护的文件账本
CATALOG_PATH = CATALOG_DIR / "literature_catalog.json"
MANIFEST_PATH = MANIFESTS_DIR / "papers_manifest.json"

# API 配置（默认仅 localhost，防误暴露）
API_HOST = _env_str("MINERU_API_HOST", "127.0.0.1")
API_PORT = _env_int("MINERU_API_PORT", 8080, min_val=1, max_val=65535)
# 上传大小上限（字节），默认 500MB
MAX_UPLOAD_SIZE = _env_int("MINERU_MAX_UPLOAD_SIZE", 500 * 1024 * 1024, min_val=1)

# MinerU 解析超时（秒），默认 600
MINERU_TIMEOUT = _env_int("MINERU_TIMEOUT", 600, min_val=1)

# MinerU 解析配置
# 后端: pipeline (4GB显存, 精度86) | hybrid-engine (8GB显存, 精度95) | vlm-engine (8GB显存, 精度95)
MINERU_BACKEND = _env_str("MINERU_BACKEND", "hybrid-engine")
# 解析强度 (仅hybrid-engine生效): medium (快, 精度95.26) | high (慢, 精度95.39, 支持图片分析)
MINERU_EFFORT = _env_str("MINERU_EFFORT", "medium")
# 解析方法: auto | ocr | txt
MINERU_METHOD = _env_str("MINERU_METHOD", "auto")
# OCR语言: ch | en 等
MINERU_LANG = _env_str("MINERU_LANG", "ch")

# 全文阅读 prompt 的单篇最大字符数（防止 prompt 过长）
PAPER_MD_MAX_CHARS = _env_int("MINERU_PAPER_MD_MAX_CHARS", 12000, min_val=1)

# 文献研究方向配置（用于 catalog-entry prompt 的 relevance_to_my_work 字段）
# 默认不写死领域；用户通过环境变量 MINERU_RESEARCH_DOMAIN 配置
RESEARCH_DOMAIN = _env_str("MINERU_RESEARCH_DOMAIN", "")

# 写作/综述风格配置（用于 prompt builder）
RESEARCH_QUESTION = _env_str("MINERU_RESEARCH_QUESTION", "")
WRITING_STYLE = _env_str("MINERU_WRITING_STYLE", "technical Chinese academic writing")
CITATION_STYLE = _env_str("MINERU_CITATION_STYLE", "author-year")

# 支持的文件格式 (MinerU 3.4)
SUPPORTED_FORMATS = {".pdf", ".docx", ".pptx", ".xlsx", ".png", ".jpg", ".jpeg"}

# 确保目录存在（导入即创建，有副作用）
for d in [RAW_DIR, PAPERS_DIR, MINERU_TMP_DIR, CATALOG_DIR, MANIFESTS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# 启动时安全检查：若 API_HOST 非 localhost 且无认证，打印 warning
if API_HOST not in ("127.0.0.1", "localhost", "::1"):
    warnings.warn(
        f"API_HOST={API_HOST} 非 localhost，当前无认证机制。"
        f"请确认防火墙已正确配置，或设置环境变量 MINERU_API_HOST=127.0.0.1",
        RuntimeWarning)
