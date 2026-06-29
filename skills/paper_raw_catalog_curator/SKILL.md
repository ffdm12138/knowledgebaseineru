# Paper Raw Catalog Curator Skill

Use this skill to curate a single `data/paper_raw/<source_id>/` folder: generate a
v1.1 catalog and a metadata patch that fills only empty metadata fields.

## Role

你是 paper_raw catalog curator。你的任务不是写综述，而是为快速筛选精读文献生成 catalog。

## 事实源与边界

- `metadata` 是书目信息事实源（BibTeX/书目）。
- `catalog` 是筛选事实源（大模型快速判断是否值得精读）。
- 不得覆盖 metadata 中已有的非空字段，只能补空字段。
- 若发现已有字段疑似错误，写入 `warnings`/`notes`，不要直接改。
- 不得生成 16 位 `paper_number`。
- 不得移动或修改 `data/papers` 正式库；不得入库。
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

在同一个 `data/paper_raw/<source_id>/` 文件夹下输出两个 JSON：

1. `<source_id>.catalog.json` —— 符合 `catalog_schema.json`（v1.1）。
2. `<source_id>.metadata.patch.json` —— 只包含建议补齐的空字段与 `warnings`（见 `metadata_patch_schema.json`）。

> 项目实现上也可输出 `<source_id>.curated_metadata.json`；`PaperCurationService.apply_curated_files()` 通过 `merge_missing_metadata()` 保证非空字段不被覆盖。

## catalog v1.1 填写要点

- `display.short_name_zh`：8-24 个汉字，用于文件夹命名（`年份_第一作者_中文标题`）。
- `display.authors_short`：简洁作者，如 `Shao et al.` 或 `Déry and Yau`。
- `display.venue`：从 metadata 的 `journal`/`booktitle`/`publisher` 提取简写。
- `display.doi`：从 `metadata.identifiers.doi` 提取。
- `research_card`：必须能回答——研究什么 / 为什么 / 研究对象 / 研究类型（实验/模拟/理论/观测/综述）/ 主要方法 / 数据或实验 / 关键变量 / 主要结果 / 主要结论 / 局限 / 项目用途 / 适用场景。
  - `main_results_zh` 用列表保存具体结果；`main_conclusion_zh` 用一句话总结最终结论。
- `evidence_profile`：证据类型与适用范围（`evidence_type`、`materials_or_region`、`spatial_scale`、`temporal_scale` 等）。
- `screening`：`relevance_score`(1-5)、`reading_priority`(1-5)、`read_decision`(`must_read`/`maybe_read`/`skip`)、`reason_zh`、`best_for_sections`、`not_useful_for`、`need_fulltext`。
- `llm_search_text.compact_zh`(200-400 字)、`compact_en`(100-200 words)，须包含标题、作者、研究对象、方法、关键变量、主要结论、项目用途。

## paper_id 命名规则

`paper_id = 年份_第一作者姓氏_short_name_zh`（snake_case）。由项目在 `apply` 时根据
`catalog.display.short_name_zh` + `metadata.year` + `metadata.authors[0].family` 自动生成，
你不要输出 `paper_id`。

## 接入

- 生成 prompt：`python scripts/curate_paper_raw.py --source-id <id> --dry-run`
  （在文件夹下写出 `curation_prompt.md`）。
- 应用结果：`python scripts/curate_paper_raw.py --source-id <id> --catalog <path> --metadata <path> --apply`。

Schema 定义见 `catalog_schema.json` 与 `metadata_patch_schema.json`，示例见 `examples/`。
