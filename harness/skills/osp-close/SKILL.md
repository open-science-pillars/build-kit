---
name: osp-close
description: Close roadmap-ID work with acceptance evidence, the deliverable's status and evidence in the roadmap, and a human-reviewed commit handoff.
disable-model-invocation: true
---

# OSP Session Close

Run the gates, then the bookkeeping. Never reorder. Frontmatter, golden
notebooks, surfaces and placeholders are not gates here: the plugin gate and
the qualification records cover them.

## Gates (report each as pass/fail with one line of evidence)
1. Acceptance: run `uv run build-kit/scripts/roadmap.py brief <roadmap-id>` and
   walk every acceptance criterion item by item.
2. Knowledge lint: only if a knowledge/ bundle was touched, run the
   knowledge-linter agent and report its findings (the linter also flags
   high-severity gotchas lacking eval cases).

## Bookkeeping
3. Add the evidence to the deliverable's issue if one exists, and to the
   deliverable's `evidence` list in `build-kit/roadmap/roadmap.yaml`.
4. Set the status: `done` only when every criterion passed, otherwise a
   truthful `active` or `blocked` with the reason. Run validate, render, and
   `audit --offline`.
5. Prepare commits per repository with the roadmap ID in each message. Show the
   diff summary; commit and push only after human confirmation. The pull
   request that finishes the deliverable closes its issue.
6. End with a three-line handoff: verified evidence, remaining gaps, and the
   next dependency or decision.
