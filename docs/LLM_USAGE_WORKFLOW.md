# LLM Usage Workflow

The repository does not call any LLM. It prepares model-readable assets and prompts.

## Read Selection

Use `data/catalog/all.catalog.json` as the compact inventory. Each item contains metadata, a v1.1 catalog (display, classification, research_card, evidence_profile, screening, reading_priority, technical_tags, llm_search_text), paths and a stable `paper_number`. The catalog is the screening fact source — the model can decide whether to read full text from the catalog alone.

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
