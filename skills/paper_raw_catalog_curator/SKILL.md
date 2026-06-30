# Paper Raw Catalog Curator Skill

Use this skill to curate a single `data/paper_raw/<source_id>/` folder: generate a
v2.0 content-only catalog from MinerU Markdown/PDF/images.

## Role

你是 paper_raw catalog curator。你的任务不是写综述，而是为快速筛选精读文献生成 catalog。

## 事实源与边界

权威边界见 `docs/PROJECT_CONTRACT.md`；本 skill 不与之冲突。

- `metadata` 是书目信息事实源（BibTeX/书目）。
- `catalog` 是筛选事实源（大模型快速判断是否值得精读）。
- 本 skill **不是 metadata resolver**；不生成 metadata patch，不修改 metadata 字段，
  不生成 DOI/作者/年份/期刊/venue/container/publication/BibTeX。
- 若发现 metadata 疑似错误，写入 catalog 的 `content_notes.warnings`，不要直接改。
- 不得编造 DOI；`metadata.identifiers.doi` 已有值时不得覆盖。
- 如果 metadata 缺 DOI，本 skill 只能提示需要可靠 metadata match 或人工补 DOI，不能生成可入库结果。
- 不得生成 16 位 `paper_number`。
- 不得移动或修改 `data/papers` 正式库；不得入库。
- catalog curator 必须在转换完成产出 md 之后运行（读 md 生成 catalog）。
- 正式 commit 到 `data/papers/` 需要 metadata 和 catalog **都**通过校验（
  metadata 要求 `metadata_match.status` 为 matched/manual_confirmed、DOI 非空、
  title/author/year/venue 齐全；catalog 要求 schema v2.0、无禁止书目字段）。
- 不确定的字段留空，不要编造。

## 输入

```
data/paper_raw/<source_id>/
  <source_id>.metadata.json
  <source_id>.pdf
  <source_id>.md
  images/
```

## 输出

在同一个 `data/paper_raw/<source_id>/` 文件夹下输出：

1. `<source_id>.catalog.json` —— 符合 `catalog_schema.json`（**v2.0，content-only**）。

> catalog curator **不生成 metadata patch**。书目字段（DOI/作者/期刊/年份/BibTeX/citation_key）
> 由 metadata resolver / enrichment 负责。如需补 metadata 空字段，交给
> `scripts/resolve_paper_raw_metadata.py` 或 metadata enrichment，不要在 catalog 里处理。

## catalog v2.0 填写要点（只填正文内容，禁止书目字段）

- `content_identity.content_title`：从 Markdown 正文标题/首屏提取的标题候选（**非 canonical title**）。
- `classification`：`primary_domain`、`secondary_domains`、`topic_tags`、`methods_tags`、
  `phenomena_tags`、`material_tags`、`model_tags`。
- `screening`：`read_decision`(`must_read`/`maybe_read`/`skip`)、`relevance_score`(1-5)、
  `novelty_score`、`method_quality_score`、`reason`。
- `research_card`：`research_problem` / `core_question` / `hypothesis_or_objective` / `study_object` /
  `method_summary` / `data_or_experiment` / `main_findings`(列表) / `mechanisms` / `limitations` /
  `usefulness_for_user`。
- `evidence_profile`：`key_claims` / `important_equations` / `important_figures` / `important_tables` /
  `quoted_terms` / `page_or_section_evidence`。
- `content_notes`：`short_summary` / `long_summary` / `possible_use_in_writing` / `open_questions` / `warnings`。
- `provenance`：`generated_from='mineru_markdown'`、`markdown_path`、`generated_at`、`generator`、`notes`。

### 禁止字段（递归检查，命中即校验失败）

catalog 任何层级都不得出现：`doi`、`authors`、`author`、`first_author`、`journal`、`venue`、
`publisher`、`container`、`publication`、`year`、`volume`、`issue`、`pages`、`article_number`、
`url`、`publisher_url`、`repository_url`、`bibtex`、`citation_key`、`identifiers`、`metadata_match`、
`crossref`、`openalex`、`semantic_scholar`、`external_metadata`。如正文中出现 DOI，只能写进
`evidence_profile.page_or_section_evidence` 或 `content_notes.warnings`，不得写入 catalog 顶层。

## paper_id 命名规则

`paper_id = 年份_第一作者姓氏_short_name_zh`（snake_case）。由项目在 `apply` 时**只从 metadata**
（`metadata.year` + `metadata.authors[0].family` + `metadata.title.short_zh`）自动生成，你不要输出
`paper_id`，也不要把 short_name_zh/year/author 写进 catalog。

## 接入

- 生成 prompt：`python scripts/curate_paper_raw.py --source-id <id> --dry-run`
  （在文件夹下写出 `curation_prompt.md`）。
- 应用结果：`python scripts/curate_paper_raw.py --source-id <id> --catalog <path> --apply`。

注意：curation prompt 和 apply 都要求 `metadata_match.status` 为 `matched` 或
`manual_confirmed`，且 `metadata.identifiers.doi` 非空。网络/搜索 metadata
导入必须有 DOI；手动 PDF 可以先无 DOI，但不能进入 curation/commit。

Schema 定义见 `catalog_schema.json`（v2.0），示例见 `examples/`。
