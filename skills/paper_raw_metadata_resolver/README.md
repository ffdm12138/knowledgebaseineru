# paper_raw_metadata_resolver

This skill resolves metadata for a `data/paper_raw/<source_id>/` folder whose
metadata is unmatched or incomplete. It is metadata-first, not catalog-first:
it reads `metadata.json` and the MinerU Markdown, proposes scored metadata
candidates with evidence, and emits a patch that fills only empty fields.

It must NOT read `data/papers` or the catalog, must NOT invent DOI/author/year/
venue, and must NOT set `metadata_match.status`. An LLM-guessed DOI is invalid.
The patch is applied by `scripts/resolve_paper_raw_metadata.py --apply`, which
re-checks DOI validity, duplicates, conflicts, and completeness.
