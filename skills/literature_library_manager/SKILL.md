# Literature Library Manager Skill

Use this skill for pure v2 `paper_raw` literature library work.

Formal import commands（manual PDF path — convert first, then resolve metadata from converted md）:

```bash
set MINERU_REQUIRE_GPU=true
set CUDA_VISIBLE_DEVICES=0
set MINERU_RUNNER=cli_api_proxy
set MINERU_API_URL=http://127.0.0.1:8000
python scripts/stage_raw_pdfs_to_paper_raw.py --move --apply
python scripts/convert_paper_raw_batch.py --all --apply
python scripts/resolve_paper_raw_metadata.py --all-unmatched --apply --allow-network
python scripts/curate_paper_raw.py --all-ready --dry-run
python scripts/curate_paper_raw.py --all-ready --apply
python scripts/commit_paper_raw_to_papers.py --all-ready --apply
python scripts/rebuild_all_catalog.py --apply
python scripts/validate_v2_library.py
```

Network metadata path（metadata 已带 DOI，先行）: stage_network_metadata_to_paper_raw.py
→ fetch_pdf_for_paper_raw.py → convert → curate → commit → rebuild → validate.
手动 PDF 路径 metadata resolver 依赖转换后的 md，必须在 MinerU 转换之后运行（先转换，再解析）。

Writing workspace creation:

```bash
python scripts/create_write_job.py --job-id review_001 --paper-numbers 0000000000000001
```

Manual PDF staging SOP:

- `data/raw/` is the manual PDF queue / raw 是待处理队列.
- Normal manual ingest uses `stage_raw_pdfs_to_paper_raw.py --move --apply`.
- Successful staging consumes PDFs from `data/raw/` and places them under `data/paper_raw/<source_id>/<source_id>.pdf`.
- Copy mode is only for debugging, backup, tests, or explicit one-off inspection.
- MinerU conversion requires GPU / MinerU 正式转换必须使用 GPU. Staging does not need GPU, but
  `convert_paper_raw_batch.py` does. Default runtime requires GPU unless `MINERU_ALLOW_CPU=true`
  or `MINERU_REQUIRE_GPU=false` is explicitly set for debugging.
- Batch conversion should use persistent `mineru-api` via `MINERU_RUNNER=cli_api_proxy` and
  `MINERU_API_URL=http://127.0.0.1:8000`.

Facts:

- `data/raw/` is the manual PDF queue.
- `data/paper_raw/` is the pre-ingest workspace.
- `data/papers/` is formal storage.
- `data/catalog/all.catalog.json` is the local generated content-only writing index.
- `data/catalog/paper_number_ledger.json` owns stable numbering.
- `write/jobs/<job_id>/article/<paper_number>/` is the writing article workspace.
- `metadata.json` is the bibliographic source of truth for BibTeX.
- `catalog.json` and `all.catalog.json` are content-only.
