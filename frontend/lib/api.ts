// Server-only API client for the TruthLayer FastAPI backend.
//
// This module must ONLY be imported from server code (route handlers /
// server components). It reads TRUTHLAYER_API_KEY, which is deliberately
// NOT prefixed with NEXT_PUBLIC_: Next.js inlines NEXT_PUBLIC_* values into
// the browser bundle at build time, where anyone can read them with
// view-source. Server-only env vars never leave the server process.

export interface SourceAssessment {
  url: string;
  stance: "supports" | "disputes" | "context";
}

export interface VerifyResult {
  claim: string;
  verdict: "true" | "false" | "mixed" | "unverifiable";
  confidence: number;
  rationale: string;
  sources: string[];
  // Per-source stance; may be absent/empty on verdicts cached before the
  // field existed, so treat `sources` as the fallback.
  source_assessments?: SourceAssessment[];
  sub_claims: string[];
  low_confidence: boolean;
  retries: number;
  served_from_cache?: boolean;
  // Permalink id (GET /verdicts/{id}); null when the cache write failed.
  verdict_id?: string | null;
}

export class BackendError extends Error {
  constructor(
    message: string,
    public readonly status: number,
  ) {
    super(message);
  }
}

function requireEnv(name: "TRUTHLAYER_API_URL" | "TRUTHLAYER_API_KEY"): string {
  const value = process.env[name];
  if (!value) {
    throw new Error(`${name} is not configured on the server`);
  }
  return value;
}

/** Call the backend /verify endpoint. Server-side only. */
export async function verifyClaim(claim: string): Promise<VerifyResult> {
  const response = await fetch(`${requireEnv("TRUTHLAYER_API_URL")}/verify`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-API-Key": requireEnv("TRUTHLAYER_API_KEY"),
    },
    body: JSON.stringify({ claim }),
    // The pipeline legitimately takes 10-30+ seconds.
    signal: AbortSignal.timeout(180_000),
    cache: "no-store",
  });

  if (!response.ok) {
    // Surface the status, never the backend's internals.
    throw new BackendError(`Backend responded ${response.status}`, response.status);
  }
  return (await response.json()) as VerifyResult;
}

/** Fetch a stored verdict by permalink id. Server-side only. Null on 404. */
export async function getVerdict(id: string): Promise<VerifyResult | null> {
  const response = await fetch(
    `${requireEnv("TRUTHLAYER_API_URL")}/verdicts/${encodeURIComponent(id)}`,
    {
      headers: { "X-API-Key": requireEnv("TRUTHLAYER_API_KEY") },
      cache: "no-store",
    },
  );
  if (response.status === 404 || response.status === 422) {
    return null; // unknown or malformed id — both render as "not found"
  }
  if (!response.ok) {
    throw new BackendError(`Backend responded ${response.status}`, response.status);
  }
  return (await response.json()) as VerifyResult;
}
