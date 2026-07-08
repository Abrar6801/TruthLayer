"use client";

// Single-page claim checker. Client-side fetch (not a Server Action) because
// the request runs 10-30+ seconds and the UI must stay interactive with a
// live elapsed-time indicator while it's in flight — a Server Action would
// tie the result to a form submission lifecycle with less control over
// progress display. The fetch goes to our own /api/verify route handler,
// which holds the backend key server-side.

import { FormEvent, useEffect, useRef, useState } from "react";
import type { VerifyResult } from "@/lib/api";

type Phase = "idle" | "loading" | "done" | "error";

const VERDICT_STYLES: Record<VerifyResult["verdict"], { label: string; className: string }> = {
  true: { label: "TRUE", className: "verdict-true" },
  false: { label: "FALSE", className: "verdict-false" },
  mixed: { label: "MIXED", className: "verdict-mixed" },
  unverifiable: { label: "UNVERIFIABLE", className: "verdict-unverifiable" },
};

// Honest, time-based hints about what the pipeline is doing. These are not
// live signals (that's Phase 4 streaming) — just expectation-setting.
const LOADING_HINTS: Array<[afterSeconds: number, hint: string]> = [
  [0, "Breaking the claim into checkable parts…"],
  [4, "Searching the web for evidence…"],
  [12, "Reading and embedding sources…"],
  [20, "Weighing the evidence…"],
  [30, "Still working — low-confidence verdicts trigger a broader second search…"],
];

export default function Home() {
  const [claim, setClaim] = useState("");
  const [phase, setPhase] = useState<Phase>("idle");
  const [result, setResult] = useState<VerifyResult | null>(null);
  const [error, setError] = useState<string>("");
  const [elapsed, setElapsed] = useState(0);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (phase === "loading") {
      const started = Date.now();
      timerRef.current = setInterval(
        () => setElapsed(Math.floor((Date.now() - started) / 1000)),
        1000,
      );
    } else if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [phase]);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (phase === "loading" || claim.trim().length < 3) return;
    setPhase("loading");
    setResult(null);
    setError("");
    setElapsed(0);
    try {
      const response = await fetch("/api/verify", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ claim: claim.trim() }),
      });
      const body = (await response.json()) as VerifyResult & { error?: string };
      if (!response.ok) {
        throw new Error(body.error ?? `Request failed (${response.status})`);
      }
      setResult(body);
      setPhase("done");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong.");
      setPhase("error");
    }
  }

  const hint =
    LOADING_HINTS.filter(([after]) => elapsed >= after).at(-1)?.[1] ?? LOADING_HINTS[0][1];

  return (
    <main className="container">
      <h1>TruthLayer</h1>
      <p className="tagline">
        Paste a factual claim. TruthLayer searches the web, weighs the evidence, and returns a
        cited verdict.
      </p>

      <form onSubmit={onSubmit}>
        <textarea
          value={claim}
          onChange={(e) => setClaim(e.target.value)}
          placeholder='e.g. "The Great Wall of China is visible from space with the naked eye"'
          maxLength={1000}
          rows={3}
          disabled={phase === "loading"}
          aria-label="Claim to verify"
        />
        <div className="form-row">
          <span className="charcount">{claim.length}/1000</span>
          <button type="submit" disabled={phase === "loading" || claim.trim().length < 3}>
            {phase === "loading" ? "Checking…" : "Check this claim"}
          </button>
        </div>
      </form>

      {phase === "loading" && (
        <div className="card loading" role="status">
          <div className="spinner" aria-hidden="true" />
          <p className="hint">{hint}</p>
          <p className="elapsed">{elapsed}s elapsed — a full check usually takes 15-40 seconds.</p>
        </div>
      )}

      {phase === "error" && (
        <div className="card error" role="alert">
          <strong>Couldn&apos;t verify that claim.</strong>
          <p>{error}</p>
        </div>
      )}

      {phase === "done" && result && (
        <div className="card result">
          <div className="verdict-row">
            <span className={`verdict-badge ${VERDICT_STYLES[result.verdict].className}`}>
              {VERDICT_STYLES[result.verdict].label}
            </span>
            <span className="confidence">
              {Math.round(result.confidence * 100)}% confidence
              {result.low_confidence && (
                <em className="low-conf"> — low confidence; evidence may be incomplete</em>
              )}
            </span>
          </div>

          <p className="rationale">{result.rationale}</p>

          {result.sub_claims.length > 1 && (
            <details>
              <summary>Checked as {result.sub_claims.length} sub-claims</summary>
              <ul>
                {result.sub_claims.map((sc) => (
                  <li key={sc}>{sc}</li>
                ))}
              </ul>
            </details>
          )}

          {result.sources.length > 0 ? (
            <div className="sources">
              <h2>Sources</h2>
              <ul>
                {result.sources.map((url) => (
                  <li key={url}>
                    <a href={url} target="_blank" rel="noopener noreferrer nofollow">
                      {url}
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          ) : (
            <p className="no-sources">No sources were cited for this verdict.</p>
          )}
        </div>
      )}

      <footer>
        <p>
          TruthLayer is a demo project for learning agentic RAG. Verdicts are generated by an AI
          pipeline and <strong>may be wrong</strong> — always check the cited sources yourself.
          Don&apos;t submit sensitive or personal information.
        </p>
      </footer>
    </main>
  );
}
