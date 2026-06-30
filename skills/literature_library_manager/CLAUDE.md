# Literature Library Manager

Use only the v2 paper_raw workflow:

```bash
python scripts/stage_raw_pdfs_to_paper_raw.py --apply
python scripts/match_paper_raw_metadata.py --all --apply
python scripts/convert_paper_raw_batch.py --all --apply
python scripts/curate_paper_raw.py --all-ready --dry-run
python scripts/curate_paper_raw.py --all-ready --apply
python scripts/commit_paper_raw_to_papers.py --all-ready --apply
python scripts/rebuild_all_catalog.py --apply
python scripts/validate_v2_library.py
```

Curation 产出由项目级 skill `paper_raw_catalog_curator` 生成（catalog v2.0 content-only）。
metadata patch 由 metadata resolver / enrichment 负责。
`copy_paper_to_llm_work.py` / `data/llm_work` 仅为 legacy/API compatibility 精读复制流程：
`python scripts/copy_paper_to_llm_work.py --paper-number <16位> --session-id <id> --apply`。
writing v0.1 主流程不要使用 `data/llm_work`，主路径是 `write/jobs/<job_id>/article/<paper_number>/`。
