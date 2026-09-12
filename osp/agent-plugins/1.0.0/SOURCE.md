# Agent Plugins 1.0.0 schemas, vendored

`plugin.schema.json` and `mcp.schema.json` are the published
machine-readable schemas of the Agent Plugins specification, version
1.0.0 (github.com/agentplugins/agent-plugins-spec, `schemas/1.0.0/`),
copied unchanged on 2026-09-12. The specification says a client must
not retrieve a schema while loading a plugin, and the same holds for a
conformance check: `osp.py plugin-check` validates against these files
and pins the version they carry, which the release lock records as
`agent_plugins_spec`.

The specification text is authoritative where it says more than the
schema (the executable token rule for `command`, the URL rules, the
placeholder rules, the skill discovery rule); those are implemented in
`scripts/osp.py` beside the schema validation. Moving to a newer
specification version means vendoring its schemas under a new directory
and changing `AGENT_PLUGINS_VERSION` in the tool.
