# LLM Usage Workflow

> **Legacy notice.** This document describes the older `write_review.py` /
> `data/llm_work` workflow. The frozen writing v0.1 main path is catalog-first:
> `write/jobs/<job_id>/article/` -> TeX/BibTeX -> `check_write_tex_project.py`
> -> `check_write_quality_text.py`. Do not use this legacy workflow unless
> explicitly requested.

The repository does not call any LLM. It prepares model-readable assets and prompts.

## Metadata Boundaries

Only formal papers with complete metadata enter `data/papers/`. In particular,
`metadata.identifiers.doi` is required before curation and commit. Network/search
metadata imports without DOI are rejected before `paper_raw` allocation; manual PDF
imports may start without DOI but remain outside the formal library until DOI is
matched or manually confirmed.

Curator and writing prompts may fill empty metadata fields but must not invent DOI
or overwrite a non-empty DOI. References are generated from metadata only.

## Read Selection

Use `data/catalog/all.catalog.json` as the compact content inventory. Each item carries ONLY catalog content (content_identity, classification, screening, research_card, evidence_profile, content_notes, asset_refs) and a stable `paper_number` — it does NOT embed bibliographic metadata (DOI/authors/year/journal). To cite or render bibliography, load `data/papers/<paper_number>/...metadata.json` via `data/catalog/paper_index.json` (or `src.services.paper_library.PaperLibrary`). The catalog is the screening fact source — the model can decide whether to read full text from the catalog alone.

## Full-Text Copy

Copy a formal paper folder into an LLM session (API or CLI):

```bash
curl -X POST http://127.0.0.1:8080/papers/by-number/0000000000000001/copy-to-llm-work \
  -H "Content-Type: application/json" \
  -d '{"session_id":"session_001"}'

# or CLI
python scripts/copy_paper_to_llm_work.py --paper-number 0000000000000001 --session-id session_001 --apply
```

The result is:

```text
data/llm_work/<session_id>/<paper_number>/
```

`data/papers/` is never modified; the model only reads and writes inside `data/llm_work/`.

## Writing

Use `scripts/write_review.py` to create jobs, match catalog entries, confirm selected papers, generate deep-reading prompts, build story plans and produce TeX templates. Every model step is manual: run the generated prompt externally and paste results back into the generated files.
