"""Run a new, isolated investigation batch without replacing the submitted run.

    python -m scripts.run_batch --run-id review-20261101 --data-dir /path/to/csvs

Outputs: runs/reviews/<run-id>/cases/, traces/, batch_summary.json.
Graph writes use REVIEW-<run-id>-HHG-* IDs. Use a dedicated review workspace
for full retrieval isolation: a prefix protects writes, not vector-search reads.
"""
from __future__ import annotations

import argparse
import asyncio
import re
from pathlib import Path

from dotenv import load_dotenv


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True, help="Unique label; letters, digits, underscores and hyphens")
    parser.add_argument("--case-ids", default=None, help="Comma-separated IDs, e.g. HHG-008,HHG-011")
    parser.add_argument("--merge", action="store_true", help="Replace selected cases within this review run only")
    parser.add_argument("--data-dir", default=None, help="Directory containing the four benchmark CSVs")
    parser.add_argument("--env-file", default=".env", help="RingSleuth service configuration (never printed)")
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,60}", args.run_id):
        parser.error("run-id must contain 1–60 letters, digits, underscores or hyphens")
    root = Path(__file__).resolve().parents[1] / "runs/reviews" / args.run_id
    if root.exists() and not args.merge:
        parser.error("That review run already exists; choose another run-id or use --merge")
    load_dotenv(args.env_file, override=True)
    # LLM configuration is captured on import; load the selected file first.
    from src.run.run_all import run_all

    case_ids = [c.strip() for c in args.case_ids.split(",")] if args.case_ids else None
    result = asyncio.run(run_all(cases_dir=root / "cases", runs_dir=root,
                                data_dir=args.data_dir, case_ids=case_ids, merge=args.merge,
                                graph_case_prefix=f"REVIEW-{args.run_id}", env_path=args.env_file))
    print(f"DONE {result.get('cases_completed')}/{result.get('cases_total')} "
          f"valid={result.get('cases_valid')} failed={result.get('cases_failed')}")
    return 0 if not result.get("errors") and result.get("cases_valid") == result.get("cases_completed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
