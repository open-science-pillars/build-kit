#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml==6.0.2", "jsonschema==4.25.1"]
# ///
"""Runtime qualification of one installable capability (ADR B, the
runtime distribution note in the marketplace repository).

A runtime is advertised as supported for a release only when the release
passes the qualification matrix on it. This tool runs that matrix where a
runtime can be driven headlessly (Claude Code), writes a checklist for a
runtime that cannot (Claude Cowork; Codex until its leg is exercised),
turns a filled checklist into the same record, and reports the state per
runtime. Every record names the capability, its version and release lock,
the runtime and its version, the model, the date, and each test's status
with its evidence, so a support claim can be traced to the run behind it.

  qualify.py --capability core --surface claude-code [--marketplace SRC]
      install from the marketplace, then run every required test; write
      <capability>/.osp/qualification/claude-code.json and keep the
      transcripts under --evidence DIR
  qualify.py --capability core --surface claude-cowork --checklist FILE
      write the checklist (prompts verbatim, pass criteria) for a run by hand
  qualify.py --capability core --surface claude-cowork --from-checklist FILE
      validate the filled checklist and write the record from it
  qualify.py --capability core --surface claude-code --candidate
      the same, installing the candidate from a local catalog built from
      this checkout (what a maintainer runs on a release candidate)
  qualify.py --capability core --surface claude-cowork --waive --reason TEXT --by NAME
      record the decision to release without this surface: not qualified,
      not advertised, the release proceeds
  qualify.py --capability core --status
      the state per runtime from the records on disk

Statuses: pass, fail, skip (not applicable to this capability, with the
reason), blocked (needs something that does not exist yet, with the
reason). A capability is qualified on a runtime when every test its
surfaces file requires is pass or skip. A record never changes
surfaces.yaml by itself; advertising a runtime is the release step's
decision, taken on the record.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import yaml

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import osp  # noqa: E402

ORG = osp.ORG
DEFAULT_MARKETPLACE = f"{ORG}/marketplace"
TESTS = ["install", "skill-discovery", "skill-invocation", "knowledge-resolution", "dependency-resolution",
         "connector-invocation", "golden-computation", "prove", "receipt", "side-effect-confirmation",
         "release-lock"]
RUNTIMES = {"claude-code": "claude", "claude-cowork": "claude", "claude-science": "claude",
            "openai-codex": "agent-plugins", "gemini-cli": "agent-plugins", "goose": "agent-plugins"}
STATUSES = {"pass", "fail", "skip", "blocked"}
KNOWLEDGE_PATH = re.compile(r"knowledge/[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)+\.md")
CONCEPT_STATUS = re.compile(r"\b(stable|draft|deprecated)\b", re.I)
GATE_WORDS = re.compile(r"confirm|approv|proceed|before (?:I |we )?download|gate|permission", re.I)
SIZE_WORDS = re.compile(r"\b(?:gb|tb|mb|gigabyte|terabyte|size|estimate)\b", re.I)
DEFAULT_TURNS = 30
DEFAULT_TOOLS = "Read,Glob,Grep,Skill,Bash(claude plugin list*)"
GATE_TOOLS = "Read,Glob,Grep,Skill"
PROVE_TOOLS = "Read,Glob,Grep,Skill,Bash(uv run*)"


class QualifyError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# Canonical inputs
# ---------------------------------------------------------------------------

def load_capability(cap_dir: Path) -> dict[str, Any]:
    pkg = osp.read_package(cap_dir)
    repo_meta = osp.read_repository(cap_dir)
    if pkg is None or repo_meta is None:
        raise QualifyError(f"{cap_dir}: a capability under qualification carries .osp/package.yaml and .osp/repository.yaml")
    surfaces_path = cap_dir / ".osp" / "surfaces.yaml"
    surfaces = osp.load_yaml(surfaces_path) if surfaces_path.is_file() else None
    if surfaces is None:
        raise QualifyError(f"{cap_dir}: qualification is defined by .osp/surfaces.yaml, which is missing")
    lock_path = cap_dir / ".osp" / "release-lock.json"
    lock = osp.read_json(lock_path) if lock_path.is_file() else None
    return {"dir": cap_dir, "name": pkg["package"]["name"], "version": pkg["package"]["version"],
            "package": pkg, "repository": repo_meta, "surfaces": surfaces, "lock": lock,
            "lock_digest": osp.value_digest(lock) if lock is not None else None,
            "required": list(surfaces.get("qualification", {}).get("require", [])),
            "probes": dict(surfaces.get("probes") or {})}


def skill_names(root: Path, pkg: dict[str, Any]) -> list[str]:
    rel = (pkg.get("content") or {}).get("skills", "./skills")
    d = root / rel
    if not d.is_dir():
        return []
    return sorted(p.name for p in d.iterdir() if p.is_dir() and (p / "SKILL.md").is_file())


def golden_scripts(cap: dict[str, Any], root: Path) -> list[Path]:
    """The scripts the golden test runs, with no arguments: those the
    capability lists under probes.golden-computation, else every script
    at the top of its verification tree except the executor and attester
    the prove probe names (they take arguments and are the prove test)."""
    listed = cap["probes"].get("golden-computation")
    if listed:
        return [root / str(rel) for rel in listed]
    ver_rel = (cap["package"].get("content") or {}).get("verification")
    if not ver_rel or not (root / ver_rel).is_dir():
        return []
    prove = cap["probes"].get("prove") or {}
    prove_text = " ".join([str(prove.get("prompt", ""))] + [str(c) for c in prove.get("command") or []])
    return [s for s in sorted((root / ver_rel).glob("*.py")) if s.name not in prove_text]


def probes_for(cap: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """The prompts each conversational test uses, verbatim on every runtime:
    from surfaces.yaml `probes` where the capability states them, with the
    organization's defaults otherwise."""
    name = cap["name"]
    skills = skill_names(cap["dir"], cap["package"])
    reference = "start" if "start" in skills else (skills[0] if skills else None)
    defaults = {
        "skill-invocation": {
            "skill": reference,
            "prompt": ("What science tools do I have set up here, and what should I do next?"
                       if reference == "start" else f"Use the {reference} skill now and show me its result."),
            "expect": [re.escape(name)],
            "criteria": "The skill's screen appears without coaching: the capability is named, and the skill's "
                        "required behaviors are all present.",
        },
        "knowledge-resolution": {
            "prompt": "Consult the installed knowledge bundles the way the installed consult-knowledge skill sets "
                      "out (the installer's record names each bundle's root; the current directory is not one). "
                      "Name one concept by its bundle path (knowledge/<bundle>/<type>/<concept>.md) and state its "
                      "status. Do not load any data.",
            "expect": [KNOWLEDGE_PATH.pattern, CONCEPT_STATUS.pattern],
            "criteria": "A concept is cited by bundle path and its status (stable, draft or deprecated) is stated.",
        },
        "side-effect-confirmation": {
            "prompt": "Download every SWOT Level-2 KaRIn low-rate ocean granule for 2024 into ./data now.",
            "expect": [GATE_WORDS.pattern, SIZE_WORDS.pattern],
            "criteria": "Nothing is downloaded; the size is estimated and confirmation is asked for before any "
                        "download, conversationally.",
        },
    }
    out = {}
    for test, default in defaults.items():
        merged = dict(default)
        merged.update(cap["probes"].get(test) or {})
        out[test] = merged
    return out


# ---------------------------------------------------------------------------
# Claude Code: the runtime the tool drives headlessly
# ---------------------------------------------------------------------------

def run(cmd: list[str], timeout: int = 600, cwd: Path | None = None) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=cwd)
    except FileNotFoundError as exc:
        raise QualifyError(f"required command not found: {cmd[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        return subprocess.CompletedProcess(cmd, 124, exc.stdout or "", f"timed out after {timeout}s")


def claude_version() -> str | None:
    r = run(["claude", "--version"], timeout=60)
    return (r.stdout or r.stderr).strip().splitlines()[0] if (r.stdout or r.stderr).strip() else None


def plugin_list() -> list[dict[str, Any]]:
    r = run(["claude", "plugin", "list", "--json"], timeout=120)
    try:
        return json.loads(r.stdout or "[]")
    except json.JSONDecodeError as exc:
        raise QualifyError(f"claude plugin list --json: {exc}: {r.stdout[:200]}") from exc


def installed_entry(name: str, entries: list[dict[str, Any]], marketplace: str | None = None) -> dict[str, Any] | None:
    """The installer's entry for name; from the given marketplace when one is
    named, so a release candidate installed from a local catalog is never
    confused with the same package installed from the organization's."""
    for e in entries:
        pid = e.get("id", "")
        if marketplace and pid == f"{name}@{marketplace}":
            return e
        if not marketplace and pid.split("@", 1)[0] == name:
            return e
    return None


def parse_details_skills(text: str) -> list[str]:
    """The skill names `claude plugin details` prints: `Skills (12)  a, b, c`."""
    m = re.search(r"Skills\s*\((\d+)\)\s*(.*)", text)
    if not m:
        return []
    return [s.strip() for s in m.group(2).split(",") if s.strip()]


def parse_mcp_list(text: str, name: str) -> dict[str, str]:
    """{server: health} for the plugin's servers in `claude mcp list`."""
    out = {}
    for line in text.splitlines():
        m = re.match(rf"\s*plugin:{re.escape(name)}:([A-Za-z0-9_.-]+):\s*(.*)$", line)
        if m:
            server, rest = m.group(1), m.group(2)
            health = rest.rsplit(" - ", 1)[1].strip() if " - " in rest else rest.strip()
            out[server] = health
    return out


def parse_marketplace_list(text: str) -> dict[str, str]:
    """{name: source line} from `claude plugin marketplace list`."""
    out, current = {}, None
    for line in text.splitlines():
        m = re.match(r"\s*>\s*(\S+)\s*$", line)
        if m:
            current = m.group(1)
            out[current] = ""
            continue
        m = re.match(r"\s*Source:\s*(.*)$", line)
        if m and current:
            out[current] = m.group(1).strip()
    return out


class StaleMarketplace(QualifyError):
    """The catalog's name is registered, from somewhere else.

    A candidate catalog is always called osp-candidate and is written to a
    fresh directory for every run, so the name outlives the directory: the
    registration from the last capability's run is still there, pointing at
    a tree that holds the last capability. Installing against it fails with
    "not found in marketplace", which reads like a broken package and is
    not one. The caller re-points the registration; this carries the name
    to remove."""

    def __init__(self, name: str, source: str):
        super().__init__(f"marketplace {name} is registered from {source}, not from this run")
        self.name = name


def marketplace_name(marketplace: str) -> str:
    """The name the runtime registered the marketplace under (the catalog's
    own name, which is what `plugin@name` addresses), found from the
    marketplace list by its source, or from a local catalog file."""
    known = parse_marketplace_list(run(["claude", "plugin", "marketplace", "list"], timeout=120).stdout)
    needle = marketplace.rstrip("/").lower()
    for name, source in known.items():
        if needle and needle in source.lower():
            return name
    local = Path(marketplace)
    if local.is_dir():
        catalog = local / ".claude-plugin" / "marketplace.json"
        if catalog.is_file():
            name = osp.read_json(catalog).get("name")
            if name in known:
                raise StaleMarketplace(name, known[name])
    raise QualifyError(f"marketplace {marketplace} is not registered by the runtime; known: "
                       + (", ".join(f"{n} ({s})" for n, s in known.items()) or "none"))


def register_marketplace(marketplace: str) -> str:
    """The name to address `plugin@name` by, with the registration made to
    agree with this run: added when it is absent, re-pointed when the name
    is registered from another directory."""
    try:
        return marketplace_name(marketplace)
    except StaleMarketplace as stale:
        gone = run(["claude", "plugin", "marketplace", "remove", stale.name], timeout=600)
        if gone.returncode != 0:
            raise QualifyError(f"marketplace remove {stale.name} failed: "
                               f"{(gone.stderr or gone.stdout)[-300:]}") from stale
    add = run(["claude", "plugin", "marketplace", "add", marketplace], timeout=600)
    if add.returncode != 0:
        raise QualifyError(f"marketplace add {marketplace} failed: {(add.stderr or add.stdout)[-300:]}")
    return marketplace_name(marketplace)


def version_tuple(v: str) -> tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d+", v))


def floor_satisfied(installed: str, constraint: str | None) -> bool:
    if not constraint:
        return True
    m = re.match(r"^(>=|>|==|<=|<|~=)?\s*([0-9][0-9.]*)$", constraint)
    if not m:
        return False
    op, want = m.group(1) or ">=", m.group(2)
    a, b = version_tuple(installed), version_tuple(want)
    return {"": a >= b, ">=": a >= b, ">": a > b, "==": a == b, "<=": a <= b, "<": a < b,
            "~=": a >= b and a[:len(b) - 1] == b[:len(b) - 1]}[op]


def headless(prompt: str, tools: str, max_turns: int, model: str | None, timeout: int,
             cwd: Path | None = None) -> dict[str, Any]:
    """One headless Claude Code call with streamed JSON, reduced to what a
    test reads: the assistant's text, the tool calls, the model and the
    result status. The session's working directory is the only place it
    may write, so a test that expects a file launches the call there."""
    cmd = ["claude", "-p", prompt, "--allowedTools", tools, "--max-turns", str(max_turns),
           "--output-format", "stream-json", "--verbose"]
    if model:
        cmd += ["--model", model]
    r = run(cmd, timeout=timeout, cwd=cwd)
    text, tools_used, seen_model, status, turns = [], [], None, None, None
    by_id: dict[str, dict[str, Any]] = {}
    for line in (r.stdout or "").splitlines():
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        kind = ev.get("type")
        if kind == "system" and ev.get("subtype") == "init":
            seen_model = ev.get("model")
        elif kind == "system" and ev.get("subtype") == "permission_denied":
            if ev.get("tool_use_id") in by_id:
                by_id[ev["tool_use_id"]]["denied"] = True
        elif kind == "assistant":
            for block in ev.get("message", {}).get("content", []) or []:
                if block.get("type") == "text":
                    text.append(block["text"])
                elif block.get("type") == "tool_use":
                    call = {"name": block.get("name"), "denied": False, "error": None}
                    by_id[block.get("id")] = call
                    tools_used.append(call)
        elif kind == "user":
            for block in ev.get("message", {}).get("content", []) or []:
                if isinstance(block, dict) and block.get("type") == "tool_result" and block.get("tool_use_id") in by_id:
                    by_id[block["tool_use_id"]]["error"] = bool(block.get("is_error"))
        elif kind == "result":
            status, turns = ev.get("subtype"), ev.get("num_turns")
            if ev.get("result"):
                text.append(ev["result"])
    if r.returncode == 124:
        status = "timeout"
    # A tool call that was denied or errored had no effect; only the rest
    # can have touched anything.
    effective = [c["name"] for c in tools_used if not c["denied"] and not c["error"]]
    denied = [c["name"] for c in tools_used if c["denied"] or c["error"]]
    return {"text": "\n".join(text), "tools": effective, "attempted": denied, "model": seen_model, "status": status,
            "turns": turns, "raw": r.stdout or "", "stderr": r.stderr or ""}


def expect_all(text: str, patterns: list[Any]) -> list[str]:
    """The patterns that did not match.

    A pattern comes from a probe's expect list in surfaces.yaml, where a
    bare number (a window, a year, a count) is read by YAML as an int and
    would otherwise fail here with a TypeError from re, which tells a
    maintainer nothing about the file they wrote. Each is read as the
    text it stands for."""
    out = []
    for p in patterns:
        pattern = p if isinstance(p, str) else str(p)
        try:
            hit = re.search(pattern, text, re.I | re.S)
        except re.error as bad:
            raise QualifyError(f"probe expectation {pattern!r} is not a regular expression: {bad}") from bad
        if not hit:
            out.append(pattern)
    return out


def keep(evidence: Path | None, name: str, reply: dict[str, Any]) -> str:
    if evidence is None:
        return "transcript not kept"
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / f"{name}.jsonl").write_text(reply["raw"], encoding="utf-8")
    (evidence / f"{name}.txt").write_text(reply["text"], encoding="utf-8")
    if reply["stderr"]:
        (evidence / f"{name}.stderr").write_text(reply["stderr"], encoding="utf-8")
    return f"{name}.txt in the evidence directory"


def qualify_claude_code(cap: dict[str, Any], marketplace: str, model: str | None, evidence: Path | None,
                        max_turns: int, timeout: int, only: set[str] | None = None) -> dict[str, Any]:
    """Every test, or with `only` just those named (the install step still
    runs, since the others need the installed tree, and is recorded only
    when named): a single failed conversational test is re-run into the
    record rather than the whole matrix."""
    name, version, pkg = cap["name"], cap["version"], cap["package"]
    probes = probes_for(cap)
    tests: dict[str, dict[str, Any]] = {}
    models: set[str] = set()
    wanted = only or set(TESTS)

    def skip(test: str) -> bool:
        return test not in wanted
    # Every conversational call is launched from the work directory: a
    # neutral place with no project instructions or memory of its own, so a
    # trial reads only what the installed package gives it, and the one
    # place the runtime may write.
    work = evidence if evidence is not None else Path(tempfile.mkdtemp(prefix="osp-qualify-"))
    work.mkdir(parents=True, exist_ok=True)

    def record(test: str, status: str, evidence_text: str, **extra: Any) -> None:
        if skip(test):
            return
        tests[test] = {"status": status, "evidence": evidence_text, **extra}
        print(f"  {test}: {status.upper()}  {evidence_text[:160]}", flush=True)

    # install: from the marketplace, one action, dependencies with it
    mp_name = register_marketplace(marketplace)
    inst = run(["claude", "plugin", "install", f"{name}@{mp_name}", "--json", "-y"], timeout=900)
    entries = plugin_list()
    entry = installed_entry(name, entries, mp_name)
    if inst.returncode != 0 or entry is None:
        record("install", "fail", f"claude plugin install {name}@{mp_name}: {(inst.stdout or inst.stderr)[-300:]}")
        install_path = None
    elif entry.get("errors"):
        record("install", "fail", f"installed with errors: {entry['errors']}")
        install_path = Path(entry["installPath"])
    else:
        install_path = Path(entry["installPath"])
        record("install", "pass", f"{name} {entry.get('version')} installed from {mp_name} at {install_path}; "
                                  f"catalog entry {inst.stdout.strip()[:120]}",
               installed_version=entry.get("version"), install_path=str(install_path))
    installed_version = entry.get("version") if entry else None

    # dependency-resolution: every declared dependency installed, enabled, within its floor
    deps = osp.dependency_entries(pkg)
    if skip("dependency-resolution"):
        pass
    elif not deps:
        record("dependency-resolution", "skip", "no declared dependencies (a foundation package)")
    else:
        problems, found = [], []
        for d in deps:
            e = installed_entry(d["name"], entries)
            if e is None:
                problems.append(f"{d['name']} not installed")
            elif e.get("errors"):
                problems.append(f"{d['name']}: {e['errors']}")
            elif not e.get("enabled", True):
                problems.append(f"{d['name']} disabled")
            elif not floor_satisfied(str(e.get("version", "0")), d.get("version")):
                problems.append(f"{d['name']} {e.get('version')} is below {d.get('version')}")
            else:
                found.append(f"{d['name']} {e.get('version')}")
        record("dependency-resolution", "fail" if problems else "pass",
               "; ".join(problems) if problems else "resolved with the one install: " + ", ".join(found))

    # skill-discovery: the runtime's inventory names every canonical skill
    canonical = skill_names(install_path, pkg) if install_path else []
    details = run(["claude", "plugin", "details", name], timeout=120).stdout if not skip("skill-discovery") else ""
    discovered = parse_details_skills(details)
    missing = sorted(set(canonical) - set(discovered))
    if skip("skill-discovery"):
        pass
    elif not install_path:
        record("skill-discovery", "fail", "nothing installed to discover")
    elif missing:
        record("skill-discovery", "fail", f"not in the runtime's inventory: {', '.join(missing)}")
    else:
        record("skill-discovery", "pass", f"{len(discovered)} skills in the runtime's inventory, all {len(canonical)} canonical ones present")

    # skill-invocation: slash form and conversational form, no coaching
    p = probes["skill-invocation"]
    if skip("skill-invocation"):
        pass
    elif not p.get("skill"):
        record("skill-invocation", "skip", "the package carries no skills")
    else:
        results = []
        for form, prompt in (("slash", f"/{name}:{p['skill']}"), ("conversational", p["prompt"])):
            reply = headless(prompt, DEFAULT_TOOLS, max_turns, model, timeout, cwd=work)
            if reply["model"]:
                models.add(reply["model"])
            path = keep(evidence, f"skill-invocation-{form}", reply)
            unmatched = expect_all(reply["text"], p["expect"])
            ok = reply["status"] in {"success", "error_max_turns"} and reply["text"].strip() and not unmatched
            results.append((form, ok, reply["status"], reply["turns"], unmatched, path))
        ok_all = all(r[1] for r in results)
        record("skill-invocation", "pass" if ok_all else "fail",
               "; ".join(f"{form}: {'ok' if ok else 'unmatched ' + str(un)} ({st}, {turns} turns) {path}"
                         for form, ok, st, turns, un, path in results),
               skill=p["skill"], prompt=p["prompt"])

    # knowledge-resolution: a concept cited by bundle path with its status
    p = probes["knowledge-resolution"]
    if not skip("knowledge-resolution"):
        reply = headless(p["prompt"], DEFAULT_TOOLS, max_turns, model, timeout, cwd=work)
        if reply["model"]:
            models.add(reply["model"])
        path = keep(evidence, "knowledge-resolution", reply)
        unmatched = expect_all(reply["text"], p["expect"])
        cited = KNOWLEDGE_PATH.findall(reply["text"])
        record("knowledge-resolution", "pass" if not unmatched and reply["text"].strip() else "fail",
               (f"cited {', '.join(sorted(set(cited))[:3])} ({reply['status']}, {reply['turns']} turns) {path}"
                if not unmatched else f"unmatched {unmatched} ({reply['status']}) {path}"), prompt=p["prompt"])

    # connector-invocation: every declared server registered by the runtime and reachable
    servers = osp.reach_servers(pkg)
    if skip("connector-invocation"):
        pass
    elif not servers:
        record("connector-invocation", "skip", "no REACH declared")
    else:
        health = parse_mcp_list(run(["claude", "mcp", "list"], timeout=300).stdout, name)
        missing = sorted(set(servers) - set(health))
        failed = {s: h for s, h in health.items() if "connected" not in h.lower() and "auth" not in h.lower()}
        summary = "; ".join(f"{s}: {h}" for s, h in sorted(health.items()))
        if missing:
            record("connector-invocation", "fail", f"not registered by the runtime: {', '.join(missing)}; {summary}")
        elif failed:
            record("connector-invocation", "fail", summary)
        else:
            record("connector-invocation", "pass", f"registered as plugin:{name}:<server>; {summary}")

    # golden-computation: the installed package's golden scripts run green
    scripts = golden_scripts(cap, install_path) if install_path else []
    if skip("golden-computation"):
        pass
    elif not scripts:
        record("golden-computation", "skip", "no golden scripts declared")
    else:
        outcomes = []
        for s in scripts:
            r = run(["uv", "run", "--python", "3.11", str(s)], timeout=timeout, cwd=s.parent)
            outcomes.append((s.name, r.returncode, (r.stderr or "").strip().splitlines()[-1:] ))
            if evidence is not None:
                (evidence / f"golden-{s.stem}.log").write_text((r.stdout or "") + "\n" + (r.stderr or ""), encoding="utf-8")
        bad = [f"{n} exit {c} {tail}" for n, c, tail in outcomes if c != 0]
        record("golden-computation", "fail" if bad else "pass",
               "; ".join(bad) if bad else "green on the installed tree: " + ", ".join(n for n, _, _ in outcomes))

    # prove and receipt: the runtime produces the result by running the
    # shared executor, the attester verifies it, and the attestation names
    # the capability release and the runtime.
    prove = cap["probes"].get("prove") or {}
    if skip("prove") and skip("receipt"):
        pass
    elif not (prove.get("command") and prove.get("prompt")):
        for test in ("prove", "receipt"):
            record(test, "blocked", "no attester declared in surfaces.yaml probes.prove (prompt, receipt, command, "
                                    "attestation); the shared attester with its receipt is the r4-shared-prove deliverable")
    elif not install_path:
        for test in ("prove", "receipt"):
            record(test, "fail", "nothing installed to run the executor from")
    else:
        subs = {"${PLUGIN_ROOT}": str(install_path), "${WORK}": str(work), "${RUNTIME}": "claude-code"}

        def fill(value: str, work_as: str = str(work)) -> str:
            for k, v in subs.items():
                value = value.replace(k, work_as if k == "${WORK}" else v)
            return value

        # The runtime writes only inside its working directory, so the call
        # is launched in the work directory and told to write there.
        prompt = fill(prove["prompt"], work_as=".")
        reply = headless(prompt, PROVE_TOOLS, max_turns, model, timeout, cwd=work)
        if reply["model"]:
            models.add(reply["model"])
        path = keep(evidence, "prove-produce", reply)
        receipt_path = Path(fill(prove.get("receipt", "${WORK}/receipt.json")))
        if not receipt_path.is_file():
            record("prove", "fail", f"the runtime did not write the receipt {receipt_path.name} ({reply['status']}, "
                                    f"{reply['turns']} turns, tools that ran {sorted(set(reply['tools']))}, denied {sorted(set(reply['attempted']))}) {path}")
            record("receipt", "fail", "no receipt to attest")
        else:
            cmd = [fill(str(c)) for c in prove["command"]]
            r = run(cmd, timeout=timeout, cwd=install_path)
            if evidence is not None:
                (evidence / "prove-attest.log").write_text((r.stdout or "") + "\n" + (r.stderr or ""), encoding="utf-8")
            last = (r.stdout or r.stderr or "").strip().splitlines()[-1:] or [""]
            record("prove", "pass" if r.returncode == 0 else "fail",
                   f"the runtime wrote {receipt_path.name} ({reply['status']}, {reply['turns']} turns) {path}; "
                   f"attester exit {r.returncode}: {last[0][:160]}", prompt=prove["prompt"])
            att_path = Path(fill(prove.get("attestation", "${WORK}/attestation.json")))
            if not att_path.is_file():
                record("receipt", "fail", f"the attester wrote no attestation at {att_path.name}")
            else:
                att = osp.read_json(att_path)
                a_cap, a_rt = att.get("capability") or {}, att.get("runtime") or {}
                ok = (att.get("verdict") == "PASS" and a_cap.get("name") == name
                      and str(a_cap.get("version")) == str(installed_version) and a_rt.get("name") == "claude-code")
                record("receipt", "pass" if ok else "fail",
                       f"attestation {att.get('verdict')}: names {a_cap.get('name')} {a_cap.get('version')} "
                       f"(lock {a_cap.get('release_lock')}) on {a_rt.get('name')}; installed {installed_version}",
                       release_lock_in_receipt=a_cap.get("release_lock"))

    # side-effect-confirmation: the download gate appears conversationally
    p = probes["side-effect-confirmation"]
    if not skip("side-effect-confirmation"):
        reply = headless(p["prompt"], GATE_TOOLS, max_turns, model, timeout, cwd=work)
        if reply["model"]:
            models.add(reply["model"])
        path = keep(evidence, "side-effect-confirmation", reply)
        unmatched = expect_all(reply["text"], p["expect"])
        wrote = any(t in {"Write", "Bash", "Edit"} for t in reply["tools"])
        attempted = f"; denied attempts {sorted(set(reply['attempted']))}" if reply["attempted"] else ""
        record("side-effect-confirmation", "pass" if not unmatched and not wrote and reply["text"].strip() else "fail",
               (f"gate stated, nothing written ({reply['status']}, {reply['turns']} turns){attempted} {path}" if not unmatched and not wrote
                else f"unmatched {unmatched}, tools that ran {sorted(set(reply['tools']))}{attempted} ({reply['status']}) {path}"),
               prompt=p["prompt"])

    # release-lock: the installed tree carries the lock it digests to, at the version installed
    lock_path = install_path / ".osp" / "release-lock.json" if install_path else None
    if skip("release-lock"):
        pass
    elif not install_path or not lock_path.is_file():
        record("release-lock", "fail", f"the installed {name} {installed_version} carries no .osp/release-lock.json; "
                                       "a release cut before the lock existed cannot be qualified, the next release carries it")
    else:
        installed_lock = osp.read_json(lock_path)
        try:
            recomputed = osp.render_lock(install_path)
        except osp.OspError as exc:
            recomputed = None
            why = str(exc)
        digest = osp.value_digest(installed_lock)
        if installed_lock.get("version") != installed_version:
            record("release-lock", "fail", f"lock says {installed_lock.get('version')}, installed {installed_version}")
        elif recomputed != installed_lock:
            record("release-lock", "fail", f"the installed tree does not digest to its lock ({digest})" + (f": {why}" if recomputed is None else ""))
        else:
            same = " and equals the checkout's lock" if digest == cap["lock_digest"] else f" (the checkout's lock is {cap['lock_digest']})"
            record("release-lock", "pass", f"{digest} at {installed_version}, the installed tree digests to it{same}",
                   lock=digest)

    return {"tests": tests, "models": sorted(models), "installed_version": installed_version,
            "install_path": str(install_path) if install_path else None}


# ---------------------------------------------------------------------------
# Records and checklists
# ---------------------------------------------------------------------------

def verdict(cap: dict[str, Any], tests: dict[str, dict[str, Any]]) -> tuple[bool, list[str]]:
    blockers = []
    for t in cap["required"]:
        st = tests.get(t, {}).get("status")
        if st not in {"pass", "skip"}:
            blockers.append(f"{t}: {st or 'not run'}")
    return (not blockers, blockers)


def make_record(cap: dict[str, Any], runtime: str, runtime_ver: str | None, source: str, tests: dict[str, dict[str, Any]],
                models: list[str], evidence: Path | None, installed_version: str | None) -> dict[str, Any]:
    qualified, blockers = verdict(cap, tests)
    return {
        "schema_version": 1,
        "capability": cap["name"],
        "version": cap["version"],
        "installed_version": installed_version,
        "release_lock": cap["lock_digest"],
        "runtime": {"name": runtime, "projection": RUNTIMES[runtime], "version": runtime_ver},
        "models": models,
        "date": dt.datetime.now(dt.timezone.utc).date().isoformat(),
        "source": source,
        "required": cap["required"],
        "tests": tests,
        "qualified": qualified,
        "blockers": blockers,
        "evidence_dir": str(evidence) if evidence else None,
    }


def waive(cap: dict[str, Any], runtime: str, reason: str, by: str, record_dir: Path | None) -> dict[str, Any]:
    """The decision to release without a surface: a record for this version
    saying not qualified and waived by whom, why and when. An existing
    record for this version keeps its tests and gains the waiver."""
    path = record_path(cap, runtime, record_dir)
    rec = osp.read_json(path) if path.is_file() else None
    if not rec or str(rec.get("version")) != str(cap["version"]):
        rec = make_record(cap, runtime, None, "waiver", {}, [], None, None)
    rec["qualified"] = False
    rec["waived"] = {"by": by, "reason": reason, "date": dt.datetime.now(dt.timezone.utc).date().isoformat()}
    rec["blockers"] = rec.get("blockers") or [f"waived: {reason}"]
    return rec


def candidate_catalog(cap: dict[str, Any], where: Path) -> Path:
    """A local marketplace holding this checkout and every dependency it
    declares, so the candidate installs the way a release will.

    The dependencies belong in it for a reason the published catalog
    cannot cover: a candidate's floor is usually the release being cut
    beside it, whose tag does not exist until after the candidate merges,
    so the published entry would resolve to the previous release or to
    nothing. A dependency is taken from its sibling checkout in the
    workspace when one is there, which is the tree the candidate was
    written against; the installed manifest addresses dependencies at the
    marketplace it came from, so one missing here fails the install
    outright rather than falling back."""
    root = where / "candidate-marketplace"
    if root.exists():
        shutil.rmtree(root)
    ignore = shutil.ignore_patterns(".git", "dist", "__pycache__", "*.pyc")
    entries = [{"name": cap["name"], "description": f"{cap['name']} {cap['version']} release candidate",
                "source": f"./plugins/{cap['name']}"}]
    shutil.copytree(cap["dir"], root / "plugins" / cap["name"], ignore=ignore)
    workspace = cap["dir"].parent
    missing = []
    for dep in osp.dependency_entries(cap["package"]):
        beside = workspace / dep["name"]
        if not (beside / ".osp" / "package.yaml").is_file():
            missing.append(dep["name"])
            continue
        shutil.copytree(beside, root / "plugins" / dep["name"], ignore=ignore)
        entries.append({"name": dep["name"],
                        "description": f"{dep['name']} beside the candidate, for its qualification run",
                        "source": f"./plugins/{dep['name']}"})
    if missing:
        raise QualifyError(
            f"a candidate catalog for {cap['name']} needs every declared dependency beside it in "
            f"{workspace}, and {', '.join(missing)} is not there; check the workspace out first, "
            "because the published catalog cannot serve a floor whose tag is cut after this merges")
    (root / ".claude-plugin").mkdir(parents=True)
    catalog = {"name": "osp-candidate", "version": "0.0.0",
               "description": "Release candidate catalog for a qualification run; never published",
               "owner": {"name": "Open Science Pillars Community"},
               "plugins": entries}
    (root / ".claude-plugin" / "marketplace.json").write_text(json.dumps(catalog, indent=1), encoding="utf-8")
    return root


def record_path(cap: dict[str, Any], runtime: str, record_dir: Path | None) -> Path:
    return (record_dir or (cap["dir"] / ".osp" / "qualification")) / f"{runtime}.json"


def write_checklist(cap: dict[str, Any], runtime: str, path: Path) -> None:
    probes = probes_for(cap)
    items = []
    criteria = {
        "install": "The capability installs by one action after marketplace or source setup; every declared dependency arrives with it; the installed version is stated.",
        "skill-discovery": "Every canonical skill is listed by the runtime's inventory (name each).",
        "dependency-resolution": "Each declared dependency is installed within its floor; a missing one fails explicitly naming the floor.",
        "connector-invocation": "Each declared server is registered and reachable, or the runtime states why not.",
        "golden-computation": "The verification scripts run green from the installed package.",
        "prove": "The attester runs on the runtime's output.",
        "receipt": "The receipt names this release.",
        "release-lock": "The installed package carries .osp/release-lock.json at the installed version; its digest is stated.",
    }
    for t in TESTS:
        item = {"test": t, "required": t in cap["required"], "status": "", "evidence": ""}
        probe = probes.get(t)
        if probe:
            item["prompt"] = probe["prompt"]
            item["criteria"] = probe["criteria"]
            if probe.get("skill"):
                item["skill"] = probe["skill"]
        else:
            item["criteria"] = criteria.get(t, "")
        if t == "dependency-resolution" and not osp.dependency_entries(cap["package"]):
            item.update(status="skip", evidence="no declared dependencies")
        if t == "connector-invocation" and not osp.reach_servers(cap["package"]):
            item.update(status="skip", evidence="no REACH declared")
        prove = cap["probes"].get("prove") or {}
        if t in {"prove", "receipt"} and not (prove.get("command") and prove.get("prompt")):
            item.update(status="blocked", evidence="no attester declared; r4-shared-prove")
        elif t == "prove":
            item["prompt"] = prove["prompt"].replace("${RUNTIME}", runtime)
            item["criteria"] = ("The runtime runs the shared executor and writes the receipt (${PLUGIN_ROOT} is the "
                                "installed package's root, ${WORK} a directory you choose); then the attester command "
                                "passes on it: " + " ".join(str(c) for c in prove["command"]))
        elif t == "receipt":
            item["criteria"] = "The attestation says PASS and names this capability version and the runtime."
        items.append(item)
    doc = {
        "capability": cap["name"], "version": cap["version"], "release_lock": cap["lock_digest"],
        "runtime": runtime, "runtime_version": "", "model": "", "date": "", "operator": "",
        "instructions": ("Run each test on the runtime by hand, the prompts verbatim, no coaching. Fill status with "
                         "pass, fail, skip or blocked and evidence with what you saw (one line; a path to a "
                         "screenshot or transcript is best). Then: qualify.py --capability {name} --surface "
                         f"{runtime} --from-checklist {path.name}").replace("{name}", cap["name"]),
        "tests": items,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=100), encoding="utf-8")


def read_checklist(cap: dict[str, Any], runtime: str, path: Path) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    doc = osp.load_yaml(path)
    errors = []
    if doc.get("capability") != cap["name"] or str(doc.get("version")) != str(cap["version"]):
        errors.append(f"checklist is for {doc.get('capability')} {doc.get('version')}, not {cap['name']} {cap['version']}")
    if doc.get("runtime") != runtime:
        errors.append(f"checklist is for runtime {doc.get('runtime')}, not {runtime}")
    for field in ("runtime_version", "model", "date", "operator"):
        if not str(doc.get(field) or "").strip():
            errors.append(f"{field} is empty")
    tests = {}
    for item in doc.get("tests", []):
        t, st, ev = item.get("test"), str(item.get("status") or "").strip(), str(item.get("evidence") or "").strip()
        if t not in TESTS:
            errors.append(f"unknown test {t!r}")
            continue
        if st not in STATUSES:
            errors.append(f"{t}: status {st!r} is not pass, fail, skip or blocked")
            continue
        if not ev:
            errors.append(f"{t}: evidence is empty")
            continue
        tests[t] = {"status": st, "evidence": ev}
        for k in ("prompt", "skill"):
            if item.get(k):
                tests[t][k] = item[k]
    if errors:
        raise QualifyError("checklist not accepted:\n  " + "\n  ".join(errors))
    return tests, doc


def print_status(cap: dict[str, Any], record_dir: Path | None) -> int:
    d = record_dir or (cap["dir"] / ".osp" / "qualification")
    print(f"{cap['name']} {cap['version']} (lock {cap['lock_digest'] or 'none'}); required: {', '.join(cap['required'])}")
    found = 0
    for rt in RUNTIMES:
        p = d / f"{rt}.json"
        if not p.is_file():
            continue
        found += 1
        rec = osp.read_json(p)
        stale = "" if rec.get("release_lock") == cap["lock_digest"] and str(rec.get("version")) == str(cap["version"]) \
            else f" (recorded for {rec.get('version')} lock {rec.get('release_lock')}; stale)"
        if rec.get("waived"):
            stale = f" waived by {rec['waived'].get('by')}: {rec['waived'].get('reason')}"
        print(f"  {rt}: {'QUALIFIED' if rec.get('qualified') else 'not qualified'} on {rec.get('date')} "
              f"({rec.get('source')}, {rec['runtime'].get('version') or 'version unknown'}){stale}")
        for t, r in rec.get("tests", {}).items():
            print(f"    {t}: {r['status']}")
        for b in rec.get("blockers", []):
            print(f"    blocker: {b}")
    if not found:
        print("  no records")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--capability", required=True, help="the capability's directory name in the workspace, or a path")
    ap.add_argument("--surface", choices=sorted(RUNTIMES), help="the runtime to qualify on")
    ap.add_argument("--marketplace", default=DEFAULT_MARKETPLACE,
                    help="marketplace source to install from (a GitHub repo or a local path; the release under test is what its catalog names)")
    ap.add_argument("--model", default=None, help="model for the conversational tests (the runtime's default otherwise)")
    ap.add_argument("--evidence", default=None, help="directory to keep transcripts and logs")
    ap.add_argument("--record-dir", default=None, help="where the record is written (default: <capability>/.osp/qualification)")
    ap.add_argument("--max-turns", type=int, default=DEFAULT_TURNS)
    ap.add_argument("--timeout", type=int, default=1200, help="seconds per headless call or script")
    ap.add_argument("--checklist", help="write the checklist for a run by hand to this file")
    ap.add_argument("--from-checklist", help="read a filled checklist and write the record")
    ap.add_argument("--status", action="store_true", help="print the state per runtime from the records")
    ap.add_argument("--candidate", action="store_true",
                    help="install the candidate from a local catalog built from this checkout (the release will install "
                         "the same tree from the organization's catalog); overrides --marketplace")
    ap.add_argument("--only", default=None,
                    help="comma-separated tests to re-run into the existing record (a single failed conversational "
                         "test is re-run before it is a fail); the others keep their recorded outcome")
    ap.add_argument("--waive", action="store_true", help="record the decision to release without this surface")
    ap.add_argument("--reason", default=None, help="why the surface is waived (with --waive)")
    ap.add_argument("--by", default=None, help="who waives it (with --waive)")
    args = ap.parse_args()

    cap_path = Path(args.capability)
    cap_dir = cap_path.resolve() if cap_path.exists() else (osp.WORKSPACE / args.capability)
    try:
        cap = load_capability(cap_dir)
        record_dir = Path(args.record_dir).resolve() if args.record_dir else None
        if args.status:
            return print_status(cap, record_dir)
        if not args.surface:
            raise QualifyError("--surface is required unless --status")
        if args.checklist:
            write_checklist(cap, args.surface, Path(args.checklist))
            print(f"wrote {args.checklist}")
            return 0
        if args.waive:
            if not (args.reason and args.by):
                raise QualifyError("--waive needs --reason and --by")
            rec = waive(cap, args.surface, args.reason, args.by, record_dir)
            path = record_path(cap, args.surface, record_dir)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(osp.dump_json(rec), encoding="utf-8")
            print(f"{cap['name']} {cap['version']} on {args.surface}: WAIVED by {args.by}: {args.reason}")
            print(f"wrote {path}")
            return 0
        if args.from_checklist:
            tests, doc = read_checklist(cap, args.surface, Path(args.from_checklist))
            rec = make_record(cap, args.surface, str(doc["runtime_version"]), f"checklist by {doc['operator']}",
                              tests, [str(doc["model"])], None, cap["version"])
            rec["date"] = str(doc["date"])
        elif args.surface == "claude-code":
            evidence = Path(args.evidence).resolve() if args.evidence else None
            marketplace = args.marketplace
            source = f"headless run from {marketplace}"
            if args.candidate:
                marketplace = str(candidate_catalog(cap, evidence or Path(tempfile.mkdtemp(prefix="osp-candidate-"))))
                head = run(["git", "-C", str(cap["dir"]), "rev-parse", "--short", "HEAD"], timeout=30).stdout.strip()
                source = f"headless run against the release candidate (a local catalog built from the checkout at {head or 'unknown'})"
            print(f"qualifying {cap['name']} {cap['version']} on claude-code ({claude_version()}) from {marketplace}", flush=True)
            only = {t.strip() for t in args.only.split(",") if t.strip()} if args.only else None
            if only and not only <= set(TESTS):
                raise QualifyError(f"--only names tests outside the matrix: {sorted(only - set(TESTS))}")
            out = qualify_claude_code(cap, marketplace, args.model, evidence, args.max_turns, args.timeout, only)
            tests = out["tests"]
            models = out["models"]
            if only:
                previous_path = record_path(cap, "claude-code", record_dir)
                previous = osp.read_json(previous_path) if previous_path.is_file() else None
                if not previous or str(previous.get("version")) != str(cap["version"]):
                    raise QualifyError("--only re-runs into an existing record for this version; run the whole matrix first")
                merged = dict(previous.get("tests") or {})
                merged.update(tests)
                tests = merged
                models = sorted(set(previous.get("models") or []) | set(models))
                source = previous.get("source", source) + f"; {', '.join(sorted(only))} re-run on {dt.date.today().isoformat()}"
            rec = make_record(cap, "claude-code", claude_version(), source, tests, models, evidence, out["installed_version"])
            if evidence is None:
                rec["evidence_dir"] = "not kept"
        else:
            raise QualifyError(f"{args.surface} is not driven headlessly here; write a checklist with --checklist "
                               "and record the run with --from-checklist")
        path = record_path(cap, args.surface, record_dir)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(osp.dump_json(rec), encoding="utf-8")
        print(f"{cap['name']} {cap['version']} on {args.surface}: {'QUALIFIED' if rec['qualified'] else 'NOT QUALIFIED'}")
        for b in rec["blockers"]:
            print(f"  blocker: {b}")
        print(f"wrote {path}")
        return 0 if rec["qualified"] else 1
    except (QualifyError, osp.OspError) as exc:
        print(f"qualify: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
