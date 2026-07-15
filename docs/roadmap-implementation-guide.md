# Federated roadmap implementation guide

This guide is the copy-ready Claude Code sequence for implementing and
operating the federated roadmap harness. Run from a flat workspace created by
`build-kit/bootstrap.sh`. Stop before every commit, push, merge, issue write,
label write, ruleset change, team change, or release action for human review.

## R0: Design artifacts

**Prompt**

> Read `build-kit/build-record/osp-next-steps-codex.md`,
> `build-kit/docs/development-model.md`, the
> existing harness skills, organization governance, and
> `build-kit/docs/roadmap-harness-plan.md`. Confirm that the two roadmap design
> documents are linked from build-kit and that the old next-steps file is
> labeled as a source assessment. Do not implement scripts, schemas, governance
> changes, or GitHub writes. Show the cross-document map and any contradiction.

**Human verification**

- Repository autonomy and proposal acceptance are explicit.
- AI-for-Science is declined.
- The old next-steps file is not a second source of truth.
- No GitHub state changed.

## R1: Federated governance baseline

**Prompt**

> Implement the federated governance baseline. Update organization governance,
> add `.osp/governance.yaml` to every current repository, and normalize
> CODEOWNERS without removing stricter knowledge ownership. Use PaulMRamirez as
> interim maintainer. Create no GitHub teams, labels, issues, rulesets, or branch
> protection. Produce one diff summary per repository and stop before commits.

**Machine checks**

```bash
uv run build-kit/scripts/roadmap.py validate
uv run build-kit/scripts/roadmap.py audit --offline
```

**Human verification**

- Each repository names the correct interim owner.
- Repository maintainers own acceptance and completion.
- Cross-repository changes use the 72-hour review window.
- No rule can lock out the sole maintainer.

## R2: Schema, renderer, and offline audit

**Prompt**

> Implement the roadmap and governance schemas, canonical roadmap YAML,
> deterministic ROADMAP.md renderer, validation, brief generation, and offline
> audit. Use the approved next-steps assessment only as seed input. Record
> AI-for-Science as a declined non-issue decision. Add fixture-based tests for
> invalid status, dependencies, federation rules, and rendering. Do not add
> GitHub mutations.

**Machine checks**

```bash
uv run build-kit/scripts/roadmap.py validate
uv run build-kit/scripts/roadmap.py render --check
uv run --with pyyaml==6.0.2 --with jsonschema==4.25.1 python -m unittest discover \
  -s build-kit/tests -p 'test_roadmap.py'
```

**Human verification**

- The generated roadmap matches the approved strategy.
- Acceptance state is distinct from execution status.
- Unaccepted work cannot be ready, active, or done.
- A second render produces no diff.

## R3: GitHub proposal integration

**Prompt**

> Add read-only GitHub discovery and dry-run label, seed, publish, and reconcile
> commands. Implement stable issue markers, repository acceptance labels, crash
> recovery, and the rule that accepted issue bodies are repository-owned. Use
> recorded API fixtures for tests. Do not create labels or issues in the live
> organization.

**Machine checks**

```bash
uv run build-kit/scripts/roadmap.py labels
uv run build-kit/scripts/roadmap.py seed
uv run build-kit/scripts/roadmap.py reconcile
```

**Human verification**

- Review dry-run bodies for build-kit, core, marketplace, and evals.
- Accepted issue bodies cannot be overwritten.
- Repositories with proposals disabled produce artifacts, not issues.
- Repeated seed runs remain idempotent.

## R4: Claude and Codex lifecycle

**Prompt**

> Validate and wire the cross-agent `osp-roadmap` skill to the roadmap CLI.
> Extend bootstrap for Claude and Codex. Keep numeric historical sessions
> compatible, and make future work use roadmap deliverable IDs. Test in a
> temporary workspace. Do not change live GitHub state.

**Machine checks**

```bash
python3 /path/to/skill-creator/scripts/quick_validate.py \
  build-kit/harness/skills/osp-roadmap
uv run build-kit/scripts/roadmap.py brief codex-core-manifest
```

**Human verification**

- Claude and Codex can load `osp-roadmap`.
- Unaccepted or blocked work cannot start.
- Close prepares changes instead of applying them.
- Numeric historical sessions still load.

## R5: Read-only CI

**Prompt**

> Add build-kit CI for validation, tests, rendering checks, and organization
> drift audits. Pull requests use offline checks. Monthly and manually
> dispatched audits may read repositories and issues but must have no write
> permission. Upload Markdown and JSON reports. Show the permissions and event
> matrix before editing.

**Human verification**

- Workflow permissions are read-only.
- No issue, PR, administration, or contents write exists.
- Warnings remain visible without failing.
- Errors and actionable drift fail.

## R6: Organization cleanup

**Prompt**

> Run the roadmap audit across every OSP repository. Classify findings as
> factual cleanup, repository-owned decisions, or cross-repository changes.
> Prepare separate PR-sized patches per owner. Reconcile stale status, counts,
> versions, limitations, AI-for-Science disposition, bootstrap inventory,
> issue-template surfaces, CODEOWNERS comments, and DCO or protection claims.
> Do not create issues, labels, tags, teams, rulesets, releases, or
> announcements.

**Human verification**

- Review the audit before accepting patches.
- Run each repository's own checks.
- Completed capabilities are not described as future work.
- Unverified capabilities are not promoted.
- Cross-repository changes receive the public review window.

## R7: Seed repository proposals

**Prompt**

> Refresh the live audit and render the complete dry-run label and issue plan,
> grouped by repository. Show title, labels, acceptance criteria, dependencies,
> contributor readiness, and repository policy. Exclude declined work and
> gated Phase 3. Do not apply anything.

**Human verification before any write**

- Approve or remove every proposed issue.
- Verify its owning repository and readiness.
- Run label creation only with `--apply --confirm-org open-science-pillars`.
- Run issue seeding only with the same confirmation pair.
- Rerun seed and require zero duplicate proposals.
- Apply one repository decision label to every seeded proposal.

## R8: End-to-end canary

**Prompt**

> Execute one small accepted deliverable through the federated lifecycle. Use
> `codex-core-manifest` only if the core maintainers have accepted its proposal.
> Start by roadmap ID, honor the repository
> issue's acceptance criteria, run its checks, and prepare evidence and
> reconciliation. Stop before every roadmap, issue, commit, push, or close
> mutation for confirmation.

**Human verification**

- The accepted repository issue controls implementation detail.
- Evidence supports every checked criterion.
- The issue closes only after repository acceptance passes.
- No unrelated repository status changes.
