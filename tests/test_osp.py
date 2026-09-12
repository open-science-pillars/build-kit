from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

import yaml

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "osp.py"
SPEC = importlib.util.spec_from_file_location("osp_tool", MODULE_PATH)
osp = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(osp)


def write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix == ".json":
        path.write_text(json.dumps(data, indent=2))
    else:
        path.write_text(yaml.safe_dump(data, sort_keys=False))


def capability(root: Path, name="ocean-science", status="available", version="0.8.2"):
    repo = root / name
    write(repo / ".osp" / "repository.yaml", {
        "schema_version": 1,
        "repository": {"name": name, "kind": "capability", "status": status},
        "classification": {"spheres": ["hydrosphere"], "primary_sphere": "hydrosphere",
                           "discipline": "Ocean Physics"},
    })
    if status != "planned":
        write(repo / ".osp" / "package.yaml", {
            "schema_version": 1,
            "package": {"name": name, "version": version, "type": "capability"},
            "content": {"skills": "./skills"},
            "dependencies": {"capabilities": [{"name": "core"}],
                             "knowledge": [{"name": "nasa-daac-knowledge", "version": ">=2026.9.2"}]},
        })
        write(repo / ".claude-plugin" / "plugin.json", {
            "name": name, "version": version,
            "dependencies": ["core", {"name": "nasa-daac-knowledge", "version": ">=2026.9.2"}],
        })
        (repo / "skills").mkdir(exist_ok=True)
        write(repo / ".osp" / "surfaces.yaml", {
            "schema_version": 1,
            "surfaces": {"claude-code": {"role": ["development", "runtime"], "required": True, "status": "supported"}},
            "qualification": {"require": ["install", "skill-discovery"]},
        })
    (repo / "CODEOWNERS").write_text("* @open-science-pillars/hydrosphere-maintainers\n")
    write(repo / ".osp" / "governance.yaml", {
        "schema_version": 2, "repository": name,
        "maintainers": {"users": ["someone"], "teams": ["hydrosphere-maintainers"], "status": "interim"},
        "runtime_maintainers": {"claude-cowork": {"users": [], "teams": ["runtime-cowork-maintainers"], "status": "interim"}},
        "roadmap": {"proposals": "enabled", "authority": "repository-maintainers"},
        "reviews": {"ordinary": 1, "cross_repository": "org-policy", "knowledge": "org-knowledge-policy",
                    "runtime_adapter": "org-runtime-policy"},
    })
    return repo


class OspTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_valid_capability_passes(self):
        repo = capability(self.root)
        errors, warnings = osp.validate_repo(repo)
        self.assertEqual([], errors, errors)

    def test_manifest_must_agree_with_package(self):
        repo = capability(self.root)
        manifest = json.loads((repo / ".claude-plugin" / "plugin.json").read_text())
        manifest["version"] = "0.9.0"
        manifest["dependencies"] = ["core"]
        write(repo / ".claude-plugin" / "plugin.json", manifest)
        errors, _ = osp.validate_repo(repo)
        self.assertTrue(any("version" in e for e in errors), errors)
        self.assertTrue(any("dependencies differ" in e for e in errors), errors)

    def test_planned_repository_is_never_installable(self):
        repo = capability(self.root, name="precipitation", status="planned")
        self.assertEqual([], osp.validate_repo(repo)[0])
        (repo / "skills").mkdir()
        errors, _ = osp.validate_repo(repo)
        self.assertTrue(any("never installable" in e for e in errors), errors)

    def test_primary_sphere_must_be_declared(self):
        repo = capability(self.root)
        meta = yaml.safe_load((repo / ".osp" / "repository.yaml").read_text())
        meta["classification"]["primary_sphere"] = "cryosphere"
        write(repo / ".osp" / "repository.yaml", meta)
        errors, _ = osp.validate_repo(repo)
        self.assertTrue(any("not among spheres" in e for e in errors), errors)

    def test_actions_checkout_directory_may_differ_from_the_name(self):
        import os
        repo = capability(self.root, name="ocean-science")
        checkout = self.root / "plugin"
        repo.rename(checkout)
        errors, _ = osp.validate_repo(checkout)
        self.assertTrue(any("not the repository" in e for e in errors), errors)
        os.environ["GITHUB_REPOSITORY"] = "open-science-pillars/ocean-science"
        try:
            errors, _ = osp.validate_repo(checkout)
        finally:
            del os.environ["GITHUB_REPOSITORY"]
        self.assertEqual([], errors, errors)

    def test_copied_template_fails_until_renamed(self):
        repo = capability(self.root, name="my-plugin")
        meta = yaml.safe_load((repo / ".osp" / "repository.yaml").read_text())
        meta["repository"]["name"] = "plugin-template"
        write(repo / ".osp" / "repository.yaml", meta)
        errors, _ = osp.validate_repo(repo)
        self.assertTrue(any("still names the template" in e for e in errors), errors)

    def test_placeholder_discipline_fails(self):
        repo = capability(self.root)
        meta = yaml.safe_load((repo / ".osp" / "repository.yaml").read_text())
        meta["classification"]["discipline"] = "<your discipline>"
        write(repo / ".osp" / "repository.yaml", meta)
        errors, _ = osp.validate_repo(repo)
        self.assertTrue(any("placeholder" in e for e in errors), errors)

    def test_catalog_cross_check(self):
        repo = capability(self.root)
        planned = capability(self.root, name="land-ice", status="planned")
        write(self.root / "marketplace" / ".claude-plugin" / "marketplace.json", {
            "plugins": [{"name": "land-ice", "source": {"ref": "x"}}]})
        errors, _ = osp.validate_repo(repo, self.root)
        self.assertTrue(any("absent from the marketplace catalog" in e for e in errors), errors)
        errors, _ = osp.validate_repo(planned, self.root)
        self.assertTrue(any("planned, yet listed" in e for e in errors), errors)

    def test_topics(self):
        meta = {"repository": {"name": "hydrology", "kind": "capability", "status": "developing"},
                "classification": {"spheres": ["hydrosphere", "cryosphere"], "primary_sphere": "hydrosphere",
                                   "discipline": "Terrestrial Hydrology"}}
        self.assertEqual(["osp", "cryosphere", "hydrosphere"], osp.topics_for(meta))

    def test_sphere_view_renders_every_sphere_and_is_deterministic(self):
        capability(self.root)
        capability(self.root, name="land-ice", status="planned")
        repos = [(p.name, osp.read_repository(p)) for p in osp.workspace_repos(self.root)]
        first = osp.render_sphere_view(repos)
        self.assertEqual(first, osp.render_sphere_view(repos))
        for sphere in ("Atmosphere", "Biosphere", "Cryosphere", "Geosphere", "Hydrosphere"):
            self.assertIn(f"## {sphere}", first)
        self.assertIn("| `ocean-science` | Ocean Physics | available |", first)
        self.assertIn("No domain capability yet.", first)

    def test_codeowners_names_registered_teams_only(self):
        repo = capability(self.root)
        (repo / "CODEOWNERS").write_text("* @someone\n/knowledge/ @open-science-pillars/no-such-team\n")
        errors, _ = osp.validate_repo(repo)
        self.assertTrue(any("names an individual" in e for e in errors), errors)
        self.assertTrue(any("does not declare" in e for e in errors), errors)
        (repo / "CODEOWNERS").unlink()
        errors, _ = osp.validate_repo(repo)
        self.assertTrue(any("no root CODEOWNERS" in e for e in errors), errors)

    def test_governance_teams_must_be_registered(self):
        repo = capability(self.root)
        gov = yaml.safe_load((repo / ".osp" / "governance.yaml").read_text())
        gov["maintainers"]["teams"] = ["nobody-maintainers"]
        write(repo / ".osp" / "governance.yaml", gov)
        errors, _ = osp.validate_repo(repo)
        self.assertTrue(any("nobody-maintainers" in e for e in errors), errors)

    def test_teams_registry_is_consistent(self):
        teams = osp.registered_teams()
        for slug, meta in teams.items():
            self.assertIn(meta["kind"], {"maintainers", "sphere", "composite", "stewards", "runtime"})
            if meta.get("parent"):
                self.assertIn(meta["parent"], teams)
        for sphere in osp.SPHERES:
            self.assertIn(f"{sphere}-maintainers", teams)

    def test_profile_block_is_spliced_between_markers(self):
        capability(self.root)
        repos = [(p.name, osp.read_repository(p)) for p in osp.workspace_repos(self.root)]
        page = "# Profile\n\nintro\n\n<!-- osp-sphere-view:start -->\nold\n<!-- osp-sphere-view:end -->\n\nfooter\n"
        out = osp.splice(page, osp.render_profile_block(repos))
        self.assertIn("**Hydrosphere**", out)
        self.assertIn("[ocean-science](https://github.com/open-science-pillars/ocean-science) *(available)*: Ocean Physics", out)
        self.assertNotIn("old", out)
        self.assertTrue(out.startswith("# Profile\n\nintro\n") and out.endswith("footer\n"))
        with self.assertRaises(osp.OspError):
            osp.splice("no markers", "x")

    def test_build_kit_own_metadata_validates(self):
        errors, _ = osp.validate_repo(osp.BUILD_KIT)
        self.assertEqual([], errors, errors)


if __name__ == "__main__":
    unittest.main()
