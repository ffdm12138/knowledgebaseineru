# Zotero Integration

Zotero can be used as a metadata source by exporting records to JSONL or BibTeX-derived JSON, then staging them into v2:

```bash
python scripts/stage_network_metadata_to_paper_raw.py --input zotero_candidates.jsonl --apply
```

PDF files exported from Zotero should be copied into `data/raw/` and staged with:

```bash
python scripts/stage_raw_pdfs_to_paper_raw.py --apply
```
