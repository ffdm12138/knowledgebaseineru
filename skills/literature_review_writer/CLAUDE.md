# CLAUDE.md — literature_review_writer skill

本 skill 在 MinerU 文献资产库上做博士论文级综述写作。**不恢复 ChromaDB / embedding / 语义搜索**。

## 核心铁律（必须遵守）

1. **prompt_generated ≠ content_filled**。生成 prompt/模板只是开始，不算完成。
2. **candidates ≠ selected_papers**。`catalog_candidates.json` 是候选，`selected_papers.json` 初始为空，必须显式确认。
3. **template_generated ≠ content_filled**。TeX 模板生成不等于正文完成。
4. **默认绝不覆盖用户已写内容**。`build_tex` 默认 `force=False`，已有正文跳过。
5. 所有引用必须能追踪到 `bib_key` 和 `references.bib`；用 `\cite{bib_key}`，禁止裸作者年份。
6. 所有图片必须能追踪到原始 `data/papers/<paper_id>/` 路径；进 TeX 必须复制到 `write/<job>/figures/`。
7. **validate 通过后才能标记任务完成**（`validated=True, status="validated"`）。
8. 不允许把 candidates 当 selected；不允许把空模板当完成稿；不能编造图号、DOI、引用、公式；所有强事实必须来自 paper_notes/evidence_table。

## 严格多阶段工作流

每一步都有状态位（run_meta.steps），前置未完成则下一步报错：

```
create                          → status=created
match                           → catalog_match_prompt_generated=True
                                 （selected_papers.json 为空，selection_status=awaiting_llm_or_manual_review）
confirm-papers                  → catalog_selection_confirmed=True
                                 （selected_papers.json confirmed，非空）
deep-read                       → deep_read_prompt_generated=True
                                 （要求 catalog_selection_confirmed；notes 仍是模板）
mark-deep-read                  → deep_read_notes_filled=True
                                 （校验 paper_notes/evidence_table 非模板）
story                           → story_prompt_generated=True
                                 （要求 deep_read_notes_filled；story_plan 仍是模板）
mark-story                      → story_plan_filled=True
                                 （校验 story_plan/chapter_outline 非模板，含必填 section）
tex                             → tex_template_generated=True, bib_exported=True
                                 （要求 story_plan_filled；默认不覆盖已有正文）
mark-tex                        → tex_content_filled=True
                                 （校验 introduction/method 非模板、有 \cite、引用一致）
copy-figures                    → figures_copied=True
                                 （只复制明确指定的图，不自动复制全部候选）
validate                        → validated=True, status=validated
                                 （全量校验，0 fatal 才通过）
```

## 状态位含义（run_meta.steps）

```
catalog_match_prompt_generated   已生成目录匹配 prompt
catalog_selection_confirmed      selected_papers.json 已确认（非空模板）
deep_read_prompt_generated       已生成精读 prompt
deep_read_notes_filled           paper_notes/evidence_table 已实质填充
story_prompt_generated           已生成故事线 prompt
story_plan_filled                story_plan/chapter_outline 已实质填充
tex_template_generated           已生成 TeX 模板
tex_content_filled               introduction/method 已写入正文
figures_copied                   使用的图已复制并记录来源
bib_exported                     references.bib 已按 selected 导出
validated                        validate 全量通过
```

## 博士论文写作标准

### Introduction（8 步递进）
宏观重要性 → 气候/工程/灾害/模型意义 → 已有认识 → 实验/观测/理论/模型各自解决什么 → 关键机制链条 → 当前方法不足 → 本研究切入点 → 目标与贡献。
禁止：简单堆文献、只写"某某研究了什么"、无矛盾递进、无问题导向引出方法、无研究空缺。

### Method
综述型：文献筛选原则 → 分类框架 → 机制分析框架 → 模型比较框架 → 证据整合方法 → 图表公式整理原则。

## TeX 项目解耦

每个 `write/<job>/tex/` 自包含可整体挪走：
- `tex/references.bib` 是任务专属副本（由 `bibtex_from_metadata` 从 `metadata.json` 逐篇生成），不依赖全局 bib/catalog。
- `main.tex` 用相对路径 `\bibliography{references}`、`\input{sections/...}`；图片用 `../figures/<pid>/<img>`。
- `validate` 含 `portability_check`：拦截指向 `data/papers` 等外部路径的引用。

## 文件结构（每任务）

```
write/00N_<slug>/
├── input/{research_input.md, normalized_task.md}
├── planning/{catalog_candidates.json, selected_papers.json, reading_plan.md,
│            story_plan.md, chapter_outline.md}
├── reading/{paper_notes/<pid>.md, evidence_table.md, figure_candidates.md}
├── tex/{main.tex, sections/{introduction.tex, method.tex}, references.bib}
├── figures/<pid>/{img, README.md（含 original_path）}
├── logs/{prompts/01-04_*.md, run_meta.json}
└── README.md
```
