#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml==6.0.2", "jsonschema==4.25.1"]
# ///
"""Qualification tickets for a release candidate.

A release candidate is a pull request that changes the package version.
For every required surface that has no decision for that version (no
qualification record and no waiver), this tool opens one issue in the
repository, "Qualify <capability> <version> on <runtime>", carrying the
checklist verbatim, the command that records a run, the command that
waives the surface, and the runtime maintainer team to do it; it closes
the issue once the record or waiver is on the branch, and comments on
the pull request with the state of every surface. Idempotent: a re-run
updates rather than duplicates. It needs the workflow's own token
(issues: write, pull-requests: write) and nothing secret: the runs
themselves happen on the maintainers' machines and accounts, the way
users would run them.

  release_tickets.py sync --repo OWNER/NAME --pr N --capability DIR [--dry-run]

Exit 0 whether or not decisions are still missing; the gate that blocks
the merge is osp.py advertise --check --release.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import osp  # noqa: E402
import qualify  # noqa: E402

LABEL = "qualification"
GUIDE = "https://github.com/open-science-pillars/marketplace/blob/main/docs/release-qualification-guide.md"


def gh(args: list[str], dry_run: bool = False, payload: dict | None = None) -> object:
    cmd = ["gh", "api", *args]
    if payload is not None:
        cmd += ["--input", "-"]
    if dry_run and (payload is not None or "-X" in args):
        print(f"  dry-run: {' '.join(cmd)}" + (f" <<< {json.dumps(payload)[:200]}" if payload else ""))
        return None
    r = subprocess.run(cmd, capture_output=True, text=True, input=json.dumps(payload) if payload is not None else None)
    if r.returncode != 0:
        raise SystemExit(f"gh api failed: {' '.join(args)}: {(r.stderr or r.stdout).strip()[:400]}")
    return json.loads(r.stdout) if r.stdout.strip() else None


def ensure_labels(repo: str, names: list[str], dry_run: bool) -> None:
    existing = {l["name"] for l in (gh([f"repos/{repo}/labels?per_page=100"]) or [])}
    for n in names:
        if n not in existing:
            gh(["-X", "POST", f"repos/{repo}/labels"], dry_run, {"name": n, "color": "5319E7",
                                                                 "description": "Runtime qualification of a release candidate"})


def open_issues(repo: str) -> list[dict]:
    return gh([f"repos/{repo}/issues?state=open&labels={LABEL}&per_page=100"]) or []


def team_for(cap: dict, runtime: str) -> str | None:
    gov_path = cap["dir"] / ".osp" / "governance.yaml"
    if not gov_path.is_file():
        return None
    gov = osp.load_yaml(gov_path)
    runtime_teams = ((gov.get("runtime_maintainers") or {}).get(runtime) or {}).get("teams") or []
    if not runtime_teams and runtime == "claude-code":
        runtime_teams = ((gov.get("runtime_maintainers") or {}).get("claude-cowork") or {}).get("teams") or []
    teams = runtime_teams or (gov.get("maintainers") or {}).get("teams") or []
    return teams[0] if teams else None


def ticket_body(cap: dict, runtime: str, pr: int, checklist_text: str, team: str | None) -> str:
    title = osp.RUNTIME_TITLES.get(runtime, runtime)
    name, version = cap["name"], cap["version"]
    who = f"@open-science-pillars/{team}" if team else "the runtime maintainers"
    if runtime == "claude-code":
        how = (f"On your own machine, with your own Claude Code login, from a workspace holding this branch and build-kit:\n\n"
               f"```sh\nuv run build-kit/scripts/qualify.py --capability {name} --surface claude-code --candidate --evidence /tmp/{name}-qualification\n```\n\n"
               f"It builds a local catalog from the checkout, installs the candidate from it the way a release installs, runs every "
               f"required test, keeps the transcripts under the evidence directory, and writes "
               f"`.osp/qualification/claude-code.json`. Commit that file to the release branch (pull request #{pr}).")
    else:
        how = (f"Run the checklist below on {title} as a user would: the prompts verbatim, one fresh conversation each, no "
               f"coaching. Fill `status` (pass, fail, skip or blocked) and `evidence` for every test and the four header "
               f"fields, then record it:\n\n"
               f"```sh\nuv run build-kit/scripts/qualify.py --capability {name} --surface {runtime} --from-checklist {runtime}-checklist.yaml\n```\n\n"
               f"and commit `.osp/qualification/{runtime}.json` to the release branch (pull request #{pr}).")
    return f"""Release candidate **{name} {version}** (pull request #{pr}) needs a decision for **{title}** before it can merge: a qualification record, or a waiver. Owner: {who}. The procedure and the hands-on walkthrough per runtime are in [{GUIDE.rsplit('/', 1)[-1]}]({GUIDE}).

## Record a run

{how}

## Or waive the surface for this release

If the surface cannot be qualified now and the release should go ahead without it, record why:

```sh
uv run build-kit/scripts/qualify.py --capability {name} --surface {runtime} --waive --reason "<why>" --by <your handle>
```

and commit `.osp/qualification/{runtime}.json`. A waived surface is not advertised for this release; the release stays valid.

This issue closes itself when the record or waiver is on the branch.

## Checklist

```yaml
{checklist_text.rstrip()}
```

---
_Opened by build-kit's release_tickets.py for the release candidate; do not edit the checklist here, fill a copy._
"""


def decisions(cap: dict) -> dict[str, str]:
    """runtime -> 'record' | 'waiver' | 'missing' for every required surface at this version."""
    surfaces = cap["surfaces"].get("surfaces") or {}
    records = osp.qualification_records(cap["dir"])
    out = {}
    for runtime, surface in surfaces.items():
        if not surface.get("required"):
            continue
        rec = records.get(runtime)
        if rec and str(rec.get("version")) == str(cap["version"]):
            out[runtime] = "waiver" if rec.get("waived") else "record"
        else:
            out[runtime] = "missing"
    return out


def sync(repo: str, pr: int, cap: dict, dry_run: bool) -> int:
    name, version = cap["name"], cap["version"]
    state = decisions(cap)
    ensure_labels(repo, [LABEL], dry_run)
    existing = {i["title"]: i for i in open_issues(repo)}
    lines = []
    for runtime, decision in state.items():
        title = f"Qualify {name} {version} on {runtime}"
        issue = existing.get(title)
        if decision == "missing":
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / f"{runtime}-checklist.yaml"
                qualify.write_checklist(cap, runtime, path)
                body = ticket_body(cap, runtime, pr, path.read_text(encoding="utf-8"), team_for(cap, runtime))
            if issue is None:
                created = gh(["-X", "POST", f"repos/{repo}/issues"], dry_run,
                             {"title": title, "body": body, "labels": [LABEL, f"runtime:{runtime}"]})
                number = created["number"] if created else "(dry-run)"
                print(f"opened #{number}: {title}")
                lines.append(f"- {runtime}: no decision yet; ticket #{number}")
            else:
                # The branch may have moved since the ticket opened (the
                # require list, a prompt, the lock); the ticket follows it.
                if (issue.get("body") or "").strip() != body.strip():
                    gh(["-X", "PATCH", f"repos/{repo}/issues/{issue['number']}"], dry_run, {"body": body})
                    print(f"refreshed #{issue['number']}: {title}")
                else:
                    print(f"open #{issue['number']}: {title}")
                lines.append(f"- {runtime}: no decision yet; ticket #{issue['number']}")
        else:
            rec = osp.qualification_records(cap["dir"])[runtime]
            verdict = "waived" if decision == "waiver" else ("qualified" if rec.get("qualified") else "not qualified")
            lines.append(f"- {runtime}: {verdict} ({rec.get('date')})")
            if issue is not None:
                gh(["-X", "POST", f"repos/{repo}/issues/{issue['number']}/comments"], dry_run,
                   {"body": f"A {decision} for {name} {version} on {runtime} is on the release branch: {verdict}. Closing.\n\n---\n_Generated by [Claude Code](https://claude.ai/code)_"})
                gh(["-X", "PATCH", f"repos/{repo}/issues/{issue['number']}"], dry_run,
                   {"state": "closed", "state_reason": "completed"})
                print(f"closed #{issue['number']}: {title} ({verdict})")
    missing = [r for r, d in state.items() if d == "missing"]
    summary = (f"## Release candidate {name} {version}: runtime qualification\n\n" + "\n".join(lines) + "\n\n"
               + ("Every required surface has a decision; `osp.py advertise --check --release` decides the merge.\n"
                  if not missing else
                  f"Waiting on: {', '.join(missing)}. The merge is blocked until each has a record or a waiver on this branch.\n")
               + "\n---\n_Generated by [Claude Code](https://claude.ai/code)_")
    marker = f"## Release candidate {name} {version}: runtime qualification"
    comments = gh([f"repos/{repo}/issues/{pr}/comments?per_page=100"]) or []
    mine = next((c for c in comments if isinstance(c.get("body"), str) and c["body"].startswith(marker)), None)
    if mine:
        gh(["-X", "PATCH", f"repos/{repo}/issues/comments/{mine['id']}"], dry_run, {"body": summary})
    else:
        gh(["-X", "POST", f"repos/{repo}/issues/{pr}/comments"], dry_run, {"body": summary})
    print(summary)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["sync"])
    ap.add_argument("--repo", required=True, help="OWNER/NAME")
    ap.add_argument("--pr", required=True, type=int)
    ap.add_argument("--capability", required=True, help="the capability's checkout")
    ap.add_argument("--dry-run", action="store_true", help="print the writes instead of making them")
    args = ap.parse_args()
    if not (os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")) and not args.dry_run:
        print("release_tickets: GH_TOKEN is not set", file=sys.stderr)
        return 2
    cap = qualify.load_capability(Path(args.capability).resolve())
    return sync(args.repo, args.pr, cap, args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
