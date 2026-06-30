# CLAUDE.md

权威规则在 `AGENTS.md` 与 `docs/PROJECT_CONTRACT.md`；本文件仅 Claude/Codex 类 agent 的操作提醒。
新 agent 先按 `AGENTS.md` 的阅读顺序进入项目。

## 操作提醒

- 动多个文件前先 plan，按主题拆 commit，不要把多个主题混进一个 commit。
- 不修改冻结的 ingest 主链路（tag `ingest-v2.1`），除非用户显式要求。
- 不修改 writer v0.1 行为（tag `writing-v0.1`）；writer v0.2 增量改动以 `docs/WRITER_PRODUCTIZATION_PLAN.md` 为准。
- 真实入库 / 转换 / 写作验收必须用 `conda run -n mineru ...`；Windows 先 `set PYTHONIOENCODING=utf-8`。
- 不提交运行时数据：`write/jobs` runtime 与真实 `data/papers`/`data/raw`/`data/paper_raw`/`data/import_work`
  不进入 staged / snapshot。

## 关键边界速查

- ingest v2.1 frozen（`ingest-v2.1`）；writing v0.1 frozen（`writing-v0.1`）。
- `conda run -n mineru` 是唯一真实运行方式。
- `metadata` 是书目信息事实源；`catalog`（schema v2.0）content-only，`all.catalog` 不含书目字段。
- `write/jobs` 是运行时不提交；TeX 不直读 `data/papers`。
- 不做 RAG / embedding / vector DB / ChromaDB；不内置 LLM client。
- Sci-Hub 是 unsafe optional，default disabled，不属于 OA_ONLY 主流程。

每次代码改动后运行：`conda run -n mineru pytest -q` 与 `conda run -n mineru python scripts/pack_repo.py`。
