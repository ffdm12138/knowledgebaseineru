# catalog_tex_writer

This skill writes from a prepared MinerU v2 writing job. It is intentionally
catalog-first: use `selected_catalog.json` for selection context, copied
`article/<paper_number>/*.catalog.json` for synthesis, and copied
`*.metadata.json` for references.

It must not read `data/papers` directly and must not create bibliography facts
from catalog summaries or Markdown prose.
