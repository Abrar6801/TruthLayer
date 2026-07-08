"""Run the eval dataset through the TruthLayer pipeline and save raw outputs.

Usage (from the repo root, venv active):

    python eval/run_eval.py                       # full dataset, direct graph
    python eval/run_eval.py --limit 10            # first 10 claims only
    python eval/run_eval.py --tag baseline        # label the output file
    python eval/run_eval.py --api-url http://localhost:8000 --api-key KEY

Outputs eval/results/<timestamp>_<tag>.json with the model's verdicts
alongside ground truth, per-claim latency (total + per graph stage), LLM call
counts, and token usage — everything score_eval.py and the Phase 4 reports
need. Scoring is a separate step so one expensive run can be re-scored freely.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger("eval")

REPO_ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = Path(__file__).resolve().parent / "results"


def load_dataset(path: Path) -> list[dict[str, Any]]:
    """Load the labeled claims."""
    with open(path, encoding="utf-8") as f:
        items: list[dict[str, Any]] = json.load(f)["claims"]
    return items


def run_via_graph(claim: str) -> dict[str, Any]:
    """Run one claim through the graph directly, timing each node."""
    from truthlayer import telemetry
    from truthlayer.graph import get_graph

    telemetry.reset()
    initial = {
        "claim": claim,
        "retry_count": 0,
        "llm_calls_used": 0,
        "errors": [],
        "ingested_urls": [],
        "chunks_stored": 0,
    }
    stage_seconds: dict[str, float] = {}
    state: dict[str, Any] = {}
    started = time.perf_counter()
    last = started
    for update in get_graph().stream(initial, stream_mode="updates"):
        now = time.perf_counter()
        for node_name, node_state in update.items():
            stage_seconds[node_name] = stage_seconds.get(node_name, 0.0) + (now - last)
            if node_state:
                state.update(node_state)
        last = now
    total = time.perf_counter() - started

    usage = telemetry.snapshot()
    verdict = state.get("verdict")
    return {
        "predicted_verdict": verdict.verdict if verdict else None,
        "confidence": verdict.confidence if verdict else None,
        "rationale": verdict.rationale if verdict else None,
        "sources": verdict.supporting_sources if verdict else [],
        "sub_claims": state.get("sub_claims", []),
        "low_confidence": state.get("low_confidence", False),
        "retries": state.get("retry_count", 0),
        "errors": state.get("errors", []),
        "latency_seconds": round(total, 2),
        "stage_seconds": {k: round(v, 2) for k, v in stage_seconds.items()},
        "llm_calls": usage.llm_calls,
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
    }


def run_via_api(claim: str, api_url: str, api_key: str) -> dict[str, Any]:
    """Run one claim through a deployed /verify endpoint."""
    started = time.perf_counter()
    response = httpx.post(
        f"{api_url.rstrip('/')}/verify",
        json={"claim": claim},
        headers={"X-API-Key": api_key},
        timeout=180.0,
    )
    total = time.perf_counter() - started
    response.raise_for_status()
    body = response.json()
    return {
        "predicted_verdict": body["verdict"],
        "confidence": body["confidence"],
        "rationale": body["rationale"],
        "sources": body["sources"],
        "sub_claims": body["sub_claims"],
        "low_confidence": body["low_confidence"],
        "retries": body["retries"],
        "errors": [],
        "latency_seconds": round(total, 2),
        "stage_seconds": {},  # not observable through the HTTP boundary
        "llm_calls": None,
        "input_tokens": None,
        "output_tokens": None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the TruthLayer eval set.")
    parser.add_argument("--dataset", default=str(Path(__file__).parent / "dataset.json"))
    parser.add_argument("--limit", type=int, default=None, help="Only run the first N claims")
    parser.add_argument("--tag", default="run", help="Label for the output filename")
    parser.add_argument("--api-url", default=None, help="Hit a deployed API instead of the graph")
    parser.add_argument("--api-key", default=None, help="X-API-Key for --api-url")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s")
    for noisy in ("httpx", "httpcore", "sentence_transformers"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    sys.path.insert(0, str(REPO_ROOT / "src"))
    items = load_dataset(Path(args.dataset))
    if args.limit:
        items = items[: args.limit]

    results: list[dict[str, Any]] = []
    for i, item in enumerate(items, start=1):
        logger.info("[%d/%d] %s", i, len(items), item["claim"][:80])
        try:
            if args.api_url:
                if not args.api_key:
                    parser.error("--api-key is required with --api-url")
                output = run_via_api(item["claim"], args.api_url, args.api_key)
            else:
                output = run_via_graph(item["claim"])
        except Exception as exc:  # record the failure, keep evaluating
            logger.error("Claim %d failed: %s", item["id"], exc)
            output = {"predicted_verdict": None, "error": str(exc), "latency_seconds": None}
        results.append({**item, **output})

    RESULTS_DIR.mkdir(exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out_path = RESULTS_DIR / f"{stamp}_{args.tag}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"run_tag": args.tag, "timestamp": stamp, "results": results}, f, indent=2)
    logger.info("Saved %d results to %s", len(results), out_path)
    print(out_path)  # stdout: path for scripting (make eval)
    return 0


if __name__ == "__main__":
    sys.exit(main())
