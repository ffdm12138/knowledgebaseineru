# MinerU v2 文献资产库

本项目是本地文献资产库、AI 可读目录和博士论文级综述写作工作区。它只保留纯 v2 `paper_raw` 工作流，不做向量库、RAG、embedding，也不内置 LLM client。所有 prompt 和写作步骤只生成可复制文本或结构化模板。

## Project status and documentation map

- **ingest v2.1 已冻结**（tag `ingest-v2.1`）；**writing v0.1 已冻结**（tag `writing-v0.1`）。本轮不打新 tag。
- 项目**不使用 RAG / embedding / vector database / ChromaDB**，也不内置 LLM client。
- 真实入库 / 转换 / 写作必须使用 `conda run -n mineru ...`（PATH 上的 python 是 Windows Store 别名，会静默退出）。
- snapshot 不包含真实 `data/` 文献资产与 `write/jobs/` 运行产物（只跟踪 `.gitkeep`）。

文档入口：

- [AGENTS.md](AGENTS.md) — 所有 coding agent 的项目操作规约（状态、边界、主流程、提交前检查）
- [CLAUDE.md](CLAUDE.md) — Claude/Codex 类 agent 操作提醒与关键边界速查
- [docs/PROJECT_STATUS.md](docs/PROJECT_STATUS.md) — 当前冻结版本、主流程、边界、待办与禁止事项总览
- [docs/PROJECT_CONTRACT.md](docs/PROJECT_CONTRACT.md) — 不可改变的核心契约与边界
- [docs/DEPENDENCIES_AND_EXTERNAL_TOOLS.md](docs/DEPENDENCIES_AND_EXTERNAL_TOOLS.md) — 依赖、网络服务、PDF resolver、Sci-Hub unsafe optional
- [docs/WRITING_QUALITY_ACCEPTANCE.md](docs/WRITING_QUALITY_ACCEPTANCE.md) — 写作质量验收规则
- [docs/WRITER_PRODUCTIZATION_PLAN.md](docs/WRITER_PRODUCTIZATION_PLAN.md) — writer v0.2 产品化计划
- [reports/real_ingest_acceptance.md](reports/real_ingest_acceptance.md) — 真实入库验收记录

## Quick validation

全部使用 mineru conda 环境（PATH 上的 `python` 是 Windows Store 别名，会静默退出）：

```bash
conda run -n mineru pytest -q
conda run -n mineru python scripts/pack_repo.py
conda run -n mineru python scripts/validate_v2_library.py
conda run -n mineru python scripts/audit_metadata_quality.py
conda run -n mineru python scripts/doctor_ingest_pipeline.py
```

## Explicit non-goals

- no RAG / no embedding / no vector DB / no ChromaDB
- no LLM client in code（所有 prompt/写作步骤只生成文本或模板）
- 不提交真实 data 与 `write/jobs` 运行产物（只跟踪 `.gitkeep`）


## 唯一数据流

```text
手动 PDF 或网络 metadata
-> data/paper_raw/<000001>/
-> metadata 匹配或人工确认
-> PDF 获取或绑定
-> MinerU 批量转换
-> curation 生成 catalog 并补齐 metadata 空字段
-> commit 到 data/papers/<year_author_中文标题>/
-> 分配 16 位 paper_number
-> 重建 data/catalog/all.catalog.json
-> 写作流程按 paper_number 复制到 write/jobs/<job_id>/article/<paper_number>/
```

正式资产只允许位于：

```text
data/papers/<paper_id>/<paper_id>.metadata.json
data/papers/<paper_id>/<paper_id>.catalog.json
data/papers/<paper_id>/<paper_id>.md
data/papers/<paper_id>/<paper_id>.pdf
data/papers/<paper_id>/images/
data/papers/<paper_id>/<16位编号>.paper.number
```

`data/catalog/all.catalog.json`、`data/catalog/paper_index.json` 和 `data/catalog/paper_number_ledger.json` 是本地生成的 API/写作运行时索引，不提交真实库状态；源码快照只提交对应 `.template.json` 空模板。旧数据不自动迁移。

## 事实源与主键

- **metadata**（`<paper_id>.metadata.json`）：BibTeX/书目信息事实源（DOI、作者、年份、期刊、卷期页、链接、metadata_match）。
- **catalog**（`<paper_id>.catalog.json`，schema v2.0，**content-only**）：大模型快速筛选精读文献的内容索引。只含正文内容理解（content_identity、classification、screening、research_card、evidence_profile、content_notes、provenance），**不含** DOI/作者/年份/期刊/卷期页等书目字段（这些只在 metadata）。catalog 与 metadata 仅通过 `paper_number`/`paper_id` 关联。
- **paper_number**（16 位）：API 与写作流程主键。大模型先看 `all.catalog.json`（content-only）选号，再按 `paper_number` 读 metadata 取书目信息。writing v0.1 主流程使用 `write/jobs/<job_id>/article/<paper_number>/`，当前主入口为 `create_write_job.py` / `prepare_write_article_workdir.py`。`copy_paper_to_llm_work.py` 与 `data/llm_work` 仅为 legacy / API compatibility，**不是** writing v0.1 主路径。`all.catalog` 是内容索引不是书目库；references/BibTeX 只从 metadata 生成。

## Metadata 完整性门槛

- 网络/搜索 metadata 导入必须有 DOI，并写入 `metadata.identifiers.doi`；没有 DOI 的候选不得 stage 到 `paper_raw`。
- 手动 PDF 可以先进入 `data/paper_raw/<000001>/` 并保持 `metadata_match.status = unmatched`，但匹配或人工确认没有 DOI 时不得 curation/commit。
- curation、formal commit 和正式库 validate 都要求 DOI 非空；不完整的 `paper_raw` 留在原工作区，写 `.import_status.json` 说明原因。
- LLM/curator 只能补空 metadata 字段，不能编造 DOI，也不能覆盖已有非空 DOI。
- BibTeX 和 APA 参考文献只从 metadata 读取标题、作者、venue、卷期页、DOI 和 URL，不从 catalog 或 MinerU 正文拼接。

## 入库 / 写作 / API 命令链

完整命令链（含手动 PDF 导入、网络 metadata 导入、curation、commit、API、写作工作流、MinerU 运行参数）
见 [AGENTS.md](AGENTS.md) 与 `docs/PROJECT_STATUS.md`；写作详见
[docs/WRITER_PRODUCTIZATION_PLAN.md](docs/WRITER_PRODUCTIZATION_PLAN.md) 与
[skills/catalog_tex_writer/](skills/catalog_tex_writer/)。所有真实命令必须 `conda run -n mineru ...`。

要点速记：

- 手动 PDF 放 `data/raw/`；`stage_raw_pdfs_to_paper_raw.py --apply` 默认复制（`--move` 才移动）。
- 网络/搜索 metadata 必须有合法 DOI 才能进入 `paper_raw`。
- `curate_paper_raw.py` 不调用大模型：`--dry-run` 写 curation prompt，`--apply` 应用 content-only catalog；
  metadata 空字段由 `resolve_paper_raw_metadata.py` / enrichment 补齐，不在 curate 阶段处理。详见
  [skills/paper_raw_catalog_curator/](skills/paper_raw_catalog_curator/)。
- MinerU 默认 `hybrid-engine + medium + auto`，批量转换默认单进程防 GPU OOM。

## 数据与版权边界

`data/raw/`、`data/paper_raw/`、`data/papers/`、`data/llm_work/` 中的文献资产按版权数据处理，不进入源码分发。
真实 `data/papers` 不进入 snapshot，但本地真实库必须通过 `validate_v2_library.py` 和
`audit_metadata_quality.py` 的硬错误检查。`write/jobs/` 运行产物不提交（只跟踪 `.gitkeep`）。

