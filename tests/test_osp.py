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


def packaged(root: Path, name="ocean-science", **kwargs):
    """A capability whose package carries metadata and REACH, with one
    canonical skill, ready to render."""
    repo = capability(root, name=name, **kwargs)
    pkg = yaml.safe_load((repo / ".osp" / "package.yaml").read_text())
    pkg["metadata"] = {"description": "Physical oceanography.", "keywords": ["ecco", "swot"]}
    pkg["reach"] = {"servers": {
        "earthdata": {"type": "streamable-http", "url": "https://cmr.earthdata.nasa.gov/mcp/v1"},
        "observations": {"type": "stdio", "command": "uv",
                         "args": ["run", "${PLUGIN_ROOT}/connectors/observations_mcp.py"]},
        "cowork-only": {"type": "stdio", "command": "./bin/host", "portable": False},
    }}
    write(repo / ".osp" / "package.yaml", pkg)
    (repo / "skills" / "load-ecco").mkdir(parents=True, exist_ok=True)
    (repo / "skills" / "load-ecco" / "SKILL.md").write_text(
        "---\nname: load-ecco\ndescription: Load ECCO fields.\nuser-invocable: true\n---\n\nBody.\n")
    return repo


class RenderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_claude_manifest_is_the_form_the_repositories_already_use(self):
        repo = packaged(self.root)
        pkg = yaml.safe_load((repo / ".osp" / "package.yaml").read_text())
        manifest = osp.render_claude_manifest(pkg, "ocean-science")
        self.assertEqual(["name", "version", "description", "dependencies", "author", "homepage", "license", "keywords"],
                         list(manifest))
        self.assertEqual(["core", {"name": "nasa-daac-knowledge", "version": ">=2026.9.2"}], manifest["dependencies"])
        self.assertEqual({"name": "Open Science Pillars Community"}, manifest["author"])
        self.assertEqual("Apache-2.0", manifest["license"])
        # the rendered manifest satisfies the validator's agreement check
        errors, _ = osp.validate_repo(repo)
        self.assertEqual([], errors, errors)

    def test_claude_mcp_and_portable_mcp_are_two_spellings_of_one_reach(self):
        repo = packaged(self.root)
        pkg = yaml.safe_load((repo / ".osp" / "package.yaml").read_text())
        claude = osp.render_claude_mcp(pkg)["mcpServers"]
        self.assertEqual({"type": "http", "url": "https://cmr.earthdata.nasa.gov/mcp/v1"}, claude["earthdata"])
        self.assertEqual(["run", "${CLAUDE_PLUGIN_ROOT}/connectors/observations_mcp.py"], claude["observations"]["args"])
        self.assertIn("cowork-only", claude)
        portable = osp.render_portable_mcp(pkg)
        self.assertEqual(osp.MCP_SCHEMA_ID, portable["$schema"])
        self.assertEqual({"type": "streamable-http", "url": "https://cmr.earthdata.nasa.gov/mcp/v1"},
                         portable["mcpServers"]["earthdata"])
        self.assertEqual(["run", "${PLUGIN_ROOT}/connectors/observations_mcp.py"], portable["mcpServers"]["observations"]["args"])
        self.assertNotIn("cowork-only", portable["mcpServers"])
        self.assertNotIn("portable", json.dumps(portable))

    def test_portable_manifest_validates_against_the_vendored_schema(self):
        repo = packaged(self.root)
        pkg = yaml.safe_load((repo / ".osp" / "package.yaml").read_text())
        manifest = osp.render_portable_manifest(pkg, osp.read_repository(repo), "ocean-science")
        self.assertEqual([], osp.schema_errors(manifest, osp.AGENT_PLUGINS_SCHEMAS / "plugin.schema.json"))
        self.assertEqual(osp.PLUGIN_SCHEMA_ID, manifest["$schema"])
        ext = manifest["extensions"][osp.OSP_NAMESPACE]
        self.assertEqual("capability", ext["kind"])
        self.assertEqual(["hydrosphere"], ext["spheres"])
        self.assertEqual([{"name": "core"}], ext["dependencies"]["capabilities"])
        self.assertNotIn("dependencies", manifest)  # the closed portable schema has no such field

    def test_no_reach_means_no_mcp_files(self):
        repo = packaged(self.root)
        pkg = yaml.safe_load((repo / ".osp" / "package.yaml").read_text())
        del pkg["reach"]
        write(repo / ".osp" / "package.yaml", pkg)
        self.assertIsNone(osp.render_claude_mcp(pkg))
        self.assertIsNone(osp.render_portable_mcp(pkg))
        expected = osp.projections(repo)
        self.assertIsNone(expected[osp.CLAUDE_MCP])
        (repo / "mcp.json").write_text("{}")
        self.assertTrue(any("hand-written" in d for d in osp.projection_drift(repo, expected)))

    def test_render_writes_and_check_detects_a_hand_edit(self):
        repo = packaged(self.root)
        expected = osp.projections(repo)
        self.assertTrue(osp.projection_drift(repo, expected))  # portable files not yet written
        osp.write_projections(repo, expected)
        self.assertEqual([], osp.projection_drift(repo, expected))
        # formatting alone is not drift
        path = repo / "plugin.json"
        path.write_text(json.dumps(json.loads(path.read_text()), separators=(",", ":")))
        self.assertEqual([], osp.projection_drift(repo, expected))
        # a hand edit is
        manifest = json.loads(path.read_text())
        manifest["version"] = "9.9.9"
        path.write_text(json.dumps(manifest))
        self.assertTrue(any("plugin.json differs" in d for d in osp.projection_drift(repo, expected)))
        claude = repo / ".claude-plugin" / "plugin.json"
        data = json.loads(claude.read_text())
        data["keywords"] = ["hand", "edited"]
        claude.write_text(json.dumps(data))
        self.assertTrue(any(".claude-plugin/plugin.json differs" in d for d in osp.projection_drift(repo, expected)))

    def test_render_needs_a_description(self):
        repo = capability(self.root)
        with self.assertRaises(osp.OspError):
            osp.projections(repo)

    def test_lock_is_deterministic_and_tracks_content(self):
        repo = packaged(self.root)
        osp.write_projections(repo, osp.projections(repo))
        first = osp.render_lock(repo)
        self.assertEqual(first, osp.render_lock(repo))
        self.assertEqual("1.0.0", first["agent_plugins_spec"])
        self.assertEqual({"core": None}, first["dependencies"]["capabilities"])
        self.assertEqual({"nasa-daac-knowledge": ">=2026.9.2"}, first["dependencies"]["knowledge"])
        self.assertTrue(first["skills_digest"].startswith("sha256:"))
        self.assertIn("claude", first["adapters"])
        self.assertIn("agent-plugins", first["adapters"])
        (repo / "skills" / "load-ecco" / "SKILL.md").write_text(
            "---\nname: load-ecco\ndescription: Load ECCO fields, differently.\n---\n")
        second = osp.render_lock(repo)
        self.assertNotEqual(first["skills_digest"], second["skills_digest"])
        self.assertEqual(first["adapters"], second["adapters"])
        (repo / "skills" / "load-ecco" / "__pycache__").mkdir()
        (repo / "skills" / "load-ecco" / "__pycache__" / "x.pyc").write_bytes(b"\0")
        self.assertEqual(second["skills_digest"], osp.render_lock(repo)["skills_digest"])
        # what the package's ignore files exclude (a generated fixture, a
        # figure) is not part of what it ships and does not move the lock
        (repo / ".gitignore").write_text("*.png\n")
        (repo / "skills" / "load-ecco" / "fixtures").mkdir()
        (repo / "skills" / "load-ecco" / "fixtures" / ".gitignore").write_text("*.nc\nscratch/\n")
        third = osp.render_lock(repo)
        (repo / "skills" / "load-ecco" / "fixtures" / "big.nc").write_bytes(b"x")
        (repo / "skills" / "load-ecco" / "figure.png").write_bytes(b"x")
        (repo / "skills" / "load-ecco" / "fixtures" / "scratch").mkdir()
        (repo / "skills" / "load-ecco" / "fixtures" / "scratch" / "note.txt").write_text("x")
        self.assertEqual(third["skills_digest"], osp.render_lock(repo)["skills_digest"])
        (repo / "skills" / "load-ecco" / "fixtures" / "kept.txt").write_text("x")
        self.assertNotEqual(third["skills_digest"], osp.render_lock(repo)["skills_digest"])

    def test_planned_repository_may_not_carry_a_lock(self):
        repo = capability(self.root, name="land-ice", status="planned")
        write(repo / ".osp" / "release-lock.json", {"package": "land-ice"})
        errors, _ = osp.validate_repo(repo)
        self.assertTrue(any("release-lock" in e for e in errors), errors)


class PluginCheckTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.repo = packaged(self.root)
        osp.write_projections(self.repo, osp.projections(self.repo))

    def tearDown(self):
        self.tmp.cleanup()

    def test_rendered_package_conforms(self):
        errors, warnings = osp.plugin_check(self.repo)
        self.assertEqual([], errors, errors)
        self.assertTrue(any("user-invocable" in w for w in warnings), warnings)

    def test_missing_manifest_is_an_error(self):
        (self.repo / "plugin.json").unlink()
        errors, _ = osp.plugin_check(self.repo)
        self.assertTrue(any("plugin.json is missing" in e for e in errors), errors)

    def test_hand_edit_and_unknown_field_fail(self):
        path = self.repo / "plugin.json"
        manifest = json.loads(path.read_text())
        manifest["hooks"] = {}
        manifest["name"] = "Ocean-Science"
        path.write_text(json.dumps(manifest))
        errors, _ = osp.plugin_check(self.repo)
        self.assertTrue(any("hooks" in e for e in errors), errors)
        self.assertTrue(any("name" in e and "package name" in e for e in errors), errors)
        self.assertTrue(any("differs from what package.yaml renders" in e for e in errors), errors)

    def test_mcp_rules_beyond_the_schema(self):
        bad = {"type": "stdio", "command": "uv run", "args": ["${CLAUDE_PLUGIN_ROOT}/x"], "cwd": "data",
               "env": {"PLUGIN_ROOT": "/x"}}
        findings = osp.server_findings("s", bad)
        for needle in ("single executable token", "CLAUDE_PLUGIN_ROOT", "cwd", "reserved PLUGIN_ROOT"):
            self.assertTrue(any(needle in f for f in findings), (needle, findings))
        self.assertTrue(any("escapes" in f for f in osp.server_findings("s", {"type": "stdio", "command": "./../bin/x"})))
        self.assertTrue(any("bare executable" in f for f in osp.server_findings("s", {"type": "stdio", "command": "/usr/bin/x"})))
        self.assertEqual([], osp.server_findings("s", {"type": "stdio", "command": "./bin/x", "cwd": "${PLUGIN_DATA}/w"}))
        remote = {"type": "streamable-http", "url": "http://example.org/mcp#frag", "headers": {"X-A": "1", "x-a": "2"}}
        findings = osp.server_findings("r", remote)
        for needle in ("fragment", "https, not http", "different casing"):
            self.assertTrue(any(needle in f for f in findings), (needle, findings))
        self.assertEqual([], osp.server_findings("r", {"type": "streamable-http", "url": "http://localhost:8000/mcp"}))
        self.assertTrue(any("user information" in f for f in
                            osp.server_findings("r", {"type": "sse", "url": "https://u:p@example.org/sse"})))

    def test_non_portable_reach_declared_portable_fails(self):
        pkg = yaml.safe_load((self.repo / ".osp" / "package.yaml").read_text())
        pkg["reach"]["servers"]["observations"]["args"] = ["run", "${CLAUDE_PLUGIN_ROOT}/x.py"]
        write(self.repo / ".osp" / "package.yaml", pkg)
        osp.write_projections(self.repo, osp.projections(self.repo))
        errors, _ = osp.plugin_check(self.repo)
        self.assertTrue(any("CLAUDE_PLUGIN_ROOT" in e for e in errors), errors)

    def test_skill_rules(self):
        skills = self.repo / "skills"
        (skills / "load-ecco" / "SKILL.md").write_text("---\nname: load_ecco\ndescription: x\n---\n")
        (skills / "claude").mkdir()
        (skills / "claude" / "SKILL.md").write_text("---\nname: claude\ndescription: x\n---\n")
        (skills / "notes").mkdir()
        (skills / "nodesc").mkdir()
        (skills / "nodesc" / "SKILL.md").write_text("---\nname: nodesc\n---\n")
        errors, warnings = osp.plugin_check(self.repo)
        self.assertTrue(any("does not match its directory" in e for e in errors), errors)
        self.assertTrue(any("not lowercase" in e for e in errors), errors)
        self.assertTrue(any("runtime-specific skill tree" in e for e in errors), errors)
        self.assertTrue(any("description is missing" in e for e in errors), errors)
        self.assertTrue(any("skills/notes/" in w for w in warnings), warnings)

    def test_optional_field_types_and_the_length_recommendation(self):
        skills = self.repo / "skills"
        (skills / "load-ecco" / "SKILL.md").write_text(
            "---\nname: load-ecco\ndescription: x\nlicense: [MIT]\nallowed-tools:\n  - Read\n---\n" + "line\n" * 600)
        errors, warnings = osp.plugin_check(self.repo)
        self.assertTrue(any("license is a string" in e for e in errors), errors)
        self.assertTrue(any("allowed-tools is a string" in e for e in errors), errors)
        self.assertTrue(any("over 500 lines" in w for w in warnings), warnings)

    def test_planned_and_packageless_repositories_have_no_portable_package(self):
        planned = capability(self.root, name="land-ice", status="planned")
        errors, _ = osp.plugin_check(planned)
        self.assertTrue(any("no .osp/package.yaml" in e for e in errors), errors)


class AdvertiseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.repo = packaged(self.root)
        osp.write_projections(self.repo, osp.projections(self.repo))
        (self.repo / ".osp" / "release-lock.json").write_text(json.dumps(osp.render_lock(self.repo)))
        write(self.repo / ".osp" / "surfaces.yaml", {
            "schema_version": 1,
            "surfaces": {
                "claude-code": {"role": ["development", "runtime"], "required": True, "status": "supported"},
                "claude-cowork": {"role": "runtime", "required": True, "status": "tested"},
                "openai-codex": {"role": "runtime", "required": True, "status": "planned"},
            },
            "qualification": {"require": ["install", "skill-discovery"]},
        })

    def tearDown(self):
        self.tmp.cleanup()

    def record(self, runtime, qualified=True, version="0.8.2", lock=None, blockers=()):
        lock = lock or osp.value_digest(json.loads((self.repo / ".osp" / "release-lock.json").read_text()))
        write(self.repo / ".osp" / "qualification" / f"{runtime}.json", {
            "schema_version": 1, "capability": "ocean-science", "version": version, "release_lock": lock,
            "runtime": {"name": runtime}, "date": "2026-09-12", "source": "test", "qualified": qualified,
            "blockers": list(blockers), "tests": {}})

    def test_development_environment_is_supported_by_construction_and_others_need_a_record(self):
        adv = osp.advertisement(self.repo)
        self.assertEqual([], adv["errors"])
        self.assertEqual("Supported (development environment)", osp.runtime_verdict(adv["runtimes"]["claude-code"]))
        self.assertEqual("Not qualified", osp.runtime_verdict(adv["runtimes"]["claude-cowork"]))

    def test_a_support_claim_without_a_qualified_record_fails(self):
        surfaces = yaml.safe_load((self.repo / ".osp" / "surfaces.yaml").read_text())
        surfaces["surfaces"]["claude-cowork"]["status"] = "supported"
        write(self.repo / ".osp" / "surfaces.yaml", surfaces)
        adv = osp.advertisement(self.repo)
        self.assertTrue(any("advertises claude-cowork as supported without a qualified record" in e for e in adv["errors"]), adv["errors"])
        self.record("claude-cowork", qualified=False, blockers=["prove: blocked"])
        adv = osp.advertisement(self.repo)
        self.assertTrue(adv["errors"])
        self.record("claude-cowork", qualified=True)
        adv = osp.advertisement(self.repo)
        self.assertEqual([], adv["errors"])
        self.assertEqual("Qualified", osp.runtime_verdict(adv["runtimes"]["claude-cowork"]))

    def test_a_record_for_another_release_is_stale(self):
        self.record("openai-codex", qualified=True, version="0.8.1")
        adv = osp.advertisement(self.repo)
        self.assertTrue(adv["runtimes"]["openai-codex"]["stale_record"])
        self.assertFalse(adv["runtimes"]["openai-codex"]["qualified"])
        self.assertTrue(any("not this release" in w for w in adv["warnings"]), adv["warnings"])
        self.record("openai-codex", qualified=True, lock="sha256:" + "0" * 64)
        self.assertTrue(osp.advertisement(self.repo)["runtimes"]["openai-codex"]["stale_record"])

    def test_qualified_but_not_advertised_is_a_warning(self):
        self.record("claude-cowork", qualified=True)
        adv = osp.advertisement(self.repo)
        self.assertTrue(any("may be advertised as supported" in w for w in adv["warnings"]), adv["warnings"])

    def test_runtime_block_renders_and_splices(self):
        self.record("claude-cowork", qualified=False, blockers=["prove: blocked"])
        block = osp.render_runtimes_block(osp.advertisement(self.repo))
        self.assertIn("| Claude Cowork | runtime, required | tested | Not qualified (prove: blocked) |", block)
        self.assertIn("Supported (development environment)", block)
        page = "# R\n\n<!-- osp-runtimes:start -->\nold\n<!-- osp-runtimes:end -->\n\nend\n"
        out = osp.splice_runtimes(page, block)
        self.assertNotIn("old", out)
        self.assertTrue(out.startswith("# R\n") and out.endswith("end\n"))

    def test_publish_withholds_the_portable_projection_until_a_runtime_is_qualified(self):
        import zipfile
        args = type("A", (), {"repo": str(self.repo), "out": None})()
        osp.command_publish(args)
        dist = self.repo / "dist"
        release = json.loads((dist / "release.json").read_text())
        self.assertEqual("ocean-science", release["capability"])
        self.assertNotIn("agent-plugins", release["projections"])
        self.assertIn("not emitted", release["agent_plugins_projection"])
        names = zipfile.ZipFile(dist / "claude" / "ocean-science-0.8.2.zip").namelist()
        self.assertIn("ocean-science/.claude-plugin/plugin.json", names)
        self.assertIn("ocean-science/skills/load-ecco/SKILL.md", names)
        self.assertNotIn("ocean-science/plugin.json", names)
        self.assertNotIn("ocean-science/dist/release.json", names)
        self.record("openai-codex", qualified=True)
        osp.command_publish(args)
        release = json.loads((dist / "release.json").read_text())
        self.assertEqual("agent-plugin/ocean-science-0.8.2", release["projections"]["agent-plugins"])
        self.assertTrue((dist / "agent-plugin" / "ocean-science-0.8.2" / "plugin.json").is_file())
        self.assertFalse((dist / "agent-plugin" / "ocean-science-0.8.2" / ".claude-plugin").exists())
        self.assertEqual("Qualified", release["runtimes"]["openai-codex"]["qualification"])

    def test_publish_refuses_an_unsupported_claim(self):
        surfaces = yaml.safe_load((self.repo / ".osp" / "surfaces.yaml").read_text())
        surfaces["surfaces"]["openai-codex"]["status"] = "supported"
        write(self.repo / ".osp" / "surfaces.yaml", surfaces)
        args = type("A", (), {"repo": str(self.repo), "out": None})()
        with self.assertRaises(osp.OspError):
            osp.command_publish(args)


class ReleaseCandidateTests(AdvertiseTests):
    """The release-candidate mode: every required surface needs a decision."""

    def test_release_needs_a_record_or_a_waiver_for_every_required_surface(self):
        adv = osp.advertisement(self.repo, release=True)
        needs = [e for e in adv["errors"] if "needs a decision" in e]
        self.assertEqual(3, len(needs), adv["errors"])   # claude-code, claude-cowork, openai-codex are required
        self.record("claude-code", qualified=True)
        self.record("claude-cowork", qualified=False, blockers=["prove: blocked"])
        adv = osp.advertisement(self.repo, release=True)
        self.assertTrue(any("claude-cowork is not qualified" in e and "not waived" in e for e in adv["errors"]), adv["errors"])
        self.assertTrue(any("decision for openai-codex" in e for e in adv["errors"]), adv["errors"])
        # waivers are the way through
        for rt in ("claude-cowork", "openai-codex"):
            write(self.repo / ".osp" / "qualification" / f"{rt}.json", {
                "schema_version": 1, "capability": "ocean-science", "version": "0.8.2", "release_lock": None,
                "runtime": {"name": rt}, "date": "2026-09-12", "source": "waiver", "qualified": False,
                "waived": {"by": "pmr", "reason": "no shell on this runtime", "date": "2026-09-12"},
                "blockers": ["waived"], "tests": {}})
        adv = osp.advertisement(self.repo, release=True)
        self.assertEqual([], adv["errors"], adv["errors"])
        self.assertEqual("Not qualified, waived for this release", osp.runtime_verdict(adv["runtimes"]["claude-cowork"]))
        self.assertIn("no shell on this runtime", osp.render_runtimes_block(adv))
        # a waived surface can never be advertised
        surfaces = yaml.safe_load((self.repo / ".osp" / "surfaces.yaml").read_text())
        surfaces["surfaces"]["claude-cowork"]["status"] = "supported"
        write(self.repo / ".osp" / "surfaces.yaml", surfaces)
        self.assertTrue(any("waived" in e and "cannot be advertised" in e for e in osp.advertisement(self.repo)["errors"]))

    def test_ordinary_check_does_not_demand_decisions(self):
        self.assertEqual([], osp.advertisement(self.repo)["errors"])
