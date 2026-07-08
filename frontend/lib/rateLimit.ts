// Per-visitor rate limiting at the Next.js layer.
//
// Why this exists when FastAPI already rate-limits: once deployed, every
// browser request is proxied through this server, so FastAPI only ever sees
// ONE client IP (this server's). Its limiter can't tell one abusive visitor
// from a hundred honest ones — visitor-level limiting has to happen here,
// where the visitor's IP is still visible.
//
// In-memory sliding window: fine for a single-instance demo deployment.
// (On a multi-instance/serverless host each instance keeps its own counts —
// the documented tradeoff; a shared store like Upstash fixes it if needed.)

const WINDOW_MS = 60_000;
const MAX_REQUESTS_PER_WINDOW = 5;

const hits = new Map<string, number[]>();

/** Returns true when `ip` is within its request budget. */
export function allowRequest(ip: string): boolean {
  const now = Date.now();
  const recent = (hits.get(ip) ?? []).filter((t) => now - t < WINDOW_MS);
  if (recent.length >= MAX_REQUESTS_PER_WINDOW) {
    hits.set(ip, recent);
    return false;
  }
  recent.push(now);
  hits.set(ip, recent);
  // Opportunistic cleanup so the map can't grow unboundedly.
  if (hits.size > 10_000) {
    hits.forEach((times, key) => {
      if (times.every((t) => now - t >= WINDOW_MS)) hits.delete(key);
    });
  }
  return true;
}
