# Latency report — Task 4.3 (parallel sub-claim retrieval)

Comparison of the frozen baseline (`20260708T182007Z_baseline`, sequential
fan-out) against `20260708T183028Z_rerank_parallel` (sub-claim search/fetch
cycles running on a bounded 3-worker thread pool, with all branches' chunks
merged into a single embedding batch).

**Methodology note:** the "after" run also has cross-encoder reranking
enabled (Task 4.2), which *added* ~1.15s to the `retrieve` stage. The
per-stage table below separates the effects; the parallelization win is the
`search_and_embed` row. End-to-end numbers therefore *understate* the
concurrency gain slightly.

## Headline numbers

| Metric | Baseline (sequential) | Parallel (+rerank) | Δ |
|---|---|---|---|
| p50 end-to-end latency | 14.9 s | 10.5 s | **−30%** |
| p95 end-to-end latency | 25.1 s | 15.3 s | **−39%** |
| `search_and_embed` (avg) | 10.95 s | 4.73 s | **−57%** |
| `retrieve` (avg) | 0.09 s | 1.24 s | +1.15 s (reranker, Task 4.2) |
| `decompose` (avg) | 1.80 s | 2.17 s | ≈ noise (single LLM call) |
| `judge` (avg) | 3.04 s | 3.48 s | ≈ noise (single LLM call) |

The p95 improvement (−39%) is larger than the p50 improvement (−30%)
because the tail is where multi-sub-claim compound claims live — exactly the
requests that previously ran 3-4 sequential search cycles and now overlap
them.

## Did accuracy change?

Accuracy moved 77.5% → 75.0%, entirely accounted for by **one mixed claim
whose retrieved evidence changed under the reranker** (see
`reranking_report.md` for the chunk-level diff). Attribution to reranking
rather than concurrency: concurrency changes only the *timing* of the
search fan-out — URL dedup is applied deterministically in query order at
merge time, per-branch chunk caps are unchanged, and no LLM call happens in
the parallelized section. The remaining judge outputs matched the baseline
claim-for-claim on both runs' overlap. No shared-state anomaly appeared.

## Design notes (what was actually parallelized)

- **What runs concurrently:** the network phase per sub-claim — Tavily
  search + page-text extraction + chunking. This is I/O-bound waiting:
  the thread sits idle on sockets, which is why threads (or asyncio) buy
  real wall-clock time. A CPU-bound stage would gain nothing on GIL-bound
  threads.
- **Threads vs asyncio:** the underlying stack (httpx sync client, local
  embedding model) is synchronous; converting to asyncio would have meant
  either an async rewrite of every I/O call or `asyncio.to_thread` — which
  is a thread pool with extra steps. `ThreadPoolExecutor(max_workers=3)`
  states the same intent directly.
- **The bound (semaphore role):** `max_workers=3` is the concurrency limit —
  a 4-sub-claim decomposition fires at most 3 simultaneous Tavily calls,
  respecting free-tier rate limits. Unbounded fan-out is how agentic
  systems accidentally DoS their own dependencies.
- **What deliberately stayed sequential:** embedding and the DB insert. The
  local model isn't guaranteed thread-safe, and merging all branches'
  chunks first turns N small embedding batches into one large one — batched
  inference is *more* efficient, so the "sequential" part got faster too.
- **LLM budget under concurrency:** no Claude calls occur in the
  parallelized section, so the request-wide call cap is structurally
  unaffected (verified by the graph's budget tests).
