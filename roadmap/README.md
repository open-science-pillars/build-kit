`roadmap.yaml` is the canonical organization roadmap; edit it, never `../ROADMAP.md`.
`schema.json` validates it and `governance-schema.json` validates every repository's `.osp/governance.yaml`.
Render with `uv run scripts/roadmap.py render --standalone` (validate first with `uv run scripts/roadmap.py validate --standalone`).

Seed rounds: `roadmap/seeds/round-N.yaml` lists the seeds a coordinator session dispatches in parallel (one bundle per seed per wave; a seed's kind is knowledge, computation, connector or data-root, and a wave B seed depends on wave A); `uv run scripts/seed_brief.py roadmap/seeds/round-3.yaml --wave A --out DIR` renders each seed's session brief, so the rules every seed of a kind is told live in the script and only what differs per seed lives in the round file.
