"""Post-launch usage analysis (Task 4.6).

Run this after the app has collected real traffic for 1-2 weeks:

    python eval/analyze_usage.py            # against DATABASE_URL from .env
    python eval/analyze_usage.py --days 14

It reports claim volume, verdict distribution, feedback rates, and dumps a
sample of raw claims for the manual review pass (categorize them yourself:
factual claims vs opinions vs questions vs junk — that categorization is
what decides the one data-motivated improvement to build).

Honest caveats baked in: cache HITS aren't persisted (they're visible in
server logs as "Semantic cache HIT"), so the hit rate here is estimated from
near-duplicate stored claims; visitor counts live in your analytics tool
(Plausible/Umami), not the database.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze post-launch usage data.")
    parser.add_argument("--days", type=int, default=14, help="Look-back window")
    parser.add_argument("--sample", type=int, default=30, help="Raw claims to print for review")
    args = parser.parse_args()

    if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]

    from truthlayer.db import get_pool

    with get_pool().connection() as conn:
        total = conn.execute(
            "SELECT count(*) FROM verified_claims"
            " WHERE created_at > now() - make_interval(days => %s)",
            (args.days,),
        ).fetchone()[0]

        by_verdict = conn.execute(
            "SELECT verdict_payload->>'verdict' AS v, count(*)"
            " FROM verified_claims"
            " WHERE created_at > now() - make_interval(days => %s)"
            " GROUP BY v ORDER BY count(*) DESC",
            (args.days,),
        ).fetchall()

        by_day = conn.execute(
            "SELECT date_trunc('day', created_at)::date AS d, count(*)"
            " FROM verified_claims"
            " WHERE created_at > now() - make_interval(days => %s)"
            " GROUP BY d ORDER BY d",
            (args.days,),
        ).fetchall()

        feedback = conn.execute(
            "SELECT helpful, count(*) FROM verdict_feedback"
            " WHERE created_at > now() - make_interval(days => %s)"
            " GROUP BY helpful",
            (args.days,),
        ).fetchall()

        sample = conn.execute(
            "SELECT claim_text, verdict_payload->>'verdict', created_at::date"
            " FROM verified_claims"
            " WHERE created_at > now() - make_interval(days => %s)"
            " ORDER BY created_at DESC LIMIT %s",
            (args.days, args.sample),
        ).fetchall()

    print(f"# Usage over the last {args.days} days\n")
    print(f"Claims verified (pipeline runs stored): {total}")
    print("\nVerdict distribution:")
    for verdict, count in by_verdict:
        print(f"  {verdict:>14}: {count}")
    print("\nClaims per day:")
    for day, count in by_day:
        print(f"  {day}: {'█' * min(count, 60)} {count}")
    up = next((c for h, c in feedback if h), 0)
    down = next((c for h, c in feedback if not h), 0)
    print(f"\nFeedback: {up} 👍 / {down} 👎", end="")
    if up + down:
        print(f"  ({up / (up + down):.0%} positive)")
    else:
        print("  (none yet)")
    print("\nCache hit rate: grep server logs for 'Semantic cache HIT' —")
    print("  hits / (hits + stored claims) is the true rate; hits aren't persisted.")
    print(f"\n# Raw claims for manual review (latest {len(sample)})")
    print("# Categorize each: factual / opinion / question / junk\n")
    for claim, verdict, day in sample:
        print(f"  [{day}] ({verdict}) {claim[:100]}")
    print(
        "\nNext step (Task 4.6): pick the ONE improvement this data motivates,"
        "\nimplement it, and write eval/usage_report.md with the numbers."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
