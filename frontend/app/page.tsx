"use client";

// Claim checker with progressive streaming. The submit consumes the SSE
// stream from /api/verify/stream via fetch + ReadableStream (EventSource
// can't POST), rendering each pipeline stage as it completes — the user
// watches the fact-check assemble instead of staring at a spinner. The
// non-streaming /api/verify endpoint still exists for the eval script.

import { FormEvent, useEffect, useRef, useState } from "react";
import type { VerifyResult } from "@/lib/api";

type Phase = "idle" | "warming" | "loading" | "done" | "error";

interface ProgressState {
  subClaims: string[];
  sourceDomains: string[];
  evidenceCount: number | null;
  confidence: number | null;
  retrying: boolean;
}

const EMPTY_PROGRESS: ProgressState = {
  subClaims: [],
  sourceDomains: [],
  evidenceCount: null,
  confidence: null,
  retrying: false,
};

const VERDICT_STYLES: Record<VerifyResult["verdict"], { label: string; className: string }> = {
  true: { label: "TRUE", className: "verdict-true" },
  false: { label: "FALSE", className: "verdict-false" },
  mixed: { label: "MIXED", className: "verdict-mixed" },
  unverifiable: { label: "UNVERIFIABLE", className: "verdict-unverifiable" },
};

/** Parse complete SSE frames out of a text buffer; returns [events, remainder]. */
function parseSse(buffer: string): [Array<{ event: string; data: string }>, string] {
  const events: Array<{ event: string; data: string }> = [];
  const parts = buffer.split("\n\n");
  const remainder = parts.pop() ?? "";
  for (const part of parts) {
    let event = "message";
    let data = "";
    for (const line of part.split("\n")) {
      if (line.startsWith("event: ")) event = line.slice(7).trim();
      else if (line.startsWith("data: ")) data += line.slice(6);
    }
    if (data) events.push({ event, data });
  }
  return [events, remainder];
}

export default function Home() {
  const [claim, setClaim] = useState("");
  const [phase, setPhase] = useState<Phase>("idle");
  const [progress, setProgress] = useState<ProgressState>(EMPTY_PROGRESS);
  const [result, setResult] = useState<VerifyResult | null>(null);
  const [error, setError] = useState<string>("");
  const [elapsed, setElapsed] = useState(0);
  const [feedbackSent, setFeedbackSent] = useState<"up" | "down" | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Fire-and-forget warmup on mount to reduce cold-start odds.
  useEffect(() => {
    fetch("/api/health", { cache: "no-store" }).catch(() => undefined);
  }, []);

  useEffect(() => {
    if (phase === "loading" || phase === "warming") {
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

  /** Poll /api/health until the backend is up, or until we give up (90s). */
  async function waitForBackend(): Promise<boolean> {
    for (let i = 0; i < 15; i++) {
      await new Promise((r) => setTimeout(r, 6_000));
      try {
        const r = await fetch("/api/health", { cache: "no-store" });
        if (r.ok) return true;
      } catch {
        // network error — keep polling
      }
    }
    return false;
  }

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (phase === "loading" || phase === "warming" || claim.trim().length < 3) return;
    setPhase("loading");
    setProgress(EMPTY_PROGRESS);
    setResult(null);
    setError("");
    setElapsed(0);
    setFeedbackSent(null);

    try {
      let response = await fetch("/api/verify/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ claim: claim.trim() }),
      });

      // On 504, the Render free-tier backend is cold-starting. Wait for it and
      // retry once automatically rather than failing immediately.
      if (response.status === 504) {
        setPhase("warming");
        const ready = await waitForBackend();
        if (!ready) {
          throw new Error(
            "The backend took too long to start. Please try again in a moment.",
          );
        }
        setPhase("loading");
        response = await fetch("/api/verify/stream", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ claim: claim.trim() }),
        });
      }

      if (!response.ok || !response.body) {
        const body = (await response.json().catch(() => ({}))) as { error?: string };
        throw new Error(body.error ?? `Request failed (${response.status})`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let sawResult = false;

      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const [events, remainder] = parseSse(buffer);
        buffer = remainder;

        for (const { event: name, data } of events) {
          const payload = JSON.parse(data) as Record<string, unknown>;
          if (name === "sub_claims") {
            setProgress((p) => ({ ...p, subClaims: payload.sub_claims as string[] }));
          } else if (name === "evidence") {
            setProgress((p) => ({
              ...p,
              sourceDomains: payload.source_domains as string[],
              retrying: false,
            }));
          } else if (name === "retrieved") {
            setProgress((p) => ({ ...p, evidenceCount: payload.evidence_count as number }));
          } else if (name === "judging") {
            setProgress((p) => ({ ...p, confidence: payload.confidence as number }));
          } else if (name === "retrying") {
            setProgress((p) => ({ ...p, retrying: true }));
          } else if (name === "result") {
            setResult(payload as unknown as VerifyResult);
            setPhase("done");
            sawResult = true;
          } else if (name === "error") {
            throw new Error((payload.message as string) ?? "Verification failed.");
          }
        }
      }
      if (!sawResult) throw new Error("The stream ended before a verdict arrived.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong.");
      setPhase("error");
    }
  }

  async function sendFeedback(helpful: boolean) {
    if (!result || feedbackSent) return;
    setFeedbackSent(helpful ? "up" : "down");
    try {
      await fetch("/api/feedback", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ claim: result.claim, verdict: result.verdict, helpful }),
      });
    } catch {
      // Feedback is best-effort; never bother the user about it.
    }
  }

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
          <button type="submit" disabled={phase === "loading" || phase === "warming" || claim.trim().length < 3}>
            {phase === "loading" || phase === "warming" ? "Checking…" : "Check this claim"}
          </button>
        </div>
      </form>

      {phase === "warming" && (
        <div className="card loading" role="status">
          <div className="spinner" aria-hidden="true" />
          <p style={{ margin: 0 }}>
            The backend is starting up (free-tier cold start) — this takes up to
            60 seconds the first time. Your claim will be checked automatically
            once it&apos;s ready.
          </p>
          <p className="elapsed">{elapsed}s elapsed</p>
        </div>
      )}

      {phase === "loading" && (
        <div className="card loading" role="status">
          <div className="spinner" aria-hidden="true" />
          <ul className="progress-list">
            <li className={progress.subClaims.length ? "step-done" : "step-active"}>
              {progress.subClaims.length > 1
                ? `Split into ${progress.subClaims.length} checkable sub-claims`
                : progress.subClaims.length === 1
                  ? "Claim is atomic — checking as-is"
                  : "Breaking the claim into checkable parts…"}
            </li>
            <li
              className={
                progress.sourceDomains.length
                  ? "step-done"
                  : progress.subClaims.length
                    ? "step-active"
                    : "step-pending"
              }
            >
              {progress.sourceDomains.length
                ? `Evidence gathered from ${progress.sourceDomains.slice(0, 4).join(", ")}${progress.sourceDomains.length > 4 ? "…" : ""}`
                : "Searching the web for evidence…"}
            </li>
            <li
              className={
                progress.confidence !== null
                  ? "step-done"
                  : progress.evidenceCount !== null
                    ? "step-active"
                    : "step-pending"
              }
            >
              {progress.retrying
                ? "Confidence was low — broadening the search and retrying…"
                : progress.confidence !== null
                  ? `Verdict formed (${Math.round(progress.confidence * 100)}% confidence)`
                  : progress.evidenceCount !== null
                    ? `Weighing ${progress.evidenceCount} evidence passages…`
                    : "Weighing the evidence…"}
            </li>
          </ul>
          <p className="elapsed">{elapsed}s elapsed</p>
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
              {result.served_from_cache && <em className="cached"> · served from cache</em>}
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

          <div className="feedback">
            {feedbackSent ? (
              <span className="feedback-thanks">Thanks for the feedback!</span>
            ) : (
              <>
                <span>Was this verdict right?</span>
                <button type="button" className="thumb" onClick={() => sendFeedback(true)}>
                  👍
                </button>
                <button type="button" className="thumb" onClick={() => sendFeedback(false)}>
                  👎
                </button>
              </>
            )}
          </div>
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
