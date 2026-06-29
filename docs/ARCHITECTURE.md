# Architecture

MinerU v2 使用单一入库工作区和单一正式目录。

## Data Flow

```text
raw PDF or network metadata
-> paper_raw source folder
-> metadata matching
-> PDF binding
-> MinerU conversion
-> curation
-> formal paper folder
-> all catalog rebuild
```

## Components

- `src/services/v2_library.py`: allocation, staging, conversion guard, curation, commit, ledger, all catalog, LLM work copy, BibTeX generation.
- `src/catalog.py`: read-only all catalog access and compact catalog text.
- `src/library.py`: formal Markdown and image lookup through all catalog.
- `src/server.py`: v2 read/API work surface; it never commits directly to `data/papers/`.
- `scripts/*paper_raw*.py`: the only formal import CLIs.
- `src/bib.py`: per-paper BibTeX via `bibtex_from_metadata` from `metadata.json` (no global `references.bib`); `src/writer/bib_manager.py` exports a per-job `tex/references.bib`.
- `scripts/copy_paper_to_llm_work.py`: copy formal paper folders to `data/llm_work/<session_id>/<paper_number>/` by 16-digit `paper_number`.

## Facts

- `data/paper_raw/` is the pre-ingest workspace.
- `data/papers/` is the only formal asset storage.
- `data/catalog/all.catalog.json` is the catalog API entry (per-paper catalog schema v1.1).
- `data/catalog/paper_number_ledger.json` owns long-term numbering.
- `data/llm_work/` contains copied paper folders for model-facing work sessions.
