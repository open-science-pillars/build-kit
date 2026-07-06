# Developing Open Science Pillars

How to continue building this project with an AI assistant, using the same
harness that produced Phases 1 and 2. Read this once before your first session.

## The idea

Work happens in numbered **sessions**. Each session has a block in
`marketplace/docs/IMPLEMENTATION-GUIDE.md` (goal, time, ordered steps,
checkpoint) and an **autonomy mode** (how long a leash the assistant gets). A
session starts with `/osp-session N`, which reads the block and the current
state, restates the plan, and waits for your go. It ends with `/osp-close`,
which runs verification gates and updates the honest status tracker. The law
the assistant works under is the workspace `CLAUDE.md` (start from
`CLAUDE.template.md` here).

Nothing is "done" without its evidence: a workflow skill needs a green golden
notebook, a high-severity gotcha needs an eval case, a completed PROGRESS item
needs its checkpoint proof. A truthful yellow beats a false green.

## Setup

```bash
git clone https://github.com/open-science-pillars/build-kit
./build-kit/bootstrap.sh ~/osp-workspace
cd ~/osp-workspace && claude
> /osp-session <N>
```

`bootstrap.sh` clones the org repos flat, links the `osp-session` and
`osp-close` skills as project skills (so they load when you run Claude Code
from the workspace), and seeds `CLAUDE.md` from the template. It is
idempotent; re-run it to update.

**Python environment (once).** The green-golden checkpoints run real code, so
before your first session set up the scientific environment described in the
"Environment setup" block of `marketplace/docs/IMPLEMENTATION-GUIDE.md`
(conda/mamba with xarray, marimo, earthaccess and the domain libraries, Quarto
for the tutorials, and an Earthdata Login in `~/.netrc` for NASA data). Without
it, sessions boot but stall at the first golden notebook.

## Authoring a new session block

When you take on new work (a new domain, a new capability), write its block
into `IMPLEMENTATION-GUIDE.md` in the established format before you run it. The
template:

```markdown
## Session N: <Title> (<estimated hours>, <autonomy mode>)

<One-paragraph goal: what exists at the end that did not exist at the start.>

1. <Ordered step, each independently checkpointable.>
2. <...>

**Checkpoint:** <the observable evidence that this session is truly done:
green goldens, verified concepts, a recorded test, a pushed artifact.>
```

Put the autonomy mode in the header, as the later blocks do (for example
Session 17: "Applied Pack + Canonical Home (2.5 hr; tight supervision)").
Session 15 (hydrology scaffold) is a good worked example for the body shape:
it names a concrete scaffold, a live data audit, two concepts, and a green
golden as its checkpoint. Keep steps small enough that `/osp-close` can walk
them one by one.

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

## The phase gates

Some work is gated on evidence, not just planned. The live gate:
`marketplace/docs/phase2-preregistration.md` pre-registers the success/stop
conditions for the knowledge-layer effectiveness experiment (the bundle
ablation). **Phase-3 domain expansion is authorized only if that experiment
clears its go conditions**; if it comes back null, the pre-registration says
to diagnose why before shipping a new domain. Re-read the pre-registration at
the start of any session it governs, and log any deviation as a dated
amendment there. This is the same epistemics the science demands: decide the
exit test before you see the result.

## PROGRESS, PARKING, and the ingest loop

- **PROGRESS.md** is the honest status tracker and per-session log.
  `/osp-close` updates it; never mark an item green without checkpoint
  evidence.
- **PARKING.md** is where discovered gaps and new ideas go during a frozen
  build arc, one line each, triaged into the next spec revision at the
  scheduled window. The build writes the next spec; forethought does not.
- **The ingest loop** is never deferred: when a dataset peculiarity surfaces
  during any work, draft the knowledge concept immediately (correct type,
  frontmatter, evidence links), queue it for steward approval, and log it. See
  `marketplace/docs/knowledge-authoring-guide.md`.

## How skills, knowledge, and agents divide the work

The layers have clean, non-overlapping jobs, so the knowledge bundle can grow
and improve behavior without rewriting code (the design and its measured
proof are in `marketplace/docs/design-knowledge-coupling.md`):

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

## Opening "Session 20" (the next domain)

1. Confirm the phase gate against `phase2-preregistration.md`: the go
   conditions are met AND the ablation is not null or reversed (stop
   condition 1 blocks new domains on a null ablation). If the gate isn't
   clear, diagnosing the ablation is the work, not a new domain.
2. Write the spec detail for the new domain into `SPECIFICATION.md` (structure,
   skills, knowledge requirements, acceptance criteria), following the
   hydrology section (§10) as the model, at the scheduled spec-revision window.
3. Author the Session 20+ blocks in `IMPLEMENTATION-GUIDE.md`, each with an
   autonomy mode in its header.
4. Create the new repo and register it in `build-kit/bootstrap.sh`'s `REPOS`
   array (so later re-bootstraps clone it), then scaffold the plugin from
   `plugin-template`, its bundle from `knowledge-template`, and run
   `/osp-session 20`.

## Verifying the docs stay healthy

`build-kit/workflows/persona-doc-review.js` is a reusable Claude Code workflow
that reviews the documentation through five personas (newcomer, grad student,
contributor, steward, future developer) and adversarially verifies each
blocker. Run it after a docs change to catch journey-level regressions.
