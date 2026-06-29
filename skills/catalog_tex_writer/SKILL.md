---
name: catalog_tex_writer
description: Write a small TeX article from a prepared MinerU v2 write/jobs article workspace using selected_catalog.json, copied catalog files, and metadata-derived BibTeX only.
---

# Catalog TeX Writer

Use this skill when writing from `write/jobs/<job_id>/` after
`scripts/prepare_write_article_workdir.py` has copied formal papers into the
job-local `article/` directory.

## Required Reading Order

1. Read `write/jobs/<job_id>/selected_catalog.json` first.
2. For each selected `paper_number`, read
   `write/jobs/<job_id>/article/<paper_number>/<paper_id>.catalog.json`.
3. Read `write/jobs/<job_id>/article/<paper_number>/<paper_id>.metadata.json`
   for citation facts and BibTeX.
4. Read copied Markdown only when a claim needs full-text confirmation.

Do not read `data/papers` directly. The job-local `article/` copy is the only
paper source for this writing pass.

## Writing Rules

- Output TeX only under `write/jobs/<job_id>/tex/`.
- Generate `references.bib` only from metadata, preferably through
  `bibtex_from_metadata()` or `src.bib.bibtex_for_entry()`.
- Every `\cite{}` key in TeX must exist in `references.bib`.
- Do not guess DOI, authors, venue, volume, pages, or article number.
- Images may only be referenced from copied `article/<paper_number>/images/`
  or files copied into the job TeX project.
- Keep the mini article compact: Abstract, Introduction, Literature Basis, Key
  Methods or Mechanisms, Discussion, Conclusion; roughly 1000-2000 Chinese
  characters or equivalent English; at least three citations.

## Output Checklist

- `tex/main.tex`
- `tex/references.bib`
- `tex/sections/introduction.tex`
- `tex/sections/literature_basis.tex`
- `tex/sections/discussion.tex`
- `reports/write_article_report.json`
- Run `scripts/check_write_tex_project.py --job-id <job_id>` before handoff.
