# Canonical metadata: the `.osp/` directory

Every non-archived repository carries a `.osp/` directory. It is the
source of truth that the projections are rendered from: GitHub topics,
the sphere view, the marketplace catalog's classification, the Claude
plugin manifest and, when the renderer lands, the Agent Plugins
manifest. The decisions behind this are ADR A and ADR B in the
marketplace repository (`docs/decisions`).

| File | Who carries it | What it owns |
|---|---|---|
| `repository.yaml` | every repository | kind, status, spheres, primary sphere, discipline |
| `package.yaml` | a repository that publishes a package | package name, version, type, content locations, capability and knowledge dependencies |
| `surfaces.yaml` | a repository that exposes runtime capabilities | runtime support policy and the qualification a release must pass |
| `governance.yaml` | every repository | maintainers, runtime maintainers, review policy (the roadmap harness validates it too) |
| `release-lock.json` | generated at a release, later | dependency versions and content digests that identify one governed release |

Schemas live in `osp/` (`repository.schema.json`, `package.schema.json`,
`surfaces.schema.json`) and `roadmap/governance-schema.json`.

## repository.yaml

```yaml
schema_version: 1
repository:
  name: hydrology            # equals the repository name
  kind: capability           # foundation | provider | capability | composite | tooling
  status: developing         # planned | scaffold | developing | available
classification:
  spheres: [hydrosphere, cryosphere]   # one or more of the five spheres
  primary_sphere: hydrosphere
  discipline: Terrestrial Hydrology
```

Rules the validator enforces: a capability declares at least one sphere
and its discipline; `primary_sphere` is one of `spheres`; a provider or
composite repository declares no spheres at repository level (its
bundles do); a `planned` repository carries nothing installable (no
package or surfaces file, no plugin manifest, no `skills/`, no
CITATION.cff) and never appears in the catalog; a copied template fails
until `repository.name` is changed from the template's name, and an
angle-bracket placeholder anywhere fails.

Optional `audience` and `notes` strings explain a tooling repository's
readers or a pending decision; they appear in the sphere view.

## package.yaml

```yaml
schema_version: 1
package:
  name: hydrology
  version: 0.7.0             # the Claude manifest must say the same
  type: capability           # capability | foundation | knowledge
content:
  skills: ./skills
  knowledge: ./knowledge
  verification: ./verification
dependencies:
  capabilities:
    - {name: core, version: ">=0.5.0"}
  knowledge:
    - {name: nasa-daac-knowledge, version: ">=2026.9.3"}
```

The Claude manifest (`.claude-plugin/plugin.json`) is a projection of
this file: the validator fails when its name, version or dependencies
(names and version floors) disagree, and when a manifest exists with no
package file behind it. Content paths must exist.

## surfaces.yaml

```yaml
schema_version: 1
surfaces:
  claude-code:   {role: [development, runtime], required: true, status: supported}
  claude-cowork: {role: runtime, required: true, status: tested}
  openai-codex:  {role: runtime, required: true, status: planned}
  claude-science: {role: future-runtime, required: false, status: limited-release}
qualification:
  require: [install, skill-discovery, skill-invocation, knowledge-resolution,
            dependency-resolution, golden-computation, prove, receipt, release-lock]
```

`required` is policy: a required surface must pass the listed
qualification before a release advertises it (the release-blocking
qualification deliverable of the architecture alignment initiative
enforces this). `status` is the evidence today; an `evidence` string
says where it is recorded. A surfaces file needs a package file.

## governance.yaml (schema version 2)

Version 2 adds an optional `runtime_maintainers` map (claude-code,
claude-cowork, claude-science, openai-codex, agent-plugins), each with
the same `users`, `teams`, `status` shape as `maintainers`, and the
`reviews.runtime_adapter: org-runtime-policy` line. Version 1 files stay
valid until every repository has moved.

## Commands

```bash
uv run build-kit/scripts/osp.py validate            # every workspace sibling with .osp/
uv run build-kit/scripts/osp.py validate hydrology  # one repository
uv run build-kit/scripts/osp.py validate . --standalone   # inside a repository, no catalog cross-check
uv run build-kit/scripts/osp.py topics              # expected GitHub topics per repository
uv run build-kit/scripts/osp.py topics --check      # compare with the live repositories (gh)
uv run build-kit/scripts/osp.py topics --apply --confirm-org open-science-pillars
uv run build-kit/scripts/osp.py sphere-view         # write build-kit/SPHERE-VIEW.md
uv run build-kit/scripts/osp.py sphere-view --check # drift check
```

Topics are `osp`, `osp-sphere-<sphere>` for each sphere, `osp-kind-<kind>`
and `osp-status-<status>`. `topics --apply` replaces only the `osp`
and `osp-*` topics and keeps any others a repository carries. Every
GitHub mutation is dry-run without `--apply --confirm-org`.

The catalog cross-check (skipped with `--standalone`) reads
`marketplace/.claude-plugin/marketplace.json` from the workspace: a
planned repository must be absent; a developing or available repository
with a package file must be present; a catalog `ref` that is not
`{name}--v{version}` is a warning, because the catalog lags a release
until its entry moves.

## Where it runs

Each plugin, template and bundle gate checks out build-kit beside the
repository and runs `osp.py validate . --standalone`. Build-kit's own
workflow validates its metadata and runs the tool's tests. The
scheduled organization audit validates every repository against the
catalog and checks the sphere view for drift.
