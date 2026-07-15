# Open Science Pillars: Recommended Next Steps

> **Status:** Source assessment, not an executable roadmap. Its accepted
> recommendations are being migrated into the federated roadmap maintained in
> `build-kit/ROADMAP.md`. Execute work from that roadmap and from repository
> proposal issues after the roadmap harness is installed.
>
> **Decision update:** The AI-for-Science submission was declined on
> 2026-07-15 and is not pending.

**Prepared:** July 15, 2026  
**Basis:** Audit of all 11 `open-science-pillars` repositories, the Claude roadmap in `osp-next-steps-v2.md`, the current BioNeMo Agent Toolkit, current Codex plugin guidance, and local verification runs.

## Executive recommendation

Do not execute the Claude roadmap as written. Its strategic instincts are useful, but its repository inventory is stale, several proposed tasks are already complete, and parts of its distribution design copy a monorepo pattern that does not fit OSP's multi-repository architecture.

The next sequence should be:

1. Reconcile the project documentation with the system that is actually built.
2. Add Codex distribution using native Codex manifests and marketplace metadata.
3. Complete the refined, powered knowledge-bundle ablation.
4. Add executable skill-activation evaluations.
5. Finish cross-surface, non-author, steward, and release validation.
6. Start Phase 3 only if the project's pre-registered gate clears.

The AI-for-Science submission is intentionally not part of this roadmap. The project owner decided not to submit, so it should be marked declined/closed in the project record rather than carried as an outstanding yellow item.

## Current state

OSP is past its initial build phase and has entered the operate-and-evolve phase described in `build-kit/docs/development-model.md`.

The organization currently contains:

- 11 repositories.
- 38 skills: 11 core, 17 ocean-science, and 10 hydrology.
- Five agents across core, ocean-science, and hydrology.
- A canonical PO.DAAC bundle with five datasets, eight gotchas, and four recipes.
- 18 scientific-judgment eval cases: four core, eight ocean-science, and six hydrology.
- An eval runner with programmatic grading, rubric judging, Wilson intervals, ablation support, and a static scoreboard.
- A completed knowledge-coupling migration across 37 skill and agent files.
- Working Claude marketplace packaging for core, ocean-science, and hydrology.

Local verification during this audit found:

- The eval runner self-test passed all 12 grader good/bad classifications.
- The core analysis-pipeline golden passed.
- All four hydrology goldens passed.
- Ocean-science and hydrology snapshots are byte-identical to the canonical PO.DAAC concepts.
- All cloned repositories have clean tracked working trees.
- There are no open GitHub issues across the organization.
- There are no Git release tags in any repository.

## Evaluation of the Claude roadmap

### Recommendations to keep

The Claude roadmap is correct that:

- OSP's steward-owned, evidence-linked knowledge layer is its strongest differentiator.
- Codex distribution is worth adding.
- Skill activation should be evaluated independently from response correctness.
- Quantitative evidence for knowledge effectiveness matters more than rapidly expanding feature inventory.
- Execution-substrate and dependency metadata may become useful when OSP builds real hosted-model capabilities.

### Corrections required

| Claude proposal | Repository reality | Decision |
|---|---|---|
| Treat SPEC v0.5.1 and Phase 1 as the current state | The specification is v0.6.2; hydrology, the eval runner, and the knowledge migration are built. | Replace the inventory and roadmap baseline. |
| Plan hydrology as a future Phase 2 handoff | Hydrology has 10 skills, six evals, four passing goldens, and a passing Code-side end-to-end run. | Treat hydrology as release-candidate software. |
| Run the original gotcha ablation | The pilot already found the original design confounded because skills duplicated knowledge. A subsequent knowledge-coupling migration is complete. | Run the refined powered experiment, not the obsolete design. |
| Copy the Claude marketplace JSON into `.agents/plugins/marketplace.json` | The Codex path is right, but Codex uses a different marketplace schema and requires `.codex-plugin/plugin.json`. | Build native Codex manifests and marketplace entries. |
| Symlink plugin repositories into a shared marketplace root | Cross-repository symlinks do not survive independent clones and conflict with OSP's self-containment rule. | Point Codex marketplace entries at the separate Git repositories. |
| Add `skills.sh.json` to become discoverable | The current skills CLI discovered all 11 core skills directly without that file. | Document direct repository installation; use grouping metadata only if it adds demonstrated value. |
| Add trigger JSON files to every skill | JSON files without a runner do not provide evidence. | Build and pilot an activation-eval runner first. |
| Build a hosted-model flood skill next | OSP explicitly gates Phase 3 and new domains on the powered ablation. | Defer until the gate resolves. |
| Add `SECURITY.md` | The organization already has a security policy covering the skill and knowledge instruction supply chain. | Improve visibility or inheritance only if needed. |
| Dual-license knowledge immediately | Relicensing affects contributors and downstream reuse; a `CITATION.cff` note is not a license change. | Handle as a separate governance/legal decision. |
| Add substrate, dependency, and security frontmatter now | These fields are not yet consumed by OSP routing or validation, and no hosted-model skill requires them. | Derive metadata from a real implementation later. |

## Recommended roadmap

### Initiative 1: Truth reconciliation

**Duration:** 1–2 days  
**Goal:** Make the project record describe the software that currently exists.

Actions:

1. Revise the specification to incorporate the adopted knowledge-coupling model. The migration is complete, but the design document still presents some replacement language as a candidate for a future specification.
2. Update `build-kit/PROGRESS.md`:
   - Mark the AI-for-Science submission as declined by owner decision.
   - Remove or resolve duplicated Phase 2/Phase 2+ entries.
   - Record the completed knowledge-coupling migration.
   - Preserve the powered ablation as outstanding.
3. Update `marketplace/docs/known-limitations.md`:
   - Remove stale claims that fill-value coverage, release-mixing/crossover promotions, and salt/volume recipes are deferred.
   - Keep Cowork, Claude Science, non-author, and powered-ablation limitations explicit.
4. Correct repository, skill, concept, and eval counts across public documentation.
5. Decide whether Codex is:
   - a fourth supported behavioral surface, or
   - a separate distribution ecosystem whose behavior is tested independently.
6. Create GitHub issues or a milestone for the outstanding initiatives. A public project with documented yellow items but zero open issues is difficult for contributors to navigate.

**Exit criteria:**

- Public documentation agrees with repository contents.
- No completed item remains described as future work.
- The Codex support policy is explicit.
- Declined work is recorded as declined, not pending.

### Initiative 2: Native Codex distribution

**Duration:** 2–4 days  
**Goal:** Install and invoke OSP through Codex without duplicating source trees.

Actions:

1. Add `.codex-plugin/plugin.json` to:
   - `core`
   - `ocean-science`
   - `hydrology`
2. Add the same dual-manifest structure to `plugin-template` so new domain plugins support Claude and Codex from the beginning.
3. Add `.agents/plugins/marketplace.json` to `marketplace` using the Codex schema:
   - top-level marketplace name and display name;
   - one entry per plugin;
   - remote Git source pointing at each plugin repository root;
   - installation and authentication policy;
   - science category and user-facing metadata.
4. Do not use symlinks and do not vendor copies of the plugin repositories into `marketplace`.
5. Document direct skills CLI installation, for example:

   ```bash
   npx skills add open-science-pillars/core
   npx skills add open-science-pillars/ocean-science
   npx skills add open-science-pillars/hydrology
   ```

6. Test from a clean environment:
   - add the marketplace;
   - list available plugins;
   - install each plugin;
   - confirm the expected skills load;
   - run at least one positive and one negative activation prompt per plugin;
   - confirm updates work across a version bump.

`skills.sh.json` is optional grouping metadata, not a prerequisite for installation. Revisit it only if users need an aggregate catalog that direct per-repository installation does not provide.

**Exit criteria:**

- Core, ocean-science, and hydrology install through Codex from the marketplace repository.
- All expected skills are present after installation.
- Clean-install evidence and tested commands are recorded.
- The plugin template produces valid Claude and Codex packages.

### Initiative 3: Refined powered ablation

**Duration:** Approximately one week plus compute time  
**Goal:** Resolve the project's pre-registered knowledge-effectiveness gate.

The first ablation design removed `knowledge/` while leaving duplicated gotcha rules in skills. It therefore measured no difference. The repository-wide coupling migration corrected that architecture, and the MHT proof of concept produced a pilot-scale `+0.60` ON–OFF difference while the hard-refusal control remained flat.

Before the powered run:

1. Add a dated pre-registration amendment defining the post-migration design.
2. Select genuinely non-obvious, dataset-specific probes, such as:
   - ECCO MHT basin scope;
   - unapplied SWOT crossover correction;
   - ECCO release mixing;
   - SWOT reach/node scope;
   - NWIS provisional versus approved status;
   - regulated-gauge suitability;
   - other product-specific version, correction, or scope traps.
3. Retain hard-refusal cases as controls rather than expecting a knowledge effect from them.
4. Fix or recalibrate `ecco-release-mixing`, which failed in both pilot arms.
5. Use both discriminating programmatic graders and the rubric judge. Simple keyword graders can be fooled by a transcript that mentions a concept without applying it.
6. Record:
   - exact model and model version;
   - plugin and knowledge commit SHAs;
   - trial dates;
   - prompts and rubrics;
   - infrastructure errors separately from scientific failures;
   - raw transcripts;
   - per-case and pooled intervals.
7. Run the powered sample in CI or another credentialed compute environment.
8. Publish the result regardless of direction.

Decision rule:

- If the knowledge-on arm shows a resolved improvement, proceed toward Phase 3.
- If the result is null or reversed, pause new-domain expansion and diagnose concept discovery, routing, prompt sensitivity, and case design as required by the existing pre-registration.

**Exit criteria:**

- The powered result and confidence intervals are public.
- The experiment is reproducible from recorded commits and commands.
- The Phase 3 gate has an explicit pass/pivot decision.

### Initiative 4: Skill-activation evaluations

**Duration:** 3–5 days for the pilot  
**Goal:** Determine whether the right skill activates for the right request without confusing activation with answer quality.

Do not begin by adding 38 unexecuted JSON files. First build a small runner and prove that it produces useful failures.

Pilot scope:

- `quality-control`
- `discover-data`
- `load-ecco`
- `transport-analysis`
- `load-nwis`
- at least one deliberately adjacent negative pair

The schema should support:

- positive prompts;
- negative prompts;
- ambiguous prompts where either clarification or one of two skills is acceptable;
- expected skill identity;
- forbidden competing skills;
- surface and model metadata.

The runner should inspect actual skill loading, invocation, or explicit use—not merely keywords in the final answer. Run the pilot on Claude Code and Codex first, then determine whether Cowork and Claude Science expose enough evidence for equivalent measurement.

**Exit criteria:**

- Activation tests run automatically.
- At least one real routing defect has been found or the test is shown not to add value.
- The trigger schema and runner are documented before coverage expands.

### Initiative 5: Release and external validation

**Goal:** Turn working repositories into a credible, reproducible public release.

Actions:

1. Complete the Cowork and Claude Science test packets.
2. Add Codex results to the surface/distribution record according to the policy chosen in Initiative 1.
3. Have at least one non-author scientist complete Tutorial 2 unaided and record their friction notes verbatim.
4. Complete the PO.DAAC/provider steward handoff or revise public language from federated stewardship to accurate interim-steward wording.
5. Install DCO and repository ruleset controls if the governance decision still requires them.
6. Re-run release gates:
   - core golden;
   - hydrology goldens;
   - ocean goldens in the credentialed/cache-enabled environment;
   - eval runner self-test;
   - snapshot byte-identity checks;
   - marketplace clean installs.
7. Cut synchronized version tags for the marketplace and plugin repositories.
8. Validate `CITATION.cff` metadata and archive releases to Zenodo if that remains the stated release policy.
9. Record the demo.
10. Update and publish the announcement only after its claims match the powered experiment, actual surface coverage, and stewardship status.

**Exit criteria:**

- Tagged releases exist.
- Installation has been verified on every claimed ecosystem/surface.
- Citation and archive claims are true.
- At least one non-author validation is recorded.
- Stewardship language matches actual ownership.

### Initiative 6: Phase 3, conditional on the gate

If the powered ablation passes, the strongest Phase 3 initiative is a coherent remote-sensing-to-applied-science slice rather than an isolated hosted-model demonstration.

Recommended sequence:

1. Build a reusable SAR/optical measurement capability.
2. Implement a transparent, non-model flood-extent baseline.
3. Add an optional model-backed flood implementation.
4. Define validation concepts, uncertainty treatment, failure modes, and golden data.
5. Add scientific-judgment and activation evals.
6. Compare the model-backed method against the baseline on a small, documented benchmark.
7. Only then standardize `substrate`, dependency, credential, network, and disk-write metadata based on routing and validation needs observed in the implementation.

If the powered ablation does not pass, do not open a new domain. Use the next initiative to repair knowledge discovery and routing, then re-evaluate the gate.

## Deferred decisions

The following ideas may be valuable, but they should not be on the critical path:

- Dual-licensing knowledge under CC-BY-4.0.
- A top-level aggregate `skills.sh.json` catalog.
- Generic substrate frontmatter before a real routing consumer exists.
- Per-skill security metadata before its schema and enforcement are designed.
- Expansion to additional DAACs before the current steward model is validated.
- Planetary-science work before Phase 3 is authorized and completed.

## Recommended order of operations

```text
Truth reconciliation
        ↓
Codex packaging ──────────────┐
        ↓                     │
Activation-eval pilot         │
        ↓                     │
Refined powered ablation ◀────┘
        ↓
Pass or pivot decision
        ↓
Cross-surface + external validation
        ↓
Tagged release and announcement
        ↓
Conditional Phase 3 initiative
```

The key discipline is to finish the evidence and release story around the substantial system OSP already has before adding a new scientific domain or hosted-model capability.
