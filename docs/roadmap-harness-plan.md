# Roadmap harness

**Status:** Adopted 2026-07-15; simplified 2026-09-13 (the `one-state-roadmap`
decision in `roadmap/roadmap.yaml`). This document defines how Open Science
Pillars keeps one organization roadmap while repositories remain governed by
their own maintainer teams.

## Purpose

The initial OSP build used one implementation guide and one progress tracker.
That worked while one maintainer controlled every repository, and it did not
name what the organization was working toward across repositories. The roadmap
harness replaces it with roadmap-as-code:

- `build-kit/roadmap/roadmap.yaml` is the single source of truth for the
  organization's work: initiatives, deliverables, dependencies, gates,
  acceptance criteria, evidence, and one status per deliverable.
- `build-kit/ROADMAP.md` is rendered from it and never edited by hand.
- Repository maintainers implement and complete work in their repository; the
  issue that tracks an active deliverable lives there.
- Knowledge stewards retain the stricter review authority defined by the
  specification and steward playbook.

The first version of the harness also carried a proposal-state axis, seeded
proposal issues, repository decision labels, and a reconcile step, all built for
a federation of maintainer teams that does not yet exist. They were removed on
2026-09-13. The trigger for revisiting: adopt GitHub Projects as a rendered view
when a second maintainer team declines to edit the YAML or a partner asks for a
board; render it from the YAML, one way.

## Sources of truth

| Concern | Authority |
|---|---|
| Organization outcomes, dependencies, status, evidence | `build-kit/roadmap/roadmap.yaml` |
| Public roadmap view | generated `build-kit/ROADMAP.md` |
| Repository ownership and review policy | each repo's `.osp/governance.yaml` |
| Repository execution | the deliverable's issue and the repository's pull requests |
| Scientific requirements | `marketplace/docs/SPECIFICATION.md` |
| Historical build sessions | `build-kit/build-record/IMPLEMENTATION-GUIDE.md` and `build-kit/build-record/PROGRESS.md` |
| Roadmap source assessment | `build-kit/build-record/osp-next-steps-codex.md` |

`build-kit/build-record/osp-next-steps-codex.md` is the archived source
assessment the portfolio was drawn from. It is not maintained as a second
roadmap.

## Roles and review

- **Organization steward:** maintains the roadmap, the shared schemas and the
  coordination tooling, and proposes cross-repository outcomes.
- **Repository maintainers:** own implementation and review in their
  repository; a deliverable is done when its acceptance criteria pass there.
- **Knowledge stewards:** review governed knowledge paths under the
  specification's knowledge review rules, including the second-review rules
  for high-severity changes.
- **Contributors:** implement work under repository review.

During the interim solo period, `PaulMRamirez` is the declared repository
maintainer. Repository-local work may merge after its verification checklist
passes. Governance, shared schemas, org templates, and other cross-repository
changes receive a 72-hour public review window. A security or urgent-breakage
exception records why the window was bypassed. Rulesets requiring a second
reviewer are not enabled until a repository has at least two maintainers.

## Deliverable lifecycle

One status per deliverable:

| Status | Meaning |
|---|---|
| `proposed` | Named in the roadmap, not started. It is next when every dependency is done and it has no gate. |
| `active` | Being implemented; an issue in the owning repository tracks it. |
| `blocked` | Waiting on a gate or an unfinished dependency; the reason is recorded in `gate` or `depends_on`. |
| `done` | Acceptance criteria passed and evidence is recorded in the YAML. |
| `declined` | Intentionally not proceeding; the reason is recorded in `gate`. |

`done` requires evidence, `blocked` requires a gate or a dependency, and
`declined` requires a reason; the validator enforces all three. An initiative
completes when every required deliverable is done. Priorities (`P0` to `P2`),
dependencies, gates, acceptance criteria and evidence are edited in the YAML,
rendered, and reviewed in a pull request to build-kit like any other change.

## Issue ownership

An active deliverable has one issue in its owning repository. The issue is
opened when work starts, names the roadmap id in its title or body, and is
closed by the pull request that finishes the deliverable. The YAML records the
issue's number and URL once it exists (`issue: {number, url}`); nothing is
recorded before then. The tool never opens, edits, or closes an issue, never
fabricates a number, and never deletes anything: it reads issues for the audit
and reports when the two records disagree.

## Contributor information

Each deliverable carries a `contributor` block as information for a person
judging whether they can help without private context: `readiness`
(`good-first`, `ready`, `needs-context`, `owner-only`), `champion` (a handle,
or `needed`), and `prerequisites`. No label is derived from it; the audit warns
when a `ready` or `good-first` deliverable that is proposed or active has no
champion.

## Agent and automation contract

The deterministic CLI is authoritative and the `osp-roadmap` skill supplies the
workflow for Claude and Codex. Its commands are `validate`, `render`, `audit`,
`brief`, and `labels`. The only GitHub write is `labels`, which creates the
`roadmap` and `priority:P0` to `priority:P2` labels in each repository; it is
dry-run unless both `--apply` and `--confirm-org open-science-pillars` are
supplied. Nothing else writes to GitHub.

Pull requests to build-kit run schema validation, the tests, deterministic
rendering, and the offline audit. A monthly read-only workflow compares the
roadmap with the live repositories and issues, uploads Markdown and JSON
reports, and fails on actionable drift; it has no write permission. The audit's
codes: `validation`, `render-drift`, `stale-review`, `done-no-evidence`,
`champion-needed`, `no-issue` (an active deliverable with no issue number, a
warning), `issue-mismatch` (a recorded issue that is not in the repository, an
error), `status-drift` (a done or declined deliverable whose issue is still
open: close the issue), and the repository checks (`bootstrap-missing`,
`codeowners-missing`, `new-repository`, `missing-repository`).

Work starts by deliverable id with `/osp-session <id>` and ends with
`/osp-close`. Numeric `/osp-session` invocations remain available only for the
historical build record.

## Domain-expansion gate

New domains remain blocked on the powered knowledge-bundle ablation
(`marketplace/docs/phase2-preregistration.md`). A null or reversed result
triggers the pre-registered pivot. The roadmap may hold new-domain deliverables
as proposed or blocked, but none starts until the gate clears.
