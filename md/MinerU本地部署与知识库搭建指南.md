# MinerU 本地部署与知识库搭建指南

## 环境要求

| 项目 | 最低要求 | 本机配置 |
|------|---------|---------|
| GPU | 4GB 显存 (pipeline后端) | RTX 4070 Laptop 8GB |
| 内存 | 16GB | 16GB DDR5 |
| 硬盘 | 20GB 可用空间 | SSD, 充足 |
| Python | 3.10-3.13 | 3.10 (conda) |
| CUDA | 11.7+ | 12.6 |
| 操作系统 | Windows/Linux/macOS | Windows 11 |

## 一、安装步骤

### 1.1 安装 Miniconda

从 https://docs.conda.io/en/latest/miniconda.html 下载安装。

### 1.2 创建 conda 环境

```bash
conda create -n mineru python=3.10 -y
conda activate mineru
```

### 1.3 安装 MinerU 3.4

```bash
# 安装 uv (加速包管理)
pip install uv -i https://mirrors.aliyun.com/pypi/simple

# 安装 MinerU (包含所有功能)
uv pip install -U "mineru[all]" -i https://mirrors.aliyun.com/pypi/simple
```

### 1.4 安装知识库依赖

```bash
pip install chromadb sentence-transformers fastapi uvicorn python-multipart loguru PyMuPDF -i https://mirrors.aliyun.com/pypi/simple
```

### 1.5 配置文件

MinerU 的配置文件位于 `C:\Users\Admin\mineru.json`（用户目录下）：

```json
{
    "model-source": "huggingface",
    "config_version": "1.3.2",
    "device-mode": "cuda"
}
```

如果需要通过代理下载模型，设置环境变量：
```bash
set HTTP_PROXY=http://127.0.0.1:7890
set HTTPS_PROXY=http://127.0.0.1:7890
```

### 1.6 下载模型

首次运行 MinerU 时会自动下载模型（约2-3GB），缓存在：
```
C:\Users\Admin\.cache\huggingface\hub\models--opendatalab--PDF-Extract-Kit-1.0\
```

嵌入模型（知识库用）缓存在：
```
C:\Users\Admin\.cache\huggingface\hub\models--BAAI--bge-small-zh-v1.5\
```

## 二、项目结构

```
E:\1\mineru\
├── src/
│   ├── server.py          # 知识库 API 服务 (端口 8080)
│   ├── converter.py       # MinerU 文档转换引擎
│   ├── chunker.py         # 智能文本分块器
│   ├── indexer.py         # 向量化 + ChromaDB 索引
│   └── retriever.py       # RAG 检索器
├── config/
│   └── settings.py        # 全局配置
├── web/
│   └── index.html         # Web UI
├── data/
│   ├── raw/               # 原始文件 (PDF/DOCX等)
│   ├── parsed/            # MinerU 转换输出 (Markdown + 图片)
│   └── vectordb/          # ChromaDB 向量库持久化
├── md/                    # 文档目录
├── batch_convert.py       # 批量转换脚本
├── start.bat              # 一键启动
└── requirements.txt
```

### 关键组件说明

| 文件 | 功能 |
|------|------|
| `src/converter.py` | 封装 MinerU CLI，支持 PDF/DOCX/PPTX/XLSX/图片转换 |
| `src/chunker.py` | 按 Markdown 标题结构分块，支持滑动窗口重叠 |
| `src/indexer.py` | 使用 bge-small-zh-v1.5 嵌入，ChromaDB 存储 |
| `src/retriever.py` | 语义搜索 + RAG 上下文组装 |
| `src/server.py` | FastAPI 服务，提供上传/搜索/问答接口 |
| `batch_convert.py` | 批量转换目录中的文件 |

## 三、使用方式

### 3.1 启动 MinerU API 常驻服务（推荐）

常驻服务避免每次转换都重新加载模型，速度快很多：

```bash
conda activate mineru
mineru-api --port 8000
```

访问 http://127.0.0.1:8000/docs 查看 API 文档。

### 3.2 启动知识库服务

```bash
conda activate mineru
cd E:\1\mineru
python -m src.server
```

或双击 `start.bat`。

访问 http://localhost:8080 使用 Web UI，http://localhost:8080/docs 查看 API 文档。

### 3.3 转换单个文件

```bash
# 通过 API 服务（快，模型已预加载）
mineru -p input.pdf -o output -b pipeline --api-url http://127.0.0.1:8000

# 直接 CLI（慢，每次加载模型）
mineru -p input.pdf -o output -b pipeline
```

### 3.4 批量转换 + 入库

```bash
# 转换并入库
python batch_convert.py E:\文献目录 --api-url http://127.0.0.1:8000

# 只转换不入库
python batch_convert.py E:\文献目录 --api-url http://127.0.0.1:8000 --no-index
```

脚本会自动跳过已处理的文件。

### 3.5 API 接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `/upload` | POST | 上传文件，自动转换+分块+入库 |
| `/search` | POST | 语义搜索 |
| `/ask` | POST | RAG 问答（返回检索结果+Prompt） |
| `/documents` | GET | 列出已索引文档 |
| `/documents/{name}` | DELETE | 删除文档 |
| `/status` | GET | 系统状态 |

搜索参数：
```json
POST /search
{
    "query": "blowing snow particle size",
    "top_k": 10,        // 返回条数
    "min_score": 0.3    // 最低相似度阈值
}
```

## 四、配置调优

### 4.1 检索配置 (`config/settings.py`)

```python
CHUNK_SIZE = 600          # 每个chunk的目标字符数
CHUNK_OVERLAP = 100       # chunk之间的重叠字符数
MIN_CHUNK_SIZE = 50       # 最小chunk大小
DEFAULT_TOP_K = 10        # 默认返回条数
MAX_TOP_K = 50            # 最大返回条数
MIN_SCORE = 0.3           # 最低相似度阈值
```

### 4.2 MinerU 解析后端

| 后端 | 显存需求 | 精度 | 适用场景 |
|------|---------|------|---------|
| `pipeline` | 4GB | 86.47 | 快速稳定，无幻觉 |
| `hybrid-engine` | 8GB | 95.39 | 高精度，推荐 |
| `vlm-engine` | 8GB | 95.30 | 高精度，VLM模型 |

### 4.3 解析方法

| 方法 | 说明 |
|------|------|
| `auto` | 自动判断（推荐） |
| `txt` | 纯文本PDF，速度快 |
| `ocr` | 扫描件PDF，用OCR |

## 五、注意事项

### 5.1 端口规划

| 端口 | 用途 | 说明 |
|------|------|------|
| 7890 | 代理 (FLClash) | 科学上网/下载模型 |
| 8000 | MinerU API | PDF转换常驻服务 |
| 8080 | 知识库服务 | 搜索/问答/Web UI |

### 5.2 CPU 占用

MinerU 的 `pipeline` 后端中：
- 版面检测 → GPU（快）
- 公式识别 → GPU（中）
- **OCR 文字识别 → CPU（慢，吃CPU）**

CPU 占用高是正常的，这是 pipeline 后端的设计特点。

### 5.3 服务持久性

- `mineru-api` 和知识库服务是独立进程，**关闭 VS Code 不影响运行**
- 关闭终端窗口会停止服务
- 如需后台运行，可用 `start /b` 或 `Start-Process -WindowStyle Hidden`

### 5.4 增量更新

- 批量转换脚本会自动跳过已处理的文件
- 重复上传同名文件会自动覆盖旧的向量数据
- 删除文档：`DELETE /documents/{filename}.pdf`

### 5.5 模型缓存位置

| 模型 | 路径 | 大小 |
|------|------|------|
| MinerU 模型 | `~\.cache\huggingface\hub\models--opendatalab--PDF-Extract-Kit-1.0\` | ~2GB |
| 嵌入模型 | `~\.cache\huggingface\hub\models--BAAI--bge-small-zh-v1.5\` | ~90MB |
| ChromaDB | `E:\1\mineru\data\vectordb\` | 按数据量 |

## 六、快速参考

```bash
# 启动 MinerU API
conda activate mineru && mineru-api --port 8000

# 启动知识库
conda activate mineru && cd E:\1\mineru && python -m src.server

# 批量转换
python batch_convert.py E:\文献目录 --api-url http://127.0.0.1:8000

# 单文件转换
mineru -p file.pdf -o output -b pipeline --api-url http://127.0.0.1:8000

# 搜索
curl -X POST http://localhost:8080/search -H "Content-Type: application/json" -d '{"query":"关键词","top_k":10}'

# 查看状态
curl http://localhost:8080/status
```
