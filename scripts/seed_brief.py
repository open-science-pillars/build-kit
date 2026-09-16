#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml==6.0.2"]
# ///
"""Render the brief a seed session runs from, out of a seed round file
(roadmap/seeds/round-N.yaml). One brief per seed; the coordinator pastes
it as the session's opening prompt. The round file holds what differs
per seed (repository, bundle, branch, issue, concepts or deliverables,
sources, models, wave); this script holds what every seed of a kind is
told the same way (the rules, the format, the checks per repository,
the pull request body, the final report), so a rule changes in one
place.

Seed kinds: knowledge (concepts, the round-two shape), computation (an
attested computation in the sea level budget's shape), connector (tools
on the observations server plus their connector concepts), data-root (a
stamped data root and its loaders, no concepts). A seed may carry a
wave (A or B) and a depends_on list; a wave B brief renders the
`context` lines the coordinator adds once wave A has merged.

Usage:
  seed_brief.py roadmap/seeds/round-3.yaml --seed r3-argo-ohc
  seed_brief.py roadmap/seeds/round-3.yaml --all --out DIR
  seed_brief.py roadmap/seeds/round-3.yaml --wave A --out DIR
  seed_brief.py roadmap/seeds/round-3.yaml --list
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

ORG = "open-science-pillars"
KINDS = ("knowledge", "computation", "connector", "data-root")

PLUGIN_CHECKS = (
    "`uv run ../build-kit/scripts/osp.py validate . --standalone`, "
    "`uv run ../build-kit/scripts/osp.py render . --check`, "
    "`uv run ../build-kit/scripts/osp.py plugin-check .`, "
    "`uv run ../build-kit/scripts/osp.py placement-check .`, "
    "`uv run ../build-kit/scripts/osp.py advertise . --check --into README.md`, "
    "`uv run ../nasa-daac-knowledge/tools/check_okf_v02.py knowledge`, "
    "`uv run ../nasa-daac-knowledge/tools/check_script_deps.py .`, "
    "`uv run ../nasa-daac-knowledge/tools/check_prose.py .`, "
    "`uv run ../nasa-daac-knowledge/tools/signature_check.py knowledge --report`")

CHECKS = {
    "nasa-daac-knowledge": (
        "`SIGNATURE_DEBT=report bash tools/run_checks.sh` from the repository root must end "
        "in ALL GREEN with your bundle's lines included (it clones nothing; sibling plugin "
        "checks are skipped when the siblings are absent). Fix what it flags."),
    "plugin": (
        "from the repository root, all must pass: " + PLUGIN_CHECKS + ". Fix what they flag."),
    "core": (
        "from the repository root, all must pass: "
        "`uv run connectors/observations_mcp.py --test` (offline, on the fixtures; this is "
        "what CI runs), " + PLUGIN_CHECKS + ", and `uv run ../build-kit/scripts/osp.py lock . "
        "--check` (regenerate the lock with `lock .` if you declared a dependency). Fix what "
        "they flag."),
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
    "confirmed they are reachable except where a source line says otherwise.")

NO_DOWNLOAD = (
    "No data downloads and no credentials are needed. The environment may hold an "
    "Earthdata token in `EARTHDATA_TOKEN`; this seed does not use it, and it is never "
    "printed, logged, stored or committed.")

TOKEN = (
    "Data files are downloaded only by the loaders, only from the domains above, and only "
    "the derived CSVs, stamps and records are committed, never the product files. The "
    "environment holds an Earthdata Login bearer token in `EARTHDATA_TOKEN` for the "
    "downloads that need one: use it only as the header "
    "`-H \"Authorization: Bearer $EARTHDATA_TOKEN\"` on a curl download (or let earthaccess "
    "read it from the environment), never print, echo, log, store or commit it, and never "
    "write it into a stamp, SOURCES.json, RECORD.json, a receipt, a fixture, a commit or a "
    "PR body. A download that fails without the token is retried with it once; a download "
    "that still fails is named in the PR body with its status code.")

CONTENT_RULES = (
    "Repository content rules: no em dashes anywhere, no model names or identifiers in "
    "files or commit messages, plain prose, colons inside YAML values quoted.")

RULES = (
    CONTENT_RULES + " Every "
    "concept carries `generated: { by: knowledge-seeder/claude, at: <UTC now> }`, "
    "`status: draft`, `stale_after` six months out, and on a gotcha `dataset:` pointing "
    "at the concept it qualifies by relative path, `spheres`, `severity` per the "
    "specification's rule and `eval_case` on high severity. The prose of a gotcha has "
    "Mechanism, Wrong-result mode, Correct approach and Verification paragraphs. A recipe "
    "cites the concepts it builds on by relative path and names its steps, inputs and the "
    "check a reader runs; a connector concept names the tool, the source, the request "
    "shape, what leaves the machine and the failure mode. Add or "
    "drop a listed concept by what the sources support, and say so in the report; never "
    "keep a claim a source does not carry.")

EXECUTOR_RULES = (
    "The executor is deterministic and argument driven: `--fixture --seed N` builds a "
    "synthetic input with a planted answer and the receipt shows it recovered; "
    "`--data-root DIR` reads only the CSVs and stamps the loaders wrote there, never a raw "
    "product file; `--runtime NAME` is recorded verbatim; `--receipt PATH` writes JSON "
    "naming the computation and its arguments, the sha256 of the executor's own file, the "
    "window, every term with its value, units, uncertainty and the stamp it came from, the "
    "residual and the combined uncertainty, the bookkeeping statements as strings, and the "
    "data root's RECORD hash when one was read; a window the inputs do not cover exits 3 "
    "with a receipt whose refusal field says why, and computes nothing. The attester takes "
    "a receipt path, hashes the executor on disk and compares it with the receipt's hash, "
    "recomputes the arithmetic from the receipt's terms, checks each term against stated "
    "plausibility bounds, prints one `PASS name` or `FAIL name: reason` line per check, "
    "prints `PASS refusal` for a refusal receipt, and exits nonzero on any FAIL; "
    "`--selftest` exercises it on receipts it builds in a temporary directory.")

LOADER_RULES = (
    "Every loader has `--selftest` on a synthetic input it builds itself, writes one CSV "
    "and one `<term>-stamp.json` (what was read, from where, when, the product version, "
    "the grid, the aggregation, the mask, the sha256 of every file read) and never leaves "
    "a raw product file in the tree; the data-root tool writes RECORD.json (the manifest "
    "with hashes, the stamps, the bookkeeping table) and `--check` verifies the manifest "
    "against the files; SOURCES.json names every file read with its URL, hash and the "
    "time it was read. Every script carries the `# /// script` dependency header that "
    "check_script_deps.py reads, with each dependency pinned, and runs under `uv run`.")

CONCEPT_RULES = (
    "The computation concept has `type: Attested Computation` and names the executor and "
    "the attester in its frontmatter with the keys the pattern concept uses (computation, "
    "executor.resource naming the executor script itself, executor.receipt, "
    "attester.resource) and, when this seed names a wrapping skill, `executor.skill: "
    "<capability>/<skill>`; the recipe has `type: Recipe`; both carry `status: draft`, the "
    "generated block and `stale_after` six months out. The run instructions are a skill "
    "(a SKILL.md in the sphere capability), never a concept: create no references/skills/ "
    "directory, and put no script under skills/<name>/ outside its scripts/ directory and "
    "none under verification/ that a skill runs (the placement rule; `uv run "
    "../build-kit/scripts/osp.py placement-check .` reports a violation with its code). "
    "Every number in the concept names the receipt it came from, and the real-data run is "
    "anchored to the published value with its source and the distance from it.")

NO_CHECK_EDIT = (
    "Never edit the repository's check routine (tools/run_checks.sh, a workflow under "
    ".github/, tools/reference_runs.yaml unless the deliverables name it); write in the PR "
    "body the exact commands, in order, that the coordinator adds as the check chain: the "
    "fixture run with its receipt, the attester on it, the refusal run exiting 3 and "
    "attesting as a refusal, each loader's selftest, the data-root `--check` and the "
    "record run on the committed root attested.")

NO_CHECK_EDIT_ROOT = (
    "Never edit the repository's check routine (tools/run_checks.sh, a workflow under "
    ".github/); write in the PR body the exact commands, in order, that the coordinator "
    "adds as the check lines: each loader's selftest and the data-root `--check` on the "
    "committed root.")

CONNECTOR_RULES = (
    "Each tool is a thin translation from its parameters to one request against one "
    "source, wrapped in the same `guarded(source)` and `_cap` discipline as the existing "
    "tools, returning the parsed values and a citation naming the source, the request and "
    "the time; a parser is a pure function on the response text so a fixture exercises "
    "it; `--record-fixtures` records one fixture per tool under connectors/fixtures/ from "
    "a live call (small, holding no key and no token, its request named the way the "
    "existing fixtures name theirs), and where the live source is unreachable from the "
    "session the fixture is written by hand from the documented response shape and the "
    "PR body says so; `--test` passes offline on the fixtures and is what CI runs. The "
    "source's terms of use and any key are named in the tool's docstring and in "
    "CONNECTORS.md (what leaves the machine, what happens when the source is unavailable, "
    "the key if any). The server's VERSION is bumped by a minor step. A new dependency is "
    "declared in the script header and the lock regenerated; say so in the PR. The "
    "connector concepts have `type: Connector` in the shape of the models, carry "
    "`status: draft`, the generated block and `stale_after` six months out, and get a line "
    "in that repository's knowledge/index.md and knowledge/log.md; each repository's "
    "concepts go as one PR on the branch named below, and each of those repositories is "
    "cloned beside this one and checked with its own routine.")


def concept_lines(seed: dict) -> str:
    out = []
    b = seed["bundle"]
    for d in seed.get("datasets") or []:
        out.append(f"- dataset `{b}/datasets/{d['slug']}.md`")
    for r in seed.get("requirements") or []:
        out.append(f"- requirement `{b}/requirements/{r['slug']}.md`, class {r['class']}")
    for g in seed.get("gotchas") or []:
        out.append(f"- gotcha `{b}/gotchas/{g['slug']}.md`, severity {g['severity']}")
    for r in seed.get("recipes") or []:
        out.append(f"- recipe `{b}/recipes/{r['slug']}.md`")
    for c in seed.get("connectors") or []:
        out.append(f"- connector `{b}/connectors/{c['slug']}.md`")
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


def others_text(round_: dict, seed: dict) -> str:
    """The concurrency and boundary sentence. A knowledge seed's boundary is
    its bundle (plus an in-repository eval subtree); the other kinds carry an
    explicit boundary field, so only the concurrency part is rendered here."""
    repo, bundle = seed["repo"], seed["bundle"]
    provider = repo == "nasa-daac-knowledge"
    knowledge = seed.get("kind", "knowledge") == "knowledge"
    wave = seed.get("wave")
    others = [s for s in round_["seeds"] if s["repo"] == repo and s["id"] != seed["id"]
              and (wave is None or s.get("wave") == wave)]
    ev = seed.get("eval")
    allowed = f"`{bundle}/`"
    if ev and ev["repo"] == repo and not ev["subtree"].startswith(bundle.rstrip("/") + "/"):
        allowed += f" and `{ev['subtree']}/`"
    concurrency = (
        "Other seed sessions are working on this repository at the same time on their own "
        "branches and areas (" + ", ".join(f"`{o['bundle']}`" for o in others) + "); "
        if others else "")
    if not knowledge:
        return concurrency.rstrip("; ") + (". " if concurrency else "")
    if not others:
        return f"Edit nothing outside {allowed}."
    return (concurrency + f"edit nothing outside {allowed}" +
            (" (no README, no run_checks.sh, no CODEOWNERS; the bundle's index, log and DIGEST exist)."
             if provider else " (no README, no manifest, no plugin metadata)."))


def context_text(seed: dict) -> str:
    ctx = seed.get("context") or []
    deps = seed.get("depends_on") or []
    if not ctx and not deps:
        return ""
    lines = "\n".join(f"- {c}" for c in ctx) if ctx else (
        "- (the coordinator fills this in once " + ", ".join(deps) + " have merged)")
    return f"\nCONTEXT FROM EARLIER SEEDS, already on main; read before building and do not redo it:\n{lines}\n"


def sources_text(seed: dict) -> str:
    return "\n".join(f"- {s['domain']}: {s['read']}" for s in seed["sources"])


def dnr_text(seed: dict) -> str:
    dnr = "\n".join(f"- {d}" for d in seed.get("do_not_repeat") or [])
    return f"\nDO NOT REPEAT.\n{dnr}\n" if dnr else ""


def report_text() -> str:
    return ("Then report, as your final message: the PR URLs, what was built, any source "
            "you could not reach, and anything you decided differently from this brief and why.")


def pr_body_common() -> str:
    return ("the check results, a closing paragraph headed \"For the reviewer\" that says in "
            "plain words what a reviewer who knows the product should check first")


def render_knowledge(round_: dict, seed: dict) -> str:
    repo, bundle, branch = seed["repo"], seed["bundle"], seed["branch"]
    provider = repo == "nasa-daac-knowledge"
    models = ", ".join(f"`{m}`" for m in seed["models"])
    if provider:
        format_text = (
            "FORMAT. Read docs/ in this repository and, from a read-only clone "
            f"`git clone https://github.com/{ORG}/marketplace ../marketplace`, "
            "marketplace/docs/contributing-knowledge.md and marketplace/docs/okf-conformance.md. "
            f"Models (a path starting with another repository's name is in a read-only clone "
            f"beside this one): {models}. "
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
            f"repository: {models}. Update "
            f"`{bundle}/index.md` (a line per concept in its section) and add one entry at the top "
            f"of `{bundle}/log.md` naming the concepts and the sources read.")
        checks = CHECKS["plugin"]
    spheres = ", ".join(seed.get("spheres") or []) or "none (a requirement concept carries no sphere)"
    pr_second = (f" (and one in {seed['eval']['repo']} for the eval cases)"
                 if seed.get("eval") and seed["eval"]["repo"] != repo else "")
    return f"""You are seeding knowledge concepts for the Open Science Pillars organization (github.com/{ORG}) in the repository {repo}, on a new branch `{branch}` created from main. A coordinator session dispatched you and will lint, review, register eval cases and reconcile the roadmap; you draft, check, push and open one pull request per repository you touch. Do not merge anything, do not sign anything, never set a status other than `draft`. {others_text(round_, seed)} This seed is issue #{seed['issue']} in {repo}; reference it in the PR body.

WHAT TO BUILD ({seed['title']}). {seed['scope'].strip()}

CONCEPTS, one file each, spheres: {spheres}:
{concept_lines(seed)}

{eval_text(seed)}
{context_text(seed)}
SOURCES, and what to read on each:
{sources_text(seed)}

HOW TO READ THEM. {FETCH} {NO_DOWNLOAD}
{dnr_text(seed)}
{format_text}

RULES. {RULES}

CHECKS BEFORE PUSHING: {checks}

COMMIT, PUSH, PR. `git commit -s` (DCO sign-off) with the attribution lines your session instructions give you. Push the branch and open one pull request against main in {repo}{pr_second} with a body listing each concept, its severity, the sources fetched with dates, what could not be fetched, {pr_body_common()}, and the line "Knowledge PR: merges on the maintainer's review". {report_text()}
"""


def pattern_text(seed: dict) -> str:
    return (
        "PATTERN, read these first and keep their shape (a path is relative to this "
        "repository's root; a path that starts with another repository's name is in a "
        f"read-only clone beside this one, `git clone https://github.com/{ORG}/<repo> ../<repo>`):\n"
        + "\n".join(f"- {p}" for p in seed["pattern"]))


def deliverables_text(seed: dict) -> str:
    return "DELIVERABLES:\n" + "\n".join(f"- {d}" for d in seed["deliverables"])


def wrap_text(seed: dict) -> str:
    """The wrapping rule (ADR C): every attested computation is wrapped by
    a skill in the capability whose sphere it names. A seed names its wrap
    as `wrap: <capability>/<skill>`; a seed without one records why."""
    wrap = seed.get("wrap")
    if not wrap:
        return ("WRAP. Every attested computation is wrapped by a skill in the capability whose "
                "sphere it names, and this seed names none: the capability that would wrap it does "
                "not yet exist as a package, or the coordinator files the wrap separately. Leave "
                "`executor.skill` out of the concept, write the run instructions into the PR body "
                "(the coordinator carries them to the wrapping skill or the roadmap line), and expect "
                "the placement gate to report the concept as unwrapped (P6); that is the floor, not "
                "the goal.")
    cap, _, skill = wrap.partition("/")
    where = ("in this repository" if cap == seed["repo"] else
             f"in {cap}: clone it beside this repository, build the skill on a branch named `{seed['branch']}` "
             f"there, and open a second pull request against its main; the two are reviewed together")
    return (f"WRAP. The run instructions are the skill `{wrap}` (skills/{skill}/SKILL.md {where}). The "
            "skill invokes the executor by the installed bundle's path (`${CLAUDE_PLUGIN_ROOT}` for the "
            "capability's own bundle; the checkout named by the bundle's environment variable for a "
            "provider bundle, as ocean-science's receipt-figures skill does), states the parameters it "
            "binds and the runtime name it passes, and tells the agent to run the attester on the receipt "
            f"before quoting a number from it. The concept carries `executor.skill: {wrap}`.")


def render_computation(round_: dict, seed: dict) -> str:
    repo, bundle, branch = seed["repo"], seed["bundle"], seed["branch"]
    provider = repo == "nasa-daac-knowledge"
    if provider:
        format_text = (
            "FORMAT. Read docs/ in this repository and, from a read-only clone "
            f"`git clone https://github.com/{ORG}/marketplace ../marketplace`, "
            "marketplace/docs/contributing-knowledge.md and marketplace/docs/okf-conformance.md "
            "(section 10 on attested computations). "
            f"Update `{bundle}/index.md` (a line per concept in its computations and recipes "
            "sections), add one entry at the top of `" + bundle + "/log.md` naming what was built "
            f"and the sources read, and re-render the digest with `uv run tools/digest.py {bundle}`.")
        checks = (CHECKS["nasa-daac-knowledge"] + " Run the chain by hand as well (the fixture "
                  "run, the attester, the refusal, the loader selftests, the data-root check, the "
                  "record run attested) and paste the commands and their last lines into the PR body.")
    else:
        format_text = (
            "FORMAT. Clone read-only beside the repository: "
            f"`git clone https://github.com/{ORG}/marketplace ../marketplace`, likewise "
            "../nasa-daac-knowledge and ../build-kit (and ../hydrology when a pattern names it). "
            "Read marketplace/docs/contributing-knowledge.md and marketplace/docs/okf-conformance.md "
            "(section 10 on attested computations). "
            f"Update `{bundle}/index.md` (a line per concept in its computations and recipes "
            f"sections) and add one entry at the top of `{bundle}/log.md` naming what was built "
            "and the sources read.")
        checks = (CHECKS["plugin"] + " Then `uv run <the attester> --selftest` and the golden "
                  "named in the deliverables (`uv run verification/<golden>.py`) must pass; the "
                  "golden runs the fixture chain, the refusal and the record run on the committed "
                  "root, in the shape of hydrology's verification/basin_water_balance.py, and "
                  "touches no network.")
    spheres = ", ".join(seed.get("spheres") or [])
    return f"""You are building an attested computation for the Open Science Pillars organization (github.com/{ORG}) in the repository {repo}, on a new branch `{branch}` created from main. A coordinator session dispatched you and will review, merge, wire the check chain and reconcile the roadmap; you build, check, push and open one pull request per repository you touch. Do not merge anything, do not sign anything, never set a status other than `draft` on a concept you create. {others_text(round_, seed)}BOUNDARY: {seed['boundary']} This seed is issue #{seed['issue']} in {repo}; reference it in the PR body. Spheres: {spheres}.

WHAT TO BUILD ({seed['title']}). {seed['scope'].strip()}

{deliverables_text(seed)}

{pattern_text(seed)}

{wrap_text(seed)}
{context_text(seed)}
SOURCES, and what to read on each:
{sources_text(seed)}

HOW TO READ THEM. {FETCH} {TOKEN}
{dnr_text(seed)}
{format_text}

RULES. {CONTENT_RULES} {EXECUTOR_RULES} {LOADER_RULES} {CONCEPT_RULES} {NO_CHECK_EDIT}

CHECKS BEFORE PUSHING: {checks}

COMMIT, PUSH, PR. `git commit -s` (DCO sign-off) with the attribution lines your session instructions give you. Push the branch and open one pull request against main in {repo} with a body listing each file built and each concept, the fixture and real-data receipts' headline numbers with the published anchor, the sources and files fetched with dates and hashes, what could not be fetched, the chain commands for the coordinator, {pr_body_common()}, and the line "Computation PR: merges on the coordinator's review of the chain and the concepts, on the maintainer's behalf". {report_text()}
"""


def render_data_root(round_: dict, seed: dict) -> str:
    repo, bundle, branch = seed["repo"], seed["bundle"], seed["branch"]
    checks = (CHECKS["nasa-daac-knowledge"] if repo == "nasa-daac-knowledge" else CHECKS["plugin"]) + (
        " Then each loader's `--selftest` and the data-root tool's `--check` on the committed "
        "root must pass; paste the commands and their last lines into the PR body.")
    spheres = ", ".join(seed.get("spheres") or [])
    return f"""You are building a stamped data root for the Open Science Pillars organization (github.com/{ORG}) in the repository {repo}, on a new branch `{branch}` created from main. A coordinator session dispatched you and will review, merge, wire the check lines and reconcile the roadmap; you build, check, push and open one pull request. Do not merge anything, do not sign anything, write no concept. {others_text(round_, seed)}BOUNDARY: {seed['boundary']} This seed is issue #{seed['issue']} in {repo}; reference it in the PR body. Spheres: {spheres}.

WHAT TO BUILD ({seed['title']}). {seed['scope'].strip()}

{deliverables_text(seed)}

{pattern_text(seed)}
{context_text(seed)}
SOURCES, and what to read on each:
{sources_text(seed)}

HOW TO READ THEM. {FETCH} {TOKEN}
{dnr_text(seed)}
FORMAT. Read docs/ in this repository for the reference file conventions. Keep the pattern loaders' argument names, stamp keys and RECORD.json layout so the wave B computation reads this root the way the sea level budget reads its own. The bookkeeping table in RECORD.json states, per term, the product and version, the forcing, the grid, the mask and aggregation, the units, the sign convention and the uncertainty basis, and names the alternates not read.

RULES. {CONTENT_RULES} {LOADER_RULES} No concept, index, log or DIGEST edits. {NO_CHECK_EDIT_ROOT}

CHECKS BEFORE PUSHING: {checks}

COMMIT, PUSH, PR. `git commit -s` (DCO sign-off) with the attribution lines your session instructions give you. Push the branch and open one pull request against main in {repo} with a body listing each file built, the per-term aggregate numbers over the record with their units and the mask used, the sources and files fetched with dates and hashes, what could not be fetched, the check lines for the coordinator, {pr_body_common()}, and the line "Data-root PR: merges on green CI and the coordinator's review". {report_text()}
"""


def render_connector(round_: dict, seed: dict) -> str:
    repo, bundle, branch = seed["repo"], seed["bundle"], seed["branch"]
    checks = CHECKS["core"] if repo == "core" else CHECKS["plugin"]
    spheres = ", ".join(seed.get("spheres") or [])
    return f"""You are extending a connector for the Open Science Pillars organization (github.com/{ORG}) in the repository {repo}, on a new branch `{branch}` created from main. A coordinator session dispatched you and will review, merge and reconcile the roadmap; you build, check, push and open one pull request per repository you touch. Do not merge anything, do not sign anything, never set a status other than `draft` on a concept you create. {others_text(round_, seed)}BOUNDARY: {seed['boundary']} This seed is issue #{seed['issue']} in {repo}; reference it in the PR body. Spheres: {spheres}.

WHAT TO BUILD ({seed['title']}). {seed['scope'].strip()}

{deliverables_text(seed)}

{pattern_text(seed)}
{context_text(seed)}
SOURCES, and what to read on each:
{sources_text(seed)}

HOW TO READ THEM. {FETCH} The environment holds an Earthdata Login bearer token in `EARTHDATA_TOKEN` for a source that needs one (Hydrocron does not; say in CONNECTORS.md which tools need no credential): use it only as the header `-H "Authorization: Bearer $EARTHDATA_TOKEN"`, never print, echo, log, store or commit it, and never write it into a fixture, a commit or a PR body.
{dnr_text(seed)}
FORMAT. Clone read-only beside the repository: `git clone https://github.com/{ORG}/marketplace ../marketplace`, likewise ../nasa-daac-knowledge, ../build-kit, ../hydrology and ../ocean-science (the last two are where the connector concepts go, on the same branch name, each as its own PR). Read marketplace/docs/contributing-knowledge.md and marketplace/docs/okf-conformance.md for the concept format and CONNECTORS.md in this repository for the disclosure shape.

RULES. {CONTENT_RULES} {CONNECTOR_RULES}

CHECKS BEFORE PUSHING: {checks} In each concept repository, {CHECKS['plugin']}

COMMIT, PUSH, PR. `git commit -s` (DCO sign-off) with the attribution lines your session instructions give you. Push the branch and open one pull request against main in {repo}, and one in each concept repository, with bodies listing each tool and its source, what leaves the machine, whether the fixture was recorded live or written by hand, the sources fetched with dates, what could not be fetched, {pr_body_common()}, and the line "Connector PR: merges on green CI and the coordinator's review" (the concept PRs carry "Knowledge PR: merges on the maintainer's review" instead). {report_text()}
"""


RENDERERS = {
    "knowledge": render_knowledge,
    "computation": render_computation,
    "connector": render_connector,
    "data-root": render_data_root,
}


def render(round_: dict, seed: dict) -> str:
    kind = seed.get("kind", "knowledge")
    if kind not in RENDERERS:
        sys.exit(f"{seed['id']}: unknown kind {kind!r}; one of {', '.join(KINDS)}")
    return RENDERERS[kind](round_, seed)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("round_file", type=Path)
    ap.add_argument("--seed")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--wave", help="render every seed of this wave")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--out", type=Path)
    a = ap.parse_args()
    round_ = yaml.safe_load(a.round_file.read_text(encoding="utf-8"))
    seeds = {s["id"]: s for s in round_["seeds"]}
    if a.list:
        for s in round_["seeds"]:
            print(f"{s['id']:34} {s.get('wave', '-'):2} {s.get('kind', 'knowledge'):12} "
                  f"{s['repo']:22} {s['bundle']:28} {s['branch']:38} #{s['issue']}")
        return
    if a.all:
        chosen = list(seeds.values())
    elif a.wave:
        chosen = [s for s in seeds.values() if s.get("wave") == a.wave]
    elif a.seed in seeds:
        chosen = [seeds[a.seed]]
    else:
        chosen = None
    if not chosen:
        sys.exit("name a seed with --seed, a wave with --wave, or --all")
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
