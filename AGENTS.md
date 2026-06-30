# AGENTS.md

面向所有 coding agent 的项目操作规约。修改本仓库前必须阅读：

- `docs/PROJECT_STATUS.md`（当前冻结状态与主流程总览）
- `docs/PROJECT_CONTRACT.md`（不可破坏契约）
- `README.md`（文档入口地图）

新 agent 建议阅读顺序：`AGENTS.md` → `docs/PROJECT_STATUS.md` → `docs/PROJECT_CONTRACT.md` → `README.md`。
按改动类型深入：ingest 改动看 `docs/PROJECT_CONTRACT.md`、`docs/DEPENDENCIES_AND_EXTERNAL_TOOLS.md`、
`reports/real_ingest_acceptance.md`；writing 改动看 `docs/WRITING_QUALITY_ACCEPTANCE.md`、
`docs/WRITER_PRODUCTIZATION_PLAN.md`、`skills/catalog_tex_writer`；fetch/依赖改动看
`docs/DEPENDENCIES_AND_EXTERNAL_TOOLS.md` 与 `docs/PROJECT_CONTRACT.md`。

## 1. 项目状态

- ingest v2.1 frozen，tag `ingest-v2.1`。
- writing v0.1 frozen，tag `writing-v0.1`。
- 不重构 ingest 主链路，不修改 catalog/metadata schema，不修改 writer v0.1 行为。
- 当前增量改动必须文档化，不打新 tag。

## 2. 不可违反的边界

- `metadata`（`<paper_id>.metadata.json`）是书目信息事实源（DOI、作者、年份、期刊、卷期页、BibTeX）。
- `catalog`（schema v2.0）是 content-only：`all.catalog` 不得含 DOI/作者/年份/venue/metadata/display 等书目字段，
  两者仅通过 `paper_number`/`paper_id` 关联。
- `references.bib` 只从复制的 metadata 生成，绝不从 catalog 或正文拼接。
- `write/jobs` 是写作运行时，不提交（只跟踪 `.gitkeep`）；TeX 不得直接读 `data/papers`、`data/raw`、
  `data/paper_raw`、`data/llm_work`，只能读 job-local 复制副本。
- 不做 RAG / embedding / vector DB / ChromaDB；不内置 LLM client，所有 prompt/写作步骤只生成文本或模板。
- Sci-Hub resolver 是 unsafe optional：默认 disabled，不属于 OA_ONLY 主流程；仅 `AccessMode.CUSTOM` 且
  `allow_scihub=True` 时才启用，且不得放宽该条件。
- 网络 metadata 进入 `paper_raw` 前必须有合法 DOI；没有 DOI 的候选不得 stage。
- 正式入库必须通过 `validate_v2_library.py` 与 `audit_metadata_quality.py` 的硬错误检查。

## 3. 运行环境

- 真实入库 / 转换 / 写作验收命令必须使用 `conda run -n mineru ...`
  （PATH 上的 `python` 是 Windows Store 别名，会静默退出 code 49）。
- Windows 控制台先 `set PYTHONIOENCODING=utf-8`，避免 GBK 下中文/JSON 输出失败。

## 4. 数据边界

- `data/papers`、`data/raw`、`data/paper_raw`、`data/import_work`、`write/jobs` 为运行时 / 真实数据区。
- snapshot 只含 `.gitkeep` 与 catalog `.template.json` 空模板；`pack_repo.py` 强制排除真实数据与生成的
  catalog 索引（`all.catalog.json`、`paper_index.json`、`paper_number_ledger.json`）。
- 任何 PDF / Markdown / images / TeX 编译产物不进入 snapshot。

## 5. 主流程

入库主流程（命令链）：

```bash
conda run -n mineru python scripts/stage_raw_pdfs_to_paper_raw.py --apply
conda run -n mineru python scripts/match_paper_raw_metadata.py --all --apply
conda run -n mineru python scripts/convert_paper_raw_batch.py --all --apply
conda run -n mineru python scripts/curate_paper_raw.py --all-ready --apply
conda run -n mineru python scripts/commit_paper_raw_to_papers.py --all-ready --apply
conda run -n mineru python scripts/rebuild_all_catalog.py --apply
conda run -n mineru python scripts/validate_v2_library.py
```

网络 metadata 先 `stage_network_metadata_to_paper_raw.py --apply` 与 `fetch_pdf_for_paper_raw.py --all --apply`，
再接 match/convert/curate/commit。

写作主流程：selected catalog / paper numbers → `write/jobs/<job_id>/article/` → TeX/BibTeX →
compile/check（`check_write_tex_project.py`）→ quality check（`check_write_quality_text.py`）。
详见 `docs/WRITER_PRODUCTIZATION_PLAN.md` 与 `skills/catalog_tex_writer`。

详细规则与边界见 `docs/PROJECT_STATUS.md`、`docs/PROJECT_CONTRACT.md`。

## 6. 正式资产结构

```text
data/papers/<paper_id>/<paper_id>.metadata.json
data/papers/<paper_id>/<paper_id>.catalog.json
data/papers/<paper_id>/<paper_id>.md
data/papers/<paper_id>/<paper_id>.pdf
data/papers/<paper_id>/images/
data/papers/<paper_id>/<16位编号>.paper.number
```

## 7. 提交前检查

```bash
conda run -n mineru pytest -q
conda run -n mineru python scripts/pack_repo.py
git status --short
git ls-files write/jobs                       # 应仅 .gitkeep
git ls-files data/papers data/paper_raw data/raw data/import_work  # 应仅 .gitkeep
```

- 确认无真实 data / `write/jobs` runtime 被 staged。
- 按主题拆 commit，不要把多个主题混进一个 commit。
- 每次代码改动后运行测试并生成 `mineru_snapshot.zip`。
