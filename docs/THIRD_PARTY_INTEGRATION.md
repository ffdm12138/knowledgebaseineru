# Third-Party Integration

Third-party tools may provide candidate metadata or PDF URLs, but formal import remains v2-only.

Accepted handoff formats:

- JSON or JSONL candidate metadata for `stage_network_metadata_to_paper_raw.py`.
- Local PDF files placed in `data/raw/` for `stage_raw_pdfs_to_paper_raw.py`.
- DOI or URL metadata consumed by `fetch_pdf_for_paper_raw.py`.

No integration may write directly to `data/papers/`.
