# Planr Shared Baseline

Use this with any repo-local `planr-*` skill.

## Non-Negotiable

- Prefer `python3 .planr/tooling/planr.py` whenever its command surface fits the task.
- Do not hand-edit `.planr/status/current.json` or scaffold a new `.planr/plans/*.plan.md` file by hand when the CLI already covers that operation.
- Do not invent unsupported `planr.py` subcommands. Today the CLI supports only `plan` and `status`.

## Current CLI Surface

Use these commands as the deterministic first path:

```bash
python3 .planr/tooling/planr.py plan new --title "..." --overview "..." [--todo id=content] [--slug slug] [--project]

python3 .planr/tooling/planr.py status show [--scope scope-id]
python3 .planr/tooling/planr.py status open
python3 .planr/tooling/planr.py status next

python3 .planr/tooling/planr.py status ensure-scope --id scope-id [--title "..."] [--status pending|in_progress|blocked|completed|cancelled] [--source "..."] [--plan-path path] [--owned-path path]
python3 .planr/tooling/planr.py status set-checklist --scope scope-id --item-id item-id --content "..." --status pending|in_progress|blocked|completed|cancelled
python3 .planr/tooling/planr.py status set-blocker --scope scope-id --item-id item-id --content "..." --status blocked|unverified
python3 .planr/tooling/planr.py status set-verification --scope scope-id --verification-id verification-id --status not_run|passed|failed|blocked --result "..." [--command "..."]
```

## What Each Source Means

- `.planr/plans/*.plan.md`: scoped execution contract
- `.planr/status/current.json`: live scope state
- `.planr/project/*.md`: project context pack
- path-scoped Git diff, implementation files, and tests: proof of the actual code state

## Shared Read Order

1. Use the CLI first for plan or status questions and for supported `.planr` mutations.
2. Read the governing `.planr` artifacts next: relevant plan file, live scope state, and any explicitly referenced historical source doc still in scope.
3. Read the project-context pack only when ownership, runtime boundaries, state boundaries, or quality gates matter:
   - `.planr/project/product.md`
   - `.planr/project/ownership.md`
   - `.planr/project/flows.md`
   - `.planr/project/state-ssot.md`
   - `.planr/project/constraints.md`
   - `.planr/project/quality-gates.md`
4. Drop to implementation files, tests, and path-scoped Git evidence only when the CLI and recorded `.planr` state are insufficient.

## When CLI Coverage Ends

- There is no `planr.py fix` command today.
- There is no `planr.py review` command today.
- There is no general-purpose command for editing an existing plan body beyond `plan new`.
- `planr-review` still requires direct path-scoped Git evidence.
- `planr-fix` still requires direct code, test, and verification work.
- `planr-summary` still requires a synthesized narrative from the recorded evidence.

In those cases, keep the `.planr` parts deterministic with the CLI, then use files, diff, and tests for the parts the CLI does not cover.
