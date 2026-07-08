// SSE proxy: pipes the backend's progress stream through to the browser.
// Same security shape as /api/verify — the key is attached here, server-side,
// and the browser only ever talks to this same-origin endpoint.

import { NextRequest, NextResponse } from "next/server";
import { allowRequest } from "@/lib/rateLimit";

export const dynamic = "force-dynamic";

const MAX_CLAIM_LENGTH = 1000;

export async function POST(request: NextRequest): Promise<Response> {
  const ip =
    request.headers.get("x-forwarded-for")?.split(",")[0]?.trim() ?? "unknown";
  if (!allowRequest(ip)) {
    return NextResponse.json(
      { error: "Too many requests — please wait a minute and try again." },
      { status: 429 },
    );
  }

  let claim: unknown;
  try {
    claim = ((await request.json()) as { claim?: unknown }).claim;
  } catch {
    return NextResponse.json({ error: "Invalid JSON body." }, { status: 400 });
  }
  if (
    typeof claim !== "string" ||
    claim.trim().length < 3 ||
    claim.length > MAX_CLAIM_LENGTH
  ) {
    return NextResponse.json({ error: "Please enter a valid claim." }, { status: 422 });
  }

  const apiUrl = process.env.TRUTHLAYER_API_URL;
  const apiKey = process.env.TRUTHLAYER_API_KEY;
  if (!apiUrl || !apiKey) {
    return NextResponse.json({ error: "Server misconfigured." }, { status: 500 });
  }

  const upstream = await fetch(`${apiUrl}/verify/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-API-Key": apiKey },
    body: JSON.stringify({ claim: claim.trim() }),
    signal: AbortSignal.timeout(180_000),
    cache: "no-store",
  });

  if (!upstream.ok || !upstream.body) {
    return NextResponse.json(
      { error: "Verification failed — please try again shortly." },
      { status: 502 },
    );
  }

  return new Response(upstream.body, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
    },
  });
}
