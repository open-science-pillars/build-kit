#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml==6.0.2"]
# ///
"""Render the brief a knowledge seed session runs from, out of a seed
round file (roadmap/seeds/round-N.yaml). One brief per seed; the
coordinator pastes it as the session's opening prompt. The round file
holds what differs per seed (repository, bundle, branch, issue, concepts,
sources, models); this script holds what every seed is told the same
way (the rules, the format, the checks per repository, the pull request
body, the final report), so a rule changes in one place.

Usage:
  seed_brief.py roadmap/seeds/round-2.yaml --seed seed-gesdisc-merra2
  seed_brief.py roadmap/seeds/round-2.yaml --all --out DIR
  seed_brief.py roadmap/seeds/round-2.yaml --list
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

ORG = "open-science-pillars"

CHECKS = {
    "nasa-daac-knowledge": (
        "`SIGNATURE_DEBT=report bash tools/run_checks.sh` from the repository root must end "
        "in ALL GREEN with your bundle's lines included (it clones nothing; sibling plugin "
        "checks are skipped when the siblings are absent). Fix what it flags."),
    "plugin": (
        "from the repository root, all must pass: "
        "`uv run ../build-kit/scripts/osp.py validate . --standalone`, "
        "`uv run ../build-kit/scripts/osp.py render . --check`, "
        "`uv run ../build-kit/scripts/osp.py plugin-check .`, "
        "`uv run ../build-kit/scripts/osp.py advertise . --check --into README.md`, "
        "`uv run ../nasa-daac-knowledge/tools/check_okf_v02.py knowledge`, "
        "`uv run ../nasa-daac-knowledge/tools/check_script_deps.py .`, "
        "`uv run ../nasa-daac-knowledge/tools/check_prose.py .`, "
        "`uv run ../nasa-daac-knowledge/tools/signature_check.py knowledge --report`. "
        "Fix what they flag."),
}

FETCH = (
    "WebFetch is blocked in this environment; use `curl` through the shell (never disable "
    "TLS verification or unset HTTPS_PROXY). Read PDFs with `python3 -S` after "
    "`pip install --target pylib pypdf` and `sys.path.insert(0, \"pylib\")`, since the "
    "system Python's PDF stack is broken. Verify every DOI's title, authors, journal and "
    "year with `curl -sS https://api.crossref.org/works/<doi>`; journal pages behind a bot "
    "check are cited on their registry records and abstracts, and the concept says so. "
    "Every claim cites a source entry by footnote (`[^id]`), every source entry names what "
    "was read and when, no number is invented, and a source you could not reach is named "
    "as such in the PR body. Read only the domains listed above; the coordinator has "
    "confirmed they are reachable. No data downloads and no credentials are needed.")

RULES = (
    "Repository content rules: no em dashes anywhere, no model names or identifiers in "
    "files or commit messages, plain prose, colons inside YAML values quoted. Every "
    "concept carries `generated: { by: knowledge-seeder/claude, at: <UTC now> }`, "
    "`status: draft`, `stale_after` six months out, and on a gotcha `dataset:` pointing "
    "at the concept it qualifies by relative path, `spheres`, `severity` per the "
    "specification's rule and `eval_case` on high severity. The prose of a gotcha has "
    "Mechanism, Wrong-result mode, Correct approach and Verification paragraphs. Add or "
    "drop a listed gotcha by what the sources support, and say so in the report; never "
    "keep a claim a source does not carry.")


def concept_lines(seed: dict) -> str:
    out = []
    for d in seed.get("datasets") or []:
        out.append(f"- dataset `{seed['bundle']}/datasets/{d['slug']}.md`")
    for r in seed.get("requirements") or []:
        out.append(f"- requirement `{seed['bundle']}/requirements/{r['slug']}.md`, class {r['class']}")
    for g in seed.get("gotchas") or []:
        out.append(f"- gotcha `{seed['bundle']}/gotchas/{g['slug']}.md`, severity {g['severity']}")
    return "\n".join(out)


def eval_text(seed: dict) -> str:
    ev = seed.get("eval")
    highs = [g["slug"] for g in seed.get("gotchas") or [] if g["severity"] == "high"]
    if not ev or not highs:
        return "EVAL CASES. None: no listed gotcha is high severity."
    if ev["repo"] == seed["repo"]:
        return (f"EVAL CASES. Each high-severity gotcha ({', '.join(highs)}) gets a gotcha-avoidance "
                f"case under `{ev['subtree']}/` in this repository, in the shape of the existing "
                f"cases there, named on the gotcha's `eval_case`. Registration in the evals "
                f"repository's manifest is the coordinator's follow-up; say so in the PR body.")
    return (f"EVAL CASES. Each high-severity gotcha ({', '.join(highs)}) gets a gotcha-avoidance "
            f"case in the format of agent-evals/ecco/cases/grace-intermission-gap.yaml (fetch that "
            f"file from github.com/{ORG}/{ev['repo']} to copy the shape), added under "
            f"`{ev['subtree']}/` in a second pull request in {ev['repo']} on the branch "
            f"`{ev['branch']}`; name the case on the gotcha's `eval_case`. Registration in the "
            f"evals repository's manifest is the coordinator's follow-up; say so in both PR bodies.")


def render(round_: dict, seed: dict) -> str:
    repo, bundle, branch = seed["repo"], seed["bundle"], seed["branch"]
    provider = repo == "nasa-daac-knowledge"
    others = [s for s in round_["seeds"] if s["repo"] == repo and s["id"] != seed["id"]]
    others_text = (
        "Other seed sessions are working on this repository at the same time on their own "
        "branches and bundles (" + ", ".join(f"`{o['bundle']}`" for o in others) + "); edit "
        f"nothing outside `{bundle}/`" +
        (" (no README, no run_checks.sh, no CODEOWNERS; the bundle's index, log and DIGEST exist)."
         if provider else " (no README, no manifest, no plugin metadata).")
        if others else
        f"Edit nothing outside `{bundle}/`.")
    if provider:
        format_text = (
            "FORMAT. Read docs/ in this repository and, from a read-only clone "
            f"`git clone https://github.com/{ORG}/marketplace ../marketplace`, "
            "marketplace/docs/contributing-knowledge.md and marketplace/docs/okf-conformance.md. "
            "Models in this repository: " + ", ".join(f"`{m}`" for m in seed["models"]) + ". "
            f"Update `{bundle}/index.md` (a line per concept in its section, replacing a "
            "`(none yet)` placeholder), add one entry at the top of `" + bundle + "/log.md` naming "
            f"the concepts and the sources read, and re-render the digest with "
            f"`uv run tools/digest.py {bundle}`.")
        checks = CHECKS["nasa-daac-knowledge"]
    else:
        format_text = (
            "FORMAT. Clone read-only beside the repository: "
            f"`git clone https://github.com/{ORG}/marketplace ../marketplace`, likewise "
            "../nasa-daac-knowledge and ../build-kit. Read marketplace/docs/contributing-knowledge.md "
            "and marketplace/docs/okf-conformance.md for the concept format. Models in this "
            "repository: " + ", ".join(f"`{m}`" for m in seed["models"]) + ". Update "
            f"`{bundle}/index.md` (a line per concept in its section) and add one entry at the top "
            f"of `{bundle}/log.md` naming the concepts and the sources read.")
        checks = CHECKS["plugin"]
    sources = "\n".join(f"- {s['domain']}: {s['read']}" for s in seed["sources"])
    dnr = "\n".join(f"- {d}" for d in seed.get("do_not_repeat") or [])
    dnr_text = f"\nDO NOT REPEAT.\n{dnr}\n" if dnr else ""
    spheres = ", ".join(seed.get("spheres") or []) or "none (a requirement concept carries no sphere)"
    pr_second = (f" (and one in {seed['eval']['repo']} for the eval cases)"
                 if seed.get("eval") and seed["eval"]["repo"] != repo else "")
    return f"""You are seeding knowledge concepts for the Open Science Pillars organization (github.com/{ORG}) in the repository {repo}, on a new branch `{branch}` created from main. A coordinator session dispatched you and will lint, review, register eval cases and reconcile the roadmap; you draft, check, push and open one pull request per repository you touch. Do not merge anything, do not sign anything, never set a status other than `draft`. {others_text} This seed is issue #{seed['issue']} in {repo}; reference it in the PR body.

WHAT TO BUILD ({seed['title']}). {seed['scope'].strip()}

CONCEPTS, one file each, spheres: {spheres}:
{concept_lines(seed)}

{eval_text(seed)}

SOURCES, and what to read on each:
{sources}

HOW TO READ THEM. {FETCH}
{dnr_text}
{format_text}

RULES. {RULES}

CHECKS BEFORE PUSHING: {checks}

COMMIT, PUSH, PR. `git commit -s` (DCO sign-off) with the attribution lines your session instructions give you. Push the branch and open one pull request against main in {repo}{pr_second} with a body listing each concept, its severity, the sources fetched with dates, what could not be fetched, the check results, a closing paragraph headed "For the reviewer" that says in plain words what a reviewer who knows the product should check first, and the line "Knowledge PR: merges on the maintainer's review". Then report, as your final message: the PR URLs, the concepts drafted, any source you could not reach, and anything you decided differently from this brief and why.
"""


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("round_file", type=Path)
    ap.add_argument("--seed")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--out", type=Path)
    a = ap.parse_args()
    round_ = yaml.safe_load(a.round_file.read_text(encoding="utf-8"))
    seeds = {s["id"]: s for s in round_["seeds"]}
    if a.list:
        for s in round_["seeds"]:
            print(f"{s['id']:34} {s['repo']:22} {s['bundle']:20} {s['branch']:34} #{s['issue']}")
        return
    chosen = list(seeds.values()) if a.all else [seeds[a.seed]] if a.seed in seeds else None
    if not chosen:
        sys.exit("name a seed with --seed, or --all")
    for s in chosen:
        text = render(round_, s)
        if a.out:
            a.out.mkdir(parents=True, exist_ok=True)
            (a.out / f"{s['id']}.md").write_text(text, encoding="utf-8")
        else:
            print(text)
    if a.out:
        print(f"{len(chosen)} briefs written to {a.out}")


if __name__ == "__main__":
    main()
