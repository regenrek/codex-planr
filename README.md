# codex-planr

Portable repo-local planning and execution workflow for Codex.

This repo gives you a small system you can copy into any codebase so agents work with explicit plans, honest status, scoped review, and real verification evidence instead of vague chat-state.

## What You Get

- `.planr/`
  Durable project context, scoped plans, live status, optional saved reviews, and the shared `planr.py` helper.
- `.codex/skills/planr-plan`
  Create or update a real execution plan.
- `.codex/skills/planr-fix`
  Implement scoped work to verified completion.
- `.codex/skills/planr-status`
  Answer what is actually done, blocked, or next.
- `.codex/skills/planr-review`
  Review work against the plan with scoped Git evidence.
- `.codex/skills/planr-summary`
  Explain the outcome in plain language after the evidence exists.
- `python3 .planr/tooling/planr.py`
  The shared CLI for deterministic `.planr` plan and status mutations.

## Core Workflow

1. `planr-plan`
   Define the scope, ownership, phases, verification, and acceptance criteria.
2. `planr-fix`
   Implement the work and keep `.planr/status/current.json` honest.
3. `planr-status`
   Check the smallest honest verdict for the current scope.
4. `planr-review`
   Audit the result against the plan, diff, and tests.
5. `planr-summary`
   Recap what changed, what works, and what remains blocked or unverified.

The real contract lives in `.planr/`. The skills are just the operating instructions for working with that contract consistently.

## New Project Setup

From the root of the target repository:

```bash
mkdir -p .codex/skills
cp -R /path/to/codex-simple-tasks/.planr .
cp -R /path/to/codex-simple-tasks/.codex/skills/planr-* .codex/skills/
cp /path/to/codex-simple-tasks/.codex/skills/planr-shared.md .codex/skills/
```

Then customize the project context pack before asking agents to make architectural decisions:

- `.planr/project/product.md`
- `.planr/project/ownership.md`
- `.planr/project/flows.md`
- `.planr/project/state-ssot.md`
- `.planr/project/constraints.md`
- `.planr/project/quality-gates.md`

Those files are intentionally generic templates. Rewrite them for the target repo so planning, fixing, and review use the right boundaries and verification rules.

## Running The Workflow

1. Ask Codex to use `planr-plan` when the task needs a contract.
2. Ask Codex to use `planr-fix` to implement the scoped work.
3. Ask for `planr-status` when you want the smallest honest progress verdict.
4. Ask for `planr-review` when you want a findings-first audit.
5. Ask for `planr-summary` when you want a user-facing recap.

## Why There Is No `planr-cli` Skill

The dedicated `planr-cli` skill is unnecessary.

It does not add a distinct workflow or judgment layer. It is only a thin wrapper around the real tool:

```bash
python3 .planr/tooling/planr.py
```

The lean version of the system is simpler:

- keep the five core skills
- keep the shared CLI
- let `planr-plan`, `planr-fix`, and `planr-status` call the CLI directly when they need deterministic `.planr` mutations

## Repo Layout

```text
.planr/
  project/         durable repo context
  plans/           scoped execution contracts
  status/          live status summary
  review/          optional persisted reviews
  tooling/planr.py deterministic helper CLI

.codex/skills/
  planr-shared.md
  planr-plan/
  planr-fix/
  planr-status/
  planr-review/
  planr-summary/
```

## Verification

When the shared CLI changes, run:

```bash
python3 .planr/tooling/planr.py --help
python3 .planr/tooling/test_planr.py
python3 -m py_compile .planr/tooling/planr.py .planr/tooling/test_planr.py
```

## License

MIT. See `LICENSE.md`.
