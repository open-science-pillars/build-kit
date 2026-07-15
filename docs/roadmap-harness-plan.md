# Federated roadmap harness

**Status:** Adopted 2026-07-15. This document defines how Open Science
Pillars coordinates an organization roadmap while repositories remain governed
by their own maintainer teams.

## Purpose

The initial OSP build used one implementation guide and one progress tracker.
That worked while one maintainer controlled every repository. It does not scale
to an organization where core, domains, knowledge bundles, tutorials, and
infrastructure may have different teams.

The federated model separates authority:

- `build-kit` owns the organization portfolio, cross-repository dependencies,
  audit tooling, and generated public roadmap.
- Repository maintainers accept, defer, reject, prioritize, implement, and
  complete work in their repository.
- Knowledge stewards retain the stricter review authority defined by the
  specification and steward playbook.
- Organization proposals never become executable repository work until the
  repository accepts them.

## Sources of truth

| Concern | Authority |
|---|---|
| Organization outcomes and dependencies | `build-kit/roadmap/roadmap.yaml` |
| Public portfolio view | generated `build-kit/ROADMAP.md` |
| Repository ownership and proposal policy | each repo's `.osp/governance.yaml` |
| Repository execution | the accepted issue and repository PRs |
| Scientific requirements | `marketplace/docs/SPECIFICATION.md` |
| Historical Sessions 0b-19 | `build-kit/IMPLEMENTATION-GUIDE.md` |
| Roadmap source assessment | `build-kit/build-record/osp-next-steps-codex.md` |

`build-kit/build-record/osp-next-steps-codex.md` is the archived source
assessment used to seed the portfolio. It is not maintained as a second
roadmap.

## Roles and review

- **Organization steward:** proposes cross-repository outcomes and maintains
  shared schemas and coordination tooling. The steward cannot accept or close
  repository work for a team.
- **Repository maintainers:** control proposal acceptance and implementation
  in their repository.
- **Knowledge stewards:** review governed knowledge paths under SPEC section
  5.4, including the second-review rules for high-severity changes.
- **Contributors:** implement accepted work under repository review.

During the interim solo period, `PaulMRamirez` is the declared repository
maintainer. Repository-local work may merge after its verification checklist
passes. Governance, shared schemas, org templates, and other cross-repository
changes receive a 72-hour public review window. A security or urgent-breakage
exception records why the window was bypassed. Rulesets requiring a second
reviewer are not enabled until a repository has at least two maintainers.

## Proposal lifecycle

Roadmap coordination and repository execution use separate state:

| Proposal state | Meaning |
|---|---|
| `draft` | Not sent to the repository. |
| `seeded` | Proposal issue exists, awaiting repository decision. |
| `accepted` | Repository maintainers accepted the work. |
| `deferred` | Repository accepted the need but postponed execution. |
| `rejected` | Repository declined the proposal. |

| Execution status | Meaning |
|---|---|
| `proposed` | Not executable yet. |
| `ready` | Accepted, dependencies clear, available to start. |
| `active` | Being implemented. |
| `blocked` | Accepted but gated or dependent on unfinished work. |
| `done` | Acceptance criteria passed and evidence is recorded. |
| `declined` | Intentionally not proceeding. |

Only `accepted` proposals may become `ready`, `active`, or `done`. A deferred
proposal is blocked with a reason. A rejected proposal is declined for that
repository deliverable. Cross-repository initiatives complete only when all
required repository deliverables complete.

Repository teams decide proposals by applying exactly one of
`roadmap:accepted`, `roadmap:deferred`, or `roadmap:rejected`. GitHub repository
permissions control who may apply those labels.

## Issue ownership

Before acceptance, the harness may update a delimited managed proposal block,
but only through an explicitly approved `publish --apply` operation. After
acceptance, the issue body belongs to the repository team and the harness reads
it without rewriting it. Comments and text outside the managed block are never
modified.

One issue represents one deliverable. Stable HTML roadmap IDs make creation
idempotent and recoverable if an API call succeeds before local state is saved.
The harness never deletes issues or changes teams, permissions, rulesets, PRs,
releases, or branches.

## Contributor recruitment

Each deliverable declares readiness:

- `good-first`: add `help wanted` and `good first issue`.
- `ready`: add `help wanted`.
- `needs-context`: publish missing context, but add no recruitment label.
- `owner-only`: keep with maintainers.

The proposal names prerequisites, champion status, dependencies, acceptance
criteria, and required evidence so a new contributor can judge whether they
can help without private context.

## Agent and automation contract

The deterministic CLI is authoritative. The `osp-roadmap` skill supplies the
workflow for Claude and Codex. All GitHub operations default to dry-run and
require both `--apply` and `--confirm-org open-science-pillars` to write.

Pull requests run schema validation, tests, deterministic rendering, and the
offline audit. A monthly read-only workflow compares the portfolio with live
repositories and issues, uploads Markdown and JSON reports, and fails on
actionable drift. It has no write permission.

Future work starts by deliverable ID. Numeric `/osp-session` invocations remain
available only for the historical build record.

## Phase gate

Phase 3 remains blocked on the powered knowledge-bundle ablation. A null or
reversed result triggers the pre-registered pivot. The roadmap may retain
Phase-3 context, but it does not seed Phase-3 issues until the gate clears.
