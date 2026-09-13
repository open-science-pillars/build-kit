from __future__ import annotations

import copy
import importlib.util
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "roadmap.py"
SPEC = importlib.util.spec_from_file_location("osp_roadmap", MODULE_PATH)
roadmap = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(roadmap)


def find(data, deliverable_id):
    for _, item in roadmap.deliverables(data):
        if item["id"] == deliverable_id:
            return item
    raise KeyError(deliverable_id)


class RoadmapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = roadmap.load_yaml(roadmap.ROADMAP_FILE)

    def test_canonical_data_validates(self):
        self.assertEqual([], roadmap.validate_data(copy.deepcopy(self.data), check_files=False))

    def test_render_is_deterministic(self):
        first = roadmap.render_markdown(copy.deepcopy(self.data))
        second = roadmap.render_markdown(copy.deepcopy(self.data))
        self.assertEqual(first, second)
        self.assertTrue(first.startswith("# Open Science Pillars roadmap\n\n> Generated from `roadmap/roadmap.yaml`"))

    def test_summary_places_deliverables_by_status_and_dependencies(self):
        data = copy.deepcopy(self.data)
        rendered = roadmap.render_markdown(data)
        for heading in ["## Summary", "### Now", "### Blocked", "### Next", "### Later", "### Done (", "### Declined ("]:
            self.assertIn(heading, rendered)
        self.assertLess(rendered.index("## Summary"), rendered.index("## Decisions"))
        sections = {}
        for name in ["Now", "Blocked", "Next", "Later", "Done", "Declined"]:
            start = rendered.index(f"### {name}")
            end = rendered.index("\n### ", start + 1) if name != "Declined" else rendered.index("## Decisions")
            sections[name] = rendered[start:end]
        self.assertIn("`r2-core-reference`", sections["Now"])
        self.assertIn("(`core`)", sections["Now"])
        self.assertIn("`phase3-flood-slice`", sections["Blocked"])
        self.assertIn("authorizes Phase 3", sections["Blocked"])
        # every dependency of hydro-investigation-tutorial is done, so it is Next
        self.assertIn("`hydro-investigation-tutorial`", sections["Next"])
        # powered-ablation-run waits on an undone dependency, so it is Later
        self.assertIn("`powered-ablation-run`", sections["Later"])
        self.assertNotIn("`powered-ablation-run`", sections["Next"])
        # a Next entry that still carries a gate says so
        self.assertIn("`r9-headless-ci-qualification`", sections["Next"])
        self.assertIn(": gate: ", sections["Next"])
        done = [x for _, x in roadmap.deliverables(data) if x["status"] == "done"]
        self.assertIn(f"### Done ({len(done)})", sections["Done"])
        self.assertIn("<details>", sections["Done"])
        self.assertIn("`hydro-basin-unit`", sections["Done"])
        self.assertIn("`codex-core-manifest`", sections["Declined"])
        self.assertIn("Superseded in form by r1-runtime-renderer", sections["Declined"])
        # priority order inside Next and Later
        later_ids = [line.split("`")[1] for line in sections["Later"].splitlines() if line.startswith("- P")]
        priorities = [find(data, x)["priority"] for x in later_ids]
        self.assertEqual(sorted(priorities), priorities)

    def test_ready_and_proposal_state_are_gone(self):
        data = copy.deepcopy(self.data)
        item = data["initiatives"][0]["deliverables"][0]
        item["status"] = "ready"
        errors = roadmap.validate_data(data, check_files=False)
        self.assertTrue(any("invalid status" in error or "'ready' is not one of" in error for error in errors))
        data = copy.deepcopy(self.data)
        data["initiatives"][0]["deliverables"][0]["proposal_state"] = "accepted"
        errors = roadmap.validate_data(data, check_files=False)
        self.assertTrue(any("proposal_state" in error for error in errors))

    def test_issue_is_optional_but_number_and_url_travel_together(self):
        data = copy.deepcopy(self.data)
        item = data["initiatives"][0]["deliverables"][0]
        item.pop("issue", None)
        self.assertEqual([], roadmap.validate_data(data, check_files=False))
        item["issue"] = {"number": None}
        self.assertEqual([], roadmap.validate_data(data, check_files=False))
        item["issue"] = {"number": 7}
        errors = roadmap.validate_data(data, check_files=False)
        self.assertTrue(any("issue number without URL" in error for error in errors))
        item["issue"] = {"seed": True, "number": None, "url": None}
        errors = roadmap.validate_data(data, check_files=False)
        self.assertTrue(any("seed" in error for error in errors))

    def test_done_requires_evidence(self):
        data = copy.deepcopy(self.data)
        item = data["initiatives"][0]["deliverables"][0]
        item["status"] = "done"
        item["evidence"] = []
        errors = roadmap.validate_data(data, check_files=False)
        self.assertTrue(any("done without evidence" in error for error in errors))

    def test_dependency_cycle_is_rejected(self):
        data = copy.deepcopy(self.data)
        one = data["initiatives"][0]["deliverables"][0]
        two = data["initiatives"][0]["deliverables"][1]
        one["depends_on"] = [two["id"]]
        errors = roadmap.validate_data(data, check_files=False)
        self.assertTrue(any("dependency cycle" in error for error in errors))

    def test_unknown_repository_is_rejected(self):
        data = copy.deepcopy(self.data)
        data["initiatives"][0]["deliverables"][0]["repo"] = "not-in-portfolio"
        errors = roadmap.validate_data(data, check_files=False)
        self.assertTrue(any("unknown repository" in error for error in errors))

    def test_offline_audit_warns_on_active_without_issue(self):
        data = copy.deepcopy(self.data)
        item = data["initiatives"][0]["deliverables"][0]
        item["status"] = "active"
        item.pop("issue", None)
        findings = roadmap.collect_audit(data, online=False, check_files=False)
        codes = {(f["code"], f["level"]) for f in findings if item["id"] in f["message"]}
        self.assertIn(("no-issue", "warning"), codes)

    def test_online_audit_flags_open_issue_on_finished_work_and_wrong_numbers(self):
        data = copy.deepcopy(self.data)
        done_item = find(data, "hydro-basin-unit")
        done_item["issue"] = {"number": 5, "url": "https://github.com/open-science-pillars/hydrology/issues/5"}
        missing_item = find(data, "hydro-w1-basin-balance")
        missing_item["issue"] = {"number": 77, "url": "https://github.com/open-science-pillars/hydrology/issues/77"}
        responses = {
            f"orgs/{roadmap.ORG_CONFIRM}/repos?per_page=100&type=all": [
                {"name": name, "archived": False} for name in data["repositories"]
            ],
            f"repos/{roadmap.ORG_CONFIRM}/build-kit/issues?state=all&per_page=100": [
                {"number": 32, "state": "open", "html_url": "https://github.com/open-science-pillars/build-kit/issues/32"},
            ],
            f"repos/{roadmap.ORG_CONFIRM}/hydrology/issues?state=all&per_page=100": [
                {"number": 5, "state": "open", "html_url": "https://github.com/open-science-pillars/hydrology/issues/5"},
                {"number": 6, "state": "open", "html_url": "https://github.com/open-science-pillars/hydrology/pull/6", "pull_request": {}},
            ],
        }
        original = roadmap.gh_json
        roadmap.gh_json = lambda endpoint: responses.get(endpoint, [])
        try:
            findings = roadmap.collect_audit(data, online=True, check_files=False)
        finally:
            roadmap.gh_json = original
        by_code = {}
        for f in findings:
            by_code.setdefault(f["code"], []).append(f)
        drift = [f for f in by_code.get("status-drift", []) if "hydro-basin-unit" in f["message"]]
        self.assertEqual(1, len(drift))
        self.assertEqual("actionable", drift[0]["level"])
        self.assertIn("close the issue", drift[0]["message"])
        mismatch = [f for f in by_code.get("issue-mismatch", []) if "hydro-w1-basin-balance" in f["message"]]
        self.assertEqual(1, len(mismatch))
        self.assertEqual("error", mismatch[0]["level"])
        # r9 is proposed with an open issue recorded: no drift
        self.assertFalse(any("r9-headless-ci-qualification" in f["message"] for f in findings if f["code"] == "status-drift"))
        for retired in ["missing-seeded-issue", "decision-conflict", "old-plan-active", "ai4s-pending"]:
            self.assertNotIn(retired, by_code)


if __name__ == "__main__":
    unittest.main()
