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

from truthlayer.config import ConfigError, get_settings

logger = logging.getLogger("truthlayer")

#: Claims longer than this are rejected: the pipeline is designed for short,
#: checkable statements, and an unbounded "claim" is an abuse vector.
MAX_CLAIM_LENGTH = 1000


def _configure_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    # Third-party libraries are chatty at INFO; keep the console readable.
    for noisy in ("httpx", "httpcore", "sentence_transformers", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def run_pipeline(claim: str) -> int:
    """Run the full fact-checking pipeline for one claim.

    Returns a process exit code (0 = verdict produced or insufficient
    evidence reported cleanly; 1 = pipeline error).
    """
    # Imports happen here, after config validation, so a missing env var
    # fails with a clear message before any heavy model loading starts.
    from truthlayer.ingest import gather_evidence
    from truthlayer.retrieval import retrieve_evidence
    from truthlayer.verdict import VerdictParseError, generate_verdict

    logger.info("Stage 1/3: gathering evidence from the web ...")
    stored = gather_evidence(claim)
    if stored == 0:
        print("\nVerdict: UNVERIFIABLE — web search returned no usable evidence.")
        return 0

    logger.info("Stage 2/3: retrieving the most relevant evidence ...")
    evidence = retrieve_evidence(claim)
    if not evidence:
        print(
            "\nVerdict: UNVERIFIABLE — no stored evidence was relevant enough "
            "to the claim (all below similarity threshold)."
        )
        return 0

    logger.info("Stage 3/3: generating verdict with Claude ...")
    try:
        verdict = generate_verdict(claim, evidence)
    except VerdictParseError:
        logger.error("Claude's output could not be parsed into a valid verdict")
        print("\nERROR: verdict generation failed (unparseable model output). Try again.")
        return 1

    print(f"\nClaim:      {claim}")
    print(f"Verdict:    {verdict.verdict.upper()}")
    print(f"Confidence: {verdict.confidence:.0%}")
    print(f"Rationale:  {verdict.rationale}")
    if verdict.supporting_sources:
        print("Sources:")
        for url in verdict.supporting_sources:
            print(f"  - {url}")
    else:
        print("Sources:    (none cited)")
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
