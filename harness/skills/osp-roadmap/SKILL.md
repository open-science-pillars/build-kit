---
name: osp-roadmap
description: Validate, render, audit, and explain the Open Science Pillars roadmap, the single YAML that says what is proposed, active, blocked, done and declined.
---

# OSP Roadmap

Use `build-kit/roadmap/roadmap.yaml` as the single source of truth for
organization work. Never treat generated `build-kit/ROADMAP.md` or historical
`osp-next-steps-codex.md` as editable sources.

## Choose the operation

- For status, next work, or a named deliverable, validate and run `brief`;
  the summary on top of `ROADMAP.md` says what is now, blocked, next and later.
- After YAML edits, validate, render, and run the offline audit.
- For repository drift, run the online audit and report findings before edits.
- For labels, run the dry-run first and show it to the human.

## Commands

Run commands from the workspace root:

```bash
uv run build-kit/scripts/roadmap.py validate
uv run build-kit/scripts/roadmap.py render --check
uv run build-kit/scripts/roadmap.py audit --offline
uv run build-kit/scripts/roadmap.py brief <roadmap-id>
```

These commands query GitHub but do not mutate it by default:

```bash
uv run build-kit/scripts/roadmap.py audit
uv run build-kit/scripts/roadmap.py labels
```

`labels` is the only GitHub write, and it requires both `--apply` and
`--confirm-org open-science-pillars`. Pause and obtain explicit human approval
after the matching dry-run before adding those flags. The tool never opens,
edits, or closes issues.

## Edit the roadmap

1. Read `build-kit/docs/roadmap-harness-plan.md` for the status model.
2. Edit only `build-kit/roadmap/roadmap.yaml`.
3. Preserve stable IDs; add a replacement item instead of repurposing one.
4. New work is `proposed`. It becomes `active` when work starts and an issue
   exists in its repository; record the issue number and URL then, never
   invent one.
5. Require evidence before `done`; require a gate or dependency for `blocked`;
   require a reason in `gate` for `declined`.
6. Render and audit. Include the generated Markdown in the same change.

## Report

Separate errors from actionable drift and warnings. State which repository owns
each proposed action. A done or declined deliverable whose issue is still open
needs the issue closed; an active deliverable with no issue number needs one
opened and recorded.
