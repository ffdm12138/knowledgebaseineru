# CLAUDE.md

This folder contains the AI-readable literature catalog for the local knowledge base.

## Purpose

`literature_catalog.json` is not a search index.
It is a structured literature map used by an LLM to decide:

1. which papers are relevant to a research question;
2. which full-text Markdown files should be opened;
3. how papers contribute to a scientific story;
4. how each paper may be cited in a review, proposal, thesis, or manuscript.

The catalog should help the model reason at the paper level before reading full text.

## Files

```text
data/catalog/
├── literature_catalog.json
└── CLAUDE.md
```

`literature_catalog.json` must remain valid JSON.

## Required top-level structure

```json
{
  "version": "0.1",
  "description": "AI-readable literature catalog. Each item summarizes one paper and guides full-text selection.",
  "papers": []
}
```

## Required fields for each paper

Each item in `papers` must contain:

```json
{
  "paper_id": "",
  "title": "",
  "authors": [],
  "year": null,
  "venue": "",
  "doi": "",
  "raw_pdf": "",
  "markdown": "",
  "images_dir": "",
  "status": "unsummarized",
  "ai_summary": {
    "one_sentence": "",
    "background_problem": "",
    "research_question": "",
    "method": "",
    "data_or_experiment": "",
    "main_findings": "",
    "key_equations_or_models": [],
    "important_figures": [],
    "limitations": "",
    "relevance_to_my_work": "",
    "possible_use_in_paper": ""
  },
  "tags": {
    "topic": [],
    "method": [],
    "material_or_region": [],
    "variables": [],
    "model_names": []
  },
  "selection_hints": {
    "read_when_question_contains": [],
    "do_not_use_for": [],
    "priority": 3
  },
  "notes": ""
}
```

## Writing rules

* Do not invent bibliographic information. Leave unknown fields empty.
* Keep `paper_id` stable once created.
* Use lowercase snake_case for `paper_id`.
* `paper_id` should usually follow: `firstauthor_year_shorttopic`.
* `one_sentence` must summarize the paper in one clear sentence.
* `background_problem` should explain the scientific problem the paper responds to.
* `research_question` should state what the paper tried to answer.
* `method` should describe the experimental, observational, theoretical, or numerical method.
* `data_or_experiment` should record datasets, instruments, cases, materials, boundary conditions, or experiment settings when available.
* `main_findings` should be specific, not generic.
* `key_equations_or_models` should list named equations, parameterizations, empirical models, or physical assumptions.
* `important_figures` should identify figures worth opening later and why.
* `limitations` should record assumptions, missing validation, scale limits, material limits, or uncertainty.
* `relevance_to_my_work` should explain how this paper relates to the user's research, not just the paper itself.
* `possible_use_in_paper` should state where it could be used: introduction, method, validation, discussion, mechanism explanation, comparison, or future work.
* `read_when_question_contains` should contain concepts that should trigger full-text reading of this paper.
* `do_not_use_for` should prevent false matches.
* `priority` should be 1 to 5:

  * 5 = core paper, almost always read when related;
  * 4 = important supporting paper;
  * 3 = useful background;
  * 2 = narrow use;
  * 1 = rarely needed.

## Style

Use concise technical Chinese unless the original field is a title, DOI, or path.
Avoid vague phrases such as "this paper is important" unless the reason is stated.
Prefer mechanism-level summaries: what problem, what method, what result, what limitation, and how it helps the user's work.

## Full-text selection workflow

When answering a research question:

1. Read `literature_catalog.json`.
2. Select candidate papers based on `ai_summary`, `tags`, and `selection_hints`.
3. Explain why each selected paper should be opened.
4. Open the selected papers' Markdown files.
5. Use full-text evidence to write the final answer.
6. Do not rely only on the catalog summary for detailed claims.

## Do not

* Do not add embeddings.
* Do not create ChromaDB indexes.
* Do not split papers into chunks for semantic search.
* Do not duplicate PDFs outside `data/raw/`.
* Do not keep MinerU JSON sidecars as long-term knowledge assets unless explicitly requested.
* Do not treat the catalog as a replacement for full-text reading.
