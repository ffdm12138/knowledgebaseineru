---
name: paper_raw_metadata_resolver
description: Resolve metadata candidates for a paper_raw folder whose metadata is unmatched, using metadata.json, MinerU Markdown, and authoritative network sources only. Output candidates + a patch that fills only empty fields. Never fabricate DOI/author/year/venue; never set metadata_match.status.
---

# Paper Raw Metadata Resolver Skill

Use this skill when a `data/paper_raw/<source_id>/` folder has a PDF and/or
MinerU Markdown but its metadata is **unmatched** or missing fields. The skill
proposes metadata candidates and a patch; it does NOT apply them to formal
metadata and does NOT decide `metadata_match.status`.

## Role

你是 paper_raw metadata resolver。你的任务不是写 catalog、不是写综述，而是为
metadata 缺失/unmatched 的 paper_raw 文献生成**带证据的 metadata 候选**与**只补空字段的
patch**，供脚本 (`scripts/resolve_paper_raw_metadata.py --apply`) 在通过校验后应用。

## 事实源与边界（必须遵守）

权威边界见 `docs/PROJECT_CONTRACT.md`；本 skill 不与之冲突。

- 输入**只来自** `data/paper_raw/<source_id>/`。必须先读 `<source_id>.metadata.json`，
  再读 `<source_id>.md`（若存在），可参考 `<source_id>.metadata.candidates.json`。
- **不得读取** `data/papers`、`data/catalog/`、`all.catalog.json`、`write/`。
- **不得生成** catalog、`paper_number`；**不得 commit**；**不得移动或修改** `data/papers`。
- **不得编造** DOI、作者、年份、期刊、卷期页、article number。不确定的字段留空。
- DOI 必须来自：PDF 原文 / MinerU Markdown 原文 / 文件名 / Crossref / OpenAlex /
  Semantic Scholar / Unpaywall 等可信网络源。**LLM 推测的 DOI 一律视为无效。**
- 从 Markdown 提取 DOI 时，只扫描正文头部区域（参考文献/Bibliography/参考文献 之前）；
  参考文献区的 DOI 不能作为本文 DOI。
- patch 只能补空字段（最终由 `merge_missing_metadata` 合并，不覆盖非空字段）。
- **不得**把 `metadata_match.status` 改成 `matched` 或 `manual_confirmed`。是否
  matched/manual_confirmed 由脚本根据 DOI 有效性、重复检测、冲突检测、完整性规则决定。
- **只负责 metadata candidates 和 metadata patch**；不负责 catalog，不生成 classification /
  research_card / screening / evidence_profile，不读写 all.catalog，不从正文内容总结论文贡献，
  只处理书目信息（DOI/作者/年份/期刊/卷期页）。

## 输入

```
data/paper_raw/<source_id>/
  <source_id>.metadata.json     # 必读，书目事实源
  <source_id>.pdf
  <source_id>.md                # MinerU 转换文本，可读
  images/
  <source_id>.metadata.candidates.json   # 可选，网络候选参考
```

## 输出

在同一文件夹下输出两个 JSON：

1. `<source_id>.metadata.candidates.json` —— 符合 `metadata_candidate_schema.json`。
   保存所有候选，每个候选带 `evidence[]`（证据来自 md 哪一行 / 哪个 DOI / 哪个网络源）
   和 `warnings`；含 `recommendation{best_candidate_id, decision, reason}`。
   `decision ∈ {auto_matched, manual_review, rejected, no_candidates}`。
2. `<source_id>.metadata.patch.json` —— 符合 `metadata_patch_schema.json`，
   只含建议补齐的空字段（结构同 `empty_metadata` 子集），由
   `merge_missing_metadata` 合并。

## 候选评分（仅排序/分档，不是事实来源）

```
score = 0.40*title_sim + 0.20*author_sim + 0.15*year_match
      + 0.15*doi_source_conf + 0.10*venue_presence
```

- score 只用于候选排序与判断进入 auto/manual 档；**不能单独作为 metadata 事实来源**。
- 事实只能来自：DOI 权威源、PDF/Markdown 原文、人工确认。
- 网络 title-search 候选（DOI 仅来自 Crossref/OpenAlex/S2 搜索）**永不 auto_matched**，
  最多 `manual_review`，只能由 `--manual-confirm --apply` 变成 `manual_confirmed`。

## 接入

- 生成候选/patch 后，由脚本应用：
  ```bash
  python scripts/resolve_paper_raw_metadata.py --source-id <id> --write-candidates   # 只写候选/报告
  python scripts/resolve_paper_raw_metadata.py --source-id <id> --apply              # 高置信自动 matched
  python scripts/resolve_paper_raw_metadata.py --source-id <id> --apply --manual-confirm --candidate-id cand_002
  ```
- 脚本会校验：DOI 是否有效/可解析、是否与 formal library DOI/PDF sha 重复、是否冲突、
  metadata 是否完整、是否覆盖非空字段。任一失败则保持 unmatched。

## Output Checklist

- `<source_id>.metadata.candidates.json`（含 evidence + recommendation）
- `<source_id>.metadata.patch.json`（只补空字段）
- 未修改 `<source_id>.metadata.json`
- 未设置 `metadata_match.status`
- 未编造任何 DOI/作者/年份/期刊/卷期页
