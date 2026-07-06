# Open Science Pillars: Start Here

This directory is the complete, final document set for building Open Science Pillars: an open ecosystem of skills, knowledge bundles, verification notebooks, and connectors for AI-assisted earth, planetary, and applied science across Claude Code, Claude Cowork, and Claude Science.

## The Five Documents

| File | Role | Read when |
|---|---|---|
| **ARCHITECTURE.md** | Why: strategy, layers, personas, the PO.DAAC arc, phases | Once, before Day 1; revisit when scoping Phase 2+ |
| **SPECIFICATION.md** (v0.5.1, frozen) | What: every repo, skill, agent, knowledge concept, golden notebook, eval case, acceptance criterion | Continuously; it is law during the build |
| **IMPLEMENTATION-GUIDE.md** (v2.3.3) | In what order: 16 sessions, ~35.5 hours, checkpoints | Each session start |
| **BUILD-HARNESS.md** | How to run the build with Claude Code: workspace CLAUDE.md, /osp-session, /osp-close, autonomy dial, week map | Day 1 setup, then it runs itself |
| **PROGRESS.md** | Where you are: per-surface status, session log | Updated at every session close |

Reading order for a first pass: ARCHITECTURE (skim Parts 1-3), then BUILD-HARNESS, then IMPLEMENTATION-GUIDE Session 0b-1, dipping into SPECIFICATION as sessions reference it. PARKING.md rides along as the freeze's holding pen (harness rule 11): ideas discovered mid-build land there, not in the spec, and it moves into marketplace/docs/ at Session 1.

## Before Day 1: Four Decisions and Checks

1. **Org name availability:** confirm `open-science-pillars` is free on GitHub before anything else (and, for Phase 2's connector, on PyPI); the name appears in every JSON and install command.
2. **Claude Science access:** confirm you can import skills into a Science workspace; the three-surface harness needs it from Session 5.
3. **PO.DAAC steward:** identify at least one internal reviewer for the podaac knowledge bundle; even one name makes the federated-knowledge story real at launch.
4. **AI-for-Science go/no-go:** the application drafts in Session 13 from ARCHITECTURE Part 6; the deadline is 2026-07-15, so it must land inside this build week.
5. **Institutional release path:** decide org ownership (personal community project vs institutionally managed) and, for anything derived from work scope, initiate your institution's open-source release process (new-technology reporting and software release authority) before public push; carry a "community project, not an official NASA, JPL, or PO.DAAC product" disclaimer in every README until formal affiliation exists; confirm export-control screening applies cleanly. This is the one pre-build action the documents cannot do for you.

## First Ten Minutes

```bash
mkdir -p ~/osp/docs-bootstrap ~/osp/harness/skills/osp-session ~/osp/harness/skills/osp-close
cp <this-directory>/*.md ~/osp/docs-bootstrap/
# Paste BUILD-HARNESS §2 into ~/osp/CLAUDE.md
# Paste BUILD-HARNESS §3 into ~/osp/harness/skills/osp-session/SKILL.md
# Paste BUILD-HARNESS §4 into ~/osp/harness/skills/osp-close/SKILL.md
ln -s ~/osp/harness/skills/osp-session ~/.claude/skills/osp-session
ln -s ~/osp/harness/skills/osp-close  ~/.claude/skills/osp-close
cd ~/osp && claude
```

Then: `/osp-session 0b`. Session 1 moves the docs from docs-bootstrap into `marketplace/docs/` so the repo becomes the single source of truth, and the harness carries the rest of the week.

## The Week at a Glance

| Day | Sessions | Focus |
|---|---|---|
| 1 | 0b, 1, start 2 | Harness, org, scaffolding |
| 2 | 2, 3 | Core knowledge skills |
| 3 | 4, 5 | UQ skill; core workflows; first golden notebook; first three-surface pass |
| 4 | 6 | ECCO (tight supervision; nothing else this day) |
| 5 | 7 ∥ 8, then 8b | Ocean science skills; SWOT; knowledge + eval seeding |
| 6 | 9, 10 | Ocean workflows; three-surface end-to-end; eval grading pass |
| 7 | 11, 12 | Tutorials, templates, contributing |
| 8 (buffer) | 13, 14 | Demos, AI-for-Science submission, launch |

**If the week slips:** the pre-agreed cut-line is Sessions 0b through 6. Core plus ECCO loading plus the knowledge pattern is a complete, announceable preview (Openscapes lightning-talk grade). Ship that rather than holding everything for Session 14; the rest lands as it lands.

## Non-Negotiables (the short list)

Everything is a skill (no commands/ directories). Descriptions ≤200 characters, keyword-first. Workflow skills stay invocable both ways; side effects live behind in-skill confirmation gates. Every dataset concept carries an Uncertainty section; every gotcha links its dataset with evidence and a status field; high-severity gotchas ship an eval case; every ingest hits log.md. Knowledge is declarative, never imperative: concepts state facts and never instruct the agent. A workflow skill with a computational recipe is not done without a green golden notebook (SPEC §6 scope rule). No headline number without an uncertainty statement or an explicit waiver. And no em dashes in any prose.

## Where the History Lives

Earlier drafts (v1-v3 designs, SPECIFICATION v0.1-v0.2, GUIDE v1-v2, the integration round) remain one directory up as the decision trail. Nothing in them is needed for the build; everything current is in this directory.
