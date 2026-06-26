# MinerU 文献资产库 + 博士论文级综述写作 Skill

一个本地 **文献资产库 + AI 摘要目录 + 按需全文阅读 + 博士论文级写作工作区**，基于 [MinerU 3.4](https://github.com/opendatalab/MinerU) 构建。

把 PDF/DOCX/PPTX/XLSX/图片用 MinerU 转成 Markdown，清理后只保留 `paper.md + images/` 作为 AI 可读资产；再用一个结构化目录 `literature_catalog.json` 让大模型"像导师一样"先规划该读哪些全文，最后按需读取全文 Markdown、组装可编译的独立 LaTeX 写作项目。

> **本项目不做向量检索 / RAG / 语义搜索**。重构时已删除 ChromaDB、embedding、chunker、indexer、retriever。所有 `/prompt/*` 与写作流程各步**只生成可复制粘贴的 prompt 与结构化模板，不调用任何 LLM**——仓库里没有 LLM client。LLM 步骤由用户手动跑大模型后回填对应文件。

---

## 目录

- [它能做什么](#它能做什么)
- [核心设计](#核心设计)
- [项目结构](#项目结构)
- [环境要求](#环境要求)
- [快速开始](#快速开始)
- [综述写作工作流](#综述写作工作流)
- [API 接口](#api-接口)
- [数据布局](#数据布局)
- [MinerU 开源协议与归属](#mineru-开源协议与归属)
- [License](#license)

---

## 它能做什么

1. **文献资产库**：上传 PDF/DOCX/PPTX/XLSX/图片 → MinerU 转 Markdown → 清理为 `data/papers/<paper_id>/paper.md + images/`，丢弃所有 json/layout 中间文件。
2. **AI 摘要目录**：`literature_catalog.json` 是"文献级索引"（非段落级），每篇含 `ai_summary`（问题/方法/发现/局限/与本工作关系）、`tags`、`selection_hints`、`citation`（bib_key/bibtex）。大模型据此判断该读哪些全文。
3. **按需全文阅读**：三个核心 prompt——单篇目录条目补全、目录规划阅读、基于全文写作。只生成 prompt，不调 LLM。
4. **博士论文级综述写作**：严格多阶段工作区，输出独立可编译、可整体挪走的 LaTeX 项目。

## 核心设计

- **PDF 只放 `data/raw/`**；AI 可读材料只放 `data/papers/<paper_id>/paper.md + images/`。
- **MinerU 的 json/layout/中间文件不进入长期知识库**。
- **不再 chunk / embedding / ChromaDB**。
- **`literature_catalog.json` 是"文献级索引"，不是"段落级索引"**：目录只负责判断该不该读全文，不能替代全文证据。
- **manifest 管文件状态，catalog 管文献理解，两者分离**。
- **所有 prompt 都只生成，不内置 LLM client**。
- 写作工作流三个硬区分：`prompt_generated ≠ content_filled`、`candidates ≠ selected_papers`、`template_generated ≠ content_filled`。

## 项目结构

```
mineru/
├── app.py                  # Gradio 前端 (端口 7860)
├── batch_convert.py        # 批量转换 raw → papers（可走 8000 加速）
├── watcher.py              # 轮询 data/raw/ 自动转换+入库
├── start.bat               # 一键启动 mineru-api(8000) + watcher + 服务(8080)
├── requirements.txt
├── config/
│   ├── settings.py         # 全部配置（导入即建数据目录）
│   └── paper_ids.py        # raw → paper_id 映射
├── src/
│   ├── converter.py        # MinerU CLI 包装
│   ├── cleaner.py          # 清理 MinerU 输出为 paper.md + images
│   ├── manifest.py         # papers_manifest.json 文件账本
│   ├── library.py          # 按 paper_id 读全文 md/images
│   ├── catalog.py          # literature_catalog.json 加载/校验/查询
│   ├── bib.py              # 全局 references.bib 解析
│   ├── prompt_builder.py   # catalog-entry/plan-reading/fulltext/bib-entry prompt
│   ├── naming.py           # paper_id 命名
│   ├── server.py           # FastAPI 服务 (端口 8080) + Web UI
│   └── writer/             # 综述写作 skill 核心
│       ├── job_manager.py      # 写作任务目录 + run_meta 状态机
│       ├── topic_parser.py     # 研究内容归一化
│       ├── catalog_matcher.py  # 目录匹配（candidates ≠ selected）
│       ├── deep_reader.py      # 全文精读笔记模板
│       ├── story_builder.py    # 科研故事线
│       ├── tex_project.py      # LaTeX 项目生成（覆盖保护）
│       ├── figure_manager.py   # 图片复制 + 图源追踪
│       └── bib_manager.py      # 任务级 BibTeX + citation 校验
├── skills/
│   └── literature_review_writer/  # 综述写作 skill（CLAUDE.md/README/templates）
├── web/
│   └── index.html          # 文献库 Web UI
├── scripts/
│   ├── rebuild_library.py     # 从 raw 重建 papers
│   ├── validate_catalog.py    # 校验 catalog 结构
│   ├── sync_bib_from_catalog.py  # catalog → references.bib 原子同步
│   ├── validate_bib.py        # 校验 citation 一致性
│   ├── export_job_bib.py      # 抽取 job 所需 BibTeX
│   ├── write_review.py        # 综述写作 CLI
│   └── validate_write_job.py  # 校验写作任务产物
└── data/
    ├── raw/                # PDF 原文（版权语料，不入库）
    ├── papers/<paper_id>/  # 清理后的 AI 可读资产
    ├── catalog/            # literature_catalog.json + references.bib
    └── manifests/          # papers_manifest.json
```

> 仓库不含 `data/raw/` 与 `data/papers/` 的内容（版权语料，见 `.gitignore`），仅保留目录占位。克隆后需自行投放 PDF 并运行转换。

## 环境要求

- **OS**：Windows（用 `mineru.exe`、`.bat` 编排、硬编码路径）。理论可移植，但未在 Linux/macOS 测试。
- **Conda 环境**：`mineru`（Python 3.10）。
- **CUDA**：`hybrid-engine`/`vlm-engine` 后端（lmdeploy）需要 CUDA 12.6 在 PATH 上。
- **MinerU**：3.4（`mineru[all]>=3.4.0`）。

依赖见 [requirements.txt](requirements.txt)（已移除 `chromadb` / `sentence-transformers`）。

## 快速开始

```bash
# 1. 创建 conda 环境并安装依赖
conda create -n mineru python=3.10 -y
conda activate mineru
pip install -r requirements.txt

# 2. 设置 CUDA 路径（GPU 后端需要）
set CUDA_PATH=C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.6
set PATH=%CUDA_PATH%\bin;%PATH%

# 3. 一键启动（mineru-api 8000 + watcher + 文献库服务 8080）
start.bat
# 或单独启动文献库服务：
python -m src.server
# 浏览器访问 http://localhost:8080

# 4. 投放文献：把 PDF 放进 data/raw/，watcher 会自动转换+入库
#    或通过 Web UI / curl 上传：
curl -F "file=@paper.pdf" http://localhost:8080/upload
```

服务端口（7890 是代理，勿用）：

| 服务 | 端口 | 用途 |
|------|------|------|
| mineru-api | 8000 | MinerU 解析模型常驻 GPU（可选，加速） |
| 文献库服务 (FastAPI + Web UI) | 8080 | API + Web UI；Swagger 在 `/docs` |
| Gradio UI | 7860 | 可选前端 |

## 综述写作工作流

严格多阶段状态机：每步设状态位，前置未完成则下一步报错；生成 prompt/模板不算完成，须 `mark-*` 校验非模板后才标记 filled；`validate` 通过才标记任务完成。

```
create → match → confirm-papers → deep-read → mark-deep-read
        → story → mark-story → tex → mark-tex → copy-figures → validate
```

```bash
python scripts/write_review.py create         --topic "风吹雪升华参数化的发展脉络"
python scripts/write_review.py match          --job 001_风吹雪升华参数化
# 跑 logs/prompts/01_catalog_matching_prompt.md，确认文献
python scripts/write_review.py confirm-papers --job 001_风吹雪升华参数化 \
    --papers 1999_dery_吹雪体相模型 2025_huang_雪粒破碎促进升华
python scripts/write_review.py deep-read      --job 001_风吹雪升华参数化
# 跑 02_deep_reading_prompt.md，填 paper_notes/evidence_table
python scripts/write_review.py mark-deep-read --job 001_风吹雪升华参数化
python scripts/write_review.py story          --job 001_风吹雪升华参数化
# 跑 03_storyline_prompt.md，填 story_plan
python scripts/write_review.py mark-story     --job 001_风吹雪升华参数化
python scripts/write_review.py tex            --job 001_风吹雪升华参数化
# 跑 04_tex_writing_prompt.md，填 introduction/method（删 TEMPLATE_ONLY）
python scripts/write_review.py mark-tex       --job 001_风吹雪升华参数化
python scripts/write_review.py copy-figures   --job 001_风吹雪升华参数化 \
    --figures 1999_dery_吹雪体相模型:某图.jpg
python scripts/write_review.py validate       --job 001_风吹雪升华参数化
```

每个任务输出到 `write/00N_<topic_slug>/`，含 `input/`、`planning/`、`reading/`、`tex/`、`figures/`、`logs/`。TeX 项目自包含、可整体挪走（`references.bib` 是任务专属副本，图片复制到 `figures/` 并记原路径，`validate` 含可移植性校验）。

详细规则与状态位含义见 [skills/literature_review_writer/CLAUDE.md](skills/literature_review_writer/CLAUDE.md)。

## API 接口

FastAPI 服务（端口 8080），Swagger 文档在 `http://localhost:8080/docs`。主要接口：

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/upload` | 上传 → MinerU 转 → 清理 → 入库 |
| GET | `/papers` | 列出已转换文献 |
| GET | `/papers/{paper_id}/markdown` | 读取全文 Markdown |
| GET | `/papers/{paper_id}/images/{img}` | 返回单张图片 |
| GET/POST | `/catalog`、`/catalog/validate`、`/catalog/unsummarized` | 文献目录 |
| POST | `/prompt/catalog-entry`、`/prompt/plan-reading`、`/prompt/read-fulltext`、`/prompt/bib-entry` | 生成 prompt（不调 LLM）|
| POST | `/write/jobs` 及 `/write/jobs/{job_id}/*` | 综述写作全流程（match/confirm-papers/deep-read/mark-*/build-story/build-tex/copy-figures/validate）|

所有 `/prompt/*` 与 `/write/jobs/*` **不调用 LLM**，只生成 prompt 文本与结构化模板；`mark-*`/`validate` 只做内容校验。CLI（`scripts/write_review.py`）与 API 行为一致。

## 数据布局

- `data/raw/` — PDF 原文（投放/上传目标；版权语料，不入 git）。
- `data/papers/<paper_id>/` — 清理后的 AI 可读资产：`paper.md` + `images/`。
- `data/catalog/literature_catalog.json` — AI 维护的文献理解目录。
- `data/catalog/references.bib` — 全库 BibTeX 汇总（由 catalog 同步生成）。
- `data/manifests/papers_manifest.json` — 系统维护的文件账本。
- `write/<job_id>/` — 综述写作任务输出（按需创建）。

## MinerU 开源协议与归属

本项目依赖 [MinerU](https://github.com/opendatalab/MinerU)（© OpenDataLab）作为 PDF/文档解析引擎。

MinerU 采用 **MinerU Open Source License**（基于 Apache License 2.0，并附加条款；自 v3.1.0 起由 AGPLv3 切换而来）。其主要义务摘录如下（**以 MinerU 仓库 [LICENSE.md](https://github.com/opendatalab/MinerU/blob/master/LICENSE.md) 原文为准**）：

- **商用门槛**：商业使用在门槛内无需单独许可；但若你及关联方合并后 **月活（MAU）超过 1 亿** 或 **月营收超过 2000 万美元**，需向 MinerU Team 另取商业许可。
- **在线服务归属**：若你基于 MinerU 向第三方提供在线服务，须在产品界面或公开文档中**显著标注使用了 MinerU**。
- **违约自动终止**：未取得所需商业许可或未履行归属义务，本许可及全部授予的权利自动终止。

> 本项目将 MinerU 作为**本地依赖**调用其 CLI（`mineru` / `mineru-api`）做文档解析，不修改 MinerU 源码、不分发 MinerU 本体。如你基于本项目提供对外在线服务，请务必在前端或文档中显著标注「文档解析由 [MinerU](https://github.com/opendatalab/MinerU) 提供」并确认自身 MAU/营收是否触及商用门槛。完整条款以 MinerU 官方 LICENSE.md 为准。

## License

本仓库自身的代码与文档（即 `src/`、`scripts/`、`config/`、`web/`、`skills/`、`app.py`、`watcher.py`、`batch_convert.py` 等，**不含** MinerU 本体及其依赖）采用 **MIT License**，见 [LICENSE](LICENSE)。

- `data/raw/` 与 `data/papers/` 中的文献 PDF 及其派生内容受各自原版权所有，**不在本仓库开源范围内**，仅本地使用，不随 git 分发。
- 文档解析引擎 MinerU 遵循其自身的 MinerU Open Source License，详见上一节。
