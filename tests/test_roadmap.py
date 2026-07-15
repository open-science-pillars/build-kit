from __future__ import annotations

import copy
import importlib.util
import json
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "roadmap.py"
SPEC = importlib.util.spec_from_file_location("osp_roadmap", MODULE_PATH)
roadmap = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(roadmap)


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
        self.assertIn("Generated from `roadmap/roadmap.yaml`", first)

    def test_unaccepted_work_cannot_be_active(self):
        data = copy.deepcopy(self.data)
        item = data["initiatives"][1]["deliverables"][0]
        item["proposal_state"] = "draft"
        item["status"] = "active"
        errors = roadmap.validate_data(data, check_files=False)
        self.assertTrue(any("must be accepted" in error for error in errors))

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

    def test_managed_block_replacement_preserves_repository_notes(self):
        initiative = self.data["initiatives"][1]
        item = initiative["deliverables"][0]
        desired = roadmap.issue_body(initiative, item)
        existing = desired.replace(item["title"], "Old title") + "\nRepository note.\n"
        replaced = roadmap.replace_managed_body(existing, desired)
        self.assertIn(item["title"], replaced)
        self.assertIn("Repository note.", replaced)

    def test_decision_label_conflicts_are_detected(self):
        labels = ["roadmap:accepted", "roadmap:rejected"]
        self.assertEqual("conflict", roadmap.status_from_labels(labels))

    def test_recorded_api_fixture_resolves_stable_marker_and_decision(self):
        fixture = Path(__file__).parent / "fixtures" / "issues.json"
        issues = json.loads(fixture.read_text())
        found = roadmap.find_marked_issue(issues, "codex-core-manifest")
        self.assertEqual(42, found["number"])
        self.assertEqual("accepted", roadmap.status_from_labels(found["labels"]))

    def test_unknown_repository_is_rejected(self):
        data = copy.deepcopy(self.data)
        data["initiatives"][0]["deliverables"][0]["repo"] = "not-in-portfolio"
        errors = roadmap.validate_data(data, check_files=False)
        self.assertTrue(any("unknown repository" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
