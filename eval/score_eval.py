"""Score a saved eval run: accuracy, confusion matrix, retrieval quality,
latency/cost stats, and an optional LLM-as-judge faithfulness sample.

Usage:

    python eval/score_eval.py eval/results/<file>.json
    python eval/score_eval.py eval/results/<file>.json --report eval/report.md
    python eval/score_eval.py <file> --faithfulness 8   # spends 8 Claude calls

Why accuracy alone is weak here: with four classes and an easy-heavy dataset,
a model that answers "true" whenever evidence vaguely agrees can score high
while being useless on the claims that matter. The confusion matrix shows
*which* categories bleed into which (mixed→true is the dangerous one for a
fact-checker), and the failure examples show whether misses are retrieval
problems or judgment problems — different fixes entirely.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

VERDICTS = ["true", "false", "mixed", "unverifiable"]

# Claude Sonnet 5 pricing per million tokens (introductory, through 2026-08-31;
# standard is $3/$15 — update alongside any model change).
PRICE_IN_PER_MTOK = 2.00
PRICE_OUT_PER_MTOK = 10.00


def _domain(url: str) -> str:
    netloc = urlparse(url).netloc.lower()
    return netloc.removeprefix("www.")


def score(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute all metrics from raw run results."""
    scored = [r for r in results if r.get("predicted_verdict") in VERDICTS]
    correct = [r for r in scored if r["predicted_verdict"] == r["expected_verdict"]]

    confusion: dict[str, Counter[str]] = {v: Counter() for v in VERDICTS}
    for r in scored:
        confusion[r["expected_verdict"]][r["predicted_verdict"]] += 1

    by_difficulty: dict[str, list[bool]] = {}
    for r in scored:
        by_difficulty.setdefault(r.get("difficulty", "unknown"), []).append(
            r["predicted_verdict"] == r["expected_verdict"]
        )

    # Retrieval quality: when we know a correct source, did evidence from that
    # domain actually get cited?
    retrieval_hits = 0
    retrieval_total = 0
    for r in scored:
        ref = r.get("reference_url")
        if not ref:
            continue
        retrieval_total += 1
        cited_domains = {_domain(u) for u in r.get("sources", [])}
        if _domain(ref) in cited_domains:
            retrieval_hits += 1

    latencies = [r["latency_seconds"] for r in results if r.get("latency_seconds")]
    llm_calls = [r["llm_calls"] for r in results if r.get("llm_calls") is not None]
    in_tokens = [r["input_tokens"] for r in results if r.get("input_tokens") is not None]
    out_tokens = [r["output_tokens"] for r in results if r.get("output_tokens") is not None]

    cost_per_claim = None
    if in_tokens and out_tokens:
        avg_in = statistics.mean(in_tokens)
        avg_out = statistics.mean(out_tokens)
        cost_per_claim = (avg_in * PRICE_IN_PER_MTOK + avg_out * PRICE_OUT_PER_MTOK) / 1_000_000

    def pctile(values: list[float], p: float) -> float | None:
        if not values:
            return None
        ordered = sorted(values)
        idx = min(len(ordered) - 1, round(p * (len(ordered) - 1)))
        return ordered[int(idx)]

    failures = [
        {
            "id": r["id"],
            "claim": r["claim"],
            "expected": r["expected_verdict"],
            "predicted": r["predicted_verdict"],
            "confidence": r.get("confidence"),
            "rationale": r.get("rationale"),
            "sources": r.get("sources", []),
        }
        for r in scored
        if r["predicted_verdict"] != r["expected_verdict"]
    ]

    return {
        "n_total": len(results),
        "n_scored": len(scored),
        "n_errored": len(results) - len(scored),
        "accuracy": len(correct) / len(scored) if scored else 0.0,
        "confusion": {k: dict(v) for k, v in confusion.items()},
        "accuracy_by_difficulty": {k: sum(v) / len(v) for k, v in sorted(by_difficulty.items())},
        "retrieval_hit_rate": retrieval_hits / retrieval_total if retrieval_total else None,
        "retrieval_checked": retrieval_total,
        "latency_p50": pctile(latencies, 0.50),
        "latency_p95": pctile(latencies, 0.95),
        "avg_llm_calls": statistics.mean(llm_calls) if llm_calls else None,
        "avg_input_tokens": statistics.mean(in_tokens) if in_tokens else None,
        "avg_output_tokens": statistics.mean(out_tokens) if out_tokens else None,
        "cost_per_verdict_usd": cost_per_claim,
        "failures": failures,
    }


def faithfulness_check(results: list[dict[str, Any]], sample_size: int) -> dict[str, Any]:
    """LLM-as-judge: does each rationale actually follow from its cited sources?

    Known pattern, known limits: the judge is the same model family that wrote
    the rationale, so it shares blind spots; it sees source *URLs* rather than
    the full chunks; and LLM judges skew agreeable. Treat the number as a
    smoke alarm (big drops matter), not a precision instrument.
    """
    import anthropic

    from truthlayer.config import get_settings

    settings = get_settings()
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key, timeout=60.0, max_retries=1)

    candidates = [r for r in results if r.get("rationale") and r.get("predicted_verdict")]
    sample = candidates[:sample_size]
    verdicts = []
    for r in sample:
        prompt = (
            "You are auditing a fact-checker. Given its claim, verdict, rationale, "
            "and cited sources, answer with ONLY 'faithful' if the rationale's "
            "reasoning is consistent with the verdict and plausibly grounded in the "
            "cited sources, or 'unfaithful' if the rationale contradicts the verdict "
            "or asserts things no cited source could support.\n\n"
            f"<claim>{r['claim']}</claim>\n"
            f"<verdict>{r['predicted_verdict']}</verdict>\n"
            f"<rationale>{r['rationale']}</rationale>\n"
            f"<sources>{json.dumps(r.get('sources', []))}</sources>"
        )
        message = client.messages.create(
            model=settings.anthropic_model,
            max_tokens=10,
            output_config={"effort": "low"},
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(b.text for b in message.content if b.type == "text").strip().lower()
        verdicts.append({"id": r["id"], "faithful": text.startswith("faithful")})
    faithful = sum(1 for v in verdicts if v["faithful"])
    return {
        "sampled": len(verdicts),
        "faithful": faithful,
        "rate": faithful / len(verdicts) if verdicts else None,
        "details": verdicts,
    }


def render_report(metrics: dict[str, Any], run_meta: dict[str, Any]) -> str:
    """Render metrics as a readable markdown report."""
    lines: list[str] = []
    lines.append(f"# TruthLayer eval report — {run_meta.get('run_tag', '?')}")
    lines.append("")
    lines.append(
        f"Run: `{run_meta.get('timestamp', '?')}` · {metrics['n_scored']} scored / "
        f"{metrics['n_total']} total ({metrics['n_errored']} errored)"
    )
    lines.append("")
    lines.append("## Headline numbers")
    lines.append("")
    lines.append(f"- **Verdict accuracy: {metrics['accuracy']:.1%}**")
    if metrics["retrieval_hit_rate"] is not None:
        lines.append(
            f"- Retrieval hit rate (reference domain cited): "
            f"{metrics['retrieval_hit_rate']:.1%} over {metrics['retrieval_checked']} claims"
        )
    if metrics["latency_p50"] is not None:
        lines.append(
            f"- Latency: p50 {metrics['latency_p50']:.1f}s · p95 {metrics['latency_p95']:.1f}s"
        )
    if metrics["avg_llm_calls"] is not None:
        lines.append(f"- Avg LLM calls per claim: {metrics['avg_llm_calls']:.2f}")
    if metrics["cost_per_verdict_usd"] is not None:
        lines.append(
            f"- Avg tokens per claim: {metrics['avg_input_tokens']:.0f} in / "
            f"{metrics['avg_output_tokens']:.0f} out → "
            f"**cost per verdict ≈ ${metrics['cost_per_verdict_usd']:.4f}**"
        )
    if "faithfulness" in metrics:
        f = metrics["faithfulness"]
        lines.append(f"- Faithfulness (LLM-as-judge, sample of {f['sampled']}): {f['rate']:.0%}")
    lines.append("")
    lines.append("## Confusion matrix (rows = expected, columns = predicted)")
    lines.append("")
    header = "| expected \\ predicted | " + " | ".join(VERDICTS) + " |"
    lines.append(header)
    lines.append("|---" * 5 + "|")
    for expected in VERDICTS:
        row = metrics["confusion"].get(expected, {})
        lines.append(
            f"| **{expected}** | " + " | ".join(str(row.get(p, 0)) for p in VERDICTS) + " |"
        )
    lines.append("")
    lines.append("## Accuracy by difficulty")
    lines.append("")
    for diff, acc in metrics["accuracy_by_difficulty"].items():
        lines.append(f"- {diff}: {acc:.1%}")
    lines.append("")
    lines.append("## Failures")
    lines.append("")
    if not metrics["failures"]:
        lines.append("None — suspicious in itself; the dataset may be too easy.")
    for f in metrics["failures"]:
        lines.append(f"### #{f['id']}: {f['claim']}")
        lines.append(
            f"- expected **{f['expected']}**, predicted **{f['predicted']}** "
            f"(confidence {f['confidence']})"
        )
        lines.append(f"- rationale: {f['rationale']}")
        lines.append(f"- sources: {', '.join(f['sources']) or '(none)'}")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Score a TruthLayer eval run.")
    parser.add_argument("results_file", help="A file produced by run_eval.py")
    parser.add_argument("--report", default=None, help="Where to write the markdown report")
    parser.add_argument(
        "--faithfulness",
        type=int,
        default=0,
        help="Run LLM-as-judge faithfulness on the first N outputs (spends N Claude calls)",
    )
    args = parser.parse_args()

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

    with open(args.results_file, encoding="utf-8") as f:
        run = json.load(f)
    metrics = score(run["results"])
    if args.faithfulness:
        metrics["faithfulness"] = faithfulness_check(run["results"], args.faithfulness)

    report = render_report(metrics, run)
    report_path = Path(args.report) if args.report else Path("eval/report.md")
    report_path.write_text(report, encoding="utf-8")
    print(report)
    print(f"\nReport written to {report_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
