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

Curation 产出由项目级 skill `paper_raw_catalog_curator` 生成（catalog v1.1 + metadata patch）。
按 `paper_number` 复制精读文献：`python scripts/copy_paper_to_llm_work.py --paper-number <16位> --session-id <id> --apply`。
