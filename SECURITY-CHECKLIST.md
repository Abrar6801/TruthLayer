# TruthLayer security checklist

Cross-cutting items that don't belong to any single task — review this before
considering any phase "done." Most of these are also baked into CLAUDE.md so
Claude Code should already be applying them as it goes; this checklist catches
what slips through.

## Secrets
- [ ] No API key, DB credential, or token appears in any file tracked by git,
      at any point in history — not just current files (check with a tool
      like git-secrets or trufflehog if unsure).
- [ ] `.env` and `.env.local` are gitignored from the first commit.
- [ ] `pre-commit` is installed with a secrets-scanning hook (detect-secrets
      or gitleaks) so a leaked key gets caught before a commit, not after.
- [ ] The Supabase `service_role` key never appears in any file shipped to
      the browser — check the built Next.js bundle, not just the source.

## Resilience and cost control
- [ ] Every external API call (Anthropic, Tavily, Supabase) has an explicit
      timeout and bounded retries — not just the web-fetching code.
- [ ] There's an enforced upper bound on how many LLM calls a single
      /verify request can trigger across decomposition, judging, and
      retries, not just the retry-loop cap on its own.
- [ ] CI (GitHub Actions or equivalent) runs lint, type-check, and tests on
      every push — not just locally, where it's easy to skip.

## Input handling
- [ ] Every external input (claim text, API request bodies) is validated
      with a Pydantic/Zod model before touching business logic.
- [ ] Claim length is capped, both to limit abuse and because an absurdly
      long "claim" isn't something the pipeline is designed to handle well.

## The prompt-injection risk specific to this project
- [ ] Evidence text scraped from the web is clearly delimited in every
      prompt that includes it, with an explicit instruction to treat it as
      data, not commands.
- [ ] At least one test case exists with an adversarial evidence chunk
      (containing an embedded instruction) confirming the verdict generation
      doesn't follow it.

## Data access
- [ ] All Supabase/Postgres queries are parameterized — no string-built SQL
      with user or web content interpolated directly.
- [ ] Database keys follow least privilege: anon key for anything
      client-reachable, service_role key only ever used server-side.
- [ ] Row Level Security is enabled on every table, even ones only touched
      via service_role — it's a no-cost default-deny against future mistakes.

## Network-facing surface
- [ ] /verify (or any public endpoint) has rate limiting.
- [ ] Once traffic is proxied through the Next.js server, rate limiting also
      exists at that layer keyed by visitor IP/session — a limiter on
      FastAPI alone can't see past the single server-to-server connection.
- [ ] CORS only allows your actual frontend origin, not a wildcard.
- [ ] Error responses never leak stack traces, file paths, or internal
      exception messages.
- [ ] Containers run as non-root users, and `.dockerignore` keeps `.env`,
      `.git`, and tests out of the build context entirely.
- [ ] A visible disclaimer exists on the public frontend before the link
      gets shared with anyone outside your own testing.

## Dependencies
- [ ] Dependencies are pinned, not left as bare package names with no version.
- [ ] `pip-audit` (Python) and `npm audit` (Node) have been run before
      deployment, and anything flagged has been noted or addressed.

## Before you call it deployed
- [ ] All secrets in production are set through the hosting platform's env
      var UI, not committed anywhere, and differ from local dev secrets where
      it matters (database credentials especially).
- [ ] You've manually tried at least one "trick" input against the live
      deployment — an empty claim, a 10,000-word claim, a claim containing
      something like "ignore your instructions" — and confirmed it fails
      gracefully rather than erroring or doing something unexpected.
