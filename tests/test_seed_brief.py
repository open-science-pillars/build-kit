from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "seed_brief.py"
SPEC = importlib.util.spec_from_file_location("osp_seed_brief", MODULE_PATH)
seed_brief = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(seed_brief)

# What a rendered brief never carries: an unfilled field of the round
# file, and a word ADR E retired.
PLACEHOLDERS = ["None", "TODO", "{seed", "{repo", "{}"]
RETIRED = ["placement-check", "placement rule", "placement gate", "wrap-only",
           "wrapping rule", "wrapping skill", "executor.skill"]


def load(name: str) -> dict:
    return yaml.safe_load((ROOT / "roadmap" / "seeds" / name).read_text(encoding="utf-8"))


class MigrationBriefTests(unittest.TestCase):
    """The migration kind renders round six: what moves, where it lands,
    the receiving skills, the rule that changes no number, the checks and
    the pull request."""

    @classmethod
    def setUpClass(cls):
        cls.round_ = load("round-6.yaml")
        cls.briefs = {s["id"]: seed_brief.render(cls.round_, s) for s in cls.round_["seeds"]}

    def test_every_round_six_seed_is_a_migration_seed(self):
        self.assertEqual({"migration"}, {s.get("kind") for s in self.round_["seeds"]})
        self.assertIn("migration", seed_brief.RENDERERS)
        self.assertNotIn("capability", seed_brief.RENDERERS)
        self.assertNotIn("capability", seed_brief.KINDS)

    def test_no_placeholder_remains(self):
        for seed_id, text in self.briefs.items():
            for placeholder in PLACEHOLDERS:
                self.assertNotIn(placeholder, text, (seed_id, placeholder))

    def test_the_brief_says_what_moves_and_where_it_lands(self):
        text = self.briefs["r6-ocean-science-computations"]
        self.assertIn("WHAT MOVES, and where each thing lands:", text)
        self.assertIn("knowledge/podaac/computations/sea-level-budget.md", text)
        self.assertIn("knowledge/references/retrieval/", text)
        self.assertIn("RECEIVING SKILLS", text)
        self.assertIn("`ocean-budget`", text)
        self.assertIn("SKILLS TO REPOINT", text)
        self.assertIn("${CLAUDE_PLUGIN_ROOT}", text)
        self.assertIn("ACCEPTANCE", text)

    def test_the_brief_carries_the_rule_the_checks_and_the_pull_request(self):
        text = self.briefs["r6-hydrology-computations"]
        self.assertIn("This seed changes no number.", text)
        self.assertIn("never signs", text)
        self.assertIn("This seed never edits the provider bundle", text)
        self.assertIn("osp.py validate . --standalone", text)
        self.assertIn("git commit -s", text)
        self.assertIn("Migration PR: merges on the coordinator", text)
        self.assertIn("For the reviewer", text)
        self.assertIn("report, as your final message", text)

    def test_the_bundle_seed_is_the_other_end_of_the_same_move(self):
        text = self.briefs["r6-bundle-after-the-move"]
        self.assertIn("finishing the move in the provider bundle", text)
        self.assertIn("This seed edits no capability", text)
        self.assertIn("Bundle PR: merges on the coordinator", text)
        self.assertNotIn("WHAT MOVES", text)

    def test_no_retired_word_comes_from_the_renderer(self):
        # The round file's own prose is the coordinator's; what this
        # script adds to it carries none of the retired words.
        own = "\n".join(text for text in self.briefs.values())
        source = MODULE_PATH.read_text(encoding="utf-8")
        for word in RETIRED:
            self.assertNotIn(word, source, word)
        self.assertNotIn("placement", own)


class SkillBriefTests(unittest.TestCase):
    """The skill kind stays, and is a skill with scripts and a golden."""

    @classmethod
    def setUpClass(cls):
        cls.round_ = load("round-5.yaml")
        cls.briefs = {s["id"]: seed_brief.render(cls.round_, s) for s in cls.round_["seeds"]}

    def test_every_round_five_seed_renders_without_a_placeholder(self):
        for seed_id, text in self.briefs.items():
            for placeholder in PLACEHOLDERS:
                self.assertNotIn(placeholder, text, (seed_id, placeholder))

    def test_a_skill_is_scripts_and_a_golden(self):
        text = self.briefs["r5-ocean-sweep"]
        self.assertIn("SKILLS TO BUILD", text)
        self.assertIn("the proof in a golden directly under `verification/`", text)
        self.assertIn("--selftest", text)
        self.assertNotIn("placement", text)


if __name__ == "__main__":
    unittest.main()
