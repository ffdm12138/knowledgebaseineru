# MinerU 文献资产库 + 博士论文级综述写作 Skill

一个本地 **文献资产库 + AI 摘要目录 + 按需全文阅读 + 博士论文级写作工作区**，基于 [MinerU 3.4](https://github.com/opendatalab/MinerU) 构建。

把 PDF/DOCX/PPTX/XLSX/图片用 MinerU 转成 Markdown，清理后只保留 `paper.md + images/` 作为 AI 可读资产；再用一个结构化目录 `literature_catalog.json` 让大模型"像导师一样"先规划该读哪些全文，最后按需读取全文 Markdown、组装可编译的独立 LaTeX 写作项目。

> **本项目不做向量检索 / RAG / 语义搜索**。重构时已删除 ChromaDB、embedding、chunker、indexer、retriever。所有 `/prompt/*` 与写作流程各步**只生成可复制粘贴的 prompt 与结构化模板，不调用任何 LLM**——仓库里没有 LLM client。LLM 步骤由用户手动跑大模型后回填对应文件。

> **⚠️ 核心契约**：本项目有一组不可删除、不可弱化的设计原则（不允许 RAG/embedding/LLM client/Sci-Hub 等），详见 **[`docs/PROJECT_CONTRACT.md`](docs/PROJECT_CONTRACT.md)**。代码代理（Codex / Claude Code）修改本仓库前必须先读该文件。

---

## 目录

- [它能做什么](#它能做什么)
- [核心设计](#核心设计)
- [三层文献库架构](#三层文献库架构)
- [项目结构](#项目结构)
- [环境要求](#环境要求)
- [快速开始](#快速开始)
- [综述写作工作流](#综述写作工作流)
- [多领域 compact 选文](#多领域-compact-选文)
- [DOI discovery 与 OA PDF 获取](#doi-discovery-与-oa-pdf-获取)
- [pending PDF 人工确认入库](#pending-pdf-人工确认入库)
- [API 接口](#api-接口)
- [数据布局](#数据布局)
- [MinerU 开源协议与归属](#mineru-开源协议与归属)
- [License](#license)

---

## 它能做什么

1. **文献资产库**：PDF/DOCX/PPTX/XLSX/图片 → MinerU 转 Markdown → 清理为 `data/papers/<paper_id>/paper.md + images/`，丢弃所有 json/layout 中间文件。正式新增文献推荐 `register_manual_pdf.py` → `import_pending_pdf.py --apply`。
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

## 三层文献库架构

文献库分三层，职责严格分离：

### A. Canonical storage layer（唯一物理存储层）

唯一事实源：

- `data/raw/` — PDF 原文
- `data/papers/<paper_id>/paper.md` + `images/`
- `data/manifests/papers_manifest.json`
- `data/catalog/library_index.json`

规则：每篇文献只能有一个 canonical `paper_id`；同一 DOI / 同一 sha256 / 同一 paper_id 不能产生多个 canonical 记录。所有全文与图片读取必须通过 `library_index.json` / `PaperLibrary` 解析路径，禁止硬编码 `data/papers/<paper_id>/paper.md`。

### B. Global semantic catalog（全局文献理解目录）

`data/catalog/literature_catalog.json`：每篇 canonical paper 一条，管理 `ai_summary` / `tags` / `selection_hints` / `citation` / `primary_domain` / `domains`。是“文献理解事实源”，不在全局层重复同一篇文献。

### C. Domain catalog view layer（领域视图索引层）

`data/catalog/domains/<domain_id>/literature_catalog.json` + `references.bib`：是“视图”，不是唯一事实源。**同一篇文献允许出现在多个领域 catalog 中**（跨领域重复索引合法）；同一领域 catalog 内部不应重复同一 paper_id。每个领域条目带 `domain_view`（`domain_id` / `is_primary_domain` / `canonical_paper_id`）指明它只是视图而非新实体。同一篇 paper 出现在多个 domain `references.bib` 中也合法。

`primary_domain` 决定主领域，`domains` 决定所有领域视图 membership。领域 catalog 收录所有 `domains` 中声明该领域的文献，而不只是 primary domain。

## 项目结构

```
mineru/
├── app.py                  # Gradio 前端 (端口 7860)
├── batch_convert.py        # 批量转换 raw → papers（CLI runner）
├── watcher.py              # 轮询 data/raw/ 自动转换（产物为 unregistered_converted，不直接入库）
├── start.bat               # 一键启动 Web 服务(8080)，默认不启动 watcher
├── start_fast_api_mode.bat # 加速模式：mineru-api 常驻 + cli_api_proxy runner
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
│   ├── migrate_to_domain_library.py  # 重建 library_index + 领域 catalog（--apply）
│   ├── validate_domain_library.py    # 校验领域库（允许跨领域重复、禁止物理重复）
│   ├── compact_domain_catalog.py     # 多领域 catalog compact 去重
│   ├── discover_papers.py     # 关键词 → DOI 候选
│   ├── fetch_oa_pdf.py        # DOI → OA PDF（pending 下载）
│   ├── import_pending_pdf.py  # pending PDF 人工确认入库（dry-run / --apply）
│   ├── list_pending_pdfs.py   # 列出待入库 PDF
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

### 命令语义速查

| 命令 | 用途 | 产物 | 推荐场景 |
|------|------|------|---------|
| `register_manual_pdf.py` | 单个外部 PDF → pending | pending PDF + sidecar | 日常单篇手动导入 |
| `bulk_register_manual_pdfs.py` | 外部文件夹批量 → pending | 多个 pending PDF + sidecar | 批量导入几十个 PDF |
| `import_pending_pdf.py --apply` | 单个 pending → 正式入库 | converted（manifest/catalog/index/domain/bib） | 所有正式入库必经 |
| `fetch_pdf.py` | DOI → 下载到 pending | pending PDF + sidecar | OA DOI 获取 |
| `fetch_pdf_batch.py` | 批量 DOI → pending | 多个 pending PDF + sidecar | 批量 DOI 获取 |
| `batch_convert.py` | 批量转换 raw 目录 | **unregistered_converted** | legacy/临时批量转换，非正式入库 |
| `watcher.py` | 轮询 data/raw 自动转换 | **unregistered_converted** | 先批量转了再说，不推荐用于文献整理 |
| `rebuild_library.py` | legacy repair | converted | 修复/重建，非日常入库 |

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

# 3. 一键启动 Web 服务（默认不启动 watcher）
start.bat
# start.bat 默认 START_WATCHER=0，只启动 Web 服务(8080)。
# 需要 watcher 时：set START_WATCHER=1 && start.bat
# watcher 自动转换产物为 unregistered_converted，不会直接进入正式 catalog。
# 日常新增 PDF 建议走 register_manual_pdf → import_pending_pdf --apply 正式入库。

# 3a. 加速模式（需 mineru-api 常驻服务）
start_fast_api_mode.bat
# 启动 mineru-api + Web 服务，使用 cli_api_proxy runner 避免每篇冷启动

# 4. Web 上传是临时转换入口；缺少 metadata 时产物为 unregistered_converted
# 日常正式新增本地 PDF 推荐 register_manual_pdf → import_pending_pdf
curl -F "file=@paper.pdf" http://localhost:8080/upload
```

服务端口（7890 是代理，勿用）：

| 服务 | 端口 | 用途 |
|------|------|------|
| 文献库服务 (FastAPI + Web UI) | 8080 | API + Web UI；Swagger 在 `/docs` |
| Gradio UI | 7860 | 可选前端 |

运行时状态看 `http://localhost:8080/status/runtime`。

**Runner 选择：**

| Runner | 说明 | 速度 |
|--------|------|------|
| `cli` | 纯 MinerU CLI，每篇冷启动 | 基准（82KB PDF ~63s） |
| `cli_api_proxy` | CLI + `--api-url`，复用常驻 mineru-api | **~3.2x 加速** (~20s) |
| `api` | HTTP upload adapter | 未实现，明确报错 |

加速使用：
```bash
# 终端1：启动 mineru-api
mineru-api --port 8000 --enable-vlm-preload true
# 终端2：转换
set MINERU_RUNNER=cli_api_proxy
set MINERU_API_URL=http://127.0.0.1:8000
python batch_convert.py data/raw
# 或一键：start_fast_api_mode.bat
```

### 转换性能诊断

```bash
# 单 PDF 基准测试（不修改文献库，含 GPU 检查）
python scripts/benchmark_mineru.py "E:\papers_to_import\test.pdf" --repeat 2

# 进程和锁状态
python scripts/check_mineru_processes.py

# 实时观察 GPU
nvidia-smi -l 1
```

详见 [`docs/MINERU_PERFORMANCE_PLAN.md`](docs/MINERU_PERFORMANCE_PLAN.md)。

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
| POST | `/upload` | 上传 → MinerU 转 → 清理；缺 metadata 时为 unregistered_converted，非推荐正式入库入口 |
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
- `data/catalog/library_index.json` — 全局路径/领域注册表，运行时代码优先从这里解析 `markdown_path` 和 `images_dir`。
- `data/catalog/domains/<domain_id>/` — 领域视图目录，包含该领域的 `literature_catalog.json` 与 `references.bib`。
- `data/catalog/references.bib` — 全库 BibTeX 汇总（由 catalog 同步生成）。
- `data/manifests/papers_manifest.json` — 系统维护的文件账本。
- `write/<job_id>/` — 综述写作任务输出（按需创建）。

当前领域化文献库是三层结构（详见 [三层文献库架构](#三层文献库架构)）：

- `literature_catalog.json` 是全局 AI 文献理解目录，负责摘要、标签、引用和选文提示（每篇 canonical paper 一条）。
- `library_index.json` 是全局路径/领域注册表，是 paper 物理存储唯一事实源。
- `data/catalog/domains/<domain_id>/` 是领域视图层，同一篇文献可跨领域重复索引。
- `data/discovery/doi_candidates/` 保存关键词检索得到的 DOI 候选 JSONL 与 summary。
- `data/raw/<domain_id>/pending/` 保存人工待确认的开放获取 PDF 下载结果与 sidecar JSON。

领域注册表来自 [`config/domains.json`](config/domains.json)。新增领域时先在该文件加入 `title` 和 `description`；代码中的 `VALID_DOMAINS`、`DOMAIN_LABELS`、`DOMAIN_REGISTRY` 会从配置派生，旧三个领域保持兼容。

第一阶段只做逻辑拆分，不移动 `data/papers/<paper_id>/`。以后如需物理迁移 papers，必须先更新 `library_index.json`，并通过 `PaperLibrary`/`LibraryIndex` 解析路径；不要再硬编码 `data/papers/<paper_id>/paper.md`。

## 多领域 compact 选文

同一篇文献可跨领域重复索引。多领域选文进入写作前必须 compact / dedupe，避免一篇文献被当成多条候选。

```bash
# 合并两个领域 catalog 并去重，输出 JSON + 打印统计
python scripts/compact_domain_catalog.py \
    --domains blowing_snow_physics aeolian_snow_transport \
    --output data/discovery/queries/compact_blowing_snow_aeolian.json
```

写作流程也支持按领域选文（CLI 与 API 一致）。指定 `--domains` 时会加载这些领域 catalog、compact 去重后再匹配，候选保留 `source_domains` 标记：

```bash
python scripts/write_review.py match --job 001_xxx \
    --domains blowing_snow_physics aeolian_snow_transport
```

```bash
# API
curl -X POST http://localhost:8080/write/jobs/001_xxx/match-catalog \
    -H "Content-Type: application/json" \
    -d '{"domain_ids": ["blowing_snow_physics", "aeolian_snow_transport"]}'
```

不传 `--domains` / `domain_ids` 时保持旧行为：使用全局 catalog。

## DOI discovery 与 PDF 获取

多阶段管线：关键词 → DOI 候选 → access policy → resolver chain → pending PDF。默认 `oa_only` 模式使用 OpenAlex、Semantic Scholar、Crossref、Unpaywall、arXiv 与 publisher OA 直链；非 OA 渠道须通过 `--access-mode` 显式启用。所有结果默认进入 `data/raw/<domain>/pending/`，不会自动写入 catalog、manifest 或触发 MinerU 转换。详情见 [`docs/PROJECT_CONTRACT.md`](docs/PROJECT_CONTRACT.md)。

```bash
python scripts/discover_papers.py "风吹雪 升华 破碎" \
    --domain blowing_snow_physics --max-candidates 30

python scripts/fetch_pdf.py 10.xxxx/yyyy --domain blowing_snow_physics
python scripts/import_pending_pdf.py data/raw/blowing_snow_physics/pending/10_xxxx_yyyy.pdf \
    --domain blowing_snow_physics --title "..." --doi "10.xxxx/yyyy" --year 2025 --apply
```

可选环境变量：`OPENALEX_EMAIL`、`OPENALEX_API_KEY`、`SEMANTIC_SCHOLAR_API_KEY`、`UNPAYWALL_EMAIL`。网络/API 错误会记录 warning 并返回空候选或失败结果，不应中断本地文献库校验。

## pending PDF 人工确认入库

第二阶段只做到 DOI 候选与 OA PDF pending 下载。第三阶段实现 pending PDF 的人工确认入库闭环：pending PDF → 本地查重 → MinerU 转换 → 正式入库。入库后自动更新 manifest / library_index / 全局 catalog placeholder / 领域 catalog / references.bib，但**不自动生成 AI summary**，只生成待补全 catalog 条目并提示用 `/prompt/catalog-entry` 补全。

入库前必须查重：重复 DOI 或重复 sha256 **只更新 domains membership，不新建 paper、不重新转换**；title 相似 + year 接近的疑似重复需用户确认。查重完全本地，不联网。

```bash
# 列出待入库 PDF
python scripts/list_pending_pdfs.py

# 本地 PDF：先登记为 pending，再人工确认入库
python scripts/register_manual_pdf.py paper.pdf --domain blowing_snow_physics \
    --title "..." --doi "10.xxxx/yyyy" --year 2024
python scripts/import_pending_pdf.py data/raw/blowing_snow_physics/pending/paper.pdf \
    --domain blowing_snow_physics --apply

# dry-run（默认，不写入）
python scripts/import_pending_pdf.py \
    data/raw/blowing_snow_physics/pending/10_xxxx_yyyy.pdf \
    --domain blowing_snow_physics \
    --domains blowing_snow_physics aeolian_snow_transport \
    --title "..." --doi "10.xxxx/yyyy" --year 2025

# 确认后实际入库
python scripts/import_pending_pdf.py ... --apply
```

sidecar JSON 状态机：`pending` → `imported`（新入库）/ `duplicate`（已存在，仅更新 domains）/ `failed`。

不要直接把新 PDF 扔进 `data/raw/` 根目录当正式入库；新文件应进入 `data/raw/_inbox/pending/` 或 `data/raw/<domain>/pending/`，正式入库必须经过 duplicate detection。

> **watcher 自动转换说明**：`start.bat` 默认只启动 Web 服务，不启动 watcher（`START_WATCHER=0`）。只有设置 `START_WATCHER=1` 或直接运行 `python watcher.py` 时，watcher 才会扫描 `data/raw/` 根目录并自动转换。这些自动转换的产物是 **unregistered_converted**（manifest 有记录但无 catalog 条目），不会直接进入正式 catalog / library_index / domain catalog / BibTeX。日常正式入库推荐 `register_manual_pdf.py` → `import_pending_pdf.py --apply`。

> **完整验收命令与禁止事项**参见 **[`docs/PROJECT_CONTRACT.md`](docs/PROJECT_CONTRACT.md)**。

## MinerU 开源协议与归属

本项目依赖 [MinerU](https://github.com/opendatalab/MinerU)（© OpenDataLab）作为 PDF/文档解析引擎。

MinerU 采用 **MinerU Open Source License**（基于 Apache License 2.0，并附加条款；自 v3.1.0 起由 AGPLv3 切换而来）。其主要义务摘录如下（**以 MinerU 仓库 [LICENSE.md](https://github.com/opendatalab/MinerU/blob/master/LICENSE.md) 原文为准**）：

- **商用门槛**：商业使用在门槛内无需单独许可；但若你及关联方合并后 **月活（MAU）超过 1 亿** 或 **月营收超过 2000 万美元**，需向 MinerU Team 另取商业许可。
- **在线服务归属**：若你基于 MinerU 向第三方提供在线服务，须在产品界面或公开文档中**显著标注使用了 MinerU**。
- **违约自动终止**：未取得所需商业许可或未履行归属义务，本许可及全部授予的权利自动终止。

> 本项目将 MinerU 作为**本地依赖**调用其 CLI（`mineru` / `mineru-api`）做文档解析，不修改 MinerU 源码、不分发 MinerU 本体。如你基于本项目提供对外在线服务，请务必在前端或文档中显著标注「文档解析由 [MinerU](https://github.com/opendatalab/MinerU) 提供」并确认自身 MAU/营收是否触及商用门槛。完整条款以 MinerU 官方 LICENSE.md 为准。

## 已使用的开源项目

本项目直接依赖以下开源项目：

| 项目 | 用途 | 许可 |
|------|------|------|
| [MinerU](https://github.com/opendatalab/MinerU) | PDF/DOCX 文档解析引擎 | MinerU Open Source License（基于 Apache 2.0） |
| [requests](https://github.com/psf/requests) | HTTP 库（API + PDF 下载） | Apache 2.0 |
| [fastapi](https://github.com/fastapi/fastapi) | Web API 框架 | MIT |
| [uvicorn](https://github.com/encode/uvicorn) | ASGI 服务器 | BSD-3 |
| [pydantic](https://github.com/pydantic/pydantic) | 数据模型验证 | MIT |
| [gradio](https://github.com/gradio-app/gradio) | Web UI | Apache 2.0 |
| [PyMuPDF](https://github.com/pymupdf/PyMuPDF) | PDF 操作 | AGPL v3 |
| [filelock](https://github.com/tox-dev/py-filelock) | JSON 写入原子锁 | Unlicense |
| [loguru](https://github.com/Delgan/loguru) | 日志 | MIT |
| [pytest](https://github.com/pytest-dev/pytest) | 测试框架 | MIT |

间接引用（子进程调用或借鉴架构，不直接依赖）：

| 项目 | 用途 | 许可 |
|------|------|------|
| [ref-downloader](https://github.com/nicolay-r/ref-downloader) | 机构权限 PDF 下载 | Apache 2.0 |
| [auto-paper-harvester](https://github.com/LuisDGM/auto-paper-harvester) | 借鉴三层降级架构 | MIT |
| [paperdl](https://github.com/stephanlazar/paperdl) | 借鉴多平台预印本查询 | MIT |

## License

本仓库自身的代码与文档（即 `src/`、`scripts/`、`config/`、`web/`、`skills/`、`app.py`、`watcher.py`、`batch_convert.py` 等，**不含** MinerU 本体及其依赖）采用 **MIT License**，见 [LICENSE](LICENSE)。

- `data/raw/` 与 `data/papers/` 中的文献 PDF 及其派生内容受各自原版权所有，**不在本仓库开源范围内**，仅本地使用，不随 git 分发。
- 文档解析引擎 MinerU 遵循其自身的 MinerU Open Source License，详见上一节。
