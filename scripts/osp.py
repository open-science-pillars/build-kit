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
                    presentation metadata and REACH declarations
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
import hashlib
import json
import os
import re
import subprocess
import sys
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


def validate_repo(repo_dir: Path, workspace: Path | None = None) -> tuple[list[str], list[str]]:
    """(errors, warnings) for one repository's .osp/ directory."""
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
                if manifest is not None:
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
        ("Provider knowledge", {"provider"}),
        ("Composites", {"composite"}),
        ("Foundation and tooling", {"foundation", "tooling"}),
    ]
    for title, kinds in groups:
        rows = sorted(n for n, m in repos if m["repository"]["kind"] in kinds)
        lines += [f"## {title}", ""]
        if not rows:
            lines += ["None yet.", ""]
            continue
        lines += ["| Repository | Kind | Status | Spheres | Notes |", "|---|---|---|---|---|"]
        for n in rows:
            m = by_name[n]
            spheres = ", ".join(SPHERE_TITLES[s] for s in m["classification"]["spheres"]) or "all"
            notes = m["repository"].get("audience") or m["repository"].get("notes") or ""
            lines.append(f"| `{n}` | {m['repository']['kind']} | {m['repository']['status']} | {spheres} | {notes} |")
        lines.append("")
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
    for title, kinds in (("**Provider knowledge** (signed by its stewards; cuts across spheres)", {"provider"}),
                         ("**Composites** (cross-sphere)", {"composite"}),
                         ("**Foundation and tooling** (serve every sphere)", {"foundation", "tooling"})):
        rows = sorted(n for n, m in repos if m["repository"]["kind"] in kinds)
        lines.append(title)
        lines.append("")
        if not rows:
            lines += ["- none yet", ""]
            continue
        for n in rows:
            m = by_name[n]
            note = m["repository"].get("audience") or m["repository"].get("notes") or ""
            lines.append(f"- [{n}]({org_url}/{n}) *({m['repository']['status']})*: {note}")
        lines.append("")
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
    """One REACH declaration as Claude's .mcp.json spells it: `http` for
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
        errors.append(f"{name}: package.yaml declares portable REACH but {PORTABLE_MCP} is missing; run osp.py render")
    # The declared REACH itself is checked in its canonical form too, so a
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
        errors, _ = validate_repo(repo_dir, None)
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
    tm = sub.add_parser("teams")
    tm.add_argument("--member", default="PaulMRamirez", help="the interim member added to every team ('' for none)")
    return p


COMMANDS = {"validate": command_validate, "topics": command_topics, "sphere-view": command_sphere_view,
            "teams": command_teams, "render": command_render, "lock": command_lock,
            "plugin-check": command_plugin_check}


def main() -> int:
    args = parser().parse_args()
    try:
        return COMMANDS[args.command](args)
    except OspError as exc:
        print(f"osp: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
