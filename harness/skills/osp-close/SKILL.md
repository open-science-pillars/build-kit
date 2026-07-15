---
name: osp-close
description: Close roadmap-ID work with acceptance evidence, repository-owned status, roadmap reconciliation, and a human-reviewed commit handoff.
disable-model-invocation: true
---

# OSP Session Close

Run the gates, then the bookkeeping. Never reorder.

## Gates (report each as pass/fail with one line of evidence)
1. Acceptance: run `uv run build-kit/scripts/roadmap.py brief <roadmap-id>` and
   walk every acceptance criterion item by item.
2. Frontmatter: every SKILL.md touched today has valid frontmatter;
   descriptions <=200 chars. On Claude Code, run /skills and confirm
   no skill descriptions are truncated or dropped.
3. Knowledge lint: if any knowledge/ bundle was touched, run the
   knowledge-linter agent and report its findings (the linter also
   flags high-severity gotchas lacking eval cases).
4. Golden notebooks: for every workflow skill touched, execute its
   verification/ marimo notebook headless (where one exists per the
   SPEC §6 scope rule); report green or the diff.
5. Surface matrix: list every supported surface that still needs verification;
   do not claim an untested Claude or Codex surface.
6. Placeholder sweep: `grep -rln "^Placeholder" <repos>` returns zero,
   or every hit is a declared, session-scheduled placeholder.

## Bookkeeping
7. Add durable evidence links to the owning repository issue. Repository
   maintainers decide whether the issue is complete; never infer acceptance or
   completion from code alone.
8. Update `build-kit/roadmap/roadmap.yaml` only after issue state supports the
   change. Run validate, render, and audit; use `reconcile` dry-run first.
9. Prepare commits per repository with the roadmap ID in each message. Show the
   diff summary; commit and push only after human confirmation.
10. End with a three-line handoff: verified evidence, remaining gaps, and the
    next dependency or repository decision.
