"""项目配置

重构后定位：文献资产库 + AI 摘要目录 + 按需全文阅读。
不再做 chunk / embedding / ChromaDB 语义检索。

所有配置项均可通过环境变量覆盖（保留默认值），支持 .env 文件。
"""
import os
from pathlib import Path

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent

# 数据目录
DATA_DIR = Path(os.environ.get("MINERU_DATA_DIR", PROJECT_ROOT / "data"))
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
API_HOST = os.environ.get("MINERU_API_HOST", "127.0.0.1")
API_PORT = int(os.environ.get("MINERU_API_PORT", "8080"))
# 上传大小上限（字节），默认 500MB
MAX_UPLOAD_SIZE = int(os.environ.get("MINERU_MAX_UPLOAD_SIZE", str(500 * 1024 * 1024)))

# MinerU 解析超时（秒），默认 600
MINERU_TIMEOUT = int(os.environ.get("MINERU_TIMEOUT", "600"))

# MinerU 解析配置
# 后端: pipeline (4GB显存, 精度86) | hybrid-engine (8GB显存, 精度95) | vlm-engine (8GB显存, 精度95)
MINERU_BACKEND = os.environ.get("MINERU_BACKEND", "hybrid-engine")
# 解析强度 (仅hybrid-engine生效): medium (快, 精度95.26) | high (慢, 精度95.39, 支持图片分析)
MINERU_EFFORT = os.environ.get("MINERU_EFFORT", "medium")
# 解析方法: auto | ocr | txt
MINERU_METHOD = os.environ.get("MINERU_METHOD", "auto")
# OCR语言: ch | en 等
MINERU_LANG = os.environ.get("MINERU_LANG", "ch")

# 全文阅读 prompt 的单篇最大字符数（防止 prompt 过长）
PAPER_MD_MAX_CHARS = int(os.environ.get("MINERU_PAPER_MD_MAX_CHARS", "12000"))

# 文献研究方向配置（用于 catalog-entry prompt 的 relevance_to_my_work 字段）
RESEARCH_DOMAIN = os.environ.get(
    "MINERU_RESEARCH_DOMAIN",
    "风吹雪 / 雪升华 / 跃移悬移 / 粒径分布 / 破碎")

# 支持的文件格式 (MinerU 3.4)
SUPPORTED_FORMATS = {".pdf", ".docx", ".pptx", ".xlsx", ".png", ".jpg", ".jpeg"}

# 确保目录存在（导入即创建，有副作用）
for d in [RAW_DIR, PAPERS_DIR, MINERU_TMP_DIR, CATALOG_DIR, MANIFESTS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# 启动时安全检查：若 API_HOST 非 localhost 且无认证，打印 warning
if API_HOST not in ("127.0.0.1", "localhost", "::1"):
    import warnings
    warnings.warn(
        f"API_HOST={API_HOST} 非 localhost，当前无认证机制。"
        f"请确认防火墙已正确配置，或设置环境变量 MINERU_API_HOST=127.0.0.1",
        RuntimeWarning)
