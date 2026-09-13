#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml==6.0.2", "jsonschema==4.25.1"]
# ///
"""Validate, render, audit, and brief the OSP roadmap.

roadmap/roadmap.yaml is the single source of truth for organization work.
Each deliverable carries one status (proposed, active, blocked, done,
declined) and, once work has started, the number of the repository issue
that tracks it. The tool reads GitHub for the audit and writes to it only
through `labels`, which is dry-run unless both --apply and the exact
--confirm-org value are supplied. It never opens, edits, or closes issues.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator, FormatChecker


BUILD_KIT = Path(__file__).resolve().parents[1]
WORKSPACE = BUILD_KIT.parent
ROADMAP_FILE = BUILD_KIT / "roadmap" / "roadmap.yaml"
RENDERED_FILE = BUILD_KIT / "ROADMAP.md"
ORG_CONFIRM = "open-science-pillars"
ROADMAP_SCHEMA = BUILD_KIT / "roadmap" / "schema.json"
GOVERNANCE_SCHEMA = BUILD_KIT / "roadmap" / "governance-schema.json"

ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
STATUSES = {"proposed", "active", "blocked", "done", "declined"}
READINESS = {"good-first", "ready", "needs-context", "owner-only"}
PRIORITY_ORDER = {"P0": 0, "P1": 1, "P2": 2}
REUSED_LABELS = {
    "bug",
    "documentation",
    "duplicate",
    "enhancement",
    "good first issue",
    "help wanted",
    "invalid",
    "question",
    "wontfix",
}


class RoadmapError(RuntimeError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    try:
        data = yaml.safe_load(path.read_text())
    except FileNotFoundError as exc:
        raise RoadmapError(f"missing file: {path}") from exc
    except yaml.YAMLError as exc:
        raise RoadmapError(f"invalid YAML in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise RoadmapError(f"expected mapping at {path}")
    return data


def initiatives(data: dict[str, Any]):
    for initiative in data.get("initiatives", []):
        yield initiative


def deliverables(data: dict[str, Any]):
    for initiative in initiatives(data):
        for item in initiative.get("deliverables", []):
            yield initiative, item


def item_index(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for initiative in initiatives(data):
        result[initiative["id"]] = initiative
        for item in initiative.get("deliverables", []):
            result[item["id"]] = item
    return result


def issue_of(item: dict[str, Any]) -> dict[str, Any]:
    return item.get("issue") or {}


def governance_path(repo: str) -> Path:
    return WORKSPACE / repo / ".osp" / "governance.yaml"


def schema_errors(data: dict[str, Any], schema_path: Path) -> list[str]:
    schema = json.loads(schema_path.read_text())
    Draft202012Validator.check_schema(schema)
    normalized = json.loads(json.dumps(data, default=str))
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    result = []
    for error in sorted(validator.iter_errors(normalized), key=lambda item: list(item.absolute_path)):
        location = ".".join(str(x) for x in error.absolute_path) or "root"
        result.append(f"schema {location}: {error.message}")
    return result


def validate_data(data: dict[str, Any], check_files: bool = True) -> list[str]:
    errors: list[str] = schema_errors(data, ROADMAP_SCHEMA)
    if data.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    if data.get("organization") != ORG_CONFIRM:
        errors.append(f"organization must be {ORG_CONFIRM}")
    try:
        dt.date.fromisoformat(str(data.get("last_reviewed")))
    except ValueError:
        errors.append("last_reviewed must be an ISO date")

    repos = data.get("repositories")
    if not isinstance(repos, list) or not repos:
        errors.append("repositories must be a non-empty list")
        repos = []
    if len(repos) != len(set(repos)):
        errors.append("repositories contains duplicates")

    approved_labels = set(data.get("labels", {})) | REUSED_LABELS
    seen: dict[str, str] = {}
    nodes: dict[str, list[str]] = {}

    for decision in data.get("decisions", []):
        did = decision.get("id")
        if not isinstance(did, str) or not ID_RE.fullmatch(did):
            errors.append(f"invalid decision id: {did!r}")
        elif did in seen:
            errors.append(f"duplicate id: {did}")
        else:
            seen[did] = "decision"
        if decision.get("status") == "declined" and not decision.get("rationale"):
            errors.append(f"declined decision {did} requires rationale")

    for initiative in data.get("initiatives", []):
        iid = initiative.get("id")
        if not isinstance(iid, str) or not ID_RE.fullmatch(iid):
            errors.append(f"invalid initiative id: {iid!r}")
            continue
        if iid in seen:
            errors.append(f"duplicate id: {iid}")
        seen[iid] = "initiative"
        if initiative.get("status") not in STATUSES:
            errors.append(f"initiative {iid} has invalid status")
        nodes[iid] = list(initiative.get("depends_on", []))

        for item in initiative.get("deliverables", []):
            did = item.get("id")
            prefix = f"deliverable {did}"
            if not isinstance(did, str) or not ID_RE.fullmatch(did):
                errors.append(f"invalid deliverable id: {did!r}")
                continue
            if did in seen:
                errors.append(f"duplicate id: {did}")
            seen[did] = "deliverable"
            nodes[did] = list(item.get("depends_on", []))
            if item.get("repo") not in repos:
                errors.append(f"{prefix} names unknown repository {item.get('repo')!r}")
            status = item.get("status")
            if status not in STATUSES:
                errors.append(f"{prefix} has invalid status {status!r}")
            if status == "done" and not item.get("evidence"):
                errors.append(f"{prefix} is done without evidence")
            if status == "blocked" and not (item.get("gate") or item.get("depends_on")):
                errors.append(f"{prefix} is blocked without a gate or dependency")
            if status == "declined" and not item.get("gate"):
                errors.append(f"{prefix} is declined without a reason in gate")
            if not item.get("acceptance"):
                errors.append(f"{prefix} has no acceptance criteria")
            contributor = item.get("contributor", {})
            if contributor.get("readiness") not in READINESS:
                errors.append(f"{prefix} has invalid contributor readiness")
            labels = item.get("labels", [])
            unknown = sorted(set(labels) - approved_labels)
            if unknown:
                errors.append(f"{prefix} uses unregistered labels: {', '.join(unknown)}")
            issue = issue_of(item)
            if issue.get("number") and not issue.get("url"):
                errors.append(f"{prefix} has issue number without URL")
            if issue.get("url") and not issue.get("number"):
                errors.append(f"{prefix} has issue URL without number")

    all_ids = set(seen)
    for node, deps in nodes.items():
        for dep in deps:
            if dep not in all_ids:
                errors.append(f"{node} depends on unknown id {dep}")

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str, trail: list[str]):
        if node in visiting:
            errors.append("dependency cycle: " + " -> ".join(trail + [node]))
            return
        if node in visited:
            return
        visiting.add(node)
        for dep in nodes.get(node, []):
            if dep in nodes:
                visit(dep, trail + [node])
        visiting.remove(node)
        visited.add(node)

    for node in nodes:
        visit(node, [])

    if check_files:
        for repo in repos:
            path = governance_path(repo)
            try:
                gov = load_yaml(path)
            except RoadmapError as exc:
                errors.append(str(exc))
                continue
            errors.extend(f"{repo} {error}" for error in schema_errors(gov, GOVERNANCE_SCHEMA))
            if gov.get("schema_version") not in {1, 2}:
                errors.append(f"{repo} governance schema_version must be 1 or 2")
            if gov.get("repository") != repo:
                errors.append(f"{repo} governance declares {gov.get('repository')!r}")
            maintainers = gov.get("maintainers", {})
            if not (maintainers.get("users") or maintainers.get("teams")):
                errors.append(f"{repo} governance has no maintainers")
            roadmap = gov.get("roadmap", {})
            if roadmap.get("proposals") not in {"enabled", "disabled"}:
                errors.append(f"{repo} governance has invalid proposals policy")
            if roadmap.get("authority") != "repository-maintainers":
                errors.append(f"{repo} governance authority must be repository-maintainers")
    return errors


def priority_key(item: dict[str, Any]) -> tuple[int, str]:
    return (PRIORITY_ORDER.get(item.get("priority"), len(PRIORITY_ORDER)), item["id"])


def dependencies_done(item: dict[str, Any], index: dict[str, dict[str, Any]]) -> bool:
    return all(index[dep].get("status") == "done" for dep in item.get("depends_on", []) if dep in index)


def block_reason(item: dict[str, Any]) -> str:
    if item.get("gate"):
        return item["gate"]
    if item.get("depends_on"):
        return "depends on " + ", ".join(f"`{x}`" for x in item["depends_on"])
    return "no reason recorded"


def one_line(item: dict[str, Any], with_priority: bool = False) -> str:
    prefix = f"{item['priority']} " if with_priority else ""
    return f"- {prefix}`{item['id']}`: {item['title']} (`{item['repo']}`)"


def collapsed(summary: str, entries: list[str]) -> list[str]:
    if not entries:
        return []
    return ["<details>", f"<summary>{summary}</summary>", "", *entries, "", "</details>"]


def render_summary(data: dict[str, Any]) -> list[str]:
    index = item_index(data)
    items = [item for _, item in deliverables(data)]
    now = sorted((x for x in items if x["status"] == "active"), key=priority_key)
    blocked = sorted((x for x in items if x["status"] == "blocked"), key=priority_key)
    proposed = [x for x in items if x["status"] == "proposed"]
    next_up = sorted((x for x in proposed if dependencies_done(x, index)), key=priority_key)
    later = sorted((x for x in proposed if not dependencies_done(x, index)), key=priority_key)
    done = [x for x in items if x["status"] == "done"]
    declined = [x for x in items if x["status"] == "declined"]

    lines = ["## Summary", "", "### Now", ""]
    lines.extend([one_line(x) for x in now] or ["- Nothing is active."])
    lines.extend(["", "### Blocked", ""])
    lines.extend([f"{one_line(x)}: {block_reason(x)}" for x in blocked] or ["- Nothing is blocked."])
    lines.extend(["", "### Next", "", "Proposed, every dependency done, in priority order.", ""])
    lines.extend(
        [one_line(x, with_priority=True) + (f": gate: {x['gate']}" if x.get("gate") else "") for x in next_up]
        or ["- Nothing is ready to start."]
    )
    lines.extend(["", "### Later", "", "Proposed, waiting on a dependency, in priority order.", ""])
    lines.extend([one_line(x, with_priority=True) for x in later] or ["- Nothing is waiting."])
    lines.extend(["", f"### Done ({len(done)})", ""])
    lines.extend(collapsed(f"{len(done)} done deliverables", [f"- `{x['id']}`: {x['title']}" for x in done]) or ["- Nothing is done yet."])
    lines.extend(["", f"### Declined ({len(declined)})", ""])
    lines.extend(
        collapsed(
            f"{len(declined)} declined deliverables",
            [f"- `{x['id']}`: {x['title']}: {x.get('gate') or 'no reason recorded'}" for x in declined],
        )
        or ["- Nothing is declined."]
    )
    lines.append("")
    return lines


def render_markdown(data: dict[str, Any]) -> str:
    lines = [
        "# Open Science Pillars roadmap",
        "",
        "> Generated from `roadmap/roadmap.yaml`. Do not edit this file directly.",
        "> A deliverable is proposed, active, blocked, done, or declined; an active",
        "> deliverable has an issue in its repository, closed by the pull request that finishes it.",
        "",
        f"**Last reviewed:** {data['last_reviewed']}  ",
        f"**Organization:** `{data['organization']}`",
        "",
    ]
    lines.extend(render_summary(data))
    lines.extend(["## Decisions", ""])
    for decision in data.get("decisions", []):
        lines.append(
            f"- **{decision['title']}** (`{decision['id']}`): {decision['status']}. "
            f"{decision.get('rationale', '')}".rstrip()
        )
    lines.extend(["", "## Initiatives", ""])
    for initiative in initiatives(data):
        lines.extend(
            [
                f"### {initiative['title']}",
                "",
                f"**ID:** `{initiative['id']}`  ",
                f"**Status:** {initiative['status']}  ",
                f"**Priority:** {initiative['priority']}",
                "",
                initiative["outcome"],
                "",
            ]
        )
        if initiative.get("gate"):
            lines.extend([f"> **Gate:** {initiative['gate']}", ""])
        lines.extend(
            [
                "| Deliverable | Repository | Status | Priority | Contributor | Issue |",
                "|---|---|---|---|---|---|",
            ]
        )
        for item in initiative.get("deliverables", []):
            issue = issue_of(item)
            issue_text = f"[#{issue['number']}]({issue['url']})" if issue.get("number") else "none"
            lines.append(
                f"| `{item['id']}`: {item['title']} | `{item['repo']}` | "
                f"{item['status']} | {item['priority']} | "
                f"{item['contributor']['readiness']} | {issue_text} |"
            )
        lines.extend(["", "#### Acceptance details", ""])
        for item in initiative.get("deliverables", []):
            lines.extend([f"**`{item['id']}`**", ""])
            for criterion in item.get("acceptance", []):
                lines.append(f"- [ ] {criterion}")
            if item.get("depends_on"):
                lines.append("- Depends on: " + ", ".join(f"`{x}`" for x in item["depends_on"]))
            if item.get("gate"):
                lines.append(f"- Gate: {item['gate']}")
            if item.get("evidence"):
                lines.append("- Evidence: " + ", ".join(f"`{x}`" for x in item["evidence"]))
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def run_command(args: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(args, text=True, capture_output=True, check=check)
    except FileNotFoundError as exc:
        raise RoadmapError(f"required command not found: {args[0]}") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or str(exc)).strip()
        raise RoadmapError(f"command failed: {' '.join(args)}\n{detail}") from exc


def gh_json(endpoint: str) -> Any:
    result = run_command(["gh", "api", "--paginate", endpoint])
    chunks = result.stdout.strip().splitlines()
    if not chunks:
        return []
    parsed = [json.loads(line) for line in chunks]
    if len(parsed) == 1:
        return parsed[0]
    merged: list[Any] = []
    for value in parsed:
        if isinstance(value, list):
            merged.extend(value)
        else:
            merged.append(value)
    return merged


def repo_governance(repo: str) -> dict[str, Any]:
    return load_yaml(governance_path(repo))


def repo_issues(repo: str) -> list[dict[str, Any]]:
    value = gh_json(f"repos/{ORG_CONFIRM}/{repo}/issues?state=all&per_page=100")
    return [x for x in value if "pull_request" not in x]


def collect_audit(data: dict[str, Any], online: bool, check_files: bool = True) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []

    def add(level: str, code: str, message: str):
        findings.append({"level": level, "code": code, "message": message})

    errors = validate_data(data, check_files=check_files)
    for error in errors:
        add("error", "validation", error)

    expected = render_markdown(data)
    if not RENDERED_FILE.exists() or RENDERED_FILE.read_text() != expected:
        add("error", "render-drift", "ROADMAP.md does not match roadmap.yaml")

    reviewed = dt.date.fromisoformat(str(data["last_reviewed"]))
    if (dt.date.today() - reviewed).days > 30:
        add("warning", "stale-review", f"roadmap last reviewed {reviewed}")

    if check_files:
        bootstrap = (BUILD_KIT / "bootstrap.sh").read_text()
        for repo in data.get("repositories", []):
            if not re.search(rf"(?<![A-Za-z0-9_-]){re.escape(repo)}(?![A-Za-z0-9_-])", bootstrap):
                add("actionable", "bootstrap-missing", f"{repo} is absent from bootstrap.sh")
            codeowners = WORKSPACE / repo / "CODEOWNERS"
            if not codeowners.exists():
                add("actionable", "codeowners-missing", f"{repo} has no root CODEOWNERS")

    known_path = WORKSPACE / "marketplace" / "docs" / "known-limitations.md"
    if check_files and known_path.exists():
        known = known_path.read_text()
        if "fill-value and\n  GIA/V4R4B/crossover eval-case promotions" in known:
            add("actionable", "stale-limitations", "known limitations lists completed eval and recipe work as deferred")

    for _, item in deliverables(data):
        if item["status"] == "done" and not item.get("evidence"):
            add("error", "done-no-evidence", f"{item['id']} is done without evidence")
        if item["status"] == "active" and not issue_of(item).get("number"):
            add("warning", "no-issue", f"{item['id']} is active with no issue number recorded")
        if item["contributor"]["readiness"] in {"ready", "good-first"} and item["status"] in {"proposed", "active"}:
            if item["contributor"].get("champion") == "needed":
                add("warning", "champion-needed", f"{item['id']} is contributor-ready without a champion")

    if online:
        live_repos = gh_json(f"orgs/{ORG_CONFIRM}/repos?per_page=100&type=all")
        live_names = {r["name"] for r in live_repos if not r.get("archived")}
        declared = set(data.get("repositories", []))
        for name in sorted(live_names - declared):
            add("actionable", "new-repository", f"live repository {name} is not declared in roadmap")
        for name in sorted(declared - live_names):
            add("actionable", "missing-repository", f"declared repository {name} is absent or archived")

        by_repo: dict[str, list[dict[str, Any]]] = {}
        for _, item in deliverables(data):
            if issue_of(item).get("number"):
                by_repo.setdefault(item["repo"], []).append(item)
        for repo, items in by_repo.items():
            issues = {issue["number"]: issue for issue in repo_issues(repo)}
            for item in items:
                recorded = issue_of(item)
                number = recorded["number"]
                found = issues.get(number)
                if not found:
                    add("error", "issue-mismatch", f"{item['id']} records {repo}#{number}, which is not an issue in {repo}")
                    continue
                if found.get("html_url") and recorded.get("url") != found["html_url"]:
                    add("error", "issue-mismatch", f"{item['id']} records a URL that is not {repo}#{number}")
                if item["status"] in {"done", "declined"} and found.get("state") == "open":
                    add("actionable", "status-drift", f"{item['id']} is {item['status']} but {repo}#{number} is open; close the issue")
    return findings


def audit_markdown(findings: list[dict[str, str]]) -> str:
    counts: dict[str, int] = {}
    for finding in findings:
        counts[finding["level"]] = counts.get(finding["level"], 0) + 1
    lines = ["# OSP roadmap audit", "", f"Generated: {dt.datetime.now(dt.timezone.utc).isoformat()}", ""]
    lines.append(
        "Summary: " + ", ".join(f"{level}={counts.get(level, 0)}" for level in ["error", "actionable", "warning", "info"])
    )
    lines.append("")
    if not findings:
        lines.append("No findings.")
    for level in ["error", "actionable", "warning", "info"]:
        selected = [x for x in findings if x["level"] == level]
        if not selected:
            continue
        lines.extend([f"## {level.title()}", ""])
        for finding in selected:
            lines.append(f"- `{finding['code']}`: {finding['message']}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def require_apply(args: argparse.Namespace) -> None:
    if not args.apply:
        return
    if args.confirm_org != ORG_CONFIRM:
        raise RoadmapError(f"--apply requires --confirm-org {ORG_CONFIRM}")


def command_validate(args: argparse.Namespace) -> int:
    data = load_yaml(ROADMAP_FILE)
    errors = validate_data(data, check_files=not args.standalone)
    if errors:
        print("roadmap validation: FAILED")
        for error in errors:
            print(f"  - {error}")
        return 1
    print(f"roadmap validation: PASSED ({len(list(deliverables(data)))} deliverables)")
    return 0


def command_render(args: argparse.Namespace) -> int:
    data = load_yaml(ROADMAP_FILE)
    errors = validate_data(data, check_files=not args.standalone)
    if errors:
        raise RoadmapError("cannot render invalid roadmap:\n" + "\n".join(errors))
    expected = render_markdown(data)
    if args.check:
        if not RENDERED_FILE.exists() or RENDERED_FILE.read_text() != expected:
            print("ROADMAP.md is out of date", file=sys.stderr)
            return 1
        print("ROADMAP.md is current")
        return 0
    RENDERED_FILE.write_text(expected)
    print(f"wrote {RENDERED_FILE}")
    return 0


def command_audit(args: argparse.Namespace) -> int:
    data = load_yaml(ROADMAP_FILE)
    findings = collect_audit(data, online=not args.offline, check_files=not args.standalone)
    md = audit_markdown(findings)
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(md)
        output.with_suffix(".json").write_text(json.dumps(findings, indent=2) + "\n")
        print(f"wrote {output} and {output.with_suffix('.json')}")
    else:
        print(md, end="")
    return 1 if any(x["level"] in {"error", "actionable"} for x in findings) else 0


def command_brief(args: argparse.Namespace) -> int:
    data = load_yaml(ROADMAP_FILE)
    errors = validate_data(data)
    if errors:
        raise RoadmapError("invalid roadmap:\n" + "\n".join(errors))
    for initiative, item in deliverables(data):
        if item["id"] != args.id:
            continue
        index = item_index(data)
        incomplete = [dep for dep in item.get("depends_on", []) if index[dep].get("status") != "done"]
        startable = item["status"] == "proposed" and not incomplete and not item.get("gate")
        print(f"Deliverable: {item['title']} ({item['id']})")
        print(f"Initiative: {initiative['title']} ({initiative['id']})")
        print(f"Repository: {item['repo']}")
        print(f"Status: {item['status']}; priority: {item['priority']}")
        if item["status"] == "active":
            print("Startable: already active")
        else:
            print(f"Startable: {'yes' if startable else 'no'}")
        if incomplete:
            print("Incomplete dependencies: " + ", ".join(incomplete))
        if item.get("gate"):
            print("Gate: " + item["gate"])
        print("Acceptance:")
        for criterion in item["acceptance"]:
            print(f"  - {criterion}")
        if item.get("evidence"):
            print("Evidence:")
            for line in item["evidence"]:
                print(f"  - {line}")
        issue = issue_of(item)
        if issue.get("url"):
            print("Issue: " + issue["url"])
        else:
            print("Issue: none recorded; open one when work starts and record its number in roadmap.yaml")
        return 0
    raise RoadmapError(f"unknown deliverable id: {args.id}")


def current_labels(repo: str) -> set[str]:
    return {x["name"] for x in gh_json(f"repos/{ORG_CONFIRM}/{repo}/labels?per_page=100")}


def command_labels(args: argparse.Namespace) -> int:
    require_apply(args)
    data = load_yaml(ROADMAP_FILE)
    errors = validate_data(data)
    if errors:
        raise RoadmapError("invalid roadmap:\n" + "\n".join(errors))
    actions = 0
    for repo in data["repositories"]:
        gov = repo_governance(repo)
        if gov["roadmap"]["proposals"] != "enabled":
            print(f"SKIP {repo}: proposals disabled")
            continue
        existing = current_labels(repo)
        for name, meta in data.get("labels", {}).items():
            if name in existing:
                continue
            actions += 1
            print(f"CREATE LABEL {repo}: {name}")
            if args.apply:
                run_command(
                    [
                        "gh", "api", "-X", "POST", f"repos/{ORG_CONFIRM}/{repo}/labels",
                        "-f", f"name={name}", "-f", f"color={meta['color']}",
                        "-f", f"description={meta['description']}",
                    ]
                )
    print(f"label actions: {actions} ({'applied' if args.apply else 'dry-run'})")
    return 0


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    validate = sub.add_parser("validate")
    validate.add_argument("--standalone", action="store_true", help="skip sibling repository governance files")
    render = sub.add_parser("render")
    render.add_argument("--check", action="store_true")
    render.add_argument("--standalone", action="store_true", help="skip sibling repository governance files")
    audit = sub.add_parser("audit")
    audit.add_argument("--offline", action="store_true")
    audit.add_argument("--standalone", action="store_true", help="skip sibling repository governance files")
    audit.add_argument("--output")
    brief = sub.add_parser("brief")
    brief.add_argument("id")
    labels = sub.add_parser("labels")
    labels.add_argument("--apply", action="store_true")
    labels.add_argument("--confirm-org")
    return p


COMMANDS = {
    "validate": command_validate,
    "render": command_render,
    "audit": command_audit,
    "brief": command_brief,
    "labels": command_labels,
}


def main() -> int:
    args = parser().parse_args()
    try:
        return COMMANDS[args.command](args)
    except RoadmapError as exc:
        print(f"roadmap: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
