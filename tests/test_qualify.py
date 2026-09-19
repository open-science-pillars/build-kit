from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

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

    def test_a_candidate_catalog_registered_from_elsewhere_is_stale(self):
        """The candidate catalog's name outlives its directory.

        Every candidate run writes osp-candidate to a fresh directory, so
        the registration from the previous capability's run is still there
        under the same name. Taking that name would install the previous
        capability, or fail with "not found in marketplace", which reads
        like a broken package. The name must be re-pointed instead."""
        here = Path(self.tmp.name) / "candidate-marketplace"
        (here / ".claude-plugin").mkdir(parents=True)
        (here / ".claude-plugin" / "marketplace.json").write_text(
            json.dumps({"name": "osp-candidate", "plugins": []}), encoding="utf-8")
        listing = ("Configured marketplaces:\n\n  > osp-candidate\n"
                   "    Source: Directory (/tmp/some-older-run/candidate-marketplace)\n")
        with mock.patch.object(q, "run", return_value=types.SimpleNamespace(
                returncode=0, stdout=listing, stderr="")):
            with self.assertRaises(q.StaleMarketplace) as bad:
                q.marketplace_name(str(here))
        self.assertEqual("osp-candidate", bad.exception.name)

        # registered from this run's own directory, so it is this run's
        mine = ("Configured marketplaces:\n\n  > osp-candidate\n"
                f"    Source: Directory ({here})\n")
        with mock.patch.object(q, "run", return_value=types.SimpleNamespace(
                returncode=0, stdout=mine, stderr="")):
            self.assertEqual("osp-candidate", q.marketplace_name(str(here)))

    def test_register_marketplace_repoints_a_stale_name(self):
        here = Path(self.tmp.name) / "candidate-marketplace"
        (here / ".claude-plugin").mkdir(parents=True)
        (here / ".claude-plugin" / "marketplace.json").write_text(
            json.dumps({"name": "osp-candidate", "plugins": []}), encoding="utf-8")
        stale = ("Configured marketplaces:\n\n  > osp-candidate\n"
                 "    Source: Directory (/tmp/some-older-run/candidate-marketplace)\n")
        fresh = ("Configured marketplaces:\n\n  > osp-candidate\n"
                 f"    Source: Directory ({here})\n")
        calls = []

        def fake(cmd, **kw):
            calls.append(cmd)
            if cmd[:4] == ["claude", "plugin", "marketplace", "list"]:
                out = stale if len([c for c in calls if c[3] == "add"]) == 0 else fresh
                return types.SimpleNamespace(returncode=0, stdout=out, stderr="")
            return types.SimpleNamespace(returncode=0, stdout="", stderr="")

        with mock.patch.object(q, "run", side_effect=fake):
            self.assertEqual("osp-candidate", q.register_marketplace(str(here)))
        verbs = [c[3] for c in calls if c[:3] == ["claude", "plugin", "marketplace"]]
        self.assertEqual(["list", "remove", "add", "list"], verbs)

        self.assertTrue(q.floor_satisfied("0.5.0", ">=0.5.0"))
        self.assertTrue(q.floor_satisfied("2026.9.3", ">=2026.9.2"))
        self.assertFalse(q.floor_satisfied("2026.9.1", ">=2026.9.2"))
        self.assertTrue(q.floor_satisfied("0.5.0", None))
        self.assertEqual([], q.expect_all("see knowledge/podaac/datasets/ecco-v4r4.md, status stable",
                                          [q.KNOWLEDGE_PATH.pattern, q.CONCEPT_STATUS.pattern]))
        self.assertEqual([q.SIZE_WORDS.pattern], q.expect_all("please confirm first", [q.GATE_WORDS.pattern, q.SIZE_WORDS.pattern]))
        # a bare year in a probe's expect list is an int by the time YAML is
        # done with it, and it stands for the text a plan has to contain
        self.assertEqual([], q.expect_all("the window is 2003-01:2016-12", [2003]))
        self.assertEqual(["2019"], q.expect_all("the window is 2003-01:2016-12", [2019]))
        with self.assertRaises(q.QualifyError):
            q.expect_all("x", ["ice-sheet["])

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

    def test_golden_scripts_leave_the_prove_scripts_out(self):
        cap = q.load_capability(capability(self.root))
        ver = cap["dir"] / "verification"
        ver.mkdir()
        for n in ("analysis_pipeline.py", "trend_computation.py", "trend_attester.py"):
            (ver / n).write_text("")
        self.assertEqual([ver / "analysis_pipeline.py", ver / "trend_attester.py", ver / "trend_computation.py"],
                         q.golden_scripts(cap, cap["dir"]))
        cap["probes"]["prove"] = {"prompt": "run ${PLUGIN_ROOT}/verification/trend_computation.py",
                                  "command": ["uv", "run", "${PLUGIN_ROOT}/verification/trend_attester.py"]}
        self.assertEqual([ver / "analysis_pipeline.py"], q.golden_scripts(cap, cap["dir"]))
        cap["probes"]["golden-computation"] = ["verification/analysis_pipeline.py"]
        self.assertEqual([cap["dir"] / "verification/analysis_pipeline.py"], q.golden_scripts(cap, cap["dir"]))

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


class WaiverAndCandidateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.cap = q.load_capability(capability(self.root))

    def tearDown(self):
        self.tmp.cleanup()

    def test_waiver_record(self):
        rec = q.waive(self.cap, "claude-cowork", "no shell on Cowork", "pmr", None)
        self.assertFalse(rec["qualified"])
        self.assertEqual("pmr", rec["waived"]["by"])
        self.assertEqual("0.8.2", rec["version"])
        self.assertEqual("waiver", rec["source"])
        # an existing record for this version keeps its tests
        path = q.record_path(self.cap, "claude-cowork", None)
        path.parent.mkdir(parents=True, exist_ok=True)
        full = q.make_record(self.cap, "claude-cowork", "1.0", "checklist by pmr",
                             {"install": {"status": "pass", "evidence": "x"}, "prove": {"status": "blocked", "evidence": "no shell"}},
                             ["m"], None, "0.8.2")
        path.write_text(json.dumps(full))
        rec = q.waive(self.cap, "claude-cowork", "no shell on Cowork", "pmr", None)
        self.assertIn("install", rec["tests"])
        self.assertEqual("checklist by pmr", rec["source"])
        self.assertTrue(rec["waived"])

    def test_candidate_catalog_is_a_marketplace_over_the_checkout(self):
        capability(self.root, name="core", deps=False, reach=False)
        root = q.candidate_catalog(self.cap, self.root / "work")
        cat = json.loads((root / ".claude-plugin" / "marketplace.json").read_text())
        self.assertEqual("osp-candidate", cat["name"])
        self.assertEqual("./plugins/ocean-science", cat["plugins"][0]["source"])
        self.assertTrue((root / "plugins" / "ocean-science" / ".osp" / "package.yaml").is_file())
        self.assertTrue((root / "plugins" / "ocean-science" / "skills" / "ecco" / "SKILL.md").is_file())

    def test_candidate_catalog_carries_the_declared_dependencies(self):
        """The installed manifest addresses a dependency at the marketplace
        it came from, so a candidate catalog holding only the capability
        installs a package whose dependencies cannot resolve. The published
        catalog cannot stand in: a candidate's floor is usually the release
        being cut beside it, whose tag does not exist until after the
        candidate merges."""
        capability(self.root, name="core", deps=False, reach=False)
        root = q.candidate_catalog(self.cap, self.root / "work")
        cat = json.loads((root / ".claude-plugin" / "marketplace.json").read_text())
        self.assertEqual(["ocean-science", "core"], [p["name"] for p in cat["plugins"]])
        self.assertEqual("./plugins/core", cat["plugins"][1]["source"])
        self.assertTrue((root / "plugins" / "core" / ".osp" / "package.yaml").is_file())

    def test_candidate_catalog_refuses_a_dependency_that_is_not_beside_it(self):
        with self.assertRaises(q.QualifyError) as bad:
            q.candidate_catalog(self.cap, self.root / "work")
        self.assertIn("core", str(bad.exception))
        self.assertIn("is not there", str(bad.exception))
