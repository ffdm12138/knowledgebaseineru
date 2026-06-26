# CLAUDE.md

Claude Code 在本仓库工作的指南。

## 这是什么

一个本地 **文献资产库 + AI 摘要目录 + 按需全文阅读** 系统，基于 [MinerU 3.4](https://github.com/opendatalab/MinerU)。把 PDF/DOCX/PPTX/XLSX/图片用 MinerU 转成 Markdown，清理后只保留 `paper.md + images/` 作为 AI 可读资产；再用一个结构化目录 `literature_catalog.json` 让大模型"像导师一样"先规划该读哪些全文，再按需读取全文 Markdown 进行综述/写作。

> **重要**：本项目**不做向量检索 / RAG / 语义搜索**。重构时已删除 ChromaDB、chunker、indexer、retriever、embedding 模型。所有 `/prompt/*` 接口**只生成可复制粘贴的 prompt，不调用任何 LLM**——仓库里没有任何 LLM client。`data/raw/` 中的语料是雪科学 / 风吹雪文献，但代码与领域无关。

## 设计原则

1. PDF 只放 `data/raw/`。
2. AI 可读材料只放 `data/papers/<paper_id>/paper.md + images/`。
3. MinerU 的 json / layout / 中间文件**不进入**长期知识库。
4. 不再 chunk、不再 embedding、不再 ChromaDB。
5. `literature_catalog.json` 是"文献级索引"，不是"段落级索引"。
6. 目录只负责判断该不该读全文，不能替代全文证据。
7. `manifest` 管文件状态，`catalog` 管文献理解，两者分离。
8. 所有 prompt 都只生成，不内置 LLM client。

## 项目结构

```
mineru/
├── app.py                  # Gradio 前端 (端口 7860)，文献库面板
├── batch_convert.py        # 批量转换 raw → papers（可走 8000 加速）
├── watcher.py              # 轮询 data/raw/ 自动转换+入库
├── start.bat               # 一键启动 mineru-api(8000) + watcher + 服务(8080)
├── requirements.txt        # 依赖清单
├── config/
│   ├── settings.py         # 全部配置项（导入即建数据目录，有副作用）
│   └── paper_ids.py        # 现有 13 篇 raw → paper_id 固定映射
├── src/
│   ├── converter.py        # MinerUConverter：调用 mineru CLI 子进程，输出到 tmp
│   ├── cleaner.py          # MinerUOutputCleaner：清理 MinerU 输出为 paper.md + images
│   ├── manifest.py         # PaperManifest：维护 papers_manifest.json 文件账本
│   ├── library.py          # PaperLibrary：按 paper_id 读全文 md/images
│   ├── catalog.py          # Catalog：加载/校验/查询 literature_catalog.json
│   ├── bib.py              # 全局 BibTeX：references.bib 同步/解析/校验
│   ├── prompt_builder.py   # PromptBuilder：catalog-entry/plan-reading/fulltext/bib-entry prompt
│   ├── naming.py           # paper_id 命名工具
│   ├── server.py           # FastAPI 服务 (端口 8080) + 提供 web UI
│   └── writer/             # 综述写作 skill 核心
│       ├── job_manager.py      # 写作任务目录（write/00N_<slug>/）
│       ├── topic_parser.py     # 研究内容归一化 → normalized_task.md
│       ├── catalog_matcher.py  # 目录匹配 → 候选文献 + prompt
│       ├── deep_reader.py      # 全文精读 → paper_notes/evidence_table/figure_candidates
│       ├── story_builder.py    # 故事线 → story_plan/chapter_outline
│       ├── tex_project.py      # LaTeX 项目 → main/intro/method + references.bib
│       ├── figure_manager.py   # 图片复制 + 图源 README
│       └── bib_manager.py      # 任务级 BibTeX 抽取 + \cite 一致性校验
├── skills/
│   └── literature_review_writer/  # 综述写作 skill（CLAUDE.md/README/templates）
├── write/                 # 写作任务输出根目录（按需创建，00N_<slug>/）
├── web/
│   └── index.html          # 文献库 Web UI（上传/列表/全文/Prompt 生成）
├── scripts/
│   ├── rebuild_library.py     # 从 data/raw/ 重建 data/papers/
│   ├── validate_catalog.py    # 校验 literature_catalog.json 结构
│   ├── sync_bib_from_catalog.py  # catalog → references.bib 同步
│   ├── validate_bib.py        # 校验 citation 与 references.bib 一致性
│   ├── export_job_bib.py      # 抽取 job 所需 BibTeX
│   ├── write_review.py        # 综述写作 CLI（create/match/deep-read/story/tex/figures/validate）
│   └── validate_write_job.py  # 校验写作任务产物完整性
├── data/
│   ├── raw/                # PDF 原文（投放/上传目标，当前 15 篇）
│   ├── papers/<paper_id>/  # 清理后的 AI 可读资产：paper.md + images/
│   ├── catalog/            # AI 维护的文献理解目录
│   │   ├── literature_catalog.json  # 总目录（13 篇已补全，含 citation/bib_key/bibtex）
│   │   ├── references.bib  # 全库 BibTeX 汇总（由 catalog 同步生成）
│   │   └── CLAUDE.md       # 规定目录怎么写
│   ├── manifests/          # 系统维护的文件账本 papers_manifest.json
│   ├── tmp/mineru_raw_output/  # MinerU 原始输出临时目录，处理完可清空
│   └── (vectordb/ chunks/ parsed/ 已删除)
├── md/                     # 文档（中文部署指南）
```

## 现状

- **MinerU 版本**：3.4。依赖 `mineru[all]>=3.4.0`、`fastapi`、`uvicorn`、`gradio`、`loguru`、`pydantic`、`PyMuPDF`（已移除 `chromadb` / `sentence-transformers`）。
- **语料库**：`data/raw/` 共 13 篇 PDF（重复上传的 2 篇已删，与 `data/papers/` 一一对应），已全部转换清理入 `data/papers/`。领域为雪科学/风吹雪（升华率、粒径分布、破碎、起动、跃移悬移、CryoWRF、drag model 等），代码与领域无关。
- **paper_id**：现有 13 篇用 `config/paper_ids.py` 固定映射，格式 `年份_首位作者_中文标题`（如 `1999_dery_吹雪体相模型`）。新上传文件由 `derive_paper_id()` 从文件名自动推导，规范命名（年份_作者_标题）由 AI 在补全 catalog 条目时建议、用户确认后可手动改名。
- **文献资产**：`data/papers/` 下 13 个 `<paper_id>/` 目录，各含 `paper.md` + `images/`，共约 76 万字符、544 张图。图片引用统一为 `![](images/xxx)` 相对路径。
- **文献目录**：`literature_catalog.json` 已补全全部 13 篇条目（`status: summarized`），含 ai_summary/tags/selection_hints/priority + `citation`（bib_key/bibtex），`validate_catalog.py` 与 `validate_bib.py` 均通过。`data/catalog/references.bib` 已由 catalog 同步生成 13 条 BibTeX。`/prompt/plan-reading` 现已可用。`papers_manifest.json` 记录全部 13 篇文件账本。
- **综述写作 skill**：`src/writer/` + `skills/literature_review_writer/` + `scripts/write_review.py` 已实现博士论文级综述写作全流程（建任务→目录匹配→精读→故事线→TeX→图→校验），所有 LLM 步骤只生成 prompt 不内置 LLM。端到端冒烟测试通过（42 个产物文件、`\cite` 一致性校验 valid）。`write/` 按需创建。
- **运行状态**：服务未常驻，按需通过 `start.bat` 或单条命令启动；无 CI、无测试套件，验证靠 UI 或 curl。API 已验证可用（`/papers`、`/prompt/*`、`/catalog/*` 均通）。

## 环境（必读）

- **Conda 环境**：`mineru`（Python 3.10）。所有命令假设 `conda activate mineru`，或直接用环境里的 python：`C:\Users\Admin\.conda\envs\mineru\python.exe`。
- **CUDA 路径**：`C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.6` 必须在 PATH 上，`hybrid-engine`/`vlm-engine` 后端（lmdeploy）需要。`start.bat` 已设置；从非 cmd shell 手动启动时先 export。
- **仅 Windows**：用 `mineru.exe`、`.bat` 编排、硬编码 Windows 路径。平台为 win32。
- **无测试套件**：没有 `tests/` 目录，没有 pytest 配置。验证靠 UI 或 curl。

## 运行服务

三个服务（7890 是**代理**，切勿用于这些服务）：

| 服务 | 端口 | 启动命令 | 用途 |
|------|------|----------|------|
| mineru-api | 8000 | `mineru-api --port 8000 --enable-vlm-preload true` | 把 MinerU 解析模型常驻 GPU（可选，加速转换） |
| watcher | — | `python watcher.py --interval 30` | 轮询 `data/raw/`，自动转换+入库 |
| 文献库服务 (FastAPI + Web UI) | 8080 | `python -m src.server` | API + 提供 `web/index.html`；Swagger 在 `/docs` |
| Gradio UI（可选前端） | 7860 | `python app.py` | 同一套 pipeline 的另一前端 |

- **一键启动**：双击 `start.bat` → 启动 8000 + watcher + 8080。
- **在本 shell 用 bash**（conda 不在 PATH）：`"/c/Users/Admin/.conda/envs/mineru/python.exe" -m src.server`（用 GPU 后端时先 export `CUDA_PATH`）。
- mineru-api (8000) **可选**。宕掉时 watcher/batch_convert 直走 CLI（每文件重新加载模型，较慢）。

## 架构

新流程：**Converter → Cleaner → Manifest → (Catalog / Library / PromptBuilder)**，每个都是普通类，进程启动时实例化一次（[src/server.py](src/server.py) 顶部）。

```
raw PDF → MinerU(tmp) → cleaner → data/papers/<paper_id>/paper.md + images → manifest 记录
                                                                          ↓
                                                  catalog（AI 补全摘要） + library（读全文）
                                                                          ↓
                                                  prompt_builder 生成 prompt（不调 LLM）
```

- [src/converter.py](src/converter.py) — `MinerUConverter`：包装 `mineru` CLI 子进程（`convert`，600s 超时，输出到 `tmp/<paper_id>/<stem>/<method>/<stem>.md`）。从 conda 环境解析 `mineru.exe`。返回 `markdown` + `md_path` + `output_dir`。本身不传 `--api-url`；走 8000 服务用 `batch_convert.py`。
- [src/cleaner.py](src/cleaner.py) — `MinerUOutputCleaner`：递归定位正文 Markdown（取体积最大者，**不**按 token 排除——正文文件名可能含 `model` 等词），复制为 `data/papers/<paper_id>/paper.md`，归一化图片路径为 `images/...`，复制 `images/`，丢弃所有 json/layout/中间文件。幂等（重建时先删后建）。
- [src/manifest.py](src/manifest.py) — `PaperManifest`：读写 `data/manifests/papers_manifest.json`，记录 `paper_id/raw_pdf/markdown/images_dir/status/images_count/md_chars/converted_at`。`upsert` 增量更新。
- [src/library.py](src/library.py) — `PaperLibrary`：按 `paper_id` 读 `paper.md` 全文（可截断）、列 images、批量读多篇。供 prompt_builder 组装。
- [src/catalog.py](src/catalog.py) — `Catalog`：加载/校验/查询 `literature_catalog.json`。`validate()` 检查必填字段、status 合法性、priority 范围、paper_id 唯一性。`unsummarized()` 列出 manifest 有但 catalog 未总结的。`build_compact_catalog()` 生成给大模型看的紧凑目录。
- [src/prompt_builder.py](src/prompt_builder.py) — `PromptBuilder`：三类 prompt——① `build_catalog_entry_prompt`（单篇全文→补全 catalog 条目）；② `build_catalog_planning_prompt`（研究问题→规划该读哪些）；③ `build_fulltext_prompt`（读取指定全文→写作）。**全部只返回文本，不调 LLM**。
- [src/naming.py](src/naming.py) — `derive_paper_id`：从文件名清洗出文件系统安全的 paper_id（保留中文）。
- [config/paper_ids.py](config/paper_ids.py) — 现有 13 篇 raw stem → paper_id 固定映射 + 2 个重复 raw stem（`DUPLICATE_RAW_STEMS`，迁移时跳过）。

两个前端共享同一份磁盘上的 `data/papers/` 与 `data/manifests/`，但跑在各自进程；通过任一前端上传的文献，另一端刷新即可见。

## 配置

全部在 [config/settings.py](config/settings.py)，改这里即全局生效。注意：导入该模块有**副作用**——创建数据目录。

关键值：`API_PORT=8080`、`MINERU_BACKEND="hybrid-engine"`（8GB 显存）、`MINERU_EFFORT="medium"`、`MINERU_METHOD="auto"`、`MINERU_LANG="ch"`、`PAPER_MD_MAX_CHARS=12000`（prompt 中单篇全文截断）、`SUPPORTED_FORMATS={.pdf,.docx,.pptx,.xlsx,.png,.jpg,.jpeg}`。

## 数据布局

- `data/raw/` — PDF 原文（上传/投放目标）。当前 15 篇。
- `data/papers/<paper_id>/` — 清理后的 AI 可读资产：`paper.md` + `images/`。当前 13 篇。
- `data/catalog/literature_catalog.json` — AI 维护的文献理解目录（初始为空）。
- `data/catalog/CLAUDE.md` — 规定 catalog 怎么写（schema、字段含义、写作规则）。
- `data/manifests/papers_manifest.json` — 系统维护的文件账本。
- `data/tmp/mineru_raw_output/` — MinerU 原始输出临时目录，处理完可清空。
- `md/` — 文档（中文部署指南 `MinerU本地部署与知识库搭建指南.md`）。
- （`data/parsed/`、`output/`、`data/vectordb/`、`data/chunks/` 已在重构后删除。）

## API 接口（FastAPI，端口 8080）

所有接口由 [src/server.py](src/server.py) 提供，Swagger 文档在 `http://localhost:8080/docs`。请求/响应均为 JSON。

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/` | 返回 `web/index.html` Web UI |
| POST | `/upload` | 上传 → MinerU 转 tmp → cleaner → papers → manifest。表单字段 `file`；查询参数 `method`/`backend`/`effort` |
| GET | `/papers` | 列出已转换文献及统计 |
| GET | `/papers/{paper_id}` | 单篇文献信息 |
| GET | `/papers/{paper_id}/markdown` | 读取全文 Markdown（纯文本） |
| GET | `/papers/{paper_id}/images` | 列出图片文件名 |
| GET | `/papers/{paper_id}/images/{img_name}` | 返回单张图片文件（前端预览） |
| DELETE | `/papers/{paper_id}` | 删除文献（papers 目录 + manifest + catalog 条目） |
| GET | `/catalog` | 读取 `literature_catalog.json` |
| POST | `/catalog/validate` | 校验目录结构，返回错误列表 |
| GET | `/catalog/unsummarized` | 列出 manifest 有但 catalog 未总结的 paper_id |
| POST | `/prompt/catalog-entry` | 生成单篇目录条目补全 prompt。Body: `{"paper_id"}` |
| POST | `/prompt/plan-reading` | 生成目录规划阅读 prompt。Body: `{"question"}` |
| POST | `/prompt/read-fulltext` | 生成基于全文的写作 prompt。Body: `{"question","paper_ids"}` |
| POST | `/prompt/bib-entry` | 生成单篇 BibTeX 补全 prompt。Body: `{"paper_id"}` |
| POST | `/write/jobs` | 创建写作任务。Body: `{"topic","input_file","language","target"}` |
| GET | `/write/jobs` | 列出所有写作任务 |
| GET | `/write/jobs/{job_id}` | 任务 run_meta |
| GET | `/write/jobs/{job_id}/files` | 列出任务所有文件 |
| POST | `/write/jobs/{job_id}/match-catalog` | 目录匹配 → 候选文献 + prompt（selected 为空）|
| POST | `/write/jobs/{job_id}/confirm-papers` | 确认精读文献。Body: `{"paper_ids","confirmed_by"}` |
| POST | `/write/jobs/{job_id}/deep-read` | 精读 prompt + 笔记模板。Body: `{"paper_ids"?}`（默认取 selected，须 confirmed）|
| POST | `/write/jobs/{job_id}/mark-deep-read` | 校验精读笔记非模板 → deep_read_notes_filled |
| POST | `/write/jobs/{job_id}/build-story` | 故事线 prompt + 模板（须 deep_read_notes_filled）|
| POST | `/write/jobs/{job_id}/mark-story` | 校验 story_plan 非模板 → story_plan_filled |
| POST | `/write/jobs/{job_id}/build-tex` | TeX 模板 + references.bib。Body: `{"title"?,"force"?,"template_only"?}` |
| POST | `/write/jobs/{job_id}/mark-tex` | 校验正文非模板 → tex_content_filled |
| POST | `/write/jobs/{job_id}/copy-figures` | 复制指定图到 figures/。Body: `{"figures"?}` |
| POST | `/write/jobs/{job_id}/validate` | 全量校验 → 通过设 validated |
| GET | `/status` | 系统状态：端口、模式、文献统计、目录条目数 |

所有 `/prompt/*` 与 `/write/jobs/*` **不调用 LLM**，只生成可复制的 prompt 文本与结构化模板文件；`mark-*`/`validate` 只做内容校验。CLI（`scripts/write_review.py`）与 API 行为一致。

## 使用方法

### 启动
```bash
# 一键（推荐）：启动 mineru-api(8000) + watcher + 文献库(8080)
start.bat

# 手动启动文献库服务（bash，conda 不在 PATH）
"/c/Users/Admin/.conda/envs/mineru/python.exe" -m src.server
# 用 GPU 后端时先 export CUDA_PATH=C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.6

# 仅起 Gradio 前端（端口 7860）
"/c/Users/Admin/.conda/envs/mineru/python.exe" app.py

# 仅起 mineru-api 常驻服务（可选，加速转换）
mineru-api --port 8000 --enable-vlm-preload true
```

### 投喂文献
- **Web UI**：浏览器开 `http://localhost:8080`，上传（支持 PDF/DOCX/PPTX/XLSX/图片）。
- **watcher 自动**：把文件丢进 `data/raw/`，`python watcher.py --interval 30`（或 `--once` 单次扫描）会自动转换+清理+入 manifest。
- **批量**：`python batch_convert.py data/raw --api-url http://127.0.0.1:8000`（走 8000 加速）。
- **单文件 CLI**：`mineru -p file.pdf -o data/tmp/mineru_raw_output/<id> -b hybrid-engine --api-url http://127.0.0.1:8000`，再用 `cleaner.extract()` 提取。
- **API 上传**：`curl -F "file=@x.pdf" http://localhost:8080/upload`。
- **从旧版重建**：`python scripts/rebuild_library.py`（优先复用 `data/parsed` 旧输出，免重新转换；`--reconvert` 强制重转）。

### 补全文献目录（核心工作流）
1. 调 `POST /prompt/catalog-entry`（或前端 ① 按钮），传入 `paper_id`，得到"读全文补全 catalog 条目"的 prompt。
2. 把 prompt 粘给大模型，得到一条 JSON 条目。
3. 把条目追加进 `data/catalog/literature_catalog.json` 的 `papers` 数组。
4. `python scripts/validate_catalog.py` 校验（或 `POST /catalog/validate`）。

### 写综述/论文
1. 调 `POST /prompt/plan-reading`（前端 ②），传入研究问题，得到"基于目录规划该读哪些全文"的 prompt。
2. 大模型返回推荐 `paper_id` 列表后，调 `POST /prompt/read-fulltext`（前端 ③），传入问题 + `paper_ids`，得到含若干篇全文的写作 prompt。
3. 把写作 prompt 粘给大模型生成综述。

```bash
# 语义相关查询示例（已无 /search /ask）
curl http://localhost:8080/papers
curl http://localhost:8080/status
curl -X POST http://localhost:8080/prompt/catalog-entry -H "Content-Type: application/json" \
  -d '{"paper_id":"1999_dery_吹雪体相模型"}'
curl -X POST http://localhost:8080/prompt/read-fulltext -H "Content-Type: application/json" \
  -d '{"question":"升华模型脉络","paper_ids":["1999_dery_吹雪体相模型","2025_huang_雪粒破碎促进升华"]}'
```

## 综述写作 Skill

博士论文级综述写作，**严格多阶段工作流**：每步设状态位，前置未完成则下一步报错；生成 prompt/模板不算完成，必须 `mark-*` 校验非模板后才标记 filled；validate 通过才标记完成。规则见 [skills/literature_review_writer/CLAUDE.md](skills/literature_review_writer/CLAUDE.md)。

三个核心区分：
- **prompt_generated ≠ content_filled**：生成 prompt/模板只是开始。
- **candidates ≠ selected_papers**：`catalog_candidates.json` 是候选，`selected_papers.json` 初始为空，须显式 `confirm-papers`。
- **template_generated ≠ content_filled**：TeX 模板生成 ≠ 正文完成。

每个任务输出到 `write/00N_<topic_slug>/`，含 `input/`、`planning/`、`reading/`、`tex/`、`figures/`、`logs/`，TeX 项目独立可编译。

### run_meta 状态位（steps）
```
catalog_match_prompt_generated  catalog_selection_confirmed
deep_read_prompt_generated      deep_read_notes_filled
story_prompt_generated          story_plan_filled
tex_template_generated          tex_content_filled
figures_copied                  bib_exported          validated
```
只有 `mark-*`（校验非模板后）或 `confirm-papers`（显式确认）才设 filled/confirmed；`match`/`deep-read`/`story`/`tex` 只设 prompt_generated/template_generated。

### CLI 工作流
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
CLI 与 `/write/jobs*` API 行为一致。`tex` 默认不覆盖已有正文（`--force` 先备份 `.bak_YYYYMMDD_HHMMSS` 再覆盖）；`--template-only` 跳过前序校验仅生成空模板。

### 前置条件（违反则报错）
- `deep-read` 要求 `catalog_selection_confirmed`
- `story` 要求 `deep_read_notes_filled`
- `tex`（非 template-only）要求 `story_plan_filled`
- `mark-*` 校验对应内容非模板（含 `TEMPLATE_ONLY`/`待填`/`TODO` 标记即拒）
- `validate` 要求全部 filled + 正文非模板 + 引用一致 + 图路径正确，0 fatal 才 `validated=True, status=validated`

### BibTeX 系统
- `literature_catalog.json` 每篇含 `citation.{bib_key,bibtex,citation_style_name,source,verified}`，13 篇已补全。
- `data/catalog/references.bib` 全库汇总，由 `scripts/sync_bib_from_catalog.py` 同步（**校验 citation → 备份 → 写 tmp → 校验 → 原子替换**）。
- `scripts/validate_bib.py` 校验 citation（bib_key 唯一、entry key==bib_key、含 title/author/year、catalog bib_key 在 references.bib 中）。
- 写作时 `export_job_bib()` 按 **selected_papers（须 confirmed）** 从全局 bib 抽取生成 `write/<job>/tex/references.bib`；未确认则拒绝导出。
- `/prompt/bib-entry` 为单篇生成 BibTeX 补全 prompt。

### 写作硬性约束
- 先读 `literature_catalog.json` 再决定读哪些全文，禁止盲读全部。
- 所有引用用 catalog 的 `bib_key`（`\cite{bib_key}`），禁止裸作者年份。
- 引用图必须从 `data/papers/<pid>/images/` 复制到 `write/<job>/figures/<pid>/` 并记 README（含 `original_path`），TeX 用相对路径 `../figures/<pid>/<img>`。`copy-figures` 只复制明确指定的图，不自动复制全部候选。
- 禁止编造文献、图号、公式、DOI；强事实必须来自 paper_notes/evidence_table。
- introduction / method 按博士论文标准（见 `skills/literature_review_writer/templates/`），填完正文删 `TEMPLATE_ONLY` 标记或改 `CONTENT_FILLED`。

### Tex 项目解耦（可整体挪走）
每个 `write/<job>/tex/` 是**自包含、可独立复制/挪走**的 LaTeX 项目：
- `tex/references.bib` 是任务专属副本，由 `export_job_bib` 从全局 `data/catalog/references.bib` 按 `selected_papers` 抽取生成，**不依赖**全局 bib 或 catalog。挪走后仍可编译。
- `main.tex` 用相对路径 `\bibliography{references}`、`\input{sections/...}`；图片用 `../figures/<pid>/<img>`。整个 `write/<job>/` 目录复制到任意位置，内部相对引用全部成立。
- `validate_write_job.py` / `/write/jobs/{id}/validate` 含 `portability_check`：确认所有 `\bibliography`/`\input`/`\includegraphics` 引用都在 job 目录内解析、不指向 `data/papers` 等外部路径。检出外部依赖即报 `portable: False`。

## 常见开发任务

- **冒烟测试 API**（服务须在 8080 运行）：
  ```bash
  curl http://localhost:8080/status
  curl http://localhost:8080/papers
  ```
- **批量转换文件夹**：`python batch_convert.py data/raw --api-url http://127.0.0.1:8000`。
- **watcher 单次扫描**：`python watcher.py --once`。
- **从旧版重建 papers**：`python scripts/rebuild_library.py`（`--reconvert` 强制重转）。
- **校验目录**：`python scripts/validate_catalog.py`。
- **同步/校验 BibTeX**：`python scripts/sync_bib_from_catalog.py`、`python scripts/validate_bib.py`。
- **综述写作**：见上方「综述写作 Skill」；`python scripts/write_review.py <子命令> --job <id>`。
- **校验写作任务**：`python scripts/validate_write_job.py --job <id>`。
- **单文件 CLI**：`mineru -p file.pdf -o data/tmp/mineru_raw_output/<id> -b hybrid-engine --api-url http://127.0.0.1:8000`。
- Python 3.10+（用 `str | Path` 联合语法）。日志用 `loguru`。
- 风格对齐：中文文档字符串/注释、`loguru` logger、pathlib 路径。

## 已知问题与注意事项

1. **catalog 已补全**。13 篇文献均已在 `literature_catalog.json` 中有 `status: summarized` 条目，`/prompt/plan-reading` 可直接使用。条目由人工基于 paper.md 头部信息编写，书目信息（标题/作者/年份/venue）已尽量核准，但 `ai_summary` 的细节定性描述建议在严肃写作前回到全文核对——目录只负责判断该不该读全文，不替代全文证据。
2. **paper_id 规范化靠人工**。新上传文件用 `derive_paper_id()` 从文件名推导，可能不规范。规范命名（`年份_作者_标题`）由 AI 在补全 catalog 条目时建议，用户确认后需手动改 `data/papers/` 目录名 + manifest + catalog 三处。现有 13 篇已用 `config/paper_ids.py` 固定为规范命名。
3. **重复上传去重**。`data/raw/` 原有 15 篇 PDF，其中 Déry&Yau 1999 与 Comola 2017 各有一份重复（不同文件名），已在清理时删除重复 PDF，`data/raw/` 与 `data/papers/` 现 13 篇一一对应。`config/paper_ids.py` 的 `DUPLICATE_RAW_STEMS` 仍保留，以备再次出现重复文件时 `rebuild_library.py` 自动跳过。
4. **遗留目录已清理**。`data/parsed/`（旧版输出）、`output/`（手动 CLI 零散输出）已在重构后删除。`rebuild_library.py` 仍保留复用 `data/parsed` 的逻辑分支（`find_legacy_output`），但该目录不存在时自动走重新转换路径。
5. **CORS 全开**（`allow_origins=["*"]`，[server.py](src/server.py)）——本地无所谓，暴露到公网需收紧。
6. **端口文档字符串已修正**。旧版 `server.py` 顶部写 7890 是错的，重构后已改为 8080。
7. **Gradio 6 兼容**。`app.py` 中 `gr.Blocks(theme=..., css=...)` 会触发 Gradio 6 警告（theme/css 应移到 `launch()`），不影响运行。
8. **`gradio` 和 `requests` 现已写入 requirements.txt**（旧版漏写，已修复）。
9. **写作 skill 的 LLM 步骤需手动跑**。`/write/jobs/*` 与 `scripts/write_review.py` 各步生成 prompt + 模板文件，但 introduction/method 正文、paper_notes、story_plan、selected_papers 裁剪都需人用大模型跑 prompt 后回填。`match`/`deep-read`/`story`/`tex` 只设 prompt_generated/template_generated；`mark-*` 校验非模板后才设 filled；`validate` 全量通过才设 validated。校验对"未引用 bib 条目"仅 warning，对"`\cite` 找不到"、"`TEMPLATE_ONLY`/`待填` 残留"、"`run_meta.steps.*` 未 True"作 fatal。
10. **figure_manager 只复制明确指定的图**。`copy-figures` 不再自动复制全部候选图；须通过 `--figures paper_id:image`（CLI）或 `{"figures":[...]}`（API）显式指定。进 TeX 的图必然已复制到 `figures/`（`portability_check` 拦截指向 `data/papers` 的外部引用），保证 tex 项目可挪走。
11. **paper_id 含中文时 CLI 传参编码**。Windows GBK 控制台下 `write_review.py --job <中文id>` 可能因 argv 编码出错；推荐用 API（HTTP，UTF-8）或在单条命令内用变量传递，避免跨 shell 往返。
