// Feedback proxy: forwards a thumbs-up/down to the backend with the
// server-side key attached.

import { NextRequest, NextResponse } from "next/server";
import { allowRequest } from "@/lib/rateLimit";

export async function POST(request: NextRequest): Promise<NextResponse> {
  const ip =
    request.headers.get("x-forwarded-for")?.split(",")[0]?.trim() ?? "unknown";
  if (!allowRequest(ip)) {
    return NextResponse.json({ error: "Too many requests." }, { status: 429 });
  }

  let body: { claim?: unknown; verdict?: unknown; helpful?: unknown };
  try {
    body = (await request.json()) as typeof body;
  } catch {
    return NextResponse.json({ error: "Invalid JSON body." }, { status: 400 });
  }
  if (
    typeof body.claim !== "string" ||
    typeof body.verdict !== "string" ||
    typeof body.helpful !== "boolean"
  ) {
    return NextResponse.json({ error: "Invalid feedback." }, { status: 422 });
  }

  const apiUrl = process.env.TRUTHLAYER_API_URL;
  const apiKey = process.env.TRUTHLAYER_API_KEY;
  if (!apiUrl || !apiKey) {
    return NextResponse.json({ error: "Server misconfigured." }, { status: 500 });
  }

  const upstream = await fetch(`${apiUrl}/feedback`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-API-Key": apiKey },
    body: JSON.stringify({
      claim: body.claim,
      verdict: body.verdict,
      helpful: body.helpful,
    }),
    signal: AbortSignal.timeout(15_000),
  });

  return new NextResponse(null, { status: upstream.ok ? 204 : 502 });
}
