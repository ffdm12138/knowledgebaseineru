"""Search scholarly APIs and write DOI candidates for manual review."""
import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import DISCOVERY_DIR  # noqa: E402
from src.discovery.pipeline import discover_papers  # noqa: E402
from src.library_index import VALID_DOMAINS  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Discover DOI candidates from OpenAlex/Semantic Scholar/Crossref.")
    parser.add_argument("query", help="Chinese or English literature search query.")
    parser.add_argument("--domain", choices=sorted(VALID_DOMAINS), default=None)
    parser.add_argument("--limit-per-query", type=int, default=15)
    parser.add_argument("--max-candidates", type=int, default=50)
    parser.add_argument("--output-dir", type=Path, default=DISCOVERY_DIR / "doi_candidates")
    args = parser.parse_args()

    batch = discover_papers(
        args.query,
        domain_id=args.domain,
        limit_per_query=args.limit_per_query,
        max_candidates=args.max_candidates,
        output_dir=args.output_dir,
    )
    print(f"[OK] candidates: {len(batch.candidates)}")
    for candidate in batch.candidates[:10]:
        doi = candidate.doi or "no DOI"
        print(f"- {candidate.confidence:.2f} | {candidate.year or ''} | {doi} | {candidate.title}")
    print(f"[OK] wrote JSONL + summary under: {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

