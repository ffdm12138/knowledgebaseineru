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

The writing workflow uses the local generated `data/catalog/all.catalog.json`
only as a content-only screening index, then copies selected paper folders into
the job. `selected_catalog.json` is a per-job working snapshot, not the global
catalog. TeX and BibTeX generation must use the copied `article/` metadata, not
direct `data/papers` paths.
