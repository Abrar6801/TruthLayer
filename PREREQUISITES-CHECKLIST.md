# TruthLayer — before you start Task 1.1

A literal checklist. Everything here should be true before you open the first
Claude Code session.

## Accounts and API keys

- [ ] Anthropic API key created (platform.claude.com — separate from your
      claude.ai login)
- [ ] Supabase project created, with the project URL, `anon` key, and
      `service_role` key saved somewhere (not yet in any file)
- [ ] Tavily account and API key created (1,000 free credits/month covers
      dev and the eval set)
- [ ] LangSmith account and API key created, and you've picked a project
      name (5,000 free traces/month)
- [ ] GitHub account ready, new empty repo created for TruthLayer
- [ ] Render or Fly.io account created — pick one now (see "decisions" below)
- [ ] Vercel account created

## Local environment

- [ ] Python 3.11 or newer installed (`python3 --version`)
- [ ] Node 18 or newer installed (`node --version`)
- [ ] Docker Desktop installed and actually running, not just installed
      (`docker ps` works)
- [ ] git installed and configured with your name/email
- [ ] Claude Code CLI installed and authenticated (`claude` opens a session)
- [ ] `pre-commit` available on your machine (`pipx install pre-commit` or
      `pip install pre-commit`) — Task 1.1 configures the hooks, but the
      tool itself needs to already be installed

## Decisions to lock in now, not mid-task

- [ ] **Embedding model and dimension.** Task 1.2 needs this on day one now
      that the schema and the model choice are tied together. Default if
      you don't have a strong preference: `sentence-transformers/all-MiniLM-L6-v2`,
      384 dimensions — well documented, runs fine on CPU, no GPU needed.
- [ ] **Deployment host.** Render or Fly.io — doesn't matter much which,
      just decide now so Task 2.7's Docker setup matches what Task 3.6
      actually deploys to.
- [ ] Repo name decided and the empty GitHub repo exists.

## Start this in parallel, don't wait for Phase 3

- [ ] Eval dataset groundwork — start a running list of claims you can
      personally verify the answer to (true/false/mixed/unverifiable), aiming
      for 30-50 by the time you reach Task 3.1. This is the one part of the
      whole plan that's bottlenecked by your research time, not coding time.

## Worth knowing before anything is live

- [ ] Supabase free projects pause after 7 days with no activity (restores in
      seconds, but a stale demo link will look broken for a moment first)
- [ ] Render free web services spin down after 15 minutes idle and take
      about a minute to wake on the next request
- [ ] Free tier ceilings to keep in mind so you don't blow through them by
      accident: Tavily 1,000 searches/month, LangSmith 5,000 traces/month,
      Supabase 500MB database storage on 2 projects max

## Right before you open Claude Code for Task 1.1

- [ ] `CLAUDE.md` copied into the root of the new repo
- [ ] You know which four values are going into `.env` once Task 1.1 creates
      it: `ANTHROPIC_API_KEY`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`,
      `TAVILY_API_KEY` (LangSmith's key gets added in Phase 3, no rush on that one)
