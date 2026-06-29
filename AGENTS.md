# AGENTS.md

修改本仓库前必须阅读：

- `docs/PROJECT_CONTRACT.md`
- `README.md`

## 项目定位

本项目是本地文献资产库、AI 可读目录和综述写作工作区。正式入库只允许走 v2 `paper_raw` 工作流。

## 不可违反

- 不做向量库、RAG、embedding 或 ChromaDB。
- 不内置 LLM client；prompt 和写作流程只生成文本或模板。
- 新文献必须先进入 `data/paper_raw/<000001>/`。
- MinerU 只能处理 `data/paper_raw/<000001>/<000001>.pdf`。
- 正式资产只保存到 `data/papers/<paper_id>/`。
- API 和写作只使用本地生成的 `data/catalog/all.catalog.json`、`data/catalog/paper_index.json`、`data/catalog/paper_number_ledger.json` 和正式 paper 文件夹；源码只提交对应 `.template.json` 空模板，不提交真实库索引。
- metadata 管书目信息和 BibTeX；catalog 管阅读价值、分类、主题和筛选。
- commit 前必须本地查重。
- `paper_number` 只递增不回收。
- JSON 写入必须原子化。
- 外部输入路径和 id 必须 validate + safe child。
- 测试不得访问真实网络；外部 metadata/PDF provider 必须 mock。
- 每次代码改动后运行测试并执行 `python scripts/pack_repo.py`。

## 唯一正式流程

```bash
python scripts/stage_raw_pdfs_to_paper_raw.py --apply
python scripts/match_paper_raw_metadata.py --all --apply
python scripts/convert_paper_raw_batch.py --all --apply
python scripts/curate_paper_raw.py --all-ready --apply
python scripts/commit_paper_raw_to_papers.py --all-ready --apply
python scripts/rebuild_all_catalog.py --apply
python scripts/validate_v2_library.py
```

网络 metadata 先运行：

```bash
python scripts/stage_network_metadata_to_paper_raw.py --input candidates.jsonl --apply
python scripts/fetch_pdf_for_paper_raw.py --all --apply
```

然后继续 metadata match、convert、curate、commit。

## 正式资产结构

```text
data/papers/<paper_id>/<paper_id>.metadata.json
data/papers/<paper_id>/<paper_id>.catalog.json
data/papers/<paper_id>/<paper_id>.md
data/papers/<paper_id>/<paper_id>.pdf
data/papers/<paper_id>/images/
data/papers/<paper_id>/<16位编号>.paper.number
```

## 验收

```bash
python scripts/rebuild_all_catalog.py --apply
python scripts/validate_v2_library.py
pytest -q
python scripts/pack_repo.py
```
