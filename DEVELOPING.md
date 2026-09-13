# Developing Open Science Pillars

How to continue building this project with an AI assistant, using the same
harness that produced the initial build. Read this once before your first session,
alongside `build-kit/docs/development-model.md`, which is the operating model:
now that the initial build is complete, work is spec-anchored and splits into
bounded **roadmap deliverables** and **standing processes** (the ingest loop,
`docs/maintenance.md`, and governance). This guide is how to run roadmap work.

## The idea

Future work is a stable deliverable ID in `roadmap/roadmap.yaml`, the single
source of truth: one status per deliverable (proposed, active, blocked, done,
declined), its dependencies, gate, acceptance criteria and evidence. An active
deliverable has an issue in its owning repository, opened when the work starts
and closed by the pull request that finishes it; the YAML records the issue
number once it exists. Work starts with `/osp-session <roadmap-id>` and ends
with `/osp-close`. Historical numeric
sessions remain readable but no new numbered sessions are created. The law the assistant
works under is the workspace `CLAUDE.md`, which is a thin file that imports
the single tracked law here with `@build-kit/CLAUDE.template.md` (so it never
drifts); edit the law in `CLAUDE.template.md`.
Not everything is an initiative: event- or schedule-driven work (capturing a
concept, re-verifying a dataset, reviewing a PR) is a standing process and does
not take a session number. See `docs/development-model.md` for which is which.

Nothing is "done" without its evidence: a workflow skill needs a green golden
notebook, a high-severity gotcha needs an eval case, a done roadmap deliverable
needs its evidence lines. A truthful yellow beats a false green.

## Setup

```bash
git clone https://github.com/open-science-pillars/build-kit
./build-kit/bootstrap.sh ~/osp-workspace
cd ~/osp-workspace && claude
> /osp-roadmap audit
> /osp-session <roadmap-id>
```

`bootstrap.sh` clones the org repos flat (including `evals`), links the
`osp-roadmap`, `osp-session`, and `osp-close` skills for both Claude Code and
Codex, and writes a workspace `CLAUDE.md` that
imports the law with `@build-kit/CLAUDE.template.md`. It is idempotent; re-run
it to update.

**Python environment (once).** The golden notebooks run real code, so before
your first session create the scientific environment from `environment.yml`
at the root of this repository (`conda env create -f build-kit/environment.yml`
or the mamba equivalent: xarray, marimo, earthaccess and the domain libraries),
install Quarto for the tutorials, and put an Earthdata Login in `~/.netrc` for
NASA data. Without it, sessions boot but stall at the first golden notebook.

## Proposing a roadmap deliverable

Add proposed work to `roadmap/roadmap.yaml` with a stable lowercase ID and
`status: proposed`. Include the owning repository, priority, dependencies,
gate, acceptance criteria, and contributor readiness. Run:

```bash
uv run build-kit/scripts/roadmap.py validate
uv run build-kit/scripts/roadmap.py render
uv run build-kit/scripts/roadmap.py audit --offline
```

Open the change as a pull request to build-kit; the rendered `ROADMAP.md`
travels with it. No issue exists yet: one is opened in the owning repository
when the work starts, and its number goes into the YAML then. `done` requires
evidence, `blocked` a gate or dependency, `declined` a reason.

## The autonomy dial

Set a mode per session in the block; the rationale is what matters, not the
label. The pattern the build settled on:

| Mode | When | Behavior |
|---|---|---|
| Batch-friendly | Scaffolding; the spec fully determines the output; gates catch drift. | Long leash, review at the end. |
| Supervised checkpoints | New domain; concept or skill wording quality is being established. | Autonomous within a step, pause between steps. |
| Tight supervision | Highest silent-error risk, or one-way doors (canonical migrations, headline experiments, anything external trainings anchor on). | Review each artifact before it lands. |

Default a new-domain session to **Supervised checkpoints**; escalate to
**Tight** for one-way doors and for the highest-stakes correctness work.

## The domain-expansion gate

Some work is gated on evidence, not just planned. The live gate:
`marketplace/docs/phase2-preregistration.md` pre-registers the success/stop
conditions for the knowledge-layer effectiveness experiment (the bundle
ablation). **New-domain expansion is authorized only if that experiment
clears its go conditions**; if it comes back null, the pre-registration says
to diagnose why before shipping a new domain. Re-read the pre-registration at
the start of any session it governs, and log any deviation as a dated
amendment there. This is the same epistemics the science demands: decide the
exit test before you see the result.

## Status, proposals, and the ingest loop

- **The roadmap is the status tracker.** `roadmap/roadmap.yaml` carries every
  deliverable's status and evidence, `ROADMAP.md` is rendered from it (the
  summary on top says what is now, blocked, next and later), and the owning
  repository's issue is the execution record of an active deliverable.
  `/osp-close` records the evidence and the status; never mark a deliverable
  done without its evidence.
- **New ideas and discovered gaps are roadmap proposals.** Add a `proposed`
  deliverable to `roadmap/roadmap.yaml` (see "Proposing a roadmap
  deliverable" above) in a pull request to build-kit. The historical parking
  lot and progress tracker live in `build-record/` and are not updated.
  `docs/development-model.md` is the operating model.
- **The ingest loop** is never deferred: when a dataset peculiarity surfaces
  during any work, draft the knowledge concept immediately (correct type,
  frontmatter, evidence links), queue it for steward approval, and log it. See
  `marketplace/docs/contributing-knowledge.md`.

## How skills, knowledge, and agents divide the work

The layers have clean, non-overlapping jobs, so the knowledge bundle can grow
and improve behavior without rewriting code (the rule is
`marketplace/docs/knowledge-vs-skills.md`):

- **Skills are deterministic procedures plus hard refusals.** A skill carries
  the *how* (ordered steps, invariant method) and only the safety guards that
  must fire every time: refuse a regridded budget, gate a large download,
  never write credentials to a repo. A skill carries no dataset facts, no
  inlined numbers, no gotcha rules, no named-concept lists.
- **Knowledge concepts are the single source of everything a scientist would
  look up.** The trap, the uncertainty structure, the recipe numbers, the
  version caveat: each lives in exactly one concept, never copied into a skill.
- **Agents (and skills through a standing consult step) discover and consult
  the bundle dynamically.** Given a task and a dataset, glob and read the
  relevant concepts, reason with them, and cite them by path. A concept added
  since the last run is found by discovery, not by a remembered list.

**The rule for what stays hardcoded** (so it is a judgment, not a list): a
behavior stays in a skill only if it passes all three tests, else it is
knowledge. (1) Invariance: it never changes with a product version or new
learning. (2) Response shape: the right response is refuse or gate, not inform
or adjust. (3) Universality: violating it is wrong or unsafe regardless of the
dataset. When uncertain, put it in knowledge; over-hardcoding freezes behavior
and makes the bundle inert.

Run `build-kit/workflows/knowledge-coupling-review.js` to classify every skill
and agent against this rule and get a per-file migration plan; the
knowledge-linter flags inlined concept content and inert concepts so drift is
caught mechanically.

## Opening the next domain

1. Confirm the domain-expansion gate against `phase2-preregistration.md`: the
   go conditions are met AND the ablation is not null or reversed (stop
   condition 1 blocks new domains on a null ablation). If the gate isn't
   clear, diagnosing the ablation is the work, not a new domain.
2. Write the spec detail for the new domain into `SPECIFICATION.md` (structure,
   skills, knowledge requirements, acceptance criteria), following the
   hydrology section as the model, at the scheduled spec-revision window.
3. Add proposed deliverables with acceptance criteria and contributor
   readiness; leave them proposed or blocked until the gate clears.
4. After the organization and repository owners approve creation, register the
   repository in the roadmap and `bootstrap.sh`, scaffold from the templates,
   and run `/osp-session <roadmap-id>` once the gate and dependencies are clear.

## Verifying the docs stay healthy

`build-kit/workflows/persona-doc-review.js` is a reusable Claude Code workflow
that reviews the documentation through five personas (newcomer, grad student,
contributor, steward, future developer) and adversarially verifies each
blocker. Run it after a docs change to catch journey-level regressions.
