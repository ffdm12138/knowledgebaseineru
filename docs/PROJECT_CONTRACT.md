# 项目核心契约

本仓库是本地文献资产库、AI 可读目录和综述写作工作区。正式入库只允许走 v2 `paper_raw` 工作流。

## 不可改变的规则

- 不做向量库、RAG、embedding 或 ChromaDB。
- 不内置 LLM client；所有 prompt 和写作步骤只生成文本或模板。
- 所有新文献先进入 `data/paper_raw/<000001>/`。
- MinerU 只能处理 `data/paper_raw/<000001>/<000001>.pdf`。
- 正式资产只保存在 `data/papers/<paper_id>/`，同目录保存 PDF、Markdown、metadata、catalog、images 和 paper number。
- API 与写作只读取 `data/catalog/all.catalog.json`、`data/catalog/paper_number_ledger.json` 和 `data/papers/<paper_id>/`。
- metadata 管书目信息和 BibTeX 事实；catalog（schema v2.0）只管正文内容理解（分类、研究卡片、证据画像、精读筛选 `screening`），**不含** DOI/作者/年份/期刊/卷期页等书目字段。两者仅通过 `paper_number`/`paper_id` 关联。
- **metadata is bibliographic truth; catalog is content understanding; paper_number links them. all.catalog is a content index, not a bibliography database.** references/BibTeX 必须从 metadata 生成，绝不从 catalog 生成。
- catalog 由项目级 skill `paper_raw_catalog_curator` 在 commit 前从 MinerU Markdown 生成（content-only，不生成 metadata patch）；metadata 空字段由 metadata resolver/enrichment 补齐，不覆盖非空字段。
- `data/catalog/all.catalog.json` 只聚合 catalog 内容（content-only，无 metadata）；`data/catalog/paper_index.json` 做 paper_number→路径映射（也不含书目字段）。需要书目信息时按 paper_number 读 `data/papers/<paper_number>/...metadata.json`。
- 网络/搜索 metadata 导入必须有 DOI，并写入 `metadata.identifiers.doi`；没有 DOI 的搜索结果不得进入 `paper_raw`。
- 手动 PDF 可以先生成无 DOI 的空壳 metadata，但只有补齐 DOI 且 `metadata_match.status` 为 `matched` 或 `manual_confirmed` 后才能 curation/commit。
- 正式库 `data/papers/<paper_id>/` 中每篇论文必须有 DOI；metadata 不完整的 `paper_raw` 保留在 `paper_raw`，不得入库。
- LLM/curator 只能补 metadata 空字段，不能编造 DOI，不能覆盖非空 DOI。
- 全局 `references.bib` 已移除；写作 per-job `references.bib` 由 `bibtex_from_metadata` 从 metadata 逐篇生成。
- JSON 写入必须原子化：filelock、临时文件、`os.replace`。
- 外部输入的 id、文件名和路径必须校验并通过 safe child 解析。
- commit 前必须本地查重：重复 DOI、PDF sha、标题/作者/年份或正文指纹不得新建正式 paper。
- `paper_number` 为 16 位长期编号，只递增不回收。
- 测试不得访问真实网络；网络 provider 必须 mock。
- 每次代码改动后必须运行测试并生成 `mineru_snapshot.zip`。

## 唯一正式流程

```text
data/raw/*.pdf 或网络 metadata
-> data/paper_raw/<000001>/
-> metadata match 或 manual confirm
-> PDF attach 或 fetch
-> MinerU convert
-> curation
-> commit 到 data/papers/<paper_id>/
-> rebuild all.catalog
-> API 按 paper_number 复制到 data/llm_work/
```

## 正式目录

```text
data/papers/<paper_id>/<paper_id>.metadata.json
data/papers/<paper_id>/<paper_id>.catalog.json
data/papers/<paper_id>/<paper_id>.md
data/papers/<paper_id>/<paper_id>.pdf
data/papers/<paper_id>/images/
data/papers/<paper_id>/<16位编号>.paper.number
```

## 验收命令

```bash
python scripts/rebuild_all_catalog.py --apply
python scripts/validate_v2_library.py
pytest -q
python scripts/pack_repo.py
```
