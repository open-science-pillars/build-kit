from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_qualify import capability, q, write  # noqa: E402

SPEC = importlib.util.spec_from_file_location("release_tickets", SCRIPTS / "release_tickets.py")
rt = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(rt)


class FakeGitHub:
    """Records the writes and answers the reads the tool makes."""

    def __init__(self):
        self.issues: list[dict] = []
        self.comments: list[dict] = []
        self.labels = [{"name": "bug"}]
        self.writes: list[tuple] = []

    def __call__(self, args, dry_run=False, payload=None):
        path = args[-1] if payload is None else args[-1]
        if payload is None and "-X" not in args:
            if path.startswith("repos/o/r/labels"):
                return self.labels
            if path.startswith("repos/o/r/issues?"):
                return [i for i in self.issues if i["state"] == "open"]
            if "/comments" in path:
                return self.comments
            raise AssertionError(path)
        if dry_run:
            return None
        self.writes.append((args[1], path, payload))
        if path == "repos/o/r/labels":
            self.labels.append({"name": payload["name"]})
        elif path == "repos/o/r/issues":
            issue = {"number": len(self.issues) + 1, "title": payload["title"], "body": payload["body"], "state": "open"}
            self.issues.append(issue)
            return issue
        elif path.startswith("repos/o/r/issues/comments/"):
            cid = int(path.rsplit("/", 1)[1])
            for c in self.comments:
                if c["id"] == cid:
                    c["body"] = payload["body"]
        elif path.endswith("/comments"):
            number = int(path.split("/")[4])
            if number == 99:   # the pull request
                self.comments.append({"id": len(self.comments) + 1, "body": payload["body"]})
        elif args[1] == "PATCH" and path.startswith("repos/o/r/issues/"):
            number = int(path.rsplit("/", 1)[1])
            if "state" in payload:
                self.issues[number - 1]["state"] = payload["state"]
            if "body" in payload:
                self.issues[number - 1]["body"] = payload["body"]
        return None


class ReleaseTicketTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        repo = capability(self.root)
        surfaces = {
            "schema_version": 1,
            "surfaces": {
                "claude-code": {"role": ["development", "runtime"], "required": True, "status": "supported"},
                "claude-cowork": {"role": "runtime", "required": True, "status": "tested"},
                "openai-codex": {"role": "runtime", "required": True, "status": "planned"},
                "claude-science": {"role": "future-runtime", "required": False, "status": "limited-release"},
            },
            "qualification": {"require": ["install", "skill-discovery", "skill-invocation"]},
            "probes": {"skill-invocation": {"skill": "ecco", "prompt": "Load ECCO for me.", "expect": ["ECCO"]}},
        }
        write(repo / ".osp" / "surfaces.yaml", surfaces)
        write(repo / ".osp" / "governance.yaml", {
            "schema_version": 2, "repository": "ocean-science",
            "maintainers": {"users": ["someone"], "teams": ["hydrosphere-maintainers"], "status": "interim"},
            "runtime_maintainers": {"claude-cowork": {"users": [], "teams": ["runtime-cowork-maintainers"], "status": "interim"},
                                    "openai-codex": {"users": [], "teams": ["runtime-codex-maintainers"], "status": "interim"}},
            "roadmap": {"proposals": "enabled", "authority": "repository-maintainers"},
            "reviews": {"ordinary": 1, "cross_repository": "org-policy", "knowledge": "org-knowledge-policy"}})
        self.cap = q.load_capability(repo)
        self.gh = FakeGitHub()
        rt.gh = self.gh

    def tearDown(self):
        self.tmp.cleanup()

    def test_tickets_open_for_missing_decisions_and_close_on_records(self):
        rt.sync("o/r", 99, self.cap, dry_run=False)
        bodies = [i["body"] for i in self.gh.issues]
        self.assertTrue(any("needs a decision for **OpenAI Codex**" in b for b in bodies), bodies[0][:200])
        self.assertFalse(any("decision for **agent-plugins**" in b or "decision for **claude**" in b for b in bodies))
        titles = sorted(i["title"] for i in self.gh.issues)
        self.assertEqual(["Qualify ocean-science 0.8.2 on claude-code", "Qualify ocean-science 0.8.2 on claude-cowork",
                          "Qualify ocean-science 0.8.2 on openai-codex"], titles)
        self.assertIn("qualification", [l["name"] for l in self.gh.labels])
        body = self.gh.issues[1]["body"]
        self.assertIn("--from-checklist claude-cowork-checklist.yaml", body)
        self.assertIn("--waive", body)
        self.assertIn("prompt: Load ECCO for me.", body)
        self.assertIn("@open-science-pillars/runtime-cowork-maintainers", body)
        self.assertIn("@open-science-pillars/runtime-codex-maintainers", self.gh.issues[2]["body"])
        self.assertIn("--candidate", self.gh.issues[0]["body"])
        self.assertEqual(1, len(self.gh.comments))
        self.assertIn("Waiting on: claude-code, claude-cowork, openai-codex", self.gh.comments[0]["body"])
        # a second run is idempotent
        rt.sync("o/r", 99, self.cap, dry_run=False)
        self.assertEqual(3, len(self.gh.issues))
        self.assertEqual(1, len(self.gh.comments))
        # the branch moves (the require list grows): the open tickets follow it
        surfaces = rt.osp.load_yaml(self.cap["dir"] / ".osp" / "surfaces.yaml")
        surfaces["qualification"]["require"].append("release-lock")
        write(self.cap["dir"] / ".osp" / "surfaces.yaml", surfaces)
        self.cap = q.load_capability(self.cap["dir"])
        writes_before = len(self.gh.writes)
        rt.sync("o/r", 99, self.cap, dry_run=False)
        self.assertEqual(3, len(self.gh.issues))
        self.assertIn("- test: release-lock\n  required: true", self.gh.issues[1]["body"])
        self.assertIn("The procedure and the hands-on walkthrough per runtime are in [release-qualification-guide.md]", self.gh.issues[1]["body"])
        self.assertNotIn("release-candidate-walkthrough", self.gh.issues[1]["body"])
        self.assertEqual(1, self.gh.issues[1]["body"].count("release-qualification-guide.md]("))
        refreshed = [w for w in self.gh.writes[writes_before:] if w[0] == "PATCH" and w[1].startswith("repos/o/r/issues/") and "/comments/" not in w[1] and "body" in (w[2] or {})]
        self.assertEqual(3, len(refreshed))
        # a record and a waiver close their tickets; the third stays open
        self.cap = q.load_capability(self.cap["dir"])
        rec = q.make_record(self.cap, "claude-code", "2.1", "headless", {t: {"status": "pass", "evidence": "x"} for t in self.cap["required"]}, ["m"], None, "0.8.2")
        write(self.cap["dir"] / ".osp" / "qualification" / "claude-code.json", rec)
        write(self.cap["dir"] / ".osp" / "qualification" / "claude-cowork.json", q.waive(self.cap, "claude-cowork", "no shell", "pmr", None))
        rt.sync("o/r", 99, self.cap, dry_run=False)
        states = {i["title"].rsplit(" ", 1)[1]: i["state"] for i in self.gh.issues}
        self.assertEqual({"claude-code": "closed", "claude-cowork": "closed", "openai-codex": "open"}, states)
        self.assertIn("claude-code: qualified", self.gh.comments[0]["body"])
        self.assertIn("claude-cowork: waived", self.gh.comments[0]["body"])
        self.assertIn("Waiting on: openai-codex", self.gh.comments[0]["body"])

    def test_dry_run_writes_nothing(self):
        rt.sync("o/r", 99, self.cap, dry_run=True)
        self.assertEqual([], self.gh.issues)
        self.assertEqual([], self.gh.writes)
