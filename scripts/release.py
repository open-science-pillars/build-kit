#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml==6.0.2", "jsonschema==4.25.1"]
# ///
"""A capability release, step by step, the same way every time.

  release.py candidate DIR --version X.Y.Z [--summary TEXT] [--notes FILE]
                       [--branch NAME] [--push] [--pr] [--dry-run]
      the release candidate: a branch from the current commit, the
      version set in .osp/package.yaml and CITATION.cff, the projections
      re-rendered, the lock regenerated, the README's runtime table
      refreshed, every gate check run locally, one signed commit
      "Release X.Y.Z: summary" with the notes; --push pushes the branch and
      --pr opens the pull request with gh. The pull request is the
      candidate: the release-qualification workflow opens one ticket per
      required runtime under the milestone "<name> X.Y.Z" (created by
      that first sync run, set on the tickets and on the pull request),
      and the merge waits on a record or a waiver for each (the release
      qualification guide).
  release.py tag DIR [--push] [--dry-run]
      after the candidate merged: on the merged commit, with the lock
      current and every advertising rule satisfied, the annotated tag
      <name>--vX.Y.Z (claude plugin tag, which checks the manifest agrees).
      The milestone is not closed here: it closes when its issues are
      done, which is the maintainer's call.
  release.py catalog DIR --marketplace MARKETPLACE_DIR [--push] [--pr] [--dry-run]
      the catalog line: the marketplace entry's ref moved to the tag, on a
      branch with one commit "Catalog: <name> X.Y.Z"; --pr opens it.
  release.py publish DIR [--out DIST]
      osp.py publish: dist/ with the projections a qualified runtime
      consumes and the honest status per runtime, to attach to the
      GitHub release.

Every write is printed first; --dry-run prints and stops. Nothing here
holds or needs a secret: git and gh use the maintainer's own login.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import osp  # noqa: E402

OSP = HERE / "osp.py"


class ReleaseError(RuntimeError):
    pass


def sh(cmd: list[str], cwd: Path, dry_run: bool = False, check: bool = True, quiet: bool = False) -> subprocess.CompletedProcess:
    if dry_run:
        print(f"  would run: {' '.join(cmd)}")
        return subprocess.CompletedProcess(cmd, 0, "", "")
    if not quiet:
        print(f"  {' '.join(cmd)}")
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if check and r.returncode != 0:
        raise ReleaseError(f"{' '.join(cmd)} failed:\n{(r.stdout + r.stderr).strip()[-1500:]}")
    return r


def version_tuple(v: str) -> tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d+", v))


def set_version(text: str, version: str) -> tuple[str, str]:
    """(new text, old version) for a package.yaml: the version line inside
    the package block, comments and order kept."""
    m = re.search(r"^(  version: *['\"]?)([0-9][0-9.]*)(['\"]?)\s*$", text, re.M)
    if not m:
        raise ReleaseError("package.yaml has no `  version:` line to set")
    old = m.group(2)
    return text[:m.start(2)] + version + text[m.end(2):], old


def set_citation_version(text: str, version: str) -> str:
    return re.sub(r'^(version: *")[0-9][0-9.]*(")', rf'\g<1>{version}\2', text, count=1, flags=re.M)


def release_notes(summary: str, notes: str | None, changes: list[str]) -> str:
    body = [f"{summary}".strip()]
    if notes:
        body += ["", notes.strip()]
    if changes:
        body += ["", "Changes since the previous release:", *[f"- {c}" for c in changes]]
    return "\n".join(body).rstrip() + "\n"


def changes_since_tag(cap_dir: Path, name: str, old_version: str) -> list[str]:
    tag = f"{name}--v{old_version}"
    r = sh(["git", "rev-parse", "-q", "--verify", f"refs/tags/{tag}"], cap_dir, check=False, quiet=True)
    if r.returncode != 0:
        r = sh(["git", "ls-remote", "--tags", "origin", tag], cap_dir, check=False, quiet=True)
        if not r.stdout.strip():
            return []
        sh(["git", "fetch", "-q", "origin", f"refs/tags/{tag}:refs/tags/{tag}"], cap_dir, check=False, quiet=True)
    r = sh(["git", "log", "--first-parent", "--format=%s", f"{tag}..HEAD"], cap_dir, check=False, quiet=True)
    out = []
    for line in r.stdout.splitlines():
        line = line.strip()
        if line.startswith("Merge pull request"):
            continue
        out.append(line)
    return out


def pr_body(name: str, version: str, notes: str) -> str:
    return f"""# Pull request

## What and why

Release candidate **{name} {version}**. {notes.strip()}

This pull request is the candidate: the release-qualification workflow opens one ticket per required runtime surface with no decision for {version} under the milestone `{name} {version}` (created on its first run and set on this pull request); each closes on a qualification record (Claude Code: `qualify.py --capability {name} --surface claude-code --candidate` on a maintainer's machine; other runtimes by checklist) or a waiver; the merge waits on every required surface having one. After the merge: `release.py tag` for the annotated tag `{name}--v{version}`, `release.py catalog` for the marketplace line, `release.py publish` for the projections to attach to the GitHub release (the release candidate guide in the marketplace repository).

## Checklist

- [x] DCO sign-off on every commit (`git commit -s`)
- [x] No `commands/` directories anywhere (everything is a skill)
- [ ] Touched SKILL.md files (none touched by the release commit)
- [ ] Workflow skills touched (none touched by the release commit)
- [ ] Knowledge concepts touched (none touched by the release commit)
- [x] Layer check: a version bump and rendered files only
- [ ] High-severity gotcha added or edited (none)
- [x] No credentials, tokens, or `~/.netrc` contents anywhere in the diff
- [x] Prose uses no em dashes (commas, colons, parentheses, semicolons instead)

## Reviews

A release: one maintainer review plus the qualification records or waivers the tickets ask for.
"""


def command_candidate(args: argparse.Namespace) -> int:
    cap_dir = Path(args.dir).resolve()
    dry = args.dry_run
    pkg_path = cap_dir / ".osp" / "package.yaml"
    pkg = osp.read_package(cap_dir)
    if pkg is None:
        raise ReleaseError(f"{cap_dir}: no .osp/package.yaml; only a package is released")
    name = pkg["package"]["name"]
    old = str(pkg["package"]["version"])
    new = args.version
    if version_tuple(new) <= version_tuple(old):
        raise ReleaseError(f"{name}: {new} is not above the current {old}")
    status = sh(["git", "status", "--porcelain"], cap_dir, quiet=True).stdout.strip()
    if status and not args.allow_dirty:
        raise ReleaseError(f"{name}: the working tree is not clean; commit or stash first:\n{status}")
    tag = f"{name}--v{new}"
    if sh(["git", "ls-remote", "--tags", "origin", tag], cap_dir, check=False, quiet=True).stdout.strip():
        raise ReleaseError(f"{name}: the tag {tag} already exists on origin")
    branch = args.branch or f"release-{new}"
    summary = args.summary or f"{name} {new}"
    notes = Path(args.notes).read_text(encoding="utf-8") if args.notes else None
    changes = changes_since_tag(cap_dir, name, old)
    body = release_notes(summary, notes, changes)
    print(f"{name}: {old} -> {new} on branch {branch}")
    print("release notes:\n" + "\n".join("  " + l for l in body.splitlines()))
    if dry:
        print("dry run; nothing written")
        return 0
    sh(["git", "checkout", "-B", branch], cap_dir)
    text, _ = set_version(pkg_path.read_text(encoding="utf-8"), new)
    pkg_path.write_text(text, encoding="utf-8")
    cff = cap_dir / "CITATION.cff"
    if cff.is_file():
        cff.write_text(set_citation_version(cff.read_text(encoding="utf-8"), new), encoding="utf-8")
    run = lambda *a: sh(["uv", "run", "--quiet", str(OSP), *a], cap_dir)  # noqa: E731
    run("render", str(cap_dir))
    run("lock", str(cap_dir))
    readme = cap_dir / "README.md"
    if readme.is_file() and osp.RUNTIMES_START in readme.read_text(encoding="utf-8"):
        run("advertise", str(cap_dir), "--into", "README.md")
    run("validate", str(cap_dir), "--standalone")
    run("render", str(cap_dir), "--check")
    run("lock", str(cap_dir), "--check")
    if (cap_dir / osp.PORTABLE_MANIFEST).is_file():
        run("plugin-check", str(cap_dir))
    sh(["git", "add", "-A"], cap_dir)
    message = f"Release {new}: {summary}\n\n{body}".rstrip() + "\n"
    r = subprocess.run(["git", "commit", "-q", "-s", "-F", "-"], cwd=cap_dir, input=message, capture_output=True, text=True)
    if r.returncode != 0:
        raise ReleaseError(f"git commit failed: {(r.stdout + r.stderr).strip()[-800:]}")
    print(f"  committed: Release {new}: {summary}")
    if args.push or args.pr:
        sh(["git", "push", "-u", "origin", branch], cap_dir)
    if args.pr:
        if shutil.which("gh") is None:
            raise ReleaseError("gh is not installed; push is done, open the pull request by hand with the body release.py prints with --print-pr-body")
        r = subprocess.run(["gh", "pr", "create", "--base", args.base, "--head", branch, "--title", f"Release {new}: {summary}",
                            "--body", pr_body(name, new, body), "--label", "release"],
                           cwd=cap_dir, capture_output=True, text=True)
        if r.returncode != 0 and "label" in (r.stderr or "").lower():
            r = subprocess.run(["gh", "pr", "create", "--base", args.base, "--head", branch, "--title", f"Release {new}: {summary}",
                                "--body", pr_body(name, new, body)], cwd=cap_dir, capture_output=True, text=True)
        if r.returncode != 0:
            raise ReleaseError(f"gh pr create failed: {(r.stdout + r.stderr).strip()[-800:]}")
        print(f"  pull request: {r.stdout.strip()}")
    else:
        print(f"next: git push -u origin {branch}; open the pull request (release.py candidate ... --pr does both)")
    return 0


def command_tag(args: argparse.Namespace) -> int:
    cap_dir = Path(args.dir).resolve()
    pkg = osp.read_package(cap_dir)
    name, version = pkg["package"]["name"], str(pkg["package"]["version"])
    tag = f"{name}--v{version}"
    if sh(["git", "status", "--porcelain"], cap_dir, quiet=True).stdout.strip():
        raise ReleaseError(f"{name}: the working tree is not clean")
    run = lambda *a: sh(["uv", "run", "--quiet", str(OSP), *a], cap_dir, dry_run=False)  # noqa: E731
    run("lock", str(cap_dir), "--check")
    run("advertise", str(cap_dir), "--check", "--release", "--into", "README.md")
    cmd = ["claude", "plugin", "tag", "--message", f"{name} %s"] + (["--push"] if args.push else []) + (["--dry-run"] if args.dry_run else [])
    if shutil.which("claude") is None:
        cmd = ["git", "tag", "-a", tag, "-m", f"{name} {version}"]
        sh(cmd, cap_dir, dry_run=args.dry_run)
        if args.push:
            sh(["git", "push", "origin", tag], cap_dir, dry_run=args.dry_run)
    else:
        r = sh(cmd, cap_dir)
        print(r.stdout.strip())
    print(f"{tag}: {'pushed' if args.push else 'created locally; push with --push'}; next: release.py catalog, then release.py publish")
    print(f"the milestone {name} {version} stays open until its issues are done; close it by hand when they are")
    return 0


def command_catalog(args: argparse.Namespace) -> int:
    cap_dir = Path(args.dir).resolve()
    market = Path(args.marketplace).resolve()
    pkg = osp.read_package(cap_dir)
    name, version = pkg["package"]["name"], str(pkg["package"]["version"])
    tag = f"{name}--v{version}"
    path = market / ".claude-plugin" / "marketplace.json"
    data = osp.read_json(path)
    entry = next((p for p in data.get("plugins", []) if p.get("name") == name), None)
    if entry is None:
        raise ReleaseError(f"{name} is not in the catalog {path}")
    old_ref = (entry.get("source") or {}).get("ref")
    print(f"catalog: {name} {old_ref} -> {tag}")
    if args.dry_run:
        return 0
    if sh(["git", "ls-remote", "--tags", "origin", tag], cap_dir, check=False, quiet=True).stdout.strip() == "":
        raise ReleaseError(f"{tag} is not on origin yet; release.py tag --push first")
    branch = args.branch or f"catalog-{name}-{version}"
    sh(["git", "checkout", "-B", branch], market)
    entry["source"]["ref"] = tag
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    sh(["git", "add", "-A"], market)
    r = subprocess.run(["git", "commit", "-q", "-s", "-m", f"Catalog: {name} {version}"], cwd=market, capture_output=True, text=True)
    if r.returncode != 0:
        raise ReleaseError(f"git commit failed: {(r.stdout + r.stderr).strip()[-800:]}")
    if args.push or args.pr:
        sh(["git", "push", "-u", "origin", branch], market)
    if args.pr:
        if shutil.which("gh") is None:
            raise ReleaseError("gh is not installed; the branch is pushed, open the pull request by hand")
        r = subprocess.run(["gh", "pr", "create", "--base", args.base, "--head", branch, "--title", f"Catalog: {name} {version}",
                            "--body", f"The catalog entry for {name} moves to `{tag}` (the release rule: a catalog entry whose ref names the tag)."],
                           cwd=market, capture_output=True, text=True)
        if r.returncode != 0:
            raise ReleaseError(f"gh pr create failed: {(r.stdout + r.stderr).strip()[-800:]}")
        print(f"  pull request: {r.stdout.strip()}")
    return 0


def command_publish(args: argparse.Namespace) -> int:
    cap_dir = Path(args.dir).resolve()
    cmd = ["uv", "run", "--quiet", str(OSP), "publish", str(cap_dir)] + (["--out", args.out] if args.out else [])
    r = sh(cmd, cap_dir)
    print(r.stdout.strip())
    pkg = osp.read_package(cap_dir)
    name, version = pkg["package"]["name"], str(pkg["package"]["version"])
    dist = Path(args.out).resolve() if args.out else cap_dir / "dist"
    print(f"next: gh release create {name}--v{version} {dist}/claude/{name}-{version}.zip {dist}/release.json {dist}/RUNTIMES.md "
          f"--title \"{name} {version}\" --notes-file <notes>")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True)
    c = sub.add_parser("candidate")
    c.add_argument("dir")
    c.add_argument("--version", required=True)
    c.add_argument("--summary", help="one line after 'Release X.Y.Z:'")
    c.add_argument("--notes", help="a file with the release notes body")
    c.add_argument("--branch")
    c.add_argument("--base", default="main")
    c.add_argument("--push", action="store_true")
    c.add_argument("--pr", action="store_true", help="push and open the pull request with gh (adds the release label when it exists)")
    c.add_argument("--allow-dirty", action="store_true")
    c.add_argument("--dry-run", action="store_true")
    t = sub.add_parser("tag")
    t.add_argument("dir")
    t.add_argument("--push", action="store_true")
    t.add_argument("--dry-run", action="store_true")
    k = sub.add_parser("catalog")
    k.add_argument("dir")
    k.add_argument("--marketplace", required=True)
    k.add_argument("--branch")
    k.add_argument("--base", default="main")
    k.add_argument("--push", action="store_true")
    k.add_argument("--pr", action="store_true")
    k.add_argument("--dry-run", action="store_true")
    p = sub.add_parser("publish")
    p.add_argument("dir")
    p.add_argument("--out")
    args = ap.parse_args()
    try:
        return {"candidate": command_candidate, "tag": command_tag, "catalog": command_catalog, "publish": command_publish}[args.command](args)
    except (ReleaseError, osp.OspError) as exc:
        print(f"release: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
