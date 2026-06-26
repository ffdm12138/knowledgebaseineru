# CLAUDE.md — literature_review_writer skill

本 skill 在 MinerU 文献资产库上做博士论文级综述写作。**不恢复 ChromaDB / embedding / 语义搜索**。

## 工作流程（严格按序）

1. **建任务**：`python scripts/write_review.py create --topic "..."`（或 `--input doc.md`），生成 `write/00N_<slug>/`。
2. **归一化**：`normalized_task.md` 已自动建骨架，需用大模型补全（topic_parser 返回的 prompt）。
3. **目录匹配**：`match --job ...` → 读 `data/catalog/literature_catalog.json`，生成匹配 prompt + `catalog_candidates.json` / `selected_papers.json`。用大模型跑 prompt，把入选文献回填 `selected_papers.json`。**禁止盲读所有全文**。
4. **全文精读**：`deep-read --job ... --papers <pid> <pid>` → 读 `data/papers/<pid>/paper.md`，生成 `paper_notes/<pid>.md`、`evidence_table.md`、`figure_candidates.md` + 精读 prompt。用大模型填实笔记。
5. **故事线**：`story --job ...` → 基于笔记+证据生成 `story_plan.md`、`chapter_outline.md` + prompt。
6. **TeX 生成**：`tex --job ...` → 生成 `main.tex`、`sections/introduction.tex`、`sections/method.tex`、`references.bib`（从全局 `data/catalog/references.bib` 按 selected 抽取）+ 写作 prompt。用大模型填实正文。
7. **图片**：`figures --job ...` → 把被引用图从 `data/papers/<pid>/images/` 复制到 `write/<job>/figures/<pid>/`，记 README。TeX 用相对路径 `../figures/<pid>/<img>`。
8. **校验**：`validate --job ...` → 检查文件齐全、`\cite{}` 一致、`\includegraphics` 存在、图源 README、run_meta。

## 硬性要求

- 先读 `literature_catalog.json` 再决定读哪些全文，不允许直接盲读全部。
- 所有引用用 catalog 中的 `bib_key`（`\cite{bib_key}`），禁止裸作者年份。
- 所有图片来自 `data/papers/<pid>/images/`；进 TeX 必须复制到 `figures/`，记原路径。
- 不允许编造文献、图号、公式、DOI、引用。
- introduction / method 按博士论文标准（见 templates），不写短论文压缩风。
- 所有 prompt 只生成文本，不内置 LLM client；LLM 步骤由人手动跑。

## 博士论文写作标准

### Introduction（8 步递进）
宏观重要性 → 气候/工程/灾害/模型意义 → 已有认识 → 实验/观测/理论/模型各自解决什么 → 关键机制链条 → 当前方法不足 → 本研究切入点 → 目标与贡献。
禁止：简单堆文献、只写"某某研究了什么"、无矛盾递进、无问题导向引出方法、无研究空缺。

### Method
综述型：文献筛选原则 → 分类框架 → 机制分析框架 → 模型比较框架 → 证据整合方法 → 图表公式整理原则。

## 文件结构（每任务）

```
write/00N_<slug>/
├── input/{research_input.md, normalized_task.md}
├── planning/{catalog_candidates.json, reading_plan.md, selected_papers.json, story_plan.md, chapter_outline.md}
├── reading/{paper_notes/<pid>.md, evidence_table.md, figure_candidates.md}
├── tex/{main.tex, sections/{introduction.tex, method.tex}, references.bib}
├── figures/<pid>/{img, README.md}
├── logs/{prompts/01..04_*.md, run_meta.json}
└── README.md
```
