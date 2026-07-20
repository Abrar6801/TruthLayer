"""End-to-end CLI: `python -m truthlayer "claim text"`.

Runs the full Phase 1 pipeline — search, extract, chunk, embed, store,
retrieve, judge — with stage-by-stage logging so it's obvious where time goes
and where failures happen. If no evidence clears the relevance threshold, it
reports insufficient evidence instead of asking the judge to guess.
"""

from __future__ import annotations

import argparse
import logging
import sys

from truthlayer.config import MAX_CLAIM_LENGTH, ConfigError, get_settings

logger = logging.getLogger("truthlayer")


def _configure_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    # Third-party libraries are chatty at INFO; keep the console readable.
    for noisy in ("httpx", "httpcore", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def run_pipeline(claim: str) -> int:
    """Run the agentic fact-checking graph for one claim.

    Returns a process exit code (0 = verdict produced, including honest
    "unverifiable"; 1 = pipeline error).
    """
    # Imports happen here, after config validation, so a missing env var
    # fails with a clear message before any heavy model loading starts.
    import truthlayer.graph

    state = truthlayer.graph.verify_claim(claim)
    verdict = state.get("verdict")
    if verdict is None:
        logger.error("Graph finished without producing a verdict; errors: %s", state.get("errors"))
        print("\nERROR: pipeline failed to produce a verdict. Try again.")
        return 1

    sub_claims = state.get("sub_claims", [])
    print(f"\nClaim:      {claim}")
    if len(sub_claims) > 1:
        print("Sub-claims checked:")
        for sc in sub_claims:
            print(f"  - {sc}")
    print(f"Verdict:    {verdict.verdict.upper()}")
    print(f"Confidence: {verdict.confidence:.0%}")
    if state.get("low_confidence"):
        print("            (low confidence — evidence may be incomplete)")
    print(f"Rationale:  {verdict.rationale}")
    if verdict.supporting_sources:
        print("Sources:")
        for url in verdict.supporting_sources:
            print(f"  - {url}")
    else:
        print("Sources:    (none cited)")
    if state.get("retry_count", 0) > 0:
        print(f"Retries:    {state['retry_count']} broadened-search retry/retries used")
    return 0


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="python -m truthlayer",
        description="Fact-check a claim against web evidence.",
    )
    parser.add_argument("claim", help="The claim to fact-check, in quotes")
    parser.add_argument("-v", "--verbose", action="store_true", help="Debug logging")
    args = parser.parse_args(argv)

    _configure_logging(args.verbose)

    claim = args.claim.strip()
    if not claim:
        parser.error("claim must not be empty")
    if len(claim) > MAX_CLAIM_LENGTH:
        parser.error(f"claim is too long ({len(claim)} chars; max {MAX_CLAIM_LENGTH})")

    try:
        get_settings()
    except ConfigError as exc:
        logger.error("%s", exc)
        return 1

    try:
        return run_pipeline(claim)
    except Exception:
        logger.exception("Pipeline failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
