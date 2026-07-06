# Phase 3 — evals, frontend, deployment

Goal of this phase: turn the working pipeline into something with real
measured numbers behind it, a usable frontend, and a live deployed link you
can put in front of an interviewer.

---

## Task 3.1 — Eval dataset

**Concepts you'll learn:** building a golden eval set, label quality, why
dataset size and difficulty mix matter.

```
<task>
Build a small hand-labeled evaluation dataset for TruthLayer.
</task>
<requirements>
- An eval/dataset.json (or .csv) with 30-50 claims I've personally verified
  the answer to, spanning true, false, mixed, and unverifiable categories,
  with the correct verdict and, where applicable, a reference source URL.
- A short script that loads this dataset and runs it through the /verify
  endpoint or the graph directly, saving the model's outputs alongside the
  ground truth for later scoring.
- Mix easy/unambiguous claims with a few genuinely hard or ambiguous ones —
  an eval set of only easy claims won't tell us anything useful.
</requirements>
Follow CLAUDE.md for the explanation and learning-notes requirements. Explain
why eval set size and label quality matter more than people expect, and what
could go wrong if I'd just used 5 obvious claims instead.
```

---

## Task 3.2 — LangSmith tracing

**Concepts you'll learn:** observability for LLM applications, trace
metadata, debugging multi-step agents via traces instead of print statements.

```
<task>
Wire up LangSmith tracing across the LangGraph pipeline so every run is fully
observable.
</task>
<requirements>
- Enable LangSmith tracing via env vars (project name, API key), and confirm
  traces show up in the LangSmith UI for a real run.
- Tag each trace with useful metadata (claim text, which retry attempt, final
  confidence) so traces are filterable and searchable later.
- Document in README.md how to view a trace and what it shows: which node
  ran, how long each step took, and the full prompts/responses at each step.
</requirements>
Follow CLAUDE.md for the explanation and learning-notes requirements. Explain
what tracing gives you that simple console logging doesn't, especially for a
multi-step graph that can retry.
```

---

## Task 3.3 — Eval scoring

**Concepts you'll learn:** accuracy/precision/recall for classification,
retrieval-quality metrics, the LLM-as-judge pattern and its limitations.

```
<task>
Build the evaluation scoring script that turns Task 3.1's dataset and
outputs into actual numbers.
</task>
<requirements>
- Verdict accuracy: percentage of claims where the predicted verdict matches
  ground truth, plus a confusion matrix across the four verdict categories.
- Retrieval quality: for claims where I know a "correct" source, check
  whether evidence from that source or domain was actually retrieved.
- A faithfulness check: a simple LLM-as-judge pass where Claude is asked
  whether a rationale's claims actually follow from the cited evidence, run
  on a sample of outputs. Explain that this is a known pattern (LLM-as-judge)
  and what its limitations are.
- Output a readable eval/report.md with the numbers and a couple of concrete
  failure examples, not just aggregate stats.
</requirements>
Follow CLAUDE.md for the explanation and learning-notes requirements. Explain
why accuracy alone is a weak metric here, and why looking at actual failure
cases matters more than the headline number.
```

---

## Task 3.4 — Next.js frontend

**Concepts you'll learn:** Next.js App Router data fetching, form handling,
designing for slow/long-running requests.

```
<task>
Build a minimal Next.js 14 frontend: a claim input box, a submit button, and
a result view.
</task>
<requirements>
- A single page with a textarea for the claim, a submit button calling the
  FastAPI /verify endpoint, and a result card showing the verdict,
  confidence, rationale, and a list of cited sources as links.
- A loading state while the request is in flight — this pipeline can take
  10-20+ seconds across multiple LLM calls, and the UI needs to communicate
  that clearly rather than just appearing frozen.
- An error state if the API call fails or times out.
- Use the App Router with either Server Actions or a simple client-side
  fetch — your call, but explain which you picked and why.
</requirements>
Follow CLAUDE.md for the explanation and learning-notes requirements. Explain
the loading-state design decision given how long this pipeline actually takes
end to end.
```

---

## Task 3.5 — Frontend-backend integration and env config

**Concepts you'll learn:** API client patterns, env var handling across
dev/prod, the difference between browser-visible and server-only env vars.

```
<task>
Connect the frontend to the real backend cleanly across local dev and
production, and add the API key auth from Task 2.6 on the frontend side.
</task>
<requirements>
- A small typed API client module, not fetch calls scattered through
  components, that reads the backend URL and API key from the appropriate
  env vars.
- Confirm the API key used to call the backend is NOT exposed in the
  client-side bundle — it should be called from a Next.js server
  action/route handler, not directly from the browser.
- Add rate limiting at this Next.js layer too, keyed by visitor IP or
  session — once this is live, all traffic gets proxied through one
  server-to-server connection, so FastAPI's rate limiter from Task 2.5 only
  ever sees your Vercel server's IP, not the actual visitor's. Without a
  limiter here, FastAPI's limiter can't tell one abusive visitor from a
  hundred different ones.
- Test the full path end to end: type a claim in the browser, see a real
  verdict come back from the Dockerized API.
</requirements>
<security_and_best_practices>
- Double-check which env vars are NEXT_PUBLIC_ (browser-visible) versus
  server-only, and confirm secrets are in the right bucket.
</security_and_best_practices>
Follow CLAUDE.md for the explanation and learning-notes requirements. Explain
the NEXT_PUBLIC_ versus server-only env var distinction and why getting it
wrong here would leak the API key.
```

---

## Task 3.6 — Deployment

**Concepts you'll learn:** containerized deployment to a PaaS, managed
Postgres in production, environment parity between dev and prod.

```
<task>
Deploy TruthLayer: the backend container to Render or Fly.io, the frontend to
Vercel, and the database on Supabase production.
</task>
<requirements>
- Deploy the Docker image from Task 2.7 to your chosen host's free tier, with
  all secrets set via that platform's env var/secrets UI, never committed.
- Point the deployed backend at production Supabase, not the local
  docker-compose Postgres from dev.
- Deploy the Next.js app to Vercel, pointed at the deployed backend URL, with
  CORS updated to allow the real Vercel domain.
- Add a short, visible disclaimer on the frontend before sharing the link
  with anyone — this is a demo project, verdicts may be inaccurate, don't
  submit sensitive personal information. Once it's live, anyone can type
  anything into it.
- Smoke-test the live deployed app with 2-3 claims, and confirm the eval
  script from Task 3.3 can also be pointed at the deployed URL.
</requirements>
Follow CLAUDE.md for the explanation and learning-notes requirements. Explain
what "environment parity" means and where this deployment does and doesn't
achieve it.
```

---

## Task 3.7 — Documentation and portfolio polish

**Concepts you'll learn:** technical writing for an interview audience,
documenting architecture decisions, being honest about limitations.

```
<task>
Write the final project README aimed at someone evaluating this for a job
interview, not just a future-me reminder.
</task>
<requirements>
- Sections: what it does and why (one paragraph), an architecture overview
  with a simple diagram, the tech stack and why each piece was chosen, the
  eval results from Task 3.3 with the actual numbers, known limitations and
  what you'd do with more time, and how to run it locally.
- Link to or summarize LEARNING_NOTES.md as evidence of the learning process,
  not just the end result.
- Keep it honest about limitations — a fact-checker that's right 80% of the
  time on a 40-claim eval set is a legitimate, explainable result. Don't
  oversell it.
</requirements>
Follow CLAUDE.md for the explanation and learning-notes requirements. This
closes the project — also write a final retrospective in LEARNING_NOTES.md:
what you'd explain confidently in an interview versus what still needs more
practice.
```
