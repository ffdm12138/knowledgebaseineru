# literature_review_writer

MinerU 文献资产库上的博士论文级综述写作 skill。

## 它做什么

输入一段研究内容或一个 Markdown 项目文档，输出一个独立、可编译、可追溯的 LaTeX 写作项目：

```
研究内容 → 读 literature_catalog.json 匹配文献 → 精读全文 → 组织故事线 → 写 introduction/method → 独立 LaTeX 项目
```

## 核心原则

- 不用向量检索，用 catalog 目录级匹配 + 全文精读。
- 每个结论可回到 `paper_id` / `paper.md` / BibTeX 引用。
- 引用图必须复制到任务目录，TeX 用相对路径。
- 所有 LLM 步骤只生成 prompt，不内置 LLM。

## 快速开始

```bash
conda activate mineru
python scripts/write_review.py create  --topic "风吹雪升华参数化的发展脉络"
python scripts/write_review.py match   --job 001_风吹雪升华参数化发展脉络
# 用大模型跑 logs/prompts/01_catalog_matching_prompt.md，回填 planning/selected_papers.json
python scripts/write_review.py deep-read --job 001_风吹雪升华参数化发展脉络 \
    --papers 1999_dery_吹雪体相模型 2025_huang_雪粒破碎促进升华
python scripts/write_review.py story  --job 001_风吹雪升华参数化发展脉络
python scripts/write_review.py tex    --job 001_风吹雪升华参数化发展脉络
python scripts/write_review.py figures --job 001_风吹雪升华参数化发展脉络
python scripts/write_review.py validate --job 001_风吹雪升华参数化发展脉络
```

也可通过 API（见 `src/server.py` 的 `/write/jobs*`）或 Web UI 操作。

## 依赖

- 已有的 `data/papers/`、`data/catalog/literature_catalog.json`、`data/catalog/references.bib`。
- `src/writer/` 包、`src/bib.py`、`scripts/write_review.py`、`scripts/validate_write_job.py`。

详细流程规则见 `CLAUDE.md`。
