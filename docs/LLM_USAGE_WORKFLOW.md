# LLM / Agent 使用工作流

本文面向 ChatGPT / Claude / Codex 等 agent，说明如何把本项目当作文献资产库使用。当前项目不使用 ChromaDB、embedding、vector search、RAG、`/ask`、`/search`，也不内置 LLM client。

## 稳定接口

这些文件和目录可作为 agent 的稳定读取接口：

- `data/papers/<paper_id>/paper.md`
- `data/papers/<paper_id>/images/`
- `data/catalog/literature_catalog.json`
- `data/catalog/library_index.json`
- `data/catalog/domains/<domain>/literature_catalog.json`
- `data/catalog/domains/<domain>/references.bib`
- `data/manifests/papers_manifest.json`

全文和图片路径优先从 `library_index.json` / `PaperLibrary` 解析，不要硬编码假设所有文献都在同一种物理目录布局下。

## 选文献

1. 先读 `data/catalog/literature_catalog.json` 获取全局文献理解条目。
2. 若任务有领域范围，优先读 `data/catalog/domains/<domain>/literature_catalog.json`。
3. 多领域任务先 compact / dedupe：

   ```bash
   python scripts/compact_domain_catalog.py --domains blowing_snow_physics aeolian_snow_transport
   ```

4. 依据 `ai_summary`、`tags`、`selection_hints`、`citation`、`domains` 判断是否需要深读全文。
5. `domain catalog` 是视图层，同一篇文献跨领域重复出现是合法的；进入写作前必须按 `paper_id` 去重。

## 读取全文

1. 从 catalog 或 domain catalog 取得 `paper_id`。
2. 用 API 读取：

   ```bash
   curl http://localhost:8080/papers/<paper_id>/markdown
   ```

3. 或本地读取 `data/papers/<paper_id>/paper.md`，但路径变更时应以 `library_index.json` 为准。
4. 图片在 `data/papers/<paper_id>/images/`，单图也可用 `/papers/{paper_id}/images/{img}`。

## 补全 Catalog 条目

正式入库后的新文献通常是 `status=unsummarized`，不会自动生成 AI summary。

1. 生成补全 prompt：

   ```bash
   curl -X POST http://localhost:8080/prompt/catalog-entry \
     -H "Content-Type: application/json" \
     -d "{\"paper_id\":\"<paper_id>\"}"
   ```

2. 由外部 LLM 阅读全文后补齐 `ai_summary`、`tags`、`selection_hints`、`citation`。
3. 写回后运行：

   ```bash
   python scripts/validate_catalog.py
   python scripts/validate_bib.py
   python scripts/migrate_to_domain_library.py --apply
   python scripts/validate_domain_library.py
   ```

## 生成综述

使用写作工作流，不调用内置 LLM：

```bash
python scripts/write_review.py create --topic "研究主题"
python scripts/write_review.py match --job <job_id> --domains blowing_snow_physics aeolian_snow_transport
python scripts/write_review.py confirm-papers --job <job_id> --papers <paper_id> ...
python scripts/write_review.py deep-read --job <job_id>
python scripts/write_review.py mark-deep-read --job <job_id>
python scripts/write_review.py story --job <job_id>
python scripts/write_review.py mark-story --job <job_id>
python scripts/write_review.py tex --job <job_id>
python scripts/write_review.py mark-tex --job <job_id>
python scripts/write_review.py validate --job <job_id>
```

`prompt_generated` 不等于 `content_filled`；agent 必须在外部 LLM 填入内容并通过 `mark-*` 校验后再进入下一步。

## 建库和入库

正式新增 PDF 必须走 pending/import：

```bash
python scripts/register_manual_pdf.py "E:\papers_to_import\paper.pdf" --domain blowing_snow_physics --title "Title" --year 2024
python scripts/import_pending_pdf.py data/raw/blowing_snow_physics/pending/paper.pdf --domain blowing_snow_physics --apply
```

关键词发现 DOI：

```bash
python scripts/discover_papers.py "风吹雪 升华 破碎" --domain blowing_snow_physics --max-candidates 30
```

DOI 获取 PDF 只进入 pending：

```bash
python scripts/fetch_pdf.py 10.xxxx/yyyy --domain blowing_snow_physics --access-mode oa_only
python scripts/list_pending_pdfs.py
python scripts/import_pending_pdf.py data/raw/blowing_snow_physics/pending/<file>.pdf --domain blowing_snow_physics --apply
```

## `unregistered_converted`

以下路径可能只产生 `unregistered_converted`，即 manifest 有记录但无正式 catalog/index/domain/bib 元数据：

- Web `/upload` 未提供 title/doi/year/domain。
- `watcher.py` 扫描 `data/raw/` 根目录。
- `batch_convert.py` 临时批量转换。

这类结果不等于正式入库。需要人工补 metadata 或通过正规 pending/import 流程整理。

## 运行产物不要提交或打包

不要提交或依赖这些运行态目录：

- `data/raw/`
- `data/papers/`
- `data/tmp/`
- `data/logs/`
- `data/jobs/`
- `data/transactions/`
- `data/discovery/doi_candidates/`
- `data/discovery/pdf_fetch_logs/`
- `data/discovery/fetch_logs/`
- `data/locks/*.lock`
- `write/`

## 禁止事项

- 不要调用 ChromaDB、embedding、vector database。
- 不要调用或恢复 `/ask`、`/search`。
- 不要把 `/upload` 或 watcher 描述为推荐正式入库入口。
- 不要绕过 pending PDF duplicate detection。
- 不要让代码自动调用外部 LLM。
