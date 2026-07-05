---
name: osp-close
description: Close an Open Science Pillars build session. Runs verification gates, updates PROGRESS.md and the session log truthfully, and prepares commits.
disable-model-invocation: true
---

# OSP Session Close

Run the gates, then the bookkeeping. Never reorder.

## Gates (report each as pass/fail with one line of evidence)
1. Checkpoint: walk this session's checkpoint list item by item.
2. Frontmatter: every SKILL.md touched today has valid frontmatter;
   descriptions <=200 chars. On Claude Code, run /skills and confirm
   no skill descriptions are truncated or dropped.
3. Knowledge lint: if any knowledge/ bundle was touched, run the
   knowledge-linter agent and report its findings (the linter also
   flags high-severity gotchas lacking eval cases).
4. Golden notebooks: for every workflow skill touched, execute its
   verification/ marimo notebook headless (where one exists per the
   SPEC §6 scope rule); report green or the diff.
5. Surface matrix: list which of today's items still need Cowork and
   Claude Science verification; do not claim those columns.
6. Placeholder sweep: `grep -rln "^Placeholder" <repos>` returns zero,
   or every hit is a declared, session-scheduled placeholder.

## Bookkeeping
7. Update marketplace/docs/PROGRESS.md: statuses with evidence,
   session-log row (date, actual hours, issues).
8. Stage commits per repo with messages "Session N: <summary>".
   Show me the diff summary; push only after my confirmation.
9. End with a three-line handoff note: what is green, what is yellow
   and why, and the single most important thing Session N+1 must know.
