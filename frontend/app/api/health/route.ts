// Thin proxy to Render's health endpoint — used for background warmup on page
// load and for polling during cold-start auto-retry.
import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";
// Short maxDuration — this route is polled frequently during cold-start waits.
export const maxDuration = 10;

export async function GET(): Promise<Response> {
  const apiUrl = process.env.TRUTHLAYER_API_URL;
  if (!apiUrl) {
    return NextResponse.json({ status: "misconfigured" }, { status: 500 });
  }

  try {
    const upstream = await fetch(`${apiUrl}/health`, {
      signal: AbortSignal.timeout(7_000),
      cache: "no-store",
    });
    const body = (await upstream.json()) as Record<string, unknown>;
    return NextResponse.json(body, { status: upstream.status });
  } catch {
    return NextResponse.json({ status: "unavailable" }, { status: 503 });
  }
}
