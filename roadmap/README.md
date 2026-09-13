`roadmap.yaml` is the canonical organization roadmap; edit it, never `../ROADMAP.md`.
`schema.json` validates it and `governance-schema.json` validates every repository's `.osp/governance.yaml`.
Render with `uv run scripts/roadmap.py render --standalone` (validate first with `uv run scripts/roadmap.py validate --standalone`).
