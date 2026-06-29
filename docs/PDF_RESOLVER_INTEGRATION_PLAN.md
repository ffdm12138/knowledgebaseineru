# PDF Resolver Integration

The resolver chain is integrated only through `fetch_pdf_for_paper_raw.py`.

## v2 Integration

1. Create metadata sources with `stage_network_metadata_to_paper_raw.py`.
2. Run `fetch_pdf_for_paper_raw.py --all --apply`.
3. Run metadata match, conversion, curation and commit.

Resolvers return URLs or temporary local files. The v2 fetch CLI performs the final attachment into the matching `paper_raw` source folder.
