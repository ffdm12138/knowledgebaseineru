# MinerU v2 文献资产库

本项目是本地文献资产库、AI 可读目录和博士论文级综述写作工作区。它只保留纯 v2 `paper_raw` 工作流，不做向量库、RAG、embedding，也不内置 LLM client。所有 prompt 和写作步骤只生成可复制文本或结构化模板。

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
-> API 按 paper_number 复制到 data/llm_work/
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

`data/catalog/all.catalog.json` 和 `data/catalog/paper_number_ledger.json` 是 API 与写作事实源。旧数据不自动迁移。

## 事实源与主键

- **metadata**（`<paper_id>.metadata.json`）：BibTeX/书目信息事实源（DOI、作者、年份、期刊、卷期页、链接、metadata_match）。
- **catalog**（`<paper_id>.catalog.json`，schema v2.0，**content-only**）：大模型快速筛选精读文献的内容索引。只含正文内容理解（content_identity、classification、screening、research_card、evidence_profile、content_notes、provenance），**不含** DOI/作者/年份/期刊/卷期页等书目字段（这些只在 metadata）。catalog 与 metadata 仅通过 `paper_number`/`paper_id` 关联。
- **paper_number**（16 位）：API 与写作流程主键。大模型先看 `all.catalog.json`（content-only）选号，再按 `paper_number` 读 metadata 取书目信息、用 `copy_paper_to_llm_work.py` 复制全文到 `data/llm_work/` 精读写作。`all.catalog` 是内容索引不是书目库；references/BibTeX 只从 metadata 生成。

## Metadata 完整性门槛

- 网络/搜索 metadata 导入必须有 DOI，并写入 `metadata.identifiers.doi`；没有 DOI 的候选不得 stage 到 `paper_raw`。
- 手动 PDF 可以先进入 `data/paper_raw/<000001>/` 并保持 `metadata_match.status = unmatched`，但匹配或人工确认没有 DOI 时不得 curation/commit。
- curation、formal commit 和正式库 validate 都要求 DOI 非空；不完整的 `paper_raw` 留在原工作区，写 `.import_status.json` 说明原因。
- LLM/curator 只能补空 metadata 字段，不能编造 DOI，也不能覆盖已有非空 DOI。
- BibTeX 和 APA 参考文献只从 metadata 读取标题、作者、venue、卷期页、DOI 和 URL，不从 catalog 或 MinerU 正文拼接。

## 手动 PDF 导入

把 PDF 放到 `data/raw/` 根目录后运行：

```bash
python scripts/stage_raw_pdfs_to_paper_raw.py --apply
python scripts/match_paper_raw_metadata.py --all --apply
python scripts/convert_paper_raw_batch.py --all --apply

# 生成 curation prompt（在每个 paper_raw 文件夹写出 curation_prompt.md）
python scripts/curate_paper_raw.py --all-ready --dry-run

# 大模型/项目级 skill paper_raw_catalog_curator 生成 catalog 与 metadata patch 后
python scripts/curate_paper_raw.py --all-ready --apply

python scripts/commit_paper_raw_to_papers.py --all-ready --apply
python scripts/rebuild_all_catalog.py --apply
python scripts/validate_v2_library.py

# 复制精读文献到写作工作区（按 16 位 paper_number）
python scripts/copy_paper_to_llm_work.py --paper-number 0000000000000001 --session-id review_001 --apply
```

## 网络 metadata 导入

```bash
python scripts/discover_papers.py "风吹雪 升华 破碎" --max-candidates 30
python scripts/stage_network_metadata_to_paper_raw.py --input candidates.jsonl --apply
python scripts/fetch_pdf_for_paper_raw.py --all --apply
python scripts/match_paper_raw_metadata.py --all --apply
python scripts/convert_paper_raw_batch.py --all --apply
python scripts/curate_paper_raw.py --all-ready --dry-run   # 生成 curation prompt
python scripts/curate_paper_raw.py --all-ready --apply     # 应用 catalog + metadata patch
python scripts/commit_paper_raw_to_papers.py --all-ready --apply
python scripts/rebuild_all_catalog.py --apply
python scripts/validate_v2_library.py
```

已有本地 PDF 可绑定到指定工作区：

```bash
python scripts/attach_pdf_to_paper_raw.py --source-id 000001 --pdf "E:\papers\paper.pdf" --apply
```

## Curation

`curate_paper_raw.py` 不调用大模型：`--dry-run` 在每个 `data/paper_raw/<source_id>/` 写出 `curation_prompt.md`（含 skill `paper_raw_catalog_curator`、catalog v2.0 content-only schema、命名规则）；`--apply` 应用大模型产出的 catalog（content-only，不含书目字段），按 `年份_第一作者_中文标题` 规范重命名（paper_id 仅从 metadata 生成）。metadata 空字段由 `resolve_paper_raw_metadata.py` / enrichment 补齐，不在 curate 阶段处理。`metadata_match.status` 必须为 `matched` 或 `manual_confirmed`，否则 curation 和 commit 都会拒绝。详见项目级 skill `skills/paper_raw_catalog_curator/`。

`metadata.identifiers.doi` 也必须非空；没有 DOI 的手动 PDF 需要先完成可靠 metadata match 或人工补 DOI，不能生成正式 curation prompt，也不能入库。

## API

启动服务：

```bash
python -m src.server
```

主要接口：

```text
GET  /catalog/all
GET  /papers/by-number/{paper_number}
GET  /papers/by-number/{paper_number}/markdown
POST /papers/by-number/{paper_number}/copy-to-llm-work
POST /bibtex
POST /validate/v2-library
```

复制全文资产到大模型工作区（API 或 CLI 均可）：

```bash
curl -X POST http://127.0.0.1:8080/papers/by-number/0000000000000001/copy-to-llm-work ^
  -H "Content-Type: application/json" ^
  -d "{\"session_id\":\"review_001\"}"

# 或 CLI
python scripts/copy_paper_to_llm_work.py --paper-number 0000000000000001 --session-id review_001 --apply
```

BibTeX 从 metadata 生成：

```bash
curl -X POST http://127.0.0.1:8080/bibtex ^
  -H "Content-Type: application/json" ^
  -d "{\"paper_numbers\":[\"0000000000000001\"]}"
```

## 写作工作流

```bash
python scripts/write_review.py create --topic "研究主题"
python scripts/write_review.py match --job <job_id> --topics topic_a topic_b
python scripts/write_review.py confirm-papers --job <job_id> --papers <paper_id>
python scripts/write_review.py deep-read --job <job_id>
python scripts/write_review.py mark-deep-read --job <job_id>
python scripts/write_review.py story --job <job_id>
python scripts/write_review.py mark-story --job <job_id>
python scripts/write_review.py tex --job <job_id>
python scripts/write_review.py mark-tex --job <job_id>
python scripts/write_review.py copy-figures --job <job_id>
python scripts/write_review.py validate --job <job_id>
```

## MinerU 运行

默认产品路径是 `hybrid-engine + medium + auto`。批量转换默认单进程，避免 GPU OOM。加速模式可手动启动常驻 `mineru-api` 后设置：

```bash
set MINERU_RUNNER=cli_api_proxy
set MINERU_API_URL=http://127.0.0.1:8000
```

诊断命令：

```bash
python scripts/check_mineru_processes.py
python scripts/benchmark_mineru.py "E:\papers\test.pdf" --repeat 2
```

## 验收

```bash
python scripts/rebuild_all_catalog.py --apply
python scripts/validate_v2_library.py
pytest -q
python scripts/pack_repo.py
```

`data/raw/`、`data/paper_raw/`、`data/papers/`、`data/llm_work/` 中的文献资产按版权数据处理，不进入源码分发。
