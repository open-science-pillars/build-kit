---
name: osp-roadmap
description: Audit, render, explain, and safely reconcile the federated Open Science Pillars roadmap across repositories and GitHub issues.
---

# OSP Roadmap

Use `build-kit/roadmap/roadmap.yaml` as the organization portfolio and each
repository's accepted issue as that repository team's execution record. Never
treat generated `build-kit/ROADMAP.md` or historical
`osp-next-steps-codex.md` as editable sources.

## Choose the operation

- For status, next work, or a named deliverable, validate and run `brief`.
- After YAML edits, validate, render, and run the offline audit.
- For repository drift, run the online audit and report findings before edits.
- For labels, proposal issues, publishing, or reconciliation, always run the
  dry-run first and show it to the human.
- Do not accept a proposal on behalf of a repository team.

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
uv run build-kit/scripts/roadmap.py seed
uv run build-kit/scripts/roadmap.py publish
uv run build-kit/scripts/roadmap.py reconcile
```

GitHub writes require both `--apply` and
`--confirm-org open-science-pillars`. Pause and obtain explicit human approval
after the matching dry-run before adding those flags. Treat label creation,
issue creation or editing, and reconciliation writes as separate approvals.

## Edit the portfolio

1. Read `build-kit/docs/roadmap-harness-plan.md` for authority boundaries.
2. Edit only `build-kit/roadmap/roadmap.yaml`.
3. Preserve stable IDs; add a replacement item instead of repurposing one.
4. Use `draft` for unreviewed proposals. Only repository maintainers may move
   a proposal to `accepted`, `deferred`, or `rejected`.
5. Require evidence before `done`; require a gate or dependency for `blocked`.
6. Render and audit. Include the generated Markdown in the same change.

## Report

Separate errors from actionable drift and warnings. State which repository owns
each proposed action. When an issue is accepted, do not overwrite its managed
body; repository maintainers own its execution and completion evidence.
