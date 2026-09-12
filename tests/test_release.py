from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location("release_tool", SCRIPTS / "release.py")
rel = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(rel)


class ReleaseToolTests(unittest.TestCase):
    def test_set_version_keeps_comments_and_order(self):
        text = "# comment\nschema_version: 1\npackage:\n  name: core\n  version: 0.5.0\n  type: foundation\ncontent: {}\n"
        new, old = rel.set_version(text, "0.5.1")
        self.assertEqual("0.5.0", old)
        self.assertEqual("# comment\nschema_version: 1\npackage:\n  name: core\n  version: 0.5.1\n  type: foundation\ncontent: {}\n", new)
        quoted, _ = rel.set_version("package:\n  name: x\n  version: '2026.9.3'\n", "2026.9.4")
        self.assertIn("  version: '2026.9.4'", quoted)
        with self.assertRaises(rel.ReleaseError):
            rel.set_version("package:\n  name: x\n", "1.0.0")

    def test_citation_version(self):
        cff = 'cff-version: 1.2.0\ntitle: "x"\nversion: "0.5.0"\n'
        self.assertIn('version: "0.5.1"', rel.set_citation_version(cff, "0.5.1"))

    def test_notes_and_body(self):
        notes = rel.release_notes("the rendered projections and the lock", "Longer text.", ["PROVE: the attester", "Runtime table"])
        self.assertTrue(notes.startswith("the rendered projections and the lock\n\nLonger text.\n\nChanges since the previous release:\n- PROVE"))
        body = rel.pr_body("core", "0.5.1", notes)
        self.assertIn("Release candidate **core 0.5.1**", body)
        self.assertIn("--surface claude-code --candidate", body)
        self.assertIn("core--v0.5.1", body)
        self.assertTrue(rel.version_tuple("0.5.1") > rel.version_tuple("0.5.0"))
        self.assertTrue(rel.version_tuple("2026.9.10") > rel.version_tuple("2026.9.9"))
