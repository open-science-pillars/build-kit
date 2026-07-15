# build-kit

The development harness for Open Science Pillars: how the project is built, and
how to continue building it with an AI assistant.

If you want to *use* the plugins, you're in the wrong place: start at the
[tutorials](https://github.com/open-science-pillars/tutorials). This repo is
for **maintainers and future core developers** who want to extend the project
(a new science domain, a new capability) the way it was originally built.

## What's here

- **[ROADMAP.md](ROADMAP.md)**: generated organization roadmap; edit
  `roadmap/roadmap.yaml`, never this file directly.
- **[DEVELOPING.md](DEVELOPING.md)**: the roadmap-ID work protocol, autonomy
  dial, phase gates, and contributor workflow.
- **[docs/roadmap-harness-plan.md](docs/roadmap-harness-plan.md)** and
  **[docs/roadmap-implementation-guide.md](docs/roadmap-implementation-guide.md)**:
  federated design and copy-ready Claude Code implementation sessions.
- **[bootstrap.sh](bootstrap.sh)**: clones the org repos flat and wires the
  session harness so `/osp-session` and `/osp-close` work.
- **[CLAUDE.template.md](CLAUDE.template.md)**: the canonical workspace "law" (the workspace `CLAUDE.md` imports it, never copies it)
  (the non-negotiable global rules) to seed a new build workspace.
- **[harness/skills/](harness/skills/)**: the runnable `osp-roadmap`,
  `osp-session`, and `osp-close` skills for Claude Code and Codex.
- **[workflows/persona-doc-review.js](workflows/persona-doc-review.js)**: a
  reusable Claude Code workflow that reviews the docs through five personas.

## How this project was built

Open Science Pillars was built in numbered sessions by an AI assistant working
under a human steward, each session gated and logged. The historical record is
public in `build-kit/PROGRESS.md` and `build-kit/IMPLEMENTATION-GUIDE.md`. What made it work
was not speed but the verification loops, and they repeatedly caught real
errors in the project's own output:

- A behavior test found a transport recipe comparing a full-latitude-circle
  number against Atlantic-only observations, a silent scope mismatch.
- Golden notebooks falsified two assumed closure tolerances by measuring the
  actual residual.
- The linter caught skills that documented a new gotcha but still routed
  around it.
- A steward-persona doc review found evidence links that broke when concepts
  moved to their canonical home.

The lesson the harness encodes: encode expertise as knowledge with evidence,
verify every computation with a green notebook, test the assistant's judgment
with evals, and keep an honest status. Then a new person plus an AI assistant
can pick it up and keep going.

## Continue the build

```bash
git clone https://github.com/open-science-pillars/build-kit
./build-kit/bootstrap.sh ~/osp-workspace
cd ~/osp-workspace && claude
> /osp-roadmap audit
> /osp-session <roadmap-id>
```

Codex users invoke `$osp-roadmap` and `$osp-session` from the same workspace.
Read [DEVELOPING.md](DEVELOPING.md) first, and
`marketplace/docs/phase2-preregistration.md` before any Phase-3 domain work
(new domains are gated on the knowledge-layer effectiveness experiment).

License: Apache-2.0.
