# TruthLayer build plan — how to use this

This folder is a self-contained build plan for TruthLayer, broken into 4 phases
and 28 tasks. Each task has a ready-to-paste prompt for the Claude Code CLI.

## Files

- `CLAUDE.md` — put this in the root of your TruthLayer repo. Claude Code reads
  it automatically at the start of every session, so you don't have to repeat
  project context, conventions, or the "explain things to me" instruction in
  every single prompt.
- `01-phase-1-foundations.md` — the linear pipeline, no orchestration framework
  yet. Goal: get something working end to end and understand the fundamentals.
- `02-phase-2-orchestration.md` — LangGraph, FastAPI, Docker.
- `03-phase-3-evals-deploy.md` — LangSmith evals, Next.js frontend, deployment.
- `04-phase-4-production-credibility.md` — measured improvements (reranking,
  parallelization, semantic caching), streaming UX, a real public launch, and
  turning the results into resume bullets. This phase is what separates the
  project from a standard portfolio RAG app.
- `PREREQUISITES-CHECKLIST.md` — everything to have in hand before Task 1.1.
- `SECURITY-CHECKLIST.md` — cross-cutting checklist. Review it before considering
  any phase "done," not just at the end of the project.

## Workflow

1. `git init` a new repo, copy `CLAUDE.md` into the root, commit it first thing.
2. Open a Claude Code session in that repo by running `claude`.
3. Paste the prompt for the next task, in order — phases and tasks are
   sequential, later tasks assume earlier ones already exist.
4. Read the explanation it gives you before moving on. That explanation is the
   actual point of this whole structure, not a formality to skip past.
5. Run whatever it tells you to run to verify the step actually works.
6. `git add -A && git commit` with a short message.
7. Check that `LEARNING_NOTES.md` got a new entry. Move to the next task.

## Prerequisites

- Python 3.11+, Node 18+, Docker Desktop, git
- A Supabase project (free tier) with the project URL, anon key, and
  service_role key
- An Anthropic API key
- A web search API key — Tavily has a generous free tier and is built for
  exactly this use case (LLM-facing search), so it's the default assumption in
  these prompts. Swap for Serper or Bing if you'd rather.

## Pacing

This is scoped as a side project, not a sprint, given everything else you've
got going with the job search. Roughly: Phase 1 in a weekend or two, Phase 2
over one to two weeks, Phase 3 over one to two weeks, Phase 4 over two to
three weeks — noting that Task 4.6 includes a 1-2 week window where the app
just runs and collects real usage while you work on other things. Don't skip
the explanation step to go faster — the eval numbers and the "why did you
build it this way" answer are what actually make this useful in an interview.
A working demo with no understanding of why it works is a much weaker
portfolio piece than a half-finished one you can explain in depth.

One sequencing note: the project can legitimately go on your resume after
Phase 3 (it works, it's deployed, it has eval numbers), and the bullets get
stronger as Phase 4 results land — you don't have to wait for everything to
finish before it counts.
