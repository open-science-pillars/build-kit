# build-kit

The development harness for Open Science Pillars: how the project is built, and
how to continue building it with an AI assistant.

If you want to *use* the plugins, you're in the wrong place: start at the
[tutorials](https://github.com/open-science-pillars/tutorials).

## What's here

**Who this is for.** Maintainers running the organization roadmap and the
releases, and people extending the tooling (a new script, a new check, a new
skill for the harness). Extending the science (a new domain capability, a new
knowledge concept) starts in the marketplace's
[CONTRIBUTING.md](https://github.com/open-science-pillars/marketplace/blob/main/CONTRIBUTING.md)
and comes back here only for the roadmap and release steps.

**Tools.**

- [bootstrap.sh](bootstrap.sh): clones the organization's repositories flat
  into a workspace and links the harness skills for Claude Code and Codex.
  Documented in [DEVELOPING.md](DEVELOPING.md).
- [scripts/osp.py](scripts/osp.py): validates every repository's canonical
  `.osp/` metadata, including the two findings that measure where the files go
  (runnable code under `knowledge/`, and an attested computation whose code is
  not in the package beside a golden that names it); renders the runtime
  projections, the sphere view and the GitHub topics, checks Agent Plugins
  conformance, writes the release lock and the `dist/` of a release; runs the
  re-attestation ritual of one computation (`reattest`) and reads a receipt's
  release and runtime identity (`receipt-identity`). Documented in
  [docs/osp-metadata.md](docs/osp-metadata.md).
- [scripts/qualify.py](scripts/qualify.py): runs the qualification matrix a
  capability requires per runtime and writes the record, or a waiver.
  Documented in [docs/osp-metadata.md](docs/osp-metadata.md) and the
  marketplace's
  [release qualification guide](https://github.com/open-science-pillars/marketplace/blob/main/docs/release-qualification-guide.md).
- [scripts/release.py](scripts/release.py): runs a release end to end
  (candidate, tag, catalog, publish). Documented in the marketplace's
  [release candidate guide](https://github.com/open-science-pillars/marketplace/blob/main/docs/release-candidate-guide.md).
- [scripts/release_tickets.py](scripts/release_tickets.py): opens and closes
  one qualification ticket per required runtime on a release candidate.
  Documented in [docs/osp-metadata.md](docs/osp-metadata.md).
- [scripts/roadmap.py](scripts/roadmap.py): validates, renders, audits and
  briefs the organization roadmap (`roadmap/roadmap.yaml`, one status per
  deliverable, an issue per active one); its only GitHub write is `labels`,
  dry-run by default. Documented in
  [docs/roadmap-harness-plan.md](docs/roadmap-harness-plan.md) and
  [roadmap/README.md](roadmap/README.md).
- [scripts/fanout_pr.sh](scripts/fanout_pr.sh): the same change as a pull
  request in every clone that carries it, in parallel (branch, signed commit,
  push, pull request, gates, merge); `--no-merge` holds for review and
  `--finish` completes it. Documented in its header.

**Generated, do not edit.** [ROADMAP.md](ROADMAP.md) is rendered from
`roadmap/roadmap.yaml`; [SPHERE-VIEW.md](SPHERE-VIEW.md) is rendered from every
repository's `.osp/repository.yaml`. Edit the sources and re-render.

**Guidance.**

- [DEVELOPING.md](DEVELOPING.md): the roadmap-ID work protocol, the autonomy
  dial, the domain-expansion gate, and the contributor workflow.
- [docs/development-model.md](docs/development-model.md): the operating model,
  standing processes versus initiatives.
- [docs/maintenance.md](docs/maintenance.md): the maintenance cadence.
- [docs/osp-metadata.md](docs/osp-metadata.md): the `.osp/` files, the
  projections, qualification, advertising and publishing.
- [docs/roadmap-harness-plan.md](docs/roadmap-harness-plan.md): the roadmap,
  its status model, and who decides what.

**The harness.** [harness/skills/](harness/skills/) holds the runnable
`osp-roadmap`, `osp-session` and `osp-close` skills for Claude Code and Codex;
[CLAUDE.template.md](CLAUDE.template.md) is the workspace law the workspace
`CLAUDE.md` imports; [workflows/](workflows/) holds reusable Claude Code
workflow scripts (documented in [workflows/README.md](workflows/README.md)).

**History.** `build-record/` is frozen history from the initial build; nobody
needs to read it to work today.

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
`marketplace/docs/phase2-preregistration.md` before any new-domain work (new
domains are gated on the knowledge-layer effectiveness experiment).

License: Apache-2.0.
