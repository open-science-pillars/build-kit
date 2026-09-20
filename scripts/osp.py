#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml==6.0.2", "jsonschema==4.25.1"]
# ///
"""Canonical OSP metadata: validate the .osp/ files, compute the GitHub
topics they imply, and render the organization by sphere.

The .osp/ directory of a repository is the source of truth the
projections are rendered from (the decision records in the marketplace
repository, docs/decisions):

  repository.yaml   kind, status, spheres, primary sphere, discipline
                    (every non-archived repository)
  package.yaml      package identity, version, content, dependencies,
                    presentation metadata and connector declarations
                    (only a repository that publishes a package)
  surfaces.yaml     runtime support policy and qualification requirements
                    (only a repository that exposes runtime capabilities)
  governance.yaml   maintainers, runtime maintainers, review policy
                    (validated by the roadmap harness as well)

  osp.py validate [REPO_DIR ...]      default: every workspace sibling
                                      that carries .osp/repository.yaml
  osp.py topics [REPO_DIR ...]        print the expected topics (osp and the
                                      plain sphere words); --check
                                      compares with the live repository
                                      (gh api), --apply --confirm-org
                                      open-science-pillars sets them
  osp.py sphere-view [--check]        render SPHERE-VIEW.md from the
                                      workspace's repository.yaml files;
                                      --into FILE writes the view between
                                      osp-sphere-view markers in FILE (the
                                      org profile) instead
  osp.py teams                        print the gh commands that create the
                                      teams osp/teams.yaml declares
  osp.py render [REPO_DIR ...]        write the runtime projections of every
                                      package: .claude-plugin/plugin.json and
                                      .mcp.json (Claude), plugin.json and
                                      mcp.json (Agent Plugins 1.0); --check
                                      fails on drift
  osp.py lock [REPO_DIR ...]          write .osp/release-lock.json (digests of
                                      the canonical source, content and
                                      projections of one release); --check
                                      fails when stale, --report only says so
  osp.py plugin-check [REPO_DIR ...]  Agent Plugins conformance of the
                                      portable package against the pinned
                                      specification version
  osp.py reattest [--package DIR]     the re-attestation ritual of one
                                      computation, from the package's
                                      verification/reference_runs.yaml
  osp.py receipt-identity RECEIPT     does a receipt name the capability
                                      release and the runtime that made it

  osp.py advertise [REPO_DIR ...]    what a release may say per runtime: a
                                      surface is supported only on a qualified
                                      record for this version and lock; --check
                                      fails a claim without one; --into README.md
                                      writes the runtime block between
                                      osp-runtimes markers
  osp.py publish [REPO_DIR]          emit dist/: the Claude package zip, the
                                      Agent Plugins directory only when a
                                      runtime that consumes it is qualified,
                                      and release.json with the honest status
  qualify.py (beside this tool)      runtime qualification of one capability:
                                      the headless Claude Code run, the
                                      checklist for a runtime run by hand, and
                                      the record per runtime under
                                      .osp/qualification/

Every GitHub mutation is dry-run unless both --apply and the exact
--confirm-org value are supplied. Exit 1 on any validation error or
drift; warnings never fail.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator, FormatChecker

BUILD_KIT = Path(__file__).resolve().parents[1]
WORKSPACE = BUILD_KIT.parent
SCHEMAS = BUILD_KIT / "osp"
GOVERNANCE_SCHEMA = BUILD_KIT / "roadmap" / "governance-schema.json"
SPHERE_VIEW = BUILD_KIT / "SPHERE-VIEW.md"
TEAMS_FILE = SCHEMAS / "teams.yaml"
ORG = "open-science-pillars"

SPHERES = ["atmosphere", "biosphere", "cryosphere", "geosphere", "hydrosphere"]
SPHERE_TITLES = {s: s.capitalize() for s in SPHERES}
KINDS = ["foundation", "provider", "capability", "composite", "tooling"]
STATUSES = ["planned", "scaffold", "developing", "available"]
TEMPLATE_NAMES = {"plugin-template", "knowledge-template"}
PLACEHOLDER = re.compile(r"<[^>]*>|\breplace\b|\byour-[a-z-]+\b", re.I)
# What a planned repository must not carry: nothing installable.
PLANNED_FORBIDDEN = [
    ".osp/package.yaml", ".osp/surfaces.yaml", ".claude-plugin", "plugin.json",
    "mcp.json", ".mcp.json", "skills", "CITATION.cff", ".osp/release-lock.json",
]


class OspError(RuntimeError):
    pass


def load_yaml(path: Path) -> Any:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise OspError(f"{path}: {exc}") from exc


def schema_errors(data: Any, schema_path: Path) -> list[str]:
    schema = json.loads(schema_path.read_text())
    Draft202012Validator.check_schema(schema)
    normalized = json.loads(json.dumps(data, default=str))
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    out = []
    for error in sorted(validator.iter_errors(normalized), key=lambda e: list(e.absolute_path)):
        where = ".".join(str(x) for x in error.absolute_path) or "root"
        out.append(f"schema {where}: {error.message}")
    return out


def registered_teams() -> dict[str, dict[str, Any]]:
    data = load_yaml(TEAMS_FILE) if TEAMS_FILE.is_file() else {}
    return dict((data or {}).get("teams", {}))


CODEOWNERS_HANDLE = re.compile(r"(?<!\S)@([A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)?)")


def codeowners_findings(repo_dir: Path, name: str, teams: dict[str, Any]) -> list[str]:
    """CODEOWNERS names teams from the registry, never individuals."""
    path = repo_dir / "CODEOWNERS"
    if not path.is_file():
        return [f"{name}: no root CODEOWNERS; every repository names its owning team"]
    out = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        text = line.split("#", 1)[0]
        for handle in CODEOWNERS_HANDLE.findall(text):
            org, _, team = handle.partition("/")
            if not team:
                out.append(f"{name}: CODEOWNERS line {lineno} names an individual (@{handle}); owners are teams")
            elif org != ORG:
                out.append(f"{name}: CODEOWNERS line {lineno} names a team outside the organization (@{handle})")
            elif team not in teams:
                out.append(f"{name}: CODEOWNERS line {lineno} names @{handle}, which osp/teams.yaml does not declare")
    return out


def workspace_repos(workspace: Path = WORKSPACE) -> list[Path]:
    return sorted(p for p in workspace.iterdir()
                  if p.is_dir() and (p / ".osp" / "repository.yaml").is_file())


def read_repository(repo_dir: Path) -> dict[str, Any] | None:
    path = repo_dir / ".osp" / "repository.yaml"
    return load_yaml(path) if path.is_file() else None


def plugin_manifest(repo_dir: Path) -> dict[str, Any] | None:
    path = repo_dir / ".claude-plugin" / "plugin.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise OspError(f"{path}: {exc}") from exc


def manifest_dependencies(manifest: dict[str, Any]) -> dict[str, str | None]:
    """{name: version floor or None} from a Claude plugin manifest, whose
    entries are a bare name or {name, version}."""
    out: dict[str, str | None] = {}
    for entry in manifest.get("dependencies", []) or []:
        if isinstance(entry, str):
            out[entry] = None
        elif isinstance(entry, dict) and "name" in entry:
            out[entry["name"]] = entry.get("version")
    return out


def catalog_entries(workspace: Path) -> dict[str, dict[str, Any]] | None:
    path = workspace / "marketplace" / ".claude-plugin" / "marketplace.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise OspError(f"{path}: {exc}") from exc
    return {p["name"]: p for p in data.get("plugins", []) if isinstance(p, dict) and "name" in p}


def validate_repo(repo_dir: Path, workspace: Path | None = None, projections_agree: bool = True,
                  today: str | None = None) -> tuple[list[str], list[str]]:
    """(errors, warnings) for one repository's .osp/ directory. With
    projections_agree=False the Claude manifest is not compared with the
    package file: that is the state just before `render` rewrites it after
    a version bump, and render is what fixes it. The two findings about
    where the files go are warnings until MIGRATION_ERRORS_FROM and errors
    after; `today` is for the tests."""
    errors: list[str] = []
    warnings: list[str] = []
    name = repo_dir.name
    osp = repo_dir / ".osp"

    meta = read_repository(repo_dir)
    if meta is None:
        return [f"{name}: .osp/repository.yaml is missing"], warnings
    errors += [f"{name} repository.yaml {e}" for e in schema_errors(meta, SCHEMAS / "repository.schema.json")]
    if errors:
        return errors, warnings

    repo = meta["repository"]
    cls = meta["classification"]
    declared = repo["name"]
    # The repository's name is the checkout directory's name, or, inside a
    # GitHub Actions job that checks the repository out under another
    # directory (plugin/, bundle/), the repository the job runs for.
    actions_repo = os.environ.get("GITHUB_REPOSITORY", "").rpartition("/")[2]
    if declared == name or (actions_repo and declared == actions_repo):
        name = declared
    elif declared in TEMPLATE_NAMES:
        errors.append(f"{name}: repository.yaml still names the template ({declared}); "
                      "a copied template is renamed before it validates")
    else:
        errors.append(f"{name}: repository.yaml names {declared!r}, not the repository")
    for field in ("name", "audience", "notes"):
        value = repo.get(field)
        if isinstance(value, str) and PLACEHOLDER.search(value) and field == "name":
            errors.append(f"{name}: repository.{field} is a placeholder: {value!r}")
    if isinstance(cls.get("discipline"), str) and PLACEHOLDER.search(cls["discipline"]):
        errors.append(f"{name}: classification.discipline is a placeholder: {cls['discipline']!r}")

    spheres = cls["spheres"]
    primary = cls["primary_sphere"]
    if spheres and primary is None:
        errors.append(f"{name}: spheres are declared but primary_sphere is null")
    if primary is not None and primary not in spheres:
        errors.append(f"{name}: primary_sphere {primary!r} is not among spheres {spheres}")
    if repo["kind"] == "capability" and not spheres:
        errors.append(f"{name}: a capability declares at least one sphere")
    if repo["kind"] == "capability" and not cls.get("discipline"):
        errors.append(f"{name}: a capability names its discipline")
    if repo["kind"] in {"provider", "composite"} and spheres:
        warnings.append(f"{name}: a {repo['kind']} repository normally declares no spheres at repository level "
                        "(its bundles or composites declare their own)")

    package_path = osp / "package.yaml"
    surfaces_path = osp / "surfaces.yaml"
    is_template = declared in TEMPLATE_NAMES and declared == name
    if is_template:
        # A template's manifest and package file are placeholders for the
        # copier; only their schemas are checked here. A copy that keeps
        # the template's names fails above.
        for path, schema in ((package_path, "package.schema.json"), (surfaces_path, "surfaces.schema.json")):
            if path.is_file():
                errors += [f"{name} {path.name} {e}" for e in schema_errors(load_yaml(path), SCHEMAS / schema)]
    elif repo["status"] == "planned":
        for rel in PLANNED_FORBIDDEN:
            if (repo_dir / rel).exists():
                errors.append(f"{name}: planned repositories are never installable, but {rel} exists")
    else:
        package = load_yaml(package_path) if package_path.is_file() else None
        manifest = plugin_manifest(repo_dir)
        if package is not None:
            perrors = schema_errors(package, SCHEMAS / "package.schema.json")
            errors += [f"{name} package.yaml {e}" for e in perrors]
            if not perrors:
                pkg = package["package"]
                if pkg["name"] != name:
                    errors.append(f"{name}: package.yaml names {pkg['name']!r}, not the repository")
                for key, rel in (package.get("content") or {}).items():
                    if not (repo_dir / rel).exists():
                        errors.append(f"{name}: package.yaml content.{key} points at {rel}, which does not exist")
                if manifest is not None and projections_agree:
                    if manifest.get("version") != pkg["version"]:
                        errors.append(f"{name}: package.yaml version {pkg['version']} but the Claude manifest "
                                      f"says {manifest.get('version')!r}; the manifest is a projection and must agree")
                    if manifest.get("name") != pkg["name"]:
                        errors.append(f"{name}: the Claude manifest names {manifest.get('name')!r}, package.yaml {pkg['name']!r}")
                    canonical = {d["name"]: d.get("version") for d in
                                 package["dependencies"]["capabilities"] + package["dependencies"]["knowledge"]}
                    projected = manifest_dependencies(manifest)
                    if canonical != projected:
                        errors.append(f"{name}: dependencies differ between package.yaml {canonical} "
                                      f"and the Claude manifest {projected}")
        elif manifest is not None:
            errors.append(f"{name}: a Claude manifest exists but .osp/package.yaml does not; "
                          "the manifest is a projection of package.yaml")
        if surfaces_path.is_file():
            surfaces = load_yaml(surfaces_path)
            errors += [f"{name} surfaces.yaml {e}" for e in schema_errors(surfaces, SCHEMAS / "surfaces.schema.json")]
            if package is None:
                errors.append(f"{name}: surfaces.yaml needs package.yaml; only a package has runtime surfaces")
        if repo["kind"] == "capability" and repo["status"] in {"developing", "available"} and package is None:
            errors.append(f"{name}: a {repo['status']} capability publishes a package (package.yaml)")

    teams = registered_teams()
    governance_path = osp / "governance.yaml"
    if governance_path.is_file():
        gov = load_yaml(governance_path)
        gerrors = schema_errors(gov, GOVERNANCE_SCHEMA)
        errors += [f"{name} governance.yaml {e}" for e in gerrors]
        if not gerrors:
            if gov.get("repository") != name:
                errors.append(f"{name}: governance.yaml declares {gov.get('repository')!r}")
            groups = [("maintainers", gov.get("maintainers", {}))]
            groups += list((gov.get("runtime_maintainers") or {}).items())
            for label, group in groups:
                for team in (group or {}).get("teams", []):
                    if team not in teams:
                        errors.append(f"{name}: governance {label} names team {team!r}, which osp/teams.yaml does not declare")
    else:
        warnings.append(f"{name}: no .osp/governance.yaml")
    errors += codeowners_findings(repo_dir, name, teams)
    # Where the files go: runnable code filed as knowledge, and an
    # attested computation whose code is not in the package beside a
    # golden that names it (ADR E). Reported in both modes.
    where = code_placement_findings(repo_dir, name)
    if (today or dt.date.today().isoformat()) < MIGRATION_ERRORS_FROM:
        warnings += where
    else:
        errors += where

    if workspace is not None and not is_template:
        catalog = catalog_entries(workspace)
        if catalog is not None:
            entry = catalog.get(name)
            if repo["status"] == "planned" and entry is not None:
                errors.append(f"{name}: planned, yet listed in the marketplace catalog")
            if repo["status"] in {"developing", "available"} and package_path.is_file():
                if entry is None:
                    errors.append(f"{name}: publishes a package but is absent from the marketplace catalog")
                else:
                    ref = (entry.get("source") or {}).get("ref")
                    version = load_yaml(package_path)["package"]["version"]
                    expected = f"{name}--v{version}"
                    if ref != expected:
                        warnings.append(f"{name}: catalog ref {ref!r} is not {expected!r} "
                                        "(the catalog lags a release until its entry moves)")
    return errors, warnings


def topics_for(meta: dict[str, Any]) -> list[str]:
    """The topics rendered from repository.yaml: `osp`, which finds every
    Open Science Pillars repository in one search, and each sphere as the
    plain word people search for. Kind and status stay in the file and
    the sphere view; nobody searches for them, and a topic is one more
    place for them to go stale. Hand-curated topics (the science, the
    tools) are kept as they are."""
    cls = meta["classification"]
    return ["osp"] + sorted(cls["spheres"])


def gh_json(args: list[str]) -> Any:
    try:
        result = subprocess.run(["gh", "api", *args], text=True, capture_output=True, check=True)
    except FileNotFoundError as exc:
        raise OspError("required command not found: gh") from exc
    except subprocess.CalledProcessError as exc:
        raise OspError(f"gh api failed: {(exc.stderr or exc.stdout).strip()}") from exc
    return json.loads(result.stdout) if result.stdout.strip() else None


def live_topics(name: str) -> set[str]:
    data = gh_json(["-H", "Accept: application/vnd.github+json", f"repos/{ORG}/{name}/topics"])
    return set((data or {}).get("names", []))


def set_topics(name: str, expected: list[str], keep: set[str]) -> None:
    names = sorted(set(expected) | keep)
    args = ["-X", "PUT", "-H", "Accept: application/vnd.github+json", f"repos/{ORG}/{name}/topics"]
    for n in names:
        args += ["-f", f"names[]={n}"]
    gh_json(args)


def render_sphere_view(repos: list[tuple[str, dict[str, Any]]]) -> str:
    """The organization by sphere, from repository.yaml files. A repository
    appears under its primary sphere and names its other spheres; provider,
    foundation, tooling and composite repositories have their own groups."""
    lines = [
        "# Open Science Pillars by sphere",
        "",
        "> Generated by `scripts/osp.py sphere-view` from every repository's",
        "> `.osp/repository.yaml`. Do not edit this file directly.",
        "",
        "Pillar means sphere: one of the five Earth science spheres. A domain",
        "capability is a discipline inside a sphere; provider knowledge is",
        "signed by its steward and cuts across spheres; foundation and tooling",
        "repositories serve every sphere. `planned` means visible and not",
        "installable.",
        "",
    ]
    by_name = {n: m for n, m in repos}
    for sphere in SPHERES:
        rows = sorted(n for n, m in repos
                      if m["repository"]["kind"] in {"capability"} and m["classification"]["primary_sphere"] == sphere)
        lines += [f"## {SPHERE_TITLES[sphere]}", ""]
        if not rows:
            lines += ["No domain capability yet.", ""]
            continue
        lines += ["| Repository | Discipline | Status | Also |", "|---|---|---|---|"]
        for n in rows:
            m = by_name[n]
            also = ", ".join(SPHERE_TITLES[s] for s in m["classification"]["spheres"] if s != sphere) or ""
            lines.append(f"| `{n}` | {m['classification']['discipline']} | {m['repository']['status']} | {also} |")
        lines.append("")
    groups = [
        ("Provider knowledge", {"provider"}, False),
        ("Composites", {"composite"}, False),
        ("Foundation and tooling", {"foundation", "tooling"}, True),
    ]
    for title, kinds, collapsed in groups:
        rows = sorted(n for n, m in repos if m["repository"]["kind"] in kinds)
        # The tooling group is collapsed: GitHub renders <details> in Markdown,
        # and the blank lines after <summary> and before </details> are what
        # let the table inside render as Markdown.
        if collapsed:
            lines += [f"<details><summary>{title} (serve every sphere)</summary>", ""]
        else:
            lines += [f"## {title}", ""]
        if not rows:
            lines += ["None yet.", ""]
        else:
            lines += ["| Repository | Kind | Status | Spheres | Notes |", "|---|---|---|---|---|"]
            for n in rows:
                m = by_name[n]
                spheres = ", ".join(SPHERE_TITLES[s] for s in m["classification"]["spheres"]) or "all"
                notes = m["repository"].get("audience") or m["repository"].get("notes") or ""
                lines.append(f"| `{n}` | {m['repository']['kind']} | {m['repository']['status']} | {spheres} | {notes} |")
            lines.append("")
        if collapsed:
            lines += ["</details>", ""]
    return "\n".join(lines).rstrip() + "\n"


MARK_START = "<!-- osp-sphere-view:start -->"
MARK_END = "<!-- osp-sphere-view:end -->"


def splice(text: str, block: str) -> str:
    """Replace what lies between the sphere-view markers in text with block."""
    if MARK_START not in text or MARK_END not in text:
        raise OspError(f"no {MARK_START} ... {MARK_END} markers to write between")
    head, rest = text.split(MARK_START, 1)
    _, tail = rest.split(MARK_END, 1)
    return f"{head}{MARK_START}\n{block.rstrip()}\n{MARK_END}{tail}"


def render_profile_block(repos: list[tuple[str, dict[str, Any]]]) -> str:
    """The sphere view as the organization profile shows it: the five
    spheres with their capabilities, then provider knowledge, composites,
    and the foundation and tooling repositories, each linked."""
    by_name = {n: m for n, m in repos}
    org_url = f"https://github.com/{ORG}"
    lines = ["Rendered by build-kit's `osp.py sphere-view --into` from every repository's",
             "`.osp/repository.yaml`; edit the files, not this block.", ""]
    for sphere in SPHERES:
        rows = sorted(n for n, m in repos
                      if m["repository"]["kind"] == "capability" and m["classification"]["primary_sphere"] == sphere)
        lines.append(f"**{SPHERE_TITLES[sphere]}**")
        if not rows:
            lines += ["", "- no domain capability yet", ""]
            continue
        lines.append("")
        for n in rows:
            m = by_name[n]
            also = [SPHERE_TITLES[s] for s in m["classification"]["spheres"] if s != sphere]
            extra = f"; also {', '.join(also)}" if also else ""
            lines.append(f"- [{n}]({org_url}/{n}) *({m['repository']['status']})*: {m['classification']['discipline']}{extra}")
        lines.append("")
    for title, kinds, collapsed in (("**Provider knowledge** (signed by its stewards; cuts across spheres)", {"provider"}, False),
                                    ("**Composites** (cross-sphere)", {"composite"}, False),
                                    ("Foundation and tooling (serve every sphere)", {"foundation", "tooling"}, True)):
        rows = sorted(n for n, m in repos if m["repository"]["kind"] in kinds)
        # Spheres, provider knowledge and composites open; the tooling that
        # serves every sphere collapsed. The blank line after <summary> and
        # before </details> lets GitHub render the list inside as Markdown.
        lines.append(f"<details><summary>{title}</summary>" if collapsed else title)
        lines.append("")
        if not rows:
            lines += ["- none yet", ""]
        else:
            for n in rows:
                m = by_name[n]
                note = m["repository"].get("audience") or m["repository"].get("notes") or ""
                lines.append(f"- [{n}]({org_url}/{n}) *({m['repository']['status']})*: {note}")
            lines.append("")
        if collapsed:
            lines += ["</details>", ""]
    return "\n".join(lines).rstrip() + "\n"


def resolve_dirs(args: argparse.Namespace) -> list[Path]:
    if args.repos:
        return [Path(p).resolve() for p in args.repos]
    return workspace_repos(WORKSPACE)


# ---------------------------------------------------------------------------
# Runtime projections (ADR B): the Claude package files and the Agent
# Plugins package are rendered from .osp/package.yaml and
# .osp/repository.yaml and checked for drift; the release lock digests
# what one governed release consists of.
# ---------------------------------------------------------------------------

AGENT_PLUGINS_VERSION = "1.0.0"
AGENT_PLUGINS_SCHEMAS = SCHEMAS / "agent-plugins" / AGENT_PLUGINS_VERSION
PLUGIN_SCHEMA_ID = f"https://agent-plugins.org/schemas/{AGENT_PLUGINS_VERSION}/plugin.schema.json"
MCP_SCHEMA_ID = f"https://agent-plugins.org/schemas/{AGENT_PLUGINS_VERSION}/mcp.schema.json"
# The organization's own extension namespace in the portable manifest: the
# reverse-domain form of open-science-pillars.github.io, which the
# organization controls. It carries classification and dependencies for an
# OSP-aware client; every other client ignores it, as the specification
# requires.
OSP_NAMESPACE = "io.github.open-science-pillars"
DEFAULT_AUTHOR = {"name": "Open Science Pillars Community"}
DEFAULT_LICENSE = "Apache-2.0"
CLAUDE_MANIFEST = ".claude-plugin/plugin.json"
CLAUDE_MCP = ".mcp.json"
PORTABLE_MANIFEST = "plugin.json"
PORTABLE_MCP = "mcp.json"
RELEASE_LOCK = ".osp/release-lock.json"
PLACEHOLDER_ROOT = "${PLUGIN_ROOT}"
PLACEHOLDER_DATA = "${PLUGIN_DATA}"
CLAUDE_ROOT = "${CLAUDE_PLUGIN_ROOT}"
SKILL_NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SKILL_FIELDS = {"name", "description", "license", "compatibility", "metadata", "allowed-tools"}
SKILL_BODY_LINES = 500   # the specification's recommendation for SKILL.md
RUNTIME_DIR_NAMES = {"claude", "claude-code", "cowork", "claude-cowork", "openai", "codex", "openai-codex",
                     "gemini", "gemini-cli", "goose", "cursor", "copilot", "kiro"}
DIGEST_SKIP_DIRS = {"__pycache__", ".git", ".ipynb_checkpoints"}
DIGEST_SKIP_SUFFIXES = {".pyc", ".pyo"}
DIGEST_SKIP_NAMES = {".DS_Store"}


def read_package(repo_dir: Path) -> dict[str, Any] | None:
    path = repo_dir / ".osp" / "package.yaml"
    return load_yaml(path) if path.is_file() else None


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise OspError(f"{path}: {exc}") from exc


def dump_json(data: Any) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def package_metadata(pkg: dict[str, Any], name: str) -> dict[str, Any]:
    """Presentation fields with the organization's defaults filled in."""
    meta = dict(pkg.get("metadata") or {})
    url = f"https://github.com/{ORG}/{name}"
    return {
        "description": meta.get("description"),
        "keywords": list(meta.get("keywords") or []),
        "author": dict(meta.get("author") or DEFAULT_AUTHOR),
        "homepage": meta.get("homepage", url),
        "repository": meta.get("repository", url),
        "license": meta.get("license", DEFAULT_LICENSE),
    }


def dependency_entries(pkg: dict[str, Any]) -> list[dict[str, Any]]:
    deps = pkg.get("dependencies") or {}
    return list(deps.get("capabilities") or []) + list(deps.get("knowledge") or [])


def render_claude_manifest(pkg: dict[str, Any], name: str) -> dict[str, Any]:
    """The Claude plugin manifest: name, version and dependencies from the
    package, presentation from its metadata. A dependency with no floor is
    a bare name, the form the Claude manifest has always used."""
    meta = package_metadata(pkg, name)
    if not meta["description"]:
        raise OspError(f"{name}: package.yaml needs metadata.description to render a manifest")
    out: dict[str, Any] = {"name": pkg["package"]["name"], "version": pkg["package"]["version"],
                           "description": meta["description"]}
    deps = [d["name"] if not d.get("version") else {"name": d["name"], "version": d["version"]}
            for d in dependency_entries(pkg)]
    if deps:
        out["dependencies"] = deps
    out["author"] = meta["author"]
    out["homepage"] = meta["homepage"]
    out["license"] = meta["license"]
    if meta["keywords"]:
        out["keywords"] = meta["keywords"]
    return out


def substitute(value: Any, old: str, new: str) -> Any:
    if isinstance(value, str):
        return value.replace(old, new)
    if isinstance(value, list):
        return [substitute(v, old, new) for v in value]
    if isinstance(value, dict):
        return {k: substitute(v, old, new) for k, v in value.items()}
    return value


def claude_server(server: dict[str, Any]) -> dict[str, Any]:
    """One connector declaration as Claude's .mcp.json spells it: `http` for
    the streamable transport, and the Claude placeholder for the package
    root."""
    kind = server["type"]
    out: dict[str, Any] = {"type": "http" if kind == "streamable-http" else kind}
    if kind == "stdio":
        out["command"] = server["command"]
        for key in ("args", "env", "cwd"):
            if key in server:
                out[key] = substitute(server[key], PLACEHOLDER_ROOT, CLAUDE_ROOT)
    else:
        out["url"] = server["url"]
        if "headers" in server:
            out["headers"] = dict(server["headers"])
    return out


def portable_server(server: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in server.items() if k != "portable"}


def reach_servers(pkg: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return dict(((pkg.get("reach") or {}).get("servers")) or {})


def render_claude_mcp(pkg: dict[str, Any]) -> dict[str, Any] | None:
    servers = reach_servers(pkg)
    if not servers:
        return None
    return {"mcpServers": {n: claude_server(s) for n, s in servers.items()}}


def render_portable_mcp(pkg: dict[str, Any]) -> dict[str, Any] | None:
    servers = {n: portable_server(s) for n, s in reach_servers(pkg).items() if s.get("portable", True)}
    if not servers:
        return None
    return {"$schema": MCP_SCHEMA_ID, "mcpServers": servers}


def render_portable_manifest(pkg: dict[str, Any], repo_meta: dict[str, Any], name: str) -> dict[str, Any]:
    """The Agent Plugins 1.0 manifest: the closed portable fields, and the
    organization's classification and dependencies under its own extension
    namespace, plus any client extension the package declares."""
    meta = package_metadata(pkg, name)
    if not meta["description"]:
        raise OspError(f"{name}: package.yaml needs metadata.description to render a manifest")
    cls = repo_meta["classification"]
    deps = pkg.get("dependencies") or {}
    osp_ext = {
        "kind": repo_meta["repository"]["kind"],
        "status": repo_meta["repository"]["status"],
        "spheres": list(cls["spheres"]),
        "primary_sphere": cls["primary_sphere"],
        "discipline": cls["discipline"],
        "package_type": pkg["package"]["type"],
        "dependencies": {
            "capabilities": [dict(d) for d in deps.get("capabilities") or []],
            "knowledge": [dict(d) for d in deps.get("knowledge") or []],
        },
    }
    extensions: dict[str, Any] = {OSP_NAMESPACE: osp_ext}
    for ns, data in (pkg.get("extensions") or {}).items():
        if ns == OSP_NAMESPACE:
            raise OspError(f"{name}: package.yaml extensions may not override {OSP_NAMESPACE}; it is rendered")
        extensions[ns] = data
    out: dict[str, Any] = {
        "$schema": PLUGIN_SCHEMA_ID,
        "name": pkg["package"]["name"],
        "version": pkg["package"]["version"],
        "description": meta["description"],
        "author": meta["author"],
        "homepage": meta["homepage"],
        "repository": meta["repository"],
        "license": meta["license"],
    }
    if meta["keywords"]:
        out["keywords"] = meta["keywords"]
    out["extensions"] = extensions
    return out


def projections(repo_dir: Path) -> dict[str, dict[str, Any] | None] | None:
    """{relative path: rendered object or None (must not exist)} for a
    repository that publishes a package; None for one that does not."""
    pkg = read_package(repo_dir)
    repo_meta = read_repository(repo_dir)
    if pkg is None or repo_meta is None:
        return None
    name = pkg["package"]["name"]
    return {
        CLAUDE_MANIFEST: render_claude_manifest(pkg, name),
        CLAUDE_MCP: render_claude_mcp(pkg),
        PORTABLE_MANIFEST: render_portable_manifest(pkg, repo_meta, name),
        PORTABLE_MCP: render_portable_mcp(pkg),
    }


def projection_drift(repo_dir: Path, expected: dict[str, dict[str, Any] | None]) -> list[str]:
    """Which rendered files differ from what is on disk, compared as JSON
    values so formatting alone is never drift."""
    out = []
    for rel, obj in expected.items():
        path = repo_dir / rel
        if obj is None:
            if path.exists():
                out.append(f"{rel} exists but package.yaml renders nothing there (a hand-written projection)")
            continue
        if not path.is_file():
            out.append(f"{rel} is missing")
        elif read_json(path) != obj:
            out.append(f"{rel} differs from what package.yaml renders")
    return out


def write_projections(repo_dir: Path, expected: dict[str, dict[str, Any] | None]) -> list[str]:
    changed = []
    for rel, obj in expected.items():
        path = repo_dir / rel
        if obj is None:
            if path.exists():
                path.unlink()
                changed.append(f"removed {rel}")
            continue
        text = dump_json(obj)
        if not path.is_file() or path.read_text(encoding="utf-8") != text:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
            changed.append(f"wrote {rel}")
    return changed


def ignore_rules(top: Path) -> list[tuple[Path, str, bool, bool]]:
    """(directory, pattern, directory_only, anchored) from every .gitignore
    under top. Negations are not honored: what a package ships is what
    its ignore files do not exclude."""
    rules = []
    for gi in sorted(top.rglob(".gitignore")):
        if set(gi.relative_to(top).parts[:-1]) & DIGEST_SKIP_DIRS:
            continue
        for line in gi.read_text(encoding="utf-8", errors="replace").splitlines():
            pat = line.strip()
            if not pat or pat.startswith("#") or pat.startswith("!"):
                continue
            directory_only = pat.endswith("/")
            pat = pat.rstrip("/")
            anchored = pat.startswith("/") or "/" in pat
            rules.append((gi.parent, pat.lstrip("/"), directory_only, anchored))
    return rules


def ignored(path: Path, is_dir: bool, rules: list[tuple[Path, str, bool, bool]]) -> bool:
    """Whether a path (or any directory above it) matches an ignore rule,
    in the subset of gitignore semantics packages use: a bare pattern
    matches a name at any depth below its file, a pattern with a slash
    matches the path relative to that file, a trailing slash matches only
    directories."""
    import fnmatch
    for base, pat, directory_only, anchored in rules:
        try:
            rel = path.relative_to(base)
        except ValueError:
            continue
        parts = rel.parts
        for depth in range(1, len(parts) + 1):
            candidate = Path(*parts[:depth])
            candidate_is_dir = depth < len(parts) or is_dir
            if directory_only and not candidate_is_dir:
                continue
            target = candidate.as_posix() if anchored else candidate.name
            if fnmatch.fnmatchcase(target, pat):
                return True
    return False


def tree_digest(root: Path, package_root: Path | None = None) -> str | None:
    """sha256 over every regular file under root, by sorted relative path
    and content, so the same tree digests the same anywhere. Caches,
    editor droppings and whatever the package's .gitignore files exclude
    (generated fixtures, figures) are skipped: the lock digests what the
    package ships, not what a run left behind."""
    if not root.is_dir():
        return None
    rules = ignore_rules(package_root or root)
    h = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        rel = path.relative_to(root)
        if (set(rel.parts[:-1]) & DIGEST_SKIP_DIRS or path.suffix in DIGEST_SKIP_SUFFIXES
                or path.name in DIGEST_SKIP_NAMES or path.name == ".gitignore" or ignored(path, False, rules)):
            continue
        h.update(rel.as_posix().encode("utf-8") + b"\0")
        h.update(hashlib.sha256(path.read_bytes()).digest())
    return "sha256:" + h.hexdigest()


def value_digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def render_lock(repo_dir: Path) -> dict[str, Any]:
    """The release lock: what one governed release consists of, digested
    from canonical source and the rendered projections, with no timestamp
    so two renders of one tree agree."""
    pkg = read_package(repo_dir)
    repo_meta = read_repository(repo_dir)
    if pkg is None or repo_meta is None:
        raise OspError(f"{repo_dir.name}: a release lock needs .osp/package.yaml and .osp/repository.yaml")
    name = pkg["package"]["name"]
    deps = pkg.get("dependencies") or {}
    lock: dict[str, Any] = {
        "schema_version": 1,
        "package": name,
        "version": pkg["package"]["version"],
        "package_type": pkg["package"]["type"],
        "agent_plugins_spec": AGENT_PLUGINS_VERSION,
        "repository_classification_digest": value_digest(repo_meta),
        "dependencies": {
            "capabilities": {d["name"]: d.get("version") for d in deps.get("capabilities") or []},
            "knowledge": {d["name"]: d.get("version") for d in deps.get("knowledge") or []},
        },
    }
    for key, rel in sorted((pkg.get("content") or {}).items()):
        lock[f"{key}_digest"] = tree_digest(repo_dir / rel, repo_dir)
    rendered = projections(repo_dir) or {}
    lock["adapters"] = {
        "claude": value_digest({CLAUDE_MANIFEST: rendered.get(CLAUDE_MANIFEST), CLAUDE_MCP: rendered.get(CLAUDE_MCP)}),
        "agent-plugins": value_digest({PORTABLE_MANIFEST: rendered.get(PORTABLE_MANIFEST),
                                       PORTABLE_MCP: rendered.get(PORTABLE_MCP)}),
    }
    return lock


def parse_frontmatter(text: str) -> dict[str, Any] | None:
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---", 4)
    if end < 0:
        return None
    try:
        data = yaml.safe_load(text[4:end])
    except yaml.YAMLError:
        return None
    return data if isinstance(data, dict) else None


def skill_findings(skills_dir: Path, name: str) -> tuple[list[str], list[str]]:
    """Skill discovery as the specification defines it: each immediate
    child directory with a regular SKILL.md is a skill, and the skill's
    frontmatter follows the Agent Skills rules."""
    errors: list[str] = []
    warnings: list[str] = []
    if not skills_dir.exists():
        return errors, warnings
    if not skills_dir.is_dir():
        return [f"{name}: skills exists but is not a directory"], warnings
    outside: dict[str, list[str]] = {}
    for child in sorted(skills_dir.iterdir()):
        if not child.is_dir():
            continue
        if child.name in RUNTIME_DIR_NAMES:
            errors.append(f"{name}: skills/{child.name}/ is a runtime-specific skill tree; one canonical skill, no per-runtime copies")
            continue
        skill_md = child / "SKILL.md"
        if not skill_md.is_file():
            warnings.append(f"{name}: skills/{child.name}/ has no SKILL.md and is not a skill a client discovers")
            continue
        text = skill_md.read_text(encoding="utf-8")
        fm = parse_frontmatter(text)
        where = f"{name}: skills/{child.name}/SKILL.md"
        if fm is None:
            errors.append(f"{where} has no YAML frontmatter")
            continue
        skill_name = fm.get("name")
        if not isinstance(skill_name, str) or not skill_name:
            errors.append(f"{where}: frontmatter name is missing")
        else:
            if skill_name != child.name:
                errors.append(f"{where}: name {skill_name!r} does not match its directory")
            if len(skill_name) > 64 or not SKILL_NAME.match(skill_name):
                errors.append(f"{where}: name {skill_name!r} is not lowercase alphanumeric words joined by single hyphens, at most 64 characters")
        desc = fm.get("description")
        if not isinstance(desc, str) or not desc.strip():
            errors.append(f"{where}: frontmatter description is missing")
        elif len(desc) > 1024:
            errors.append(f"{where}: description is longer than 1024 characters")
        compat = fm.get("compatibility")
        if compat is not None and (not isinstance(compat, str) or not 1 <= len(compat) <= 500):
            errors.append(f"{where}: compatibility is a string of 1 to 500 characters")
        metadata = fm.get("metadata")
        if metadata is not None and (not isinstance(metadata, dict)
                                     or not all(isinstance(k, str) and isinstance(v, str) for k, v in metadata.items())):
            errors.append(f"{where}: metadata is a map of string keys to string values")
        for field in ("license", "allowed-tools"):
            if field in fm and not isinstance(fm[field], str):
                errors.append(f"{where}: {field} is a string")
        if text.count("\n") > SKILL_BODY_LINES:
            warnings.append(f"{where} is over {SKILL_BODY_LINES} lines; the specification recommends moving detail "
                            "to references/ so the activated skill stays small")
        for field in sorted(set(fm) - SKILL_FIELDS):
            outside.setdefault(field, []).append(child.name)
    for field, names in sorted(outside.items()):
        warnings.append(f"{name}: frontmatter field {field!r} is outside the Agent Skills specification and a portable "
                        f"client ignores it ({len(names)} skills: {', '.join(names)})")
    return errors, warnings


LOOPBACK = re.compile(r"^(localhost|127(?:\.\d{1,3}){3}|\[::1\]|0:0:0:0:0:0:0:1)$", re.I)


def server_findings(label: str, server: dict[str, Any]) -> list[str]:
    """The specification's rules beyond the schema for one mcp.json entry."""
    from urllib.parse import urlsplit
    out = []
    kind = server.get("type")
    if kind == "stdio":
        command = server.get("command", "")
        if any(ch.isspace() for ch in command):
            out.append(f"{label}: command {command!r} is not a single executable token")
        elif command.startswith("./"):
            if "/../" in command or command.endswith("/..") or command.startswith("./../"):
                out.append(f"{label}: command {command!r} escapes the plugin root")
        elif "/" in command or "\\" in command or command.startswith("."):
            out.append(f"{label}: command {command!r} is neither a bare executable name nor a ./ plugin-relative path")
        if CLAUDE_ROOT in json.dumps(server):
            out.append(f"{label}: uses {CLAUDE_ROOT}, which a portable client leaves literal; the portable placeholder is {PLACEHOLDER_ROOT}")
        cwd = server.get("cwd")
        if cwd is not None and not (cwd.startswith("./") or cwd == PLACEHOLDER_ROOT or cwd.startswith(PLACEHOLDER_ROOT + "/")
                                    or cwd == PLACEHOLDER_DATA or cwd.startswith(PLACEHOLDER_DATA + "/")):
            out.append(f"{label}: cwd {cwd!r} is not ./, ${{PLUGIN_ROOT}} or ${{PLUGIN_DATA}} rooted")
        for key in (server.get("env") or {}):
            if key in {"PLUGIN_ROOT", "PLUGIN_DATA"}:
                out.append(f"{label}: env may not set the reserved {key}")
    elif kind in {"streamable-http", "sse"}:
        url = server.get("url", "")
        parts = urlsplit(url)
        if parts.scheme not in {"http", "https"} or not parts.netloc:
            out.append(f"{label}: url {url!r} is not an absolute http or https URL")
        else:
            if parts.username is not None or parts.password is not None:
                out.append(f"{label}: url carries user information")
            if parts.fragment:
                out.append(f"{label}: url carries a fragment")
            if parts.scheme == "http" and not LOOPBACK.match(parts.hostname or ""):
                out.append(f"{label}: a non-loopback endpoint uses https, not http")
        headers = server.get("headers") or {}
        seen: dict[str, str] = {}
        for h in headers:
            low = h.lower()
            if low in seen:
                out.append(f"{label}: header {h!r} repeats {seen[low]!r} under different casing")
            seen[low] = h
    return out


def plugin_check(repo_dir: Path) -> tuple[list[str], list[str]]:
    """Agent Plugins conformance of the portable package at repo_dir, and
    its agreement with the canonical package file."""
    errors: list[str] = []
    warnings: list[str] = []
    name = repo_dir.name
    pkg = read_package(repo_dir)
    repo_meta = read_repository(repo_dir)
    if pkg is None:
        return [f"{name}: no .osp/package.yaml; only a package has a portable projection"], warnings
    if repo_meta is None:
        return [f"{name}: no .osp/repository.yaml"], warnings
    manifest_path = repo_dir / PORTABLE_MANIFEST
    if not manifest_path.is_file():
        return [f"{name}: {PORTABLE_MANIFEST} is missing; run osp.py render"], warnings
    manifest = read_json(manifest_path)
    errors += [f"{name} {PORTABLE_MANIFEST} {e}" for e in schema_errors(manifest, AGENT_PLUGINS_SCHEMAS / "plugin.schema.json")]
    if isinstance(manifest, dict):
        if manifest.get("$schema") != PLUGIN_SCHEMA_ID:
            errors.append(f"{name} {PORTABLE_MANIFEST}: $schema is not the pinned {PLUGIN_SCHEMA_ID}")
        if manifest.get("name") != pkg["package"]["name"]:
            errors.append(f"{name} {PORTABLE_MANIFEST}: name {manifest.get('name')!r} is not the package name")
        if manifest.get("version") != pkg["package"]["version"]:
            errors.append(f"{name} {PORTABLE_MANIFEST}: version {manifest.get('version')!r} is not the package version")
        expected = render_portable_manifest(pkg, repo_meta, pkg["package"]["name"])
        if manifest != expected:
            errors.append(f"{name} {PORTABLE_MANIFEST}: differs from what package.yaml renders; run osp.py render")
    mcp_path = repo_dir / PORTABLE_MCP
    if mcp_path.exists():
        if not mcp_path.is_file():
            errors.append(f"{name}: {PORTABLE_MCP} is not a regular file")
        else:
            mcp = read_json(mcp_path)
            errors += [f"{name} {PORTABLE_MCP} {e}" for e in schema_errors(mcp, AGENT_PLUGINS_SCHEMAS / "mcp.schema.json")]
            if isinstance(mcp, dict):
                if mcp.get("$schema") != MCP_SCHEMA_ID:
                    errors.append(f"{name} {PORTABLE_MCP}: $schema is not the pinned {MCP_SCHEMA_ID}")
                for label, server in (mcp.get("mcpServers") or {}).items():
                    if isinstance(server, dict):
                        errors += [f"{name} {PORTABLE_MCP} {f}" for f in server_findings(label, server)]
                if mcp != render_portable_mcp(pkg):
                    errors.append(f"{name} {PORTABLE_MCP}: differs from what package.yaml renders; run osp.py render")
    elif render_portable_mcp(pkg) is not None:
        errors.append(f"{name}: package.yaml declares a portable connector but {PORTABLE_MCP} is missing; run osp.py render")
    # The declared connector itself is checked in its canonical form too, so a
    # non-portable entry is caught even before it is rendered.
    for label, server in reach_servers(pkg).items():
        if server.get("portable", True):
            errors += [f"{name} package.yaml reach.servers.{label}: {f.split(': ', 1)[1]}" for f in server_findings(label, server)]
    skills_rel = (pkg.get("content") or {}).get("skills", "./skills")
    s_err, s_warn = skill_findings(repo_dir / skills_rel, name)
    errors += s_err
    warnings += s_warn
    if skills_rel not in {"./skills", "skills"} and (repo_dir / skills_rel).is_dir():
        errors.append(f"{name}: skills live at {skills_rel}, but a portable client discovers only skills/")
    return errors, warnings


def package_dirs(args: argparse.Namespace) -> list[Path]:
    dirs = [d for d in resolve_dirs(args) if (d / ".osp" / "package.yaml").is_file()]
    if not dirs:
        raise OspError("no repository carries .osp/package.yaml")
    return dirs


def command_render(args: argparse.Namespace) -> int:
    drift_total = 0
    for repo_dir in package_dirs(args):
        # A write renders the projections from the package file; that the
        # old ones disagree with it is the reason to render, not an error.
        errors, _ = validate_repo(repo_dir, None, projections_agree=bool(args.check))
        if errors:
            raise OspError("cannot render from invalid metadata:\n" + "\n".join(errors))
        expected = projections(repo_dir) or {}
        if args.check:
            drift = projection_drift(repo_dir, expected)
            for d in drift:
                print(f"drift: {repo_dir.name}: {d}")
            drift_total += len(drift)
            print(f"{repo_dir.name}: {'DRIFT' if drift else 'projections current'}")
        else:
            for line in write_projections(repo_dir, expected):
                print(f"{repo_dir.name}: {line}")
            print(f"{repo_dir.name}: projections rendered")
    if args.check:
        print(f"osp render --check: {'FAILED' if drift_total else 'PASSED'} ({drift_total} drifted files)")
        return 1 if drift_total else 0
    return 0


def command_lock(args: argparse.Namespace) -> int:
    stale = 0
    for repo_dir in package_dirs(args):
        lock = render_lock(repo_dir)
        path = repo_dir / RELEASE_LOCK
        if args.check or args.report:
            current = read_json(path) if path.is_file() else None
            if current == lock:
                print(f"{repo_dir.name}: release lock current")
                continue
            stale += 1
            if current is None:
                print(f"{repo_dir.name}: no release lock; run osp.py lock")
            else:
                changed = sorted(k for k in set(current) | set(lock) if current.get(k) != lock.get(k))
                print(f"{repo_dir.name}: release lock stale ({', '.join(changed)})")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(dump_json(lock), encoding="utf-8")
            print(f"{repo_dir.name}: wrote {RELEASE_LOCK}")
    if args.check:
        print(f"osp lock --check: {'FAILED' if stale else 'PASSED'} ({stale} stale)")
        return 1 if stale else 0
    if args.report and stale:
        print(f"osp lock --report: {stale} stale (a release commit re-runs osp.py lock)")
    return 0


def command_plugin_check(args: argparse.Namespace) -> int:
    total = 0
    for repo_dir in package_dirs(args):
        errors, warnings = plugin_check(repo_dir)
        for w in warnings:
            print(f"warning: {w}")
        for e in errors:
            print(f"error: {e}")
        total += len(errors)
        print(f"{repo_dir.name}: {'FAILED' if errors else 'conforms to Agent Plugins ' + AGENT_PLUGINS_VERSION}")
    print(f"osp plugin-check: {'FAILED' if total else 'PASSED'} (Agent Plugins {AGENT_PLUGINS_VERSION}, {total} errors)")
    return 1 if total else 0


# ---------------------------------------------------------------------------
# Where the files go (ADR E, a computation is a skill): what a steward
# signs is under knowledge/, what an agent runs is under skills/<name>/
# with its scripts beside it, what proves a script is under verification/,
# and what reaches a service is under connectors/. Two findings of
# `validate` measure that one sentence, in both the standalone and the
# workspace mode: runnable code filed as knowledge, and an attested
# computation whose code is not in the package beside a golden that names
# it. Neither finding runs a computation or a golden; both read paths,
# names and frontmatter. They are warnings until MIGRATION_ERRORS_FROM
# and errors after, because the capabilities and the bundle are migrated
# after this lands and their gates stay green meanwhile.
# ---------------------------------------------------------------------------

MIGRATION_ERRORS_FROM = "2026-10-15"   # ADR E: warnings while the migrations run, errors after
COMPUTATION_TYPE = "Attested Computation"
RUNNABLE_SUFFIXES = {".py", ".sh", ".ipynb"}
COMPUTATION_KEYS = (("computation",), ("executor", "resource"), ("attester", "resource"))
SKIP_DIRS = {".git", "__pycache__", "node_modules", "dist"}


def _dig(data: dict[str, Any], keys: tuple[str, ...]) -> Any:
    """The value of a dotted frontmatter key, or None."""
    for key in keys:
        if not isinstance(data, dict):
            return None
        data = data.get(key)
    return data


def runnable_under_knowledge(repo_dir: Path) -> list[Path]:
    """Every file under knowledge/ that is code: a .py, .sh or .ipynb, or
    any file carrying the executable bit."""
    know = repo_dir / "knowledge"
    if not know.is_dir():
        return []
    out = []
    for path in sorted(know.rglob("*")):
        if not path.is_file() or any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.suffix in RUNNABLE_SUFFIXES or (path.stat().st_mode & 0o111):
            out.append(path)
    return out


def computation_concepts(repo_dir: Path) -> list[tuple[Path, dict[str, Any]]]:
    """Every concept under knowledge/ whose frontmatter is an Attested
    Computation, with that frontmatter."""
    know = repo_dir / "knowledge"
    if not know.is_dir():
        return []
    out = []
    for path in sorted(know.rglob("*.md")):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        try:
            fm = parse_frontmatter(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError):
            continue
        if isinstance(fm, dict) and fm.get("type") == COMPUTATION_TYPE:
            out.append((path, fm))
    return out


def resolve_concept_path(repo_dir: Path, concept: Path, value: Any) -> Path | None:
    """A path a computation concept names, resolved the way a reader
    resolves it: against the package root, against the concept's own
    bundle root (the directory holding its category), or beside the
    concept. None when no file is there."""
    text = str(value).strip()
    if not text or text.startswith(("http://", "https://")):
        return None
    for base in (repo_dir, concept.parent.parent, concept.parent):
        candidate = (base / text).resolve()
        if candidate.is_file():
            return candidate
    return None


def golden_texts(repo_dir: Path) -> dict[Path, str]:
    """The files directly under verification/: the goldens that prove the
    scripts a computation names."""
    ver = repo_dir / "verification"
    out: dict[Path, str] = {}
    for path in sorted(ver.iterdir()) if ver.is_dir() else []:
        if not path.is_file():
            continue
        try:
            out[path] = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
    return out


def code_placement_findings(repo_dir: Path, name: str) -> list[str]:
    """The two findings, one line each, naming the file and the rule."""
    def rel(path: Path) -> str:
        try:
            return path.resolve().relative_to(repo_dir.resolve()).as_posix()
        except ValueError:
            return path.as_posix()

    out = [f"{name}: {rel(path)} is runnable code under knowledge/; a knowledge bundle holds no code, "
           "and what an agent runs lives under skills/<name>/scripts/"
           for path in runnable_under_knowledge(repo_dir)]
    goldens = golden_texts(repo_dir)
    know = (repo_dir / "knowledge").resolve()
    for concept, fm in computation_concepts(repo_dir):
        if _dig(fm, ("executor", "skill")) is not None:
            out.append(f"{name}: {rel(concept)} carries executor.skill, a key retired with the wrap it named; "
                       "the concept names its files and the skill that runs them is beside them")
        for keys in COMPUTATION_KEYS:
            value = _dig(fm, keys)
            if value is None:
                continue
            key = ".".join(keys)
            target = resolve_concept_path(repo_dir, concept, value)
            if target is None or not target.is_relative_to(repo_dir.resolve()) or target.is_relative_to(know):
                out.append(f"{name}: {rel(concept)} names {key} {str(value)!r}, which is no file of this package "
                           "outside knowledge/; the code of a computation lives in the skill that runs it")
                continue
            named = rel(target)
            if not any(named in text or target.name in text for text in goldens.values()):
                out.append(f"{name}: {rel(concept)} names {key} {named}, which no file directly under "
                           "verification/ mentions; a golden proves every script a computation names")
    return out


# ---------------------------------------------------------------------------
# Re-attestation (ADR E): the ritual an edited computation owes, run in
# the capability that holds it. Every receipt carries the sha256 of the
# file that produced it and the attester hashes that file before it reads
# a number, so any edit to a computation invalidates every earlier
# receipt by construction. The ritual proves that in order:
#
#   1. NEW PASS      a fresh run of the working-tree file, with the
#                    reference arguments, attests PASS;
#   2. OLD PASS      the previous version of the file (HEAD, or --old
#                    REF) is run on the same data and attests PASS
#                    against itself: the edit did not start from a
#                    broken file;
#   3. OLD vs NEW    the previous version's receipt attests FAIL against
#                    the new file, on code_sha256;
#   4. TAMPER FAIL   the fresh receipt attests FAIL against a one-byte
#                    tamper of the new file.
#
# Steps 2 and 3 are skipped, and said to be skipped, when the working
# tree matches the reference version (a re-verification, not a
# re-attestation). The reference arguments come from the package's
# verification/reference_runs.yaml by run name, with every path in it
# relative to the package root: an executor and an attester under
# skills/<name>/scripts/, a data root under knowledge/references/retrieval.
# The attester is read from the concept whose frontmatter names the
# computation unless --attester says otherwise. The receipts, the old
# file and the tampered file are kept under --keep so they can be cited;
# the printed log entry is a draft, and the tool writes nothing into the
# package.
# ---------------------------------------------------------------------------

REFERENCE_RUNS = Path("verification") / "reference_runs.yaml"


def package_paths(package: Path) -> tuple[Path, Path]:
    """(the package root, the repository that holds it). The ritual runs
    a computation in its own package so that its relative paths resolve,
    and reads the previous version of a file from the repository that
    holds the package, which is derived rather than assumed."""
    package = package.resolve()
    if not package.is_dir():
        raise OspError(f"no such package directory: {package}")
    try:
        top = subprocess.run(["git", "-C", str(package), "rev-parse", "--show-toplevel"],
                             capture_output=True, text=True, check=True).stdout.strip()
        repo = Path(top)
    except (subprocess.CalledProcessError, FileNotFoundError):
        repo = package
    return package, repo


def file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_reference_runs(package: Path) -> dict[str, Any]:
    path = package / REFERENCE_RUNS
    if not path.is_file():
        raise OspError(f"{package.name}: no {REFERENCE_RUNS.as_posix()}; a capability keeps its reference runs there")
    reg = load_yaml(path) or {}
    reg.setdefault("data_roots", {})
    reg.setdefault("runs", {})
    return reg


def run_computation(package: Path, spec: dict[str, Any]) -> Path:
    """The executor a run names, relative to the package root. A bare
    file name is looked up under skills/*/scripts/, where an executor
    lives."""
    value = str(spec["computation"])
    candidate = package / value
    if candidate.is_file():
        return candidate.resolve()
    if "/" not in value:
        hits = sorted(package.glob(f"skills/*/scripts/{value}"))
        if len(hits) == 1:
            return hits[0].resolve()
    return candidate


def attester_for(computation: Path, package: Path) -> Path | None:
    """The attester the concept names for this computation; None when no
    concept in the package names it."""
    target = computation.resolve()
    for concept, fm in computation_concepts(package):
        named = resolve_concept_path(package, concept, _dig(fm, ("computation",)) or "")
        if named != target:
            continue
        attester = _dig(fm, ("attester", "resource"))
        if attester:
            return resolve_concept_path(package, concept, attester)
    return None


def run_cmd(argv: list[Any], cwd: Path) -> tuple[int, str]:
    """Run argv, return (returncode, combined output)."""
    p = subprocess.run([str(a) for a in argv], cwd=str(cwd), capture_output=True, text=True)
    return p.returncode, (p.stdout + p.stderr).strip()


def tamper(src: Path, dst: Path) -> None:
    """A one-byte edit that leaves the file runnable: one more newline at
    the end. The receipt's hash no longer matches, which is the point."""
    dst.write_bytes(src.read_bytes() + b"\n")


def old_version(path: Path, ref: str, repo: Path, dst: Path) -> Path | None:
    """The file as of REF, written to dst; None when git has no such
    version."""
    try:
        rel = path.resolve().relative_to(repo.resolve()).as_posix()
    except ValueError:
        return None
    rc, out = run_cmd(["git", "show", f"{ref}:{rel}"], repo)
    if rc != 0:
        return None
    dst.write_text(out + "\n", encoding="utf-8")
    return dst


def receipt_summary(path: Path) -> dict[str, Any]:
    try:
        r = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    data = r.get("data") if isinstance(r.get("data"), dict) else {}
    record = data.get("record") if isinstance(data.get("record"), dict) else {}
    return {"run_id": r.get("run_id"), "code_sha256": r.get("code_sha256"),
            "record": record.get("record")}


class Ritual:
    """The four steps, each recorded as (name, required, got, detail)."""

    def __init__(self, computation: Path, attester: Path, args, keep: Path,
                 package: Path, repo: Path | None = None, runner=None):
        self.computation, self.attester, self.args = computation, attester, list(args)
        self.keep, self.package = keep, package
        self.repo = repo or package
        self.run = runner or run_cmd
        self.steps: list[tuple[str, str, str, str]] = []
        self.new_receipt = keep / "receipt_new.json"
        self.old_receipt = keep / "receipt_old.json"
        self.old_file = keep / ("old_" + computation.name)
        self.tampered = keep / ("tampered_" + computation.name)
        self.skipped: list[str] = []

    def compute(self, script: Path, receipt: Path):
        return self.run(["uv", "run", script, *self.args, "--receipt", receipt], self.package)

    def attest(self, receipt: Path, against: Path):
        return self.run(["uv", "run", self.attester, receipt, "--computation", against], self.package)

    def record(self, name: str, required: str, rc: int, out: str) -> bool:
        got = "PASS" if rc == 0 else "FAIL"
        self.steps.append((name, required, got, out.splitlines()[-1] if out else ""))
        return got == required

    def perform(self, old_ref: str) -> bool:
        ok = True
        rc, out = self.compute(self.computation, self.new_receipt)
        if rc != 0:
            self.steps.append(("NEW RUN", "PASS", "FAIL", out[-400:]))
            return False
        rc, out = self.attest(self.new_receipt, self.computation)
        ok &= self.record("NEW PASS", "PASS", rc, out)

        old = old_version(self.computation, old_ref, self.repo, self.old_file)
        if old is None:
            self.skipped.append(f"no version of the file at {old_ref}; OLD steps skipped")
        elif file_digest(old) == file_digest(self.computation):
            self.skipped.append(f"working tree matches {old_ref} (sha256 "
                                f"{file_digest(old)[:12]}); a re-verification, OLD steps skipped")
        else:
            rc, out = self.compute(old, self.old_receipt)
            if rc != 0:
                self.steps.append(("OLD RUN", "PASS", "FAIL", out[-400:]))
                ok = False
            else:
                rc, out = self.attest(self.old_receipt, old)
                ok &= self.record("OLD PASS", "PASS", rc, out)
                rc, out = self.attest(self.old_receipt, self.computation)
                ok &= self.record("OLD vs NEW", "FAIL", rc, out)

        tamper(self.computation, self.tampered)
        rc, out = self.attest(self.new_receipt, self.tampered)
        ok &= self.record("TAMPER FAIL", "FAIL", rc, out)
        return ok

    def report(self, note: str, rel: str) -> str:
        lines = []
        for name, required, got, detail in self.steps:
            mark = "ok " if got == required else "BAD"
            lines.append(f"  {mark} {name:<12} required {required}, got {got}: {detail[:100]}")
        for s in self.skipped:
            lines.append(f"  --  {s}")
        new = receipt_summary(self.new_receipt)
        old = receipt_summary(self.old_receipt) if self.old_receipt.exists() else {}
        lines.append(f"  new sha256 {file_digest(self.computation)}")
        if self.old_file.exists():
            lines.append(f"  old sha256 {file_digest(self.old_file)}")
        lines.append(f"  receipts under {self.keep}")
        return "\n".join(lines) + "\n\n" + self.log_entry(note, rel, new, old)

    def log_entry(self, note: str, rel: str, new: dict, old: dict) -> str:
        day = dt.date.today().isoformat()
        new_sha = file_digest(self.computation)[:12]
        old_sha = old.get("code_sha256", "")[:12] if old else None
        shas = f"(sha256 {old_sha} -> {new_sha})" if old_sha else f"(sha256 {new_sha}, unchanged)"
        head = "RE-ATTESTATION" if old_sha else "RE-VERIFICATION"
        args = " ".join(str(a) for a in self.args)
        where = f"on the verified tree {new['record']}" if new.get("record") else "on the data given"
        evidence = [f"a fresh run ({args}) attests PASS, run {new.get('run_id')}"]
        if old_sha:
            evidence.insert(0, "a receipt from the previous file FAILS against the new one on code_sha256, "
                               "as the contract requires")
            evidence.insert(0, f"the previous file attests PASS against itself, run {old.get('run_id')}")
        evidence.append("a one-byte tamper of the new file FAILS")
        body = (f"{day} · {head} of {rel} {shas}: {note or '<why the file changed, and what did not>'} "
                f"Evidence, {where}: " + "; ".join(evidence) + ". (<who>)")
        # break_on_hyphens=False keeps a path in one piece: a path broken
        # across lines at one of its hyphens is no longer a path.
        return textwrap.fill(body, width=72, initial_indent="- ", subsequent_indent="  ",
                             break_on_hyphens=False, break_long_words=False)


def data_root_path(package: Path, value: Any) -> Path:
    """A data root of the registry: a path relative to the package root
    (knowledge/references/retrieval/<name>), or an absolute path."""
    raw = os.path.expanduser(str(value))
    root = Path(raw)
    return root if root.is_absolute() else package / root


def reference_run_args(package: Path, spec: dict[str, Any], reg: dict[str, Any],
                       receipts: dict[str, Path], data_root_override: Path | None) -> list[Any]:
    """A registry run's argv, with {receipt:NAME} filled in and the data
    root appended unless the run reads none."""
    args: list[Any] = []
    for a in spec.get("args", []):
        m = re.fullmatch(r"\{receipt:([^}]+)\}", str(a))
        args.append(receipts[m.group(1)] if m else a)
    root_key = spec.get("data_root", "fixtures")
    if root_key != "none":
        if root_key not in reg["data_roots"]:
            raise OspError(f"unknown data root {root_key!r}; verification/reference_runs.yaml declares "
                           f"{', '.join(sorted(reg['data_roots'])) or 'none'}")
        args += ["--data-root", data_root_override or data_root_path(package, reg["data_roots"][root_key])]
    return args


def reattest_selftest() -> int:
    """An offline ritual on stub scripts in a stub capability: the
    executor writes a receipt carrying its own sha256, the attester
    checks it, and the registry of the stub package resolves."""
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        subprocess.run(["git", "init", "-q", str(root)], check=True)
        subprocess.run(["git", "-C", str(root), "config", "user.email", "t@example.org"], check=True)
        subprocess.run(["git", "-C", str(root), "config", "user.name", "T"], check=True)
        scripts = root / "skills" / "stub" / "scripts"
        scripts.mkdir(parents=True)
        (root / "knowledge" / "computations").mkdir(parents=True)
        (root / "verification").mkdir()
        comp = scripts / "stub.py"
        comp.write_text(
            "import hashlib, json, sys\n"
            "args = sys.argv[1:]\nout = args[args.index('--receipt') + 1]\n"
            "json.dump({'run_id': 'r-' + hashlib.sha256(__file__.encode()).hexdigest()[:6],\n"
            "           'code_sha256': hashlib.sha256(open(__file__, 'rb').read()).hexdigest(),\n"
            "           'data': {'record': {'record': 'stub-tree'}}, 'value': 1.0}, open(out, 'w'))\n",
            encoding="utf-8")
        att = scripts / "stub_check.py"
        att.write_text(
            "import hashlib, json, sys\n"
            "r = json.load(open(sys.argv[1]))\n"
            "want = hashlib.sha256(open(sys.argv[3], 'rb').read()).hexdigest()\n"
            "ok = r['code_sha256'] == want\nprint('PASS' if ok else 'FAIL: code_sha256')\n"
            "sys.exit(0 if ok else 1)\n", encoding="utf-8")
        (root / "knowledge" / "computations" / "stub.md").write_text(
            "---\ntype: Attested Computation\ncomputation: skills/stub/scripts/stub.py\n"
            "attester:\n  resource: skills/stub/scripts/stub_check.py\nstatus: draft\n---\nBody\n",
            encoding="utf-8")
        (root / "verification" / "stub_golden.py").write_text(
            "# runs skills/stub/scripts/stub.py and skills/stub/scripts/stub_check.py\n", encoding="utf-8")
        (root / REFERENCE_RUNS).write_text(
            "data_roots:\n  stub: knowledge/references/retrieval/stub-root\n"
            "runs:\n  stub:\n    computation: skills/stub/scripts/stub.py\n"
            "    data_root: none\n    args: [--x, \"1\"]\n", encoding="utf-8")
        assert attester_for(comp, root) == att
        assert attester_for(scripts / "other.py", root) is None
        assert code_placement_findings(root, "stub") == []
        subprocess.run(["git", "-C", str(root), "add", "-A"], check=True)
        subprocess.run(["git", "-C", str(root), "commit", "-q", "-m", "stub"], check=True)

        # Stubs run under plain python; the real ritual runs `uv run`.
        def runner(argv, cwd):
            argv = [str(a) for a in argv]
            if argv[:2] == ["uv", "run"]:
                argv = [sys.executable] + argv[2:]
            return run_cmd(argv, cwd)

        keep = root / "keep"; keep.mkdir()
        r = Ritual(comp, att, ["--x", "1"], keep, package=root, runner=runner)
        assert r.perform("HEAD") is True, r.steps
        assert [s[0] for s in r.steps] == ["NEW PASS", "TAMPER FAIL"], r.steps
        assert r.skipped and "re-verification" in r.skipped[0]
        text = r.report("", "skills/stub/scripts/stub.py")
        assert "RE-VERIFICATION" in text and "unchanged" in text and "stub-tree" in text

        comp.write_text(comp.read_text(encoding="utf-8") + "# edited\n", encoding="utf-8")
        keep2 = root / "keep2"; keep2.mkdir()
        r = Ritual(comp, att, [], keep2, package=root, runner=runner)
        assert r.perform("HEAD") is True, r.steps
        assert [s[0] for s in r.steps] == ["NEW PASS", "OLD PASS", "OLD vs NEW", "TAMPER FAIL"], r.steps
        assert not r.skipped
        text = r.report("A test edit.", "skills/stub/scripts/stub.py")
        assert "RE-ATTESTATION" in text and " -> " in text and "A test edit." in text
        assert "BAD" not in text

        # An attester that always passes must make the ritual fail: the
        # tamper and the old-versus-new steps are required to FAIL.
        att.write_text("import sys\nprint('PASS')\nsys.exit(0)\n", encoding="utf-8")
        keep3 = root / "keep3"; keep3.mkdir()
        r = Ritual(comp, att, [], keep3, package=root, runner=runner)
        assert r.perform("HEAD") is False
        bad = [s for s in r.steps if s[1] != s[2]]
        assert {s[0] for s in bad} == {"OLD vs NEW", "TAMPER FAIL"}, r.steps

        reg = load_reference_runs(root)
        for name, spec in reg["runs"].items():
            assert run_computation(root, spec).is_file(), name
            assert isinstance(spec.get("args"), list), name
            if spec.get("needs"):
                assert spec["needs"] in reg["runs"], name
            assert spec.get("data_root", "fixtures") in ("none", *reg["data_roots"]), name
            assert reference_run_args(root, spec, reg, {}, None) == ["--x", "1"], name
    print("osp reattest selftest: ok")
    return 0


def command_reattest(args: argparse.Namespace) -> int:
    if args.selftest:
        return reattest_selftest()
    package, repo = package_paths(Path(args.package))
    if args.list:
        reg = load_reference_runs(package)
        for name, spec in reg["runs"].items():
            print(f"{name:<32} {str(spec['computation']):<46} {' '.join(map(str, spec.get('args', [])))}")
        return 0
    keep = Path(args.keep) if args.keep else Path(tempfile.mkdtemp(prefix="reattest-"))
    keep.mkdir(parents=True, exist_ok=True)
    receipts: dict[str, Path] = {}
    if args.run:
        reg = load_reference_runs(package)
        if args.run not in reg["runs"]:
            raise OspError(f"unknown run {args.run}; --list shows them")
        order = []
        name = args.run
        while name:
            order.insert(0, name)
            name = reg["runs"][name].get("needs")
        # Runs this one needs are produced first, from the working tree,
        # and their receipts substituted; only the named run is attested.
        for dep in order[:-1]:
            spec = reg["runs"][dep]
            out = keep / f"receipt_{dep}.json"
            rc, text = run_cmd(["uv", "run", run_computation(package, spec),
                                *reference_run_args(package, spec, reg, receipts, args.data_root),
                                "--receipt", out], package)
            if rc != 0:
                print(f"needed run {dep} failed:\n{text[-600:]}")
                return 1
            receipts[dep] = out
            print(f"needed run {dep}: receipt {out}")
        spec = reg["runs"][args.run]
        computation = run_computation(package, spec)
        run_args = reference_run_args(package, spec, reg, receipts, args.data_root)
        attester = (Path(args.attester) if args.attester else
                    (package / spec["attester"] if spec.get("attester") else None))
    else:
        if not args.computation:
            raise OspError("give --run NAME or a COMPUTATION.py")
        computation = Path(args.computation)
        run_args = list(args.args)
        if args.data_root:
            run_args += ["--data-root", args.data_root]
        attester = Path(args.attester) if args.attester else None
    if not computation.is_file():
        raise OspError(f"no such computation: {computation}")
    attester = attester or attester_for(computation, package)
    if attester is None or not attester.is_file():
        raise OspError("no attester: no concept in this package names this computation; give --attester")

    def rel(path: Path) -> str:
        p = path.resolve()
        return p.relative_to(package).as_posix() if p.is_relative_to(package) else p.as_posix()

    print(f"re-attesting {rel(computation)} with {rel(attester)}")
    print(f"  package: {package}")
    print(f"  args: {' '.join(str(x) for x in run_args)}")
    ritual = Ritual(computation, attester, run_args, keep, package=package, repo=repo)
    ok = ritual.perform(args.old)
    print(ritual.report(args.note, rel(computation)))
    print()
    print("osp reattest: " + ("every step landed as the contract requires"
                             if ok else "FAILED, see the BAD lines above"))
    return 0 if ok else 1


# ---------------------------------------------------------------------------
# Receipt identity (ADR B): does a receipt (or an attestation) identify
# the capability release and the runtime that produced it, so that a
# result produced on one runtime can be shown to belong to one release
# and be verified under one attester?
#
#   capability: { name, version, release_lock }   release_lock is the
#                                                  sha256 of the package's
#                                                  .osp/release-lock.json as
#                                                  a value, or null where the
#                                                  tree carries none
#   runtime:    { name, version }                  version may be null
# ---------------------------------------------------------------------------


def package_identity(package: Path) -> dict[str, Any]:
    """name, version and lock digest of a package tree."""
    pkg = (load_yaml(package / ".osp" / "package.yaml") or {}).get("package") or {}
    lock_path = package / ".osp" / "release-lock.json"
    lock = json.loads(lock_path.read_text(encoding="utf-8")) if lock_path.is_file() else None
    version = pkg.get("version")
    return {"name": pkg.get("name"), "version": str(version) if version is not None else None,
            "release_lock": value_digest(lock) if lock is not None else None}


def identity_findings(doc: dict[str, Any], package: dict[str, Any] | None = None) -> list[str]:
    out = []
    cap = doc.get("capability")
    if not isinstance(cap, dict):
        out.append("capability block missing")
    else:
        for k in ("name", "version"):
            if not isinstance(cap.get(k), str) or not cap.get(k):
                out.append(f"capability.{k} missing")
        if "release_lock" not in cap:
            out.append("capability.release_lock missing (null where the tree carries no lock)")
        elif cap["release_lock"] is not None and not re.match(r"^sha256:[0-9a-f]{64}$", str(cap["release_lock"])):
            out.append("capability.release_lock is not a sha256 digest")
    rt = doc.get("runtime")
    if not isinstance(rt, dict) or not isinstance(rt.get("name"), str) or not rt.get("name"):
        out.append("runtime.name missing")
    if package and isinstance(cap, dict):
        for k in ("name", "version", "release_lock"):
            if cap.get(k) != package.get(k):
                out.append(f"capability.{k} {cap.get(k)!r} is not the package's {package.get(k)!r}")
    return out


def receipt_identity_selftest() -> int:
    good = {"capability": {"name": "core", "version": "0.5.1", "release_lock": "sha256:" + "0" * 64},
            "runtime": {"name": "openai-codex", "version": None}}
    assert identity_findings(good) == []
    assert "capability block missing" in identity_findings({"runtime": {"name": "x"}})
    assert any("release_lock missing" in f
               for f in identity_findings({"capability": {"name": "a", "version": "1"}, "runtime": {"name": "x"}}))
    assert any("runtime.name" in f for f in identity_findings({"capability": good["capability"]}))
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / ".osp").mkdir()
        (root / ".osp" / "package.yaml").write_text(
            "schema_version: 1\npackage:\n  name: core\n  version: 0.5.1\n  type: foundation\n")
        pkg = package_identity(root)
        assert pkg == {"name": "core", "version": "0.5.1", "release_lock": None}, pkg
        assert any("release_lock" in f for f in identity_findings(good, pkg))
        lock = {"package": "core", "version": "0.5.1"}
        (root / ".osp" / "release-lock.json").write_text(json.dumps(lock))
        pkg = package_identity(root)
        assert identity_findings(dict(good, capability=dict(good["capability"],
                                                            release_lock=value_digest(lock))), pkg) == []
    print("osp receipt-identity selftest: ok")
    return 0


def command_receipt_identity(args: argparse.Namespace) -> int:
    if args.selftest:
        return receipt_identity_selftest()
    if not args.receipt:
        raise OspError("a receipt path or --selftest")
    doc = json.loads(Path(args.receipt).read_text(encoding="utf-8"))
    package = package_identity(Path(args.package)) if args.package else None
    out = identity_findings(doc, package)
    cap, rt = doc.get("capability") or {}, doc.get("runtime") or {}
    if out:
        for f in out:
            print(f"  {f}")
        print(f"FAIL: {args.receipt} does not identify a capability release")
        return 1
    print(f"PASS: {args.receipt} is {cap.get('name')} {cap.get('version')} "
          f"(lock {cap.get('release_lock')}) on {rt.get('name')}")
    return 0


# ---------------------------------------------------------------------------
# Advertising and publishing (ADR B, decision 10; the design's release
# rule): a runtime is advertised as supported for a release only on a
# qualified record for that release; a release stays valid when a runtime
# is not qualified, that runtime is simply not advertised; publication
# emits only the projections a qualified runtime consumes, with the
# honest status beside them.
# ---------------------------------------------------------------------------

RUNTIME_TITLES = {"claude-code": "Claude Code", "claude-cowork": "Claude Cowork", "claude-science": "Claude Science",
                  "openai-codex": "OpenAI Codex", "gemini-cli": "Gemini CLI", "goose": "Goose"}
RUNTIME_PROJECTION = {"claude-code": "claude", "claude-cowork": "claude", "claude-science": "claude",
                      "openai-codex": "agent-plugins", "gemini-cli": "agent-plugins", "goose": "agent-plugins"}
RUNTIMES_START = "<!-- osp-runtimes:start -->"
RUNTIMES_END = "<!-- osp-runtimes:end -->"
PUBLISH_SKIP = {".git", ".github", "dist"}


def qualification_records(repo_dir: Path) -> dict[str, dict[str, Any]]:
    d = repo_dir / ".osp" / "qualification"
    if not d.is_dir():
        return {}
    return {p.stem: read_json(p) for p in sorted(d.glob("*.json"))}


def role_list(surface: dict[str, Any]) -> list[str]:
    role = surface.get("role")
    return list(role) if isinstance(role, list) else [role]


def advertisement(repo_dir: Path, release: bool = False) -> dict[str, Any] | None:
    """What this release may say per runtime, from surfaces.yaml and the
    qualification records: for each surface, the declared status, whether
    a qualified record exists for this exact version and lock, whether the
    surface was waived for this release, and the findings the gate acts
    on. With release=True (a release candidate) every required surface
    needs a decision for this version: a record, qualified or not, or a
    waiver; an unqualified surface with no waiver blocks the release.
    None for a repository without runtime surfaces."""
    pkg = read_package(repo_dir)
    surfaces_path = repo_dir / ".osp" / "surfaces.yaml"
    if pkg is None or not surfaces_path.is_file():
        return None
    surfaces = load_yaml(surfaces_path)
    version = str(pkg["package"]["version"])
    lock_path = repo_dir / ".osp" / "release-lock.json"
    lock_digest = value_digest(read_json(lock_path)) if lock_path.is_file() else None
    records = qualification_records(repo_dir)
    runtimes: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    warnings: list[str] = []
    name = pkg["package"]["name"]
    for runtime, surface in (surfaces.get("surfaces") or {}).items():
        roles = role_list(surface)
        rec = records.get(runtime)
        # A waiver is for a version, not a lock: the decision to release
        # without a surface is taken on the candidate and survives the
        # lock moving with the release commit itself.
        current = bool(rec) and str(rec.get("version")) == version and rec.get("release_lock") == lock_digest
        waiver = (rec or {}).get("waived") if rec and str(rec.get("version")) == version else None
        qualified = bool(rec and rec.get("qualified") and current)
        stale = bool(rec) and not current and not waiver
        development = "development" in roles
        status = surface.get("status")
        entry = {"title": RUNTIME_TITLES.get(runtime, runtime), "roles": roles, "required": bool(surface.get("required")),
                 "status": status, "qualified": qualified, "record_date": rec.get("date") if rec else None,
                 "record_source": rec.get("source") if rec else None, "stale_record": stale,
                 "blockers": list(rec.get("blockers") or []) if (rec and current) else [],
                 "waived": dict(waiver) if isinstance(waiver, dict) else None,
                 "projection": RUNTIME_PROJECTION.get(runtime, "claude"), "development": development}
        runtimes[runtime] = entry
        if status == "supported" and waiver:
            errors.append(f"{name}: {runtime} is waived for {version} and cannot be advertised as supported")
        if release and entry["required"] and not (current or waiver):
            errors.append(f"{name}: a release candidate needs a decision for {runtime} at {version}: a qualification "
                          f"record (qualify.py --surface {runtime}) or a waiver (qualify.py --surface {runtime} --waive)")
        elif release and entry["required"] and current and not qualified and not waiver:
            errors.append(f"{name}: {runtime} is not qualified for {version} ({'; '.join(entry['blockers']) or 'see the record'}) "
                          f"and not waived; fix and re-run, or waive it (qualify.py --surface {runtime} --waive)")
        if status == "supported" and not development and not qualified:
            errors.append(f"{name}: advertises {runtime} as supported without a qualified record for {version} "
                          f"(lock {lock_digest}); " + ("the record is stale" if stale else "no record") +
                          "; a runtime is advertised only on a qualified record, else its status is tested or planned")
        if qualified and status != "supported":
            warnings.append(f"{name}: {runtime} is qualified for {version} and may be advertised as supported "
                            f"(status is {status})")
        if stale:
            warnings.append(f"{name}: the {runtime} record is for {rec.get('version')} (lock {rec.get('release_lock')}), "
                            f"not this release; re-run the qualification")
    return {"capability": name, "version": version, "release_lock": lock_digest, "runtimes": runtimes,
            "errors": errors, "warnings": warnings}


def runtime_verdict(entry: dict[str, Any]) -> str:
    if entry["qualified"]:
        return "Qualified"
    if entry.get("waived"):
        return "Not qualified, waived for this release"
    if entry["development"] and entry["status"] == "supported":
        return "Supported (development environment)"
    if "future-runtime" in entry["roles"] or "compatibility" in entry["roles"]:
        return "Outside the required matrix"
    return "Not qualified"


def render_runtimes_block(adv: dict[str, Any]) -> str:
    """The honest runtime table for a README or release notes: one line per
    surface with its declared status and the qualification verdict for
    this release."""
    lines = [f"Runtime support for {adv['capability']} {adv['version']}"
             + (f" (release lock `{adv['release_lock'][:19]}`)" if adv["release_lock"] else "")
             + ", rendered by build-kit's `osp.py advertise` from `.osp/surfaces.yaml` and the qualification records; "
             "edit those, not this block.", "",
             "| Runtime | Role | Declared status | Qualification |", "|---|---|---|---|"]
    for runtime, e in adv["runtimes"].items():
        role = " and ".join(r.replace("-", " ") for r in e["roles"]) + (", required" if e["required"] else "")
        verdict = runtime_verdict(e)
        if e["qualified"]:
            verdict += f" on {e['record_date']}"
        elif e.get("waived"):
            verdict += f" ({e['waived'].get('reason', '')}; {e['waived'].get('by', '')}, {e['waived'].get('date', '')})"
        elif e["blockers"]:
            verdict += " (" + "; ".join(e["blockers"]) + ")"
        elif e["stale_record"]:
            verdict += " (record is for another release)"
        lines.append(f"| {e['title']} | {role} | {e['status']} | {verdict} |")
    lines += ["", "A runtime is advertised as supported only on a qualified record for this exact release; a release "
                  "stays valid when a runtime is not qualified, and that runtime is simply not advertised."]
    return "\n".join(lines) + "\n"


def splice_runtimes(text: str, block: str) -> str:
    if RUNTIMES_START not in text or RUNTIMES_END not in text:
        raise OspError(f"no {RUNTIMES_START} ... {RUNTIMES_END} markers to write between")
    head, rest = text.split(RUNTIMES_START, 1)
    _, tail = rest.split(RUNTIMES_END, 1)
    return f"{head}{RUNTIMES_START}\n{block.rstrip()}\n{RUNTIMES_END}{tail}"


def shipped_files(root: Path) -> list[Path]:
    """What the package ships: every file not excluded by its ignore files,
    outside the repository's own machinery (.git, .github, dist)."""
    rules = ignore_rules(root)
    out = []
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        rel = path.relative_to(root)
        if (rel.parts[0] in PUBLISH_SKIP or set(rel.parts[:-1]) & DIGEST_SKIP_DIRS or path.suffix in DIGEST_SKIP_SUFFIXES
                or path.name in DIGEST_SKIP_NAMES or ignored(path, False, rules)):
            continue
        out.append(path)
    return out


def command_advertise(args: argparse.Namespace) -> int:
    total = 0
    for repo_dir in package_dirs(args):
        adv = advertisement(repo_dir, release=args.release)
        if adv is None:
            print(f"{repo_dir.name}: no runtime surfaces (a knowledge package advertises no runtime)")
            continue
        for w in adv["warnings"]:
            print(f"warning: {w}")
        for e in adv["errors"]:
            print(f"error: {e}")
        total += len(adv["errors"])
        block = render_runtimes_block(adv)
        if args.into:
            target = repo_dir / args.into
            current = target.read_text(encoding="utf-8")
            expected = splice_runtimes(current, block)
            if args.check:
                if current != expected:
                    print(f"error: {repo_dir.name}: {args.into} runtime block is out of date; run osp.py advertise --into {args.into}")
                    total += 1
            elif current != expected:
                target.write_text(expected, encoding="utf-8")
                print(f"{repo_dir.name}: wrote the runtime block into {args.into}")
        elif not args.check:
            print(block)
        verdicts = ", ".join(f"{e['title']}: {runtime_verdict(e)}" for e in adv["runtimes"].values())
        print(f"{repo_dir.name} {adv['version']}: {verdicts}")
    if args.check:
        print(f"osp advertise --check: {'FAILED' if total else 'PASSED'} ({total} errors)")
        return 1 if total else 0
    return 1 if total else 0


def command_publish(args: argparse.Namespace) -> int:
    """Emit the release's projections under dist/: the Claude package as a
    zip (the Claude family always has its development environment), the
    Agent Plugins package as a directory only when a runtime that consumes
    it is qualified, and release.json with the honest status per runtime."""
    import shutil
    import zipfile
    repo_dir = Path(args.repo).resolve()
    pkg = read_package(repo_dir)
    if pkg is None:
        raise OspError(f"{repo_dir.name}: nothing to publish without .osp/package.yaml")
    errors, _ = validate_repo(repo_dir, None)
    errors += projection_drift(repo_dir, projections(repo_dir) or {})
    lock_path = repo_dir / RELEASE_LOCK
    if not lock_path.is_file() or read_json(lock_path) != render_lock(repo_dir):
        errors.append(f"{repo_dir.name}: the release lock is missing or stale; run osp.py lock")
    if (repo_dir / PORTABLE_MANIFEST).is_file():
        perrors, _ = plugin_check(repo_dir)
        errors += perrors
    adv = advertisement(repo_dir)
    if adv:
        errors += adv["errors"]
    if errors:
        for e in errors:
            print(f"error: {e}")
        raise OspError(f"{repo_dir.name}: not publishable; {len(errors)} errors")
    name, version = pkg["package"]["name"], str(pkg["package"]["version"])
    dist = Path(args.out).resolve() if args.out else repo_dir / "dist"
    if dist.exists():
        shutil.rmtree(dist)
    files = shipped_files(repo_dir)
    claude_dir = dist / "claude"
    claude_dir.mkdir(parents=True)
    zip_path = claude_dir / f"{name}-{version}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in files:
            rel = f.relative_to(repo_dir).as_posix()
            if rel in {PORTABLE_MANIFEST, PORTABLE_MCP}:
                continue   # the portable files are the other projection
            zf.write(f, f"{name}/{rel}")
    emitted = {"claude": str(zip_path.relative_to(dist))}
    runtimes = adv["runtimes"] if adv else {}
    portable_qualified = [r for r, e in runtimes.items() if e["projection"] == "agent-plugins" and e["qualified"]]
    if portable_qualified and (repo_dir / PORTABLE_MANIFEST).is_file():
        target = dist / "agent-plugin" / f"{name}-{version}"
        for f in files:
            rel = f.relative_to(repo_dir)
            if rel.parts[0] == ".claude-plugin" or rel.as_posix() == CLAUDE_MCP:
                continue   # the Claude files are the other projection
            dest = target / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, dest)
        emitted["agent-plugins"] = str(target.relative_to(dist))
        portable_note = f"emitted; qualified on {', '.join(portable_qualified)}"
    elif (repo_dir / PORTABLE_MANIFEST).is_file():
        portable_note = "conformant to Agent Plugins " + AGENT_PLUGINS_VERSION + " and not qualified on any runtime that consumes it; not emitted"
    else:
        portable_note = "no portable projection"
    release = {
        "capability": name, "version": version, "release_lock": adv["release_lock"] if adv else None,
        "agent_plugins_spec": AGENT_PLUGINS_VERSION,
        "runtimes": {r: {"status": e["status"], "qualification": runtime_verdict(e), "record_date": e["record_date"],
                         "blockers": e["blockers"]} for r, e in runtimes.items()},
        "projections": emitted, "agent_plugins_projection": portable_note,
        "files": len(files),
    }
    (dist / "release.json").write_text(dump_json(release), encoding="utf-8")
    if adv:
        (dist / "RUNTIMES.md").write_text(render_runtimes_block(adv), encoding="utf-8")
    print(f"{name} {version}: {len(files)} files; claude projection {emitted['claude']}; agent-plugins projection: {portable_note}")
    for r, e in runtimes.items():
        print(f"  {e['title']}: {runtime_verdict(e)}")
    print(f"wrote {dist / 'release.json'}")
    return 0


def command_validate(args: argparse.Namespace) -> int:
    dirs = resolve_dirs(args)
    if not dirs:
        raise OspError("no repository carries .osp/repository.yaml")
    total_errors = 0
    for repo_dir in dirs:
        errors, warnings = validate_repo(repo_dir, None if args.standalone else WORKSPACE)
        for w in warnings:
            print(f"warning: {w}")
        for e in errors:
            print(f"error: {e}")
        total_errors += len(errors)
        print(f"{repo_dir.name}: {'FAILED' if errors else 'ok'}")
    print(f"osp validate: {'FAILED' if total_errors else 'PASSED'} ({len(dirs)} repositories, {total_errors} errors)")
    return 1 if total_errors else 0


def command_topics(args: argparse.Namespace) -> int:
    if args.apply and args.confirm_org != ORG:
        raise OspError(f"--apply requires --confirm-org {ORG}")
    drift = 0
    for repo_dir in resolve_dirs(args):
        meta = read_repository(repo_dir)
        if meta is None:
            raise OspError(f"{repo_dir}: no .osp/repository.yaml")
        expected = topics_for(meta)
        name = repo_dir.name
        if not (args.check or args.apply):
            print(f"{name}: {' '.join(expected)}")
            continue
        live = live_topics(name)
        managed_live = {t for t in live if t == "osp" or t.startswith("osp-") or t in SPHERES}
        keep = live - managed_live
        if managed_live == set(expected):
            print(f"{name}: topics current")
            continue
        drift += 1
        missing = sorted(set(expected) - managed_live)
        extra = sorted(managed_live - set(expected))
        print(f"{name}: DRIFT missing={missing} extra={extra}")
        if args.apply:
            set_topics(name, expected, keep)
            print(f"{name}: topics set")
    if args.check and drift:
        print(f"osp topics: {drift} repositories drift")
        return 1
    return 0


def command_sphere_view(args: argparse.Namespace) -> int:
    dirs = workspace_repos(Path(args.workspace).resolve() if args.workspace else WORKSPACE)
    repos = []
    for repo_dir in dirs:
        meta = read_repository(repo_dir)
        errors, _ = validate_repo(repo_dir, None)
        if errors:
            raise OspError("cannot render from invalid metadata:\n" + "\n".join(errors))
        repos.append((repo_dir.name, meta))
    if args.into:
        target = Path(args.into).resolve()
        current = target.read_text(encoding="utf-8")
        expected = splice(current, render_profile_block(repos))
    else:
        target = Path(args.output).resolve() if args.output else SPHERE_VIEW
        expected = render_sphere_view(repos)
    if args.check:
        if not target.exists() or target.read_text(encoding="utf-8") != expected:
            print(f"{target.name} is out of date", file=sys.stderr)
            return 1
        print(f"{target.name} is current")
        return 0
    target.write_text(expected, encoding="utf-8")
    print(f"wrote {target}")
    return 0


def command_teams(args: argparse.Namespace) -> int:
    """The gh commands that create the declared teams: parents first, then
    children with the parent's id, then the interim member. Printed, never
    run: team creation is organization administration."""
    teams = registered_teams()
    member = args.member
    print("# Create the teams osp/teams.yaml declares (organization administration; run with gh logged in as an owner).")
    print("set -e")
    ordered = sorted(teams, key=lambda t: (teams[t].get("parent") is not None, t))
    for slug in ordered:
        meta = teams[slug]
        desc = meta.get("scope", "").replace('"', "'")
        parent = meta.get("parent")
        cmd = f'gh api -X POST orgs/{ORG}/teams -f name={slug} -f privacy=closed -f description="{desc}"'
        if parent:
            cmd += f" -F parent_team_id=$(gh api orgs/{ORG}/teams/{parent} --jq .id)"
        print(cmd)
    if member:
        print(f"# The interim member occupies every team until a handoff.")
        for slug in ordered:
            print(f"gh api -X PUT orgs/{ORG}/teams/{slug}/memberships/{member} -f role=maintainer")
    return 0


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="command", required=True)
    v = sub.add_parser("validate")
    v.add_argument("repos", nargs="*", help="repository directories (default: workspace siblings)")
    v.add_argument("--standalone", action="store_true", help="skip the marketplace catalog cross-check")
    t = sub.add_parser("topics")
    t.add_argument("repos", nargs="*")
    t.add_argument("--check", action="store_true", help="compare with the live repository topics")
    t.add_argument("--apply", action="store_true")
    t.add_argument("--confirm-org")
    s = sub.add_parser("sphere-view")
    s.add_argument("--check", action="store_true")
    s.add_argument("--workspace")
    s.add_argument("--output")
    s.add_argument("--into", help="write the view between osp-sphere-view markers in this file (the org profile)")
    r = sub.add_parser("render")
    r.add_argument("repos", nargs="*")
    r.add_argument("--check", action="store_true", help="fail on a projection that differs from what package.yaml renders")
    lk = sub.add_parser("lock")
    lk.add_argument("repos", nargs="*")
    lk.add_argument("--check", action="store_true", help="fail when the release lock is not what the tree digests to")
    lk.add_argument("--report", action="store_true", help="print a stale lock without failing")
    pc = sub.add_parser("plugin-check")
    pc.add_argument("repos", nargs="*")
    ra = sub.add_parser("reattest")
    ra.add_argument("computation", nargs="?", help="the executor to re-attest, when no --run names it")
    ra.add_argument("args", nargs="*", help="the executor's arguments, after --")
    ra.add_argument("--package", default=".", help="the package the computation lives in (default: here)")
    ra.add_argument("--run", help="a run name from the package's verification/reference_runs.yaml")
    ra.add_argument("--attester", help="the attester, when the concept names none")
    ra.add_argument("--data-root", help="override the registry's data root")
    ra.add_argument("--old", default="HEAD", help="the reference version, a git ref (default HEAD)")
    ra.add_argument("--note", default="", help="why the file changed, for the log entry draft")
    ra.add_argument("--keep", help="directory for the receipts and files (default: a new temporary one)")
    ra.add_argument("--list", action="store_true", help="list the package's reference runs")
    ra.add_argument("--selftest", action="store_true")
    ri = sub.add_parser("receipt-identity")
    ri.add_argument("receipt", nargs="?", help="the receipt or attestation to read")
    ri.add_argument("--package", help="package tree whose identity the receipt must match")
    ri.add_argument("--selftest", action="store_true")
    ad = sub.add_parser("advertise")
    ad.add_argument("repos", nargs="*")
    ad.add_argument("--check", action="store_true", help="fail on a support claim with no qualified record for this release, or a stale README block")
    ad.add_argument("--into", help="write the runtime block between osp-runtimes markers in this file of each repository (README.md)")
    ad.add_argument("--release", action="store_true", help="a release candidate: every required surface needs a record or a waiver for this version")
    pb = sub.add_parser("publish")
    pb.add_argument("repo", nargs="?", default=".")
    pb.add_argument("--out", help="the dist directory (default: <repo>/dist)")
    tm = sub.add_parser("teams")
    tm.add_argument("--member", default="PaulMRamirez", help="the interim member added to every team ('' for none)")
    return p


COMMANDS = {"validate": command_validate, "topics": command_topics, "sphere-view": command_sphere_view,
            "teams": command_teams, "render": command_render, "lock": command_lock,
            "plugin-check": command_plugin_check, "reattest": command_reattest,
            "receipt-identity": command_receipt_identity,
            "advertise": command_advertise, "publish": command_publish}


def main() -> int:
    args = parser().parse_args()
    try:
        return COMMANDS[args.command](args)
    except OspError as exc:
        print(f"osp: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
