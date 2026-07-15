# The Open Science Pillars development model

**Status:** ADOPTED 2026-07-06. This is the operating model for how the project
is developed now that the initial build (Sessions 0b through 19) is complete.
It supersedes the assumption, implicit in the session sequence, that development
is one linear chain toward a fixed specification.

## The shift: from build to operate-and-evolve

The numbered sessions were the right shape for what they were: a finite,
ordered construction of a known specification. That is a **build**, and a build
ends. What replaces it is not another linear sequence of sessions. The project
has moved from *build* to *operate-and-evolve*, and that mode has two rhythms,
not one.

**The specification stays as the anchor.** SPECIFICATION.md remains the law:
what is true, what to build, what each component must do. Specs do not go away.
What changes is the *unit of work*. "The next numbered session" is retired as
the organizing unit. In its place:

1. **Standing processes** run continuously, triggered by events or a schedule,
   shaped like a stream of pull requests. They are not planned in advance and
   not numbered. Examples: the knowledge ingest loop (a dataset peculiarity
   surfaces, so a concept is captured), maintenance sweeps, governance and
   steward review.
2. **Initiatives** contain bounded, goal-and-gate-shaped deliverables with a
   real end. Each uses a stable roadmap ID and repository-owned issue with
   `/osp-session` and `/osp-close`; numbered sessions are historical only.
   Examples: a new domain, a spec revision, the powered ablation, a
   cross-cutting refactor like the knowledge-coupling migration.

The knowledge-coupling migration was, in retrospect, an initiative: it had a
goal, a plan, gates, and an end. It only looked awkward because the sole tool
available was the linear session frame. Name that shape and use it deliberately.

## Which rhythm each kind of development takes

| Development type | Rhythm | Where the process lives |
|---|---|---|
| Knowledge management (ingest loop) | Standing (event-driven) | `knowledge-authoring-guide.md`, `knowledge-template`, the seeder + linter agents, `steward-playbook.md`, `sync_check.py` |
| Governance / steward review | Standing (PR-driven) | `.github/GOVERNANCE.md`, `steward-playbook.md`, CODEOWNERS |
| Maintenance (staleness, re-verification, drift) | Standing (cadence) | `build-kit/docs/maintenance.md` (this pass adds it), the linter's staleness checks, `sync_check.py` |
| Skill development | Initiative (new) + standing (refactor) | `skill-authoring-guide.md`, `plugin-template`, `design-knowledge-coupling.md`, the coupling review/migrate workflows, linter checks 14-16 |
| Evaluation | Initiative (the ablation) + standing (runner/CI) | `eval-authoring-guide.md`, the `evals` runner, per-plugin `evals/`, `phase2-preregistration.md`, rule 9 |
| New domain / new plugin | Initiative (gated + spec-driven) | `plugin-template`, `knowledge-template`, `marketplace.json`, SPEC §1.1/§10, DEVELOPING "Opening the next domain" |

Two of these were weak because the project never left the build frame:
maintenance had no standing home (re-verification only fired when the linter
happened to run at a session close), and new-domain is gated behind an
experiment (the powered ablation) that has not yet run. Both are addressed
below.

## How to run an initiative

The federated roadmap harness coordinates initiatives without taking authority
from repository teams.

1. **Propose it.** Add a stable deliverable ID to
   `build-kit/roadmap/roadmap.yaml`, render `ROADMAP.md`, and seed a proposal
   issue after human review. The repository maintainers decide acceptance.
2. **Gate it.** If the initiative crosses a phase boundary (a new domain, a new
   phase), confirm the gate in `phase2-preregistration.md` first. A gate that
   is not clear stops the initiative; that is the point of pre-registration.
3. **Do the work,** citing the spec by section, capturing knowledge as you go
   (the ingest loop never defers), and honoring the workspace law
   (`CLAUDE.template.md`).
4. **Close it.** Run `/osp-close`: verification evidence goes to the repository
   issue, then the portfolio is reconciled and rendered. A truthful blocked or
   active state beats a false completion.

Spec revisions are roadmap deliverables. Historical parking records remain in
`build-kit/build-record/PARKING.md`; new proposals go to the roadmap.

## How to run a standing process

A standing process has no session number and no plan block. It has a **trigger**
and a **definition of done**, and it produces pull requests.

- **Knowledge ingest** (trigger: a dataset peculiarity surfaces during any
  work): draft the concept immediately with the correct type, frontmatter, and
  evidence links; mark it `status: draft`; queue for steward review; log it.
  Draft becomes verified only through steward review. This is the best-developed
  standing process and it is never deferred into an initiative.
- **Maintenance** (trigger: a schedule, or the linter flagging staleness): see
  `build-kit/docs/maintenance.md` for the cadence. Do not wait for an initiative
  to re-verify a dataset whose baseline changed.
- **Governance / steward review** (trigger: a pull request): follow
  `.github/GOVERNANCE.md` and `steward-playbook.md`. Onboarding a new steward is
  a standalone, checklist-driven process, not a session.

The test for "is this a standing process or an initiative?": if it is triggered
by an event or a schedule and produces a stream of small changes, it is a
standing process, and forcing it into a numbered session is a mistake. If it has
a goal with an end and a gate, it is an initiative.

## What is blocked, and what comes next

Phase 3 (new domains) is authorized only if the pre-registered Phase-2 ablation
clears (`phase2-preregistration.md`). That ablation has not run at power: only
underpowered pilots exist, and the migration to the knowledge-coupling model
revealed two refinements the powered run must adopt (choose non-obvious,
dataset-specific probe cases, and use the rubric judge, not programmatic-only
grading, which is fooled by "consult the concept" pointers; see
`build-kit/build-record/knowledge-coupling-migration.md` and
`marketplace/docs/design-knowledge-coupling.md`).

So the first post-build initiative is not a new domain. It is **run the powered
ablation with the refined design.** Until it clears, new-domain work is gated by
the project's own pre-registration, and that is by design.
