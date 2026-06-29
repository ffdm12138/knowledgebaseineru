# literature_review_writer

MinerU 文献资产库上的博士论文级综述写作 skill。

## 严格多阶段工作流

```
create → match → confirm-papers → deep-read → mark-deep-read
       → story → mark-story → tex → mark-tex → copy-figures → validate
```

**核心铁律**：prompt_generated ≠ content_filled；candidates ≠ selected_papers；template_generated ≠ content_filled；默认不覆盖已有内容；validate 通过才算完成。

所有 LLM 步骤只生成 prompt/模板，由人手动跑后回填；`mark-*` 校验非模板后才标记完成。

## 快速开始

```bash
conda activate mineru
python scripts/write_review.py create         --topic "风吹雪升华参数化的发展脉络"
python scripts/write_review.py match          --job 001_风吹雪升华参数化
# 跑 logs/prompts/01_catalog_matching_prompt.md，确认文献
python scripts/write_review.py confirm-papers --job 001_风吹雪升华参数化 \
    --papers 1999_dery_吹雪体相模型 2025_huang_雪粒破碎促进升华
python scripts/write_review.py deep-read      --job 001_风吹雪升华参数化
# 跑 02_deep_reading_prompt.md，填 paper_notes/evidence_table
python scripts/write_review.py mark-deep-read --job 001_风吹雪升华参数化
python scripts/write_review.py story          --job 001_风吹雪升华参数化
# 跑 03_storyline_prompt.md，填 story_plan
python scripts/write_review.py mark-story     --job 001_风吹雪升华参数化
python scripts/write_review.py tex            --job 001_风吹雪升华参数化
# 跑 04_tex_writing_prompt.md，填 introduction/method（删 TEMPLATE_ONLY 标记）
python scripts/write_review.py mark-tex       --job 001_风吹雪升华参数化
python scripts/write_review.py copy-figures   --job 001_风吹雪升华参数化 \
    --figures 1999_dery_吹雪体相模型:某图.jpg
python scripts/write_review.py validate       --job 001_风吹雪升华参数化
```

也可通过 `/write/jobs*` API（行为与 CLI 一致）。

## 子命令与前置条件

| 子命令 | 设置状态 | 前置 |
|--------|----------|------|
| create | status=created | — |
| match | catalog_match_prompt_generated | — |
| confirm-papers | catalog_selection_confirmed | — |
| deep-read | deep_read_prompt_generated | catalog_selection_confirmed |
| mark-deep-read | deep_read_notes_filled | 笔记非模板 |
| story | story_prompt_generated | deep_read_notes_filled |
| mark-story | story_plan_filled | story_plan 非模板 |
| tex | tex_template_generated, bib_exported | story_plan_filled（template-only 除外）|
| mark-tex | tex_content_filled | 正文非模板、引用一致 |
| copy-figures | figures_copied | — |
| validate | validated, status=validated | 全量校验 0 fatal |

## 依赖

- `data/papers/`、`data/catalog/all.catalog.json`（v2 catalog 事实源）
- per-job `references.bib` 由 `src/bib.py` 从 `metadata.json` 经 `bibtex_from_metadata` 逐篇生成
- `src/writer/` 包、`src/bib.py`、`scripts/write_review.py`、`scripts/validate_write_job.py`

详细规则与状态位含义见 `CLAUDE.md`。
