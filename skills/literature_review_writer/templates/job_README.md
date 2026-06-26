# {{job_id}}

综述写作任务。

## 输入
- `input/research_input.md`：用户原始研究内容
- `input/normalized_task.md`：归一化研究任务

## 流程产物
- `planning/`：目录匹配、阅读计划、故事线、章节大纲
- `reading/`：精读笔记、证据表、候选图清单
- `tex/`：`main.tex` + `sections/` + `references.bib`（独立可编译）
- `figures/`：被引用图（含图源 README）
- `logs/`：各步 prompt + `run_meta.json`

## 复现
所有 LLM 步骤的 prompt 存于 `logs/prompts/`，手动跑后回填对应文件即可复现。
