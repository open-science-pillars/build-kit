# workflows

Reusable Claude Code workflow scripts for maintaining Open Science Pillars.

- **persona-doc-review.js**: reviews the documentation across the org repos
  through five personas (newcomer scientist, grad student, contributor,
  data-provider steward, future core developer), deduplicates, then
  adversarially verifies each claimed blocker before it becomes a fix task.
  Run it after a documentation change to catch journey-level regressions.

- **knowledge-coupling-review.js** classifies every skill and agent across the
  plugins against the knowledge-coupling rule (skills = procedures plus hard
  refusals; dataset knowledge = single-source concepts consulted dynamically)
  and emits a per-file migration plan. Pass `{root, files: [...]}` as args
  (actual JSON, not a string). Re-run to catch drift.

- **knowledge-coupling-migrate.js** applies the plan the review produced:
  one agent per file, editing distinct files, slims each skill or agent to
  its procedure plus hard refusals, moves dataset-specific knowledge into
  draft concepts, and adds the dynamic consult step. Pass `{root, files:
  [...]}` and optionally `protected` (a comma-separated list of concept
  names that must not change) as args. The rule it applies is the
  marketplace's `docs/knowledge-vs-skills.md`.

Run from a workspace created by `../bootstrap.sh`; the script reads the repos
read-only. It takes an optional `{root: "<workspace path>"}` argument if your
repos are not at the default location.
