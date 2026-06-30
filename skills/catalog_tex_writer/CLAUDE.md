# Claude Notes

This is the only default article-writing skill. It is:
- not an ingest skill
- not a metadata resolver
- not a catalog curator
- not a legacy llm work workflow

Read only:
- `write/jobs/<job_id>/selected_catalog.json`
- `write/jobs/<job_id>/article/<paper_number>/`

Write only:
- `write/jobs/<job_id>/tex/`
- `write/jobs/<job_id>/references.bib`
- `write/jobs/<job_id>/writing_report.json` or similar job-local reports

- Start with `selected_catalog.json`.
- Stay inside the prepared `write/jobs/<job_id>/` directory.
- Use copied `article/` metadata for BibTeX and citation keys.
- Never use direct `data/papers` paths in TeX.
- After writing, run the TeX project checker.
