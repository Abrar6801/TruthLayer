// Route handler proxying claim verification to the FastAPI backend.
//
// The browser talks to THIS endpoint (same origin, no key). This server
// attaches the service API key and forwards to FastAPI. The key therefore
// exists only in server memory — it is never part of any response or bundle.

import { NextRequest, NextResponse } from "next/server";
import { BackendError, verifyClaim } from "@/lib/api";
import { allowRequest } from "@/lib/rateLimit";

// See app/api/verify/stream/route.ts for why this is needed — same pipeline,
// same risk of exceeding Vercel's default 10s function timeout.
export const maxDuration = 60;

const MAX_CLAIM_LENGTH = 1000;

export async function POST(request: NextRequest): Promise<NextResponse> {
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
    const body = (await request.json()) as { claim?: unknown };
    claim = body.claim;
  } catch {
    return NextResponse.json({ error: "Invalid JSON body." }, { status: 400 });
  }

  if (typeof claim !== "string" || claim.trim().length < 3) {
    return NextResponse.json(
      { error: "Please enter a claim to check (at least a few words)." },
      { status: 422 },
    );
  }
  if (claim.length > MAX_CLAIM_LENGTH) {
    return NextResponse.json(
      { error: `Claims are limited to ${MAX_CLAIM_LENGTH} characters.` },
      { status: 422 },
    );
  }

  try {
    const result = await verifyClaim(claim.trim());
    return NextResponse.json(result);
  } catch (error) {
    if (error instanceof BackendError && error.status === 429) {
      return NextResponse.json(
        { error: "The service is busy — please try again shortly." },
        { status: 429 },
      );
    }
    console.error("verify proxy failed:", error); // server logs only
    return NextResponse.json(
      { error: "Verification failed — please try again shortly." },
      { status: 502 },
    );
  }
}
