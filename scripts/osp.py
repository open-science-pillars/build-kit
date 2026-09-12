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
  package.yaml      package identity, version, content, dependencies
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

Every GitHub mutation is dry-run unless both --apply and the exact
--confirm-org value are supplied. Exit 1 on any validation error or
drift; warnings never fail.
"""

from __future__ import annotations

import argparse
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
    "mcp.json", ".mcp.json", "skills", "CITATION.cff",
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
    tm = sub.add_parser("teams")
    tm.add_argument("--member", default="PaulMRamirez", help="the interim member added to every team ('' for none)")
    return p


COMMANDS = {"validate": command_validate, "topics": command_topics, "sphere-view": command_sphere_view,
            "teams": command_teams}


def main() -> int:
    args = parser().parse_args()
    try:
        return COMMANDS[args.command](args)
    except OspError as exc:
        print(f"osp: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
