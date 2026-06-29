# CLAUDE.md

本文件与 `AGENTS.md` 同源。开始修改前阅读：

- `docs/PROJECT_CONTRACT.md`
- `README.md`

本仓库只保留纯 v2 `paper_raw` 入库链路。不要加入向量检索、RAG、embedding、LLM client 或绕过 `paper_raw` 的正式入库入口。

正式流程：

```bash
python scripts/stage_raw_pdfs_to_paper_raw.py --apply
python scripts/match_paper_raw_metadata.py --all --apply
python scripts/convert_paper_raw_batch.py --all --apply
python scripts/curate_paper_raw.py --all-ready --apply
python scripts/commit_paper_raw_to_papers.py --all-ready --apply
python scripts/rebuild_all_catalog.py --apply
python scripts/validate_v2_library.py
```

正式事实源：

- `data/papers/<paper_id>/`
- `data/catalog/all.catalog.json`
- `data/catalog/paper_number_ledger.json`
- `data/llm_work/`

每次代码改动后运行：

```bash
python scripts/rebuild_all_catalog.py --apply
python scripts/validate_v2_library.py
pytest -q
python scripts/pack_repo.py
```
