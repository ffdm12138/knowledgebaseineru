# Literature Library Manager Skill

Use this skill for pure v2 paper_raw literature library work.

Formal import commands:

```bash
python scripts/stage_raw_pdfs_to_paper_raw.py --apply
python scripts/match_paper_raw_metadata.py --all --apply
python scripts/convert_paper_raw_batch.py --all --apply
python scripts/curate_paper_raw.py --all-ready --dry-run   # 生成 curation prompt
python scripts/curate_paper_raw.py --all-ready --apply     # 应用 catalog + metadata patch
python scripts/commit_paper_raw_to_papers.py --all-ready --apply
python scripts/rebuild_all_catalog.py --apply
python scripts/validate_v2_library.py
```

Curation 由项目级 skill `paper_raw_catalog_curator` 产出 catalog（v1.1）与 metadata patch。

Metadata rules:

- Network/search metadata imports must include DOI before staging.
- Manual PDF imports may start without DOI, but curation and formal commit require `metadata.identifiers.doi`.
- Formal `data/papers/<paper_id>/` entries must have DOI and complete commit metadata.
- LLM/curator output may fill empty metadata fields only; it must not invent DOI or overwrite a non-empty DOI.

按 16 位 `paper_number` 复制精读文献到写作工作区：

```bash
python scripts/copy_paper_to_llm_work.py --paper-number 0000000000000001 --session-id review_001 --apply
```

Network metadata:

```bash
python scripts/stage_network_metadata_to_paper_raw.py --input candidates.jsonl --apply
python scripts/fetch_pdf_for_paper_raw.py --all --apply
```

Facts:

- `data/raw/` is the manual PDF inbox.
- `data/paper_raw/` is the pre-ingest workspace.
- `data/papers/` is formal storage.
- `data/catalog/all.catalog.json` is the API/writing catalog (v1.1 schema).
- `data/catalog/paper_number_ledger.json` owns stable numbering.
- `data/llm_work/` stores copied reading worksets.
- `paper_number` (16 位) is the API/writing primary key.
