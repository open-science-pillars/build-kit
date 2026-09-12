from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location("qualify_tool", SCRIPTS / "qualify.py")
q = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(q)


def write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) if path.suffix == ".json" else yaml.safe_dump(data, sort_keys=False))


def capability(root: Path, name="ocean-science", deps=True, reach=True):
    repo = root / name
    write(repo / ".osp" / "repository.yaml", {
        "schema_version": 1, "repository": {"name": name, "kind": "capability", "status": "available"},
        "classification": {"spheres": ["hydrosphere"], "primary_sphere": "hydrosphere", "discipline": "Ocean Physics"}})
    pkg = {"schema_version": 1, "package": {"name": name, "version": "0.8.2", "type": "capability"},
           "content": {"skills": "./skills", "verification": "./verification"},
           "dependencies": {"capabilities": [{"name": "core", "version": ">=0.5.0"}] if deps else [], "knowledge": []},
           "metadata": {"description": "Physical oceanography."}}
    if reach:
        pkg["reach"] = {"servers": {"earthdata": {"type": "streamable-http", "url": "https://cmr.earthdata.nasa.gov/mcp/v1"}}}
    write(repo / ".osp" / "package.yaml", pkg)
    write(repo / ".osp" / "surfaces.yaml", {
        "schema_version": 1,
        "surfaces": {"claude-code": {"role": ["development", "runtime"], "required": True, "status": "supported"}},
        "qualification": {"require": ["install", "skill-discovery", "skill-invocation", "knowledge-resolution",
                                      "dependency-resolution", "golden-computation", "prove", "receipt", "release-lock"]},
        "probes": {"skill-invocation": {"skill": "ecco", "prompt": "Load ECCO for me.", "expect": ["ECCO"]}},
    })
    for s in ("ecco", "start"):
        (repo / "skills" / s).mkdir(parents=True, exist_ok=True)
        (repo / "skills" / s / "SKILL.md").write_text(f"---\nname: {s}\ndescription: x\n---\n")
    write(repo / ".osp" / "release-lock.json", {"schema_version": 1, "package": name, "version": "0.8.2"})
    return repo


class QualifyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_parsers(self):
        details = "core 0.5.0\n  Description: x\n\nComponent inventory\n  Skills (3)  analysis-review, start, report\n  Agents (0)\n"
        self.assertEqual(["analysis-review", "start", "report"], q.parse_details_skills(details))
        mcp = ("Checking MCP server health…\n\n"
               "plugin:core:earthdata: https://cmr.earthdata.nasa.gov/mcp/v1 (HTTP) - ! Needs authentication\n"
               "plugin:core:observations: uv run /x/observations_mcp.py - √ Connected\n"
               "plugin:other:thing: x - √ Connected\n")
        self.assertEqual({"earthdata": "! Needs authentication", "observations": "√ Connected"}, q.parse_mcp_list(mcp, "core"))
        listing = ("Configured marketplaces:\n\n  > open-science-pillars\n    Source: GitHub (open-science-pillars/marketplace)\n"
                   "  > local-rc\n    Source: Local path (/tmp/rc/marketplace)\n")
        self.assertEqual({"open-science-pillars": "GitHub (open-science-pillars/marketplace)",
                          "local-rc": "Local path (/tmp/rc/marketplace)"}, q.parse_marketplace_list(listing))
        self.assertTrue(q.floor_satisfied("0.5.0", ">=0.5.0"))
        self.assertTrue(q.floor_satisfied("2026.9.3", ">=2026.9.2"))
        self.assertFalse(q.floor_satisfied("2026.9.1", ">=2026.9.2"))
        self.assertTrue(q.floor_satisfied("0.5.0", None))
        self.assertEqual([], q.expect_all("see knowledge/podaac/datasets/ecco-v4r4.md, status stable",
                                          [q.KNOWLEDGE_PATH.pattern, q.CONCEPT_STATUS.pattern]))
        self.assertEqual([q.SIZE_WORDS.pattern], q.expect_all("please confirm first", [q.GATE_WORDS.pattern, q.SIZE_WORDS.pattern]))

    def test_probes_merge_capability_overrides_with_defaults(self):
        cap = q.load_capability(capability(self.root))
        probes = q.probes_for(cap)
        self.assertEqual("ecco", probes["skill-invocation"]["skill"])
        self.assertEqual("Load ECCO for me.", probes["skill-invocation"]["prompt"])
        self.assertTrue(probes["skill-invocation"]["criteria"])  # default criteria kept
        self.assertIn("consult-knowledge", probes["knowledge-resolution"]["prompt"])
        self.assertIn("Download", probes["side-effect-confirmation"]["prompt"])
        bare = q.load_capability(capability(self.root, name="core", deps=False, reach=False))
        bare["probes"] = {}
        self.assertEqual("start", q.probes_for(bare)["skill-invocation"]["skill"])

    def test_verdict_needs_every_required_test(self):
        cap = q.load_capability(capability(self.root))
        tests = {t: {"status": "pass", "evidence": "x"} for t in cap["required"]}
        self.assertEqual((True, []), q.verdict(cap, tests))
        tests["prove"] = {"status": "blocked", "evidence": "no attester"}
        tests["dependency-resolution"] = {"status": "skip", "evidence": "none"}
        ok, blockers = q.verdict(cap, tests)
        self.assertFalse(ok)
        self.assertEqual(["prove: blocked"], blockers)
        del tests["release-lock"]
        self.assertIn("release-lock: not run", q.verdict(cap, tests)[1])

    def test_checklist_round_trip_and_record(self):
        cap = q.load_capability(capability(self.root))
        path = self.root / "cowork.yaml"
        q.write_checklist(cap, "claude-cowork", path)
        doc = yaml.safe_load(path.read_text())
        self.assertEqual("claude-cowork", doc["runtime"])
        by_test = {i["test"]: i for i in doc["tests"]}
        self.assertEqual(q.TESTS, list(by_test))
        self.assertEqual("Load ECCO for me.", by_test["skill-invocation"]["prompt"])
        self.assertEqual("blocked", by_test["prove"]["status"])
        self.assertEqual("", by_test["install"]["status"])
        # an unfilled checklist is refused, naming what is missing
        with self.assertRaises(q.QualifyError) as ctx:
            q.read_checklist(cap, "claude-cowork", path)
        self.assertIn("operator is empty", str(ctx.exception))
        self.assertIn("install: status '' is not", str(ctx.exception))
        doc.update(runtime_version="Cowork 1.4", model="claude-fable-5", date="2026-09-12", operator="pmr")
        for item in doc["tests"]:
            if not item["status"]:
                item["status"] = "pass"
                item["evidence"] = "seen"
        path.write_text(yaml.safe_dump(doc))
        tests, filled = q.read_checklist(cap, "claude-cowork", path)
        rec = q.make_record(cap, "claude-cowork", "Cowork 1.4", "checklist by pmr", tests, ["claude-fable-5"], None, "0.8.2")
        self.assertFalse(rec["qualified"])
        self.assertEqual(["prove: blocked", "receipt: blocked"], rec["blockers"])
        self.assertEqual("claude", rec["runtime"]["projection"])
        self.assertEqual(cap["lock_digest"], rec["release_lock"])
        # the wrong capability is refused
        doc["version"] = "9.9.9"
        path.write_text(yaml.safe_dump(doc))
        with self.assertRaises(q.QualifyError):
            q.read_checklist(cap, "claude-cowork", path)

    def test_status_reads_records(self):
        cap = q.load_capability(capability(self.root))
        rec = q.make_record(cap, "claude-code", "2.1", "headless", {t: {"status": "pass", "evidence": "x"} for t in cap["required"]},
                            ["m"], None, "0.8.2")
        write(cap["dir"] / ".osp" / "qualification" / "claude-code.json", rec)
        import io, contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            q.print_status(cap, None)
        self.assertIn("claude-code: QUALIFIED", buf.getvalue())
