# Literature Library Manager

This is a library / ingest management skill. It may describe how to create a
writing job, but it is not the article-writing skill.

Use only the v2 `paper_raw` ingest workflow. Do not change ingest schema from
this skill.

Manual PDF imports treat `data/raw/` as a queue / raw 是待处理队列. Normal staging
must use `stage_raw_pdfs_to_paper_raw.py --move --apply`, so successful staging
consumes PDFs from raw. Copy mode is only for debugging, backup, tests, or
explicit one-off inspection.

MinerU conversion requires GPU / MinerU 正式转换必须使用 GPU. Manual staging does
not need GPU, but `convert_paper_raw_batch.py` does. Use
`MINERU_REQUIRE_GPU=true`, `CUDA_VISIBLE_DEVICES=0`, `MINERU_RUNNER=cli_api_proxy`,
and `MINERU_API_URL=http://127.0.0.1:8000` for formal batch conversion.
`MINERU_ALLOW_CPU=true` / `MINERU_REQUIRE_GPU=false` is debug-only.

Writing starts by creating an ignored job workspace:

```bash
python scripts/create_write_job.py --job-id review_001 --paper-numbers 0000000000000001
```

The writing article copy lives at:

```text
write/jobs/<job_id>/article/<paper_number>/
```

BibTeX and citation facts come from per-paper `metadata.json`. Catalog files
remain content-only and must not receive DOI, authors, year, journal, venue, or
other bibliographic fields.
