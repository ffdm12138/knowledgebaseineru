# Write Workspace

`write/` is the local writing workspace for MinerU v2.

Committed files in this directory are only documentation and `.gitkeep`
placeholders. Runtime writing jobs belong under `write/jobs/<job_id>/` and are
ignored by git because they may contain copied PDFs, Markdown, images, TeX
outputs, and reports.

Use:

```bash
python scripts/prepare_write_article_workdir.py --job-id demo --paper-numbers 0000000000000001 0000000000000002 0000000000000003 --apply
python scripts/write_catalog_tex_article.py --job-id demo --title "Mini Review" --language zh --apply
python scripts/check_write_tex_project.py --job-id demo --compile
```

The writing workflow reads formal library facts from
`data/catalog/all.catalog.json` and copies selected paper folders into the job
before writing. TeX and BibTeX generation must use the copied `article/` data,
not direct `data/papers` paths.
