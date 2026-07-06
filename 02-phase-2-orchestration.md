# Phase 2 — orchestration (LangGraph, FastAPI, Docker)

Goal of this phase: turn the linear Phase 1 script into an agentic graph that
can decompose claims, retry on low confidence, and serve over an API in a
container. This is where most of the "AI engineer" portfolio signal lives.

---

## Task 2.1 — LangGraph state & graph skeleton

**Concepts you'll learn:** LangGraph state machines, nodes and edges, shared
state schemas, conditional edges.

```
<task>
Refactor the Phase 1 pipeline into a LangGraph graph. Start with the graph
skeleton and state schema only — don't migrate real logic yet, that happens
in the next few tasks.
</task>
<requirements>
- A TruthLayerState TypedDict or Pydantic model holding everything that
  flows through the graph: claim, sub_claims, search_results,
  evidence_chunks, verdict, confidence, errors.
- A graph skeleton in src/truthlayer/graph.py with placeholder no-op nodes
  for: decompose, search_and_embed, retrieve, judge, and a conditional edge
  after judge that loops back to retrieve (with a max-retry cap) if
  confidence is below a threshold, otherwise ends.
- Compile and run the skeleton end to end with dummy data to confirm the
  graph structure and looping logic work before real logic goes in.
</requirements>
Follow CLAUDE.md for the explanation and learning-notes requirements. Explain
what a state machine buys you here versus the plain function chain from
Phase 1, and what the conditional retry edge is actually protecting against.
```

---

## Task 2.2 — Decompose node

**Concepts you'll learn:** claim decomposition / query planning, prompting
for sub-questions, why multi-hop retrieval helps fact-checking.

```
<task>
Implement the decompose node: given a claim, ask Claude to break it into 1-4
independently checkable sub-claims, skipping decomposition for already-atomic
claims.
</task>
<requirements>
- Prompt Claude to return a small JSON list of sub-claims, validated with
  Pydantic.
- If the claim is already atomic or simple, the node should return it
  unchanged as a single sub-claim rather than forcing artificial
  decomposition.
- A unit test with 2-3 example claims (one compound, one atomic) checking the
  decomposition behaves sensibly.
</requirements>
Follow CLAUDE.md for the explanation and learning-notes requirements. Explain
what claim decomposition buys a fact-checker over checking the whole claim as
one blob, using a concrete example of a compound claim where it matters.
```

---

## Task 2.3 — Search and retrieve nodes

**Concepts you'll learn:** porting linear code into graph nodes, fan-out over
sub-claims, deduplicating evidence across sub-claims.

```
<task>
Port the Phase 1 search/embed/retrieve logic (Tasks 1.3-1.5) into the
search_and_embed and retrieve graph nodes, running once per sub-claim from
Task 2.2 and merging results.
</task>
<requirements>
- Each sub-claim runs its own search -> chunk -> embed -> store cycle, then
  retrieval pulls relevant chunks for the original claim across all newly
  stored evidence.
- Deduplicate evidence chunks that come from the same URL across different
  sub-claim searches.
- Reuse the Phase 1 modules — don't duplicate the chunking/embedding code,
  import it.
</requirements>
Follow CLAUDE.md for the explanation and learning-notes requirements. Explain
the dedup logic and why merging evidence across sub-claims, rather than
judging each sub-claim in isolation, matters for the final verdict.
```

---

## Task 2.4 — Judge node and retry loop

**Concepts you'll learn:** the self-critique/reflection agent pattern,
confidence-gated retries, avoiding infinite loops in agentic systems.

```
<task>
Implement the judge node (porting Task 1.6's verdict logic) and make the
confidence-gated retry loop from Task 2.1 actually work: if confidence is
low, the graph should try a broadened search before judging again.
</task>
<requirements>
- On retry, broaden the search query (e.g. drop overly specific terms, or
  have Claude suggest an alternative query) rather than re-running the
  identical search.
- Hard cap of 2 retries — after that, return the verdict as-is with an
  explicit "low confidence, evidence may be incomplete" flag rather than
  looping forever.
- Log each retry attempt with the reason it was triggered.
</requirements>
Follow CLAUDE.md for the explanation and learning-notes requirements. Explain
the self-critique/reflection pattern this implements and why a hard retry cap
is a necessary safeguard, not just a nice-to-have.
```

---

## Task 2.5 — FastAPI wrapper

**Concepts you'll learn:** REST API design, Pydantic request/response models,
async endpoints, auto-generated API docs.

```
<task>
Wrap the compiled LangGraph pipeline in a FastAPI service.
</task>
<requirements>
- POST /verify accepting {"claim": str}, returning the structured verdict
  from the graph.
- GET /health for a basic liveness check.
- Pydantic models for request and response — no raw dicts crossing the API
  boundary.
- Run the graph invocation asynchronously so the endpoint doesn't block the
  event loop on the LLM/network calls.
- Confirm the auto-generated OpenAPI docs at /docs work correctly given your
  typed models.
</requirements>
<security_and_best_practices>
- Validate claim length (reject empty or absurdly long input) before it
  reaches the graph.
- Add a basic rate limiter (e.g. slowapi) on /verify so this can't be
  hammered into a large Anthropic/search API bill.
</security_and_best_practices>
Follow CLAUDE.md for the explanation and learning-notes requirements. Explain
why async matters for an I/O-heavy endpoint like this one specifically.
```

---

## Task 2.6 — Auth and hardening pass

**Concepts you'll learn:** API key auth for your own service, CORS, the
difference between user auth and service-to-service auth.

```
<task>
Add a lightweight auth layer and CORS config to the FastAPI service before
it's exposed to anything beyond localhost.
</task>
<requirements>
- A simple API-key-in-header auth dependency for /verify, comparing against a
  key from env vars (not hardcoded) — this is your own app's key, distinct
  from the Anthropic API key.
- A restrictive CORS config that only allows your future Next.js frontend's
  origin, configurable via env var so it differs between local dev and
  production.
- Centralized error handling that returns clean error responses and never
  leaks stack traces or internal exception details to the client.
</requirements>
Follow CLAUDE.md for the explanation and learning-notes requirements. Explain
the difference between authenticating a user and authenticating a
service-to-service call, and which one this is.
```

---

## Task 2.7 — Dockerize

**Concepts you'll learn:** multi-stage Docker builds, running containers as
non-root, docker-compose for local dev, image size considerations.

```
<task>
Containerize the FastAPI service for local development and eventual
deployment.
</task>
<requirements>
- A multi-stage Dockerfile: a build stage installs dependencies, the final
  stage copies only what's needed to run, keeping the final image lean.
- A .dockerignore excluding .env, .git, tests/, and other files that should
  never enter the build context in the first place.
- The container runs as a non-root user.
- A docker-compose.yml for local dev that runs the API container alongside a
  local Postgres+pgvector container, so I'm not hitting production Supabase
  while developing, with env vars passed via .env.
- Confirm both `docker build` and `docker compose up` work and the /health
  endpoint responds.
</requirements>
<security_and_best_practices>
- No secrets baked into the image layers — confirm with `docker history`
  that .env contents don't show up anywhere in the image.
</security_and_best_practices>
Follow CLAUDE.md for the explanation and learning-notes requirements. Explain
why multi-stage builds and non-root users matter for a container that will
eventually be internet-facing.
```
