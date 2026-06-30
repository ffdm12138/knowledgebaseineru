# Project Status

本文档是 MinerU v2 文献资产库的当前状态总览：冻结版本、主流程、边界、待办与禁止事项。
新 agent 或未来维护者应先读此文件，再进入 `docs/PROJECT_CONTRACT.md` 与
`docs/DEPENDENCIES_AND_EXTERNAL_TOOLS.md`。

## 1. 当前冻结版本

### ingest v2.1 frozen

- tag：`ingest-v2.1`
- 验收：baseline 18、network 18→19、manual 19→20、duplicate negative、
  `validate_v2_library.py` / `audit_metadata_quality.py` / `doctor_ingest_pipeline.py` /
  `pytest -q` 全绿。
- 不重构 ingest 主链路，不修改 catalog/metadata schema。

### writing v0.1 frozen

- tag：`writing-v0.1`
- 验收：mechanical writing loop、deterministic quality checks、two real-topic samples。
- 不修改 writer 工作流。

## 2. 当前主流程

### 入库主流程

```text
data/raw 或 network metadata
-> data/paper_raw/<000001>/
-> metadata match / resolve（必须有合法 DOI）
-> MinerU convert（hybrid-engine + medium + auto）
-> catalog curation（content-only）
-> commit data/papers/<paper_id>/
-> rebuild data/catalog/all.catalog.json
-> validate / audit / doctor
```

### 写作主流程

```text
selected catalog / paper numbers
-> write/jobs/<job_id>/article/<paper_number>/
-> TeX / BibTeX（references.bib 仅从 metadata 生成）
-> compile / check（check_write_tex_project.py）
-> quality check（check_write_quality_text.py）
```

## 3. 当前边界

- `metadata` 是书目信息事实源（DOI / 作者 / 年份 / 期刊 / 卷期页）。
- `catalog`（schema v2.0）是 content-only，不含书目字段。
- `write/jobs/` 是运行时，不提交（只跟踪 `.gitkeep`）。
- TeX 不得直接读 `data/papers`、`data/raw`、`data/paper_raw`、`data/llm_work`。
- 真实入库 / 转换 / 写作必须使用 `conda run -n mineru`。
- snapshot 不含真实 data 与 `write/jobs` 运行产物。

## 4. 当前待办

- writer v0.2 P0（已实现）：`doctor_write_pipeline.py`、`create_write_job.py`。
- 第三方解耦（本轮完成）：`src/fetch/proxy.py` 已抽出共享代理逻辑；
  Sci-Hub 标注为 unsafe optional / 默认 disabled / 不属于 OA_ONLY 主流程。
- 后续可选（planned only）：
  - job-local literature matrix
  - mechanism / table / figure outline
  - stronger deterministic writing quality checks

## 5. 不做事项

- 不引入 RAG / embedding / vector DB / ChromaDB。
- 不内置 LLM client。
- 不把真实 data / `write/jobs` 运行产物入 snapshot。
- 不让外部 metadata 直接写正式库（必须经 `paper_raw` + validate/audit）。
- 不放宽 Sci-Hub 启用条件。
