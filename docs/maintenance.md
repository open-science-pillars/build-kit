# Maintenance: the standing process

**Status:** ADOPTED 2026-07-06. Maintenance is a standing process, not an
initiative (see `development-model.md`). It has triggers and a cadence, not a
session number. This doc closes the one process gap the build left open:
before this, re-verification only happened if the linter happened to run at a
session close.

Maintenance produces pull requests, reviewed under `.github/GOVERNANCE.md`. None
of it needs `/osp-session`. When a maintenance finding is large enough to need a
plan and a gate (a product baseline changed and a whole bundle must be
re-verified), promote it to an initiative; otherwise handle it in place.

## The cadence

Run the sweep below on a schedule (suggested: monthly for the quick checks,
quarterly for the full re-verification pass). The checks are tools that already
exist; the discipline this doc adds is running them on a clock, not only at a
session close.

### Quick sweep (monthly, or on any relevant event)

1. **Linter, every bundle.** Run the `knowledge-linter` agent on each
   `knowledge/` bundle. Act on its flags:
   - check 4 (staleness sense, on top of the checker's W5): a stale
     candidate, queue re-verification.
   - checks 6 and 2 (`upstream: pending` older than 60 days; `disputed` without
     an open linked issue): resolve or escalate.
   - checks 10 to 13 (coupling drift: inlined concept content, unjustified
     hardcode, inert concept, consult drift): a skill has drifted from the
     coupling model; fix the skill, do not edit around it.
2. **Declared dependencies resolve; no owed signatures.** Run
   `claude plugin list --json` on a machine with the plugins installed
   (the steward's own counts): every plugin from the catalog is listed at
   its current release with no `errors` field, and the provider bundle
   plugin is present as the domain plugins' dependency. An `errors` entry
   (a missing dependency, a range with no matching tag, a range conflict)
   is a release-blocking bug in whichever manifest or tag caused it. Run
   `nasa-daac-knowledge/tools/signature_check.py <bundle>` for every
   bundle (canonical and plugin-local). An owed signature (a stable
   concept edited since its signing commit) is the steward's to clear by
   re-signing; a release tag waits on it.
3. **Coupling review (as needed).** When skills have changed, run
   `build-kit/workflows/knowledge-coupling-review.js`; "zero files needing
   migration" is the standing invariant.

### Full re-verification (quarterly, or on a product baseline change)

1. **Dataset re-verification.** For each dataset concept, confirm the product is
   still as described: ShortNames still resolve in CMR, the version is current,
   the access path still works. Update `version`, `verified`, and `verified_by`
   with the new date; if the product baseline changed, set `status: stale`
   first, then re-verify (steward-playbook lifecycle §5.6). A dataset whose
   baseline changed may invalidate recipes and gotchas that depend on it: sweep
   them too.
2. **Dependency and tool drift.** Confirm the tools the skills assume still
   behave (the kind of drift already recorded: `/doctor` losing the
   description-budget check, `ecco_access` mishandling statics). New drift goes
   to `known-limitations.md` if user-visible, and to a fix if not.
3. **Environment.** Confirm the pinned analysis environment still builds and the
   golden notebooks still run green headless.

## Triggers (do not wait for the schedule)

- A dataset's product baseline or version changes → re-verify that dataset's
  concepts now (do not wait for the quarter).
- A dependency error in `claude plugin list --json` → fix now
  (release-blocking).
- A tool the skills depend on changes behavior → record and fix now.
- A concept's evidence link stops resolving → fix the link or mark the concept
  `disputed` with an issue.

## What maintenance is not

Maintenance does not rewrite the spec, add features, or stand up domains. Those
are initiatives. Maintenance keeps what exists true: current versions, resolving
evidence, dependencies that resolve to tagged releases, green notebooks, and no
coupling drift.
