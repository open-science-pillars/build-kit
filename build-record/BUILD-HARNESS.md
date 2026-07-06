# Open Science Pillars: Claude Code Build Harness

> **The runnable harness now lives in the [build-kit](https://github.com/open-science-pillars/build-kit) repo.**
> That repo holds the canonical `osp-session` / `osp-close` skills, the
> workspace-law template, a `bootstrap.sh`, and `DEVELOPING.md` (how to author a
> new session block and set its autonomy mode). Use build-kit to stand up a
> workspace; this document is the design rationale, and the paste-ready blocks
> below (§2-§4) are the original snapshot, kept for history. Where they and
> build-kit disagree, build-kit wins.

**Purpose:** the operational layer for building Open Science Pillars with Claude Code. The spec says what to build, the implementation guide says in what order; this harness makes each session start clean, end verified, and leave the workspace in a state the next session can trust: a workspace CLAUDE.md as law, session bootstrap and close skills, verification gates, and an explicit autonomy dial per session.

---

## 1. Workspace Layout

One workspace directory, every repo cloned flat, the harness skills wired as
project skills. This is what `build-kit/bootstrap.sh` produces:

```
osp-workspace/
├── CLAUDE.md                      # Workspace law (from build-kit/CLAUDE.template.md)
├── .claude/skills/
│   ├── osp-session -> build-kit/harness/skills/osp-session   # project skills
│   └── osp-close   -> build-kit/harness/skills/osp-close
├── marketplace/                   # Canonical docs:
│   └── docs/{SPECIFICATION, IMPLEMENTATION-GUIDE, PROGRESS,
│              ARCHITECTURE, BUILD-HARNESS, phase2-preregistration}.md
├── core/
├── ocean-science/
├── hydrology/
├── nasa-daac-knowledge/
├── tutorials/
├── plugin-template/
├── knowledge-template/
├── build-kit/
└── .github/
```

The harness skills are **not shipped inside any plugin** (they would pollute it),
but they are versioned in `build-kit` and linked into the workspace's
`.claude/skills/` as project skills, so they load when Claude Code runs from the
workspace. Earlier in the build they lived only in a personal workspace; that
single point of failure is closed by build-kit.

---

## 2. Workspace CLAUDE.md (original snapshot; use build-kit/CLAUDE.template.md)

_Do not paste this block verbatim: its version pins are frozen at the build's
early state. The maintained, version-current law is `build-kit/CLAUDE.template.md`._


```markdown
# Open Science Pillars: Workspace

This directory is the build workspace for the Open Science Pillars
organization (github.com/open-science-pillars). You are building the
plugins, knowledge bundles, and tutorials defined by the canonical
documents. Those documents are law; when this file and a canonical
document disagree, the canonical document wins, and you flag the
discrepancy instead of silently choosing.

## Canonical documents (read before acting, cite by section)
- marketplace/docs/SPECIFICATION.md          (what to build; v0.5.1)
- build-kit/IMPLEMENTATION-GUIDE.md   (in what order; v2.3.3)
- build-kit/PROGRESS.md               (current state; you update it)
- marketplace/docs/ARCHITECTURE.md           (why; strategy)

## Repo map
core, ocean-science: plugins (skills/, agents/, knowledge/, verification/)
marketplace: catalog + docs. tutorials: Quarto book. plugin-template,
knowledge-template: scaffolds. .github: org files.

## Global rules (non-negotiable)
1. NO commands/ directories. Everything is a skill (2026-01-24 unification).
2. Every SKILL.md starts with frontmatter: name; description <=200 chars,
   keyword-first. Knowledge skills set user-invocable: false (exceptions:
   quality-control, analysis-review, uncertainty-quantification).
3. Workflow skills keep both invocation paths open; side effects are
   guarded by in-skill confirmation gates, never disable-model-invocation.
4. Plugins are self-contained: no ../ paths across repos, ever.
5. Every knowledge concept: type in frontmatter; datasets also carry
   title, description, tags, timestamp, resource, and an ## Uncertainty
   section. Gotchas link to their dataset. Update the bundle log.md.
6. Every workflow skill ships a marimo golden notebook in verification/
   that runs headless. A skill without a green golden notebook is not done.
7. Writing style in all prose: no em dashes. Use commas, colons,
   parentheses, or semicolons.
8. Never mark a PROGRESS item complete without its checkpoint evidence.
9. Every high-severity gotcha ships a matching eval case in the plugin's
   evals/ (the linter enforces this); Phase-1 seeds are manually graded
   and recorded in evals/RESULTS-seed.md.
10. Every gotcha claim carries an evidence link and a status field; the
    seeder drafts, humans merge (draft becomes verified only through
    steward review with verified_by set).
11. Scope freeze: SPECIFICATION.md v0.5.1 is frozen until the Session 5
    integration test. New ideas and discovered gaps go to
    build-kit/build-record/PARKING.md with a one-line rationale, triaged into
    SPEC v0.6 only after Session 10. One exception: a failed Session-0b
    assumption check may trigger a targeted amendment before Session 1.
    The build writes the next spec revision; forethought does not.

## Session protocol
Start every session with /osp-session <N>. End every session with
/osp-close. Do not skip the close, even on a bad day; a truthful
yellow status beats a false green.
```

---

## 3. Session Bootstrap Skill: `osp-session`

`~/osp/harness/skills/osp-session/SKILL.md` (paste-ready):

```markdown
---
name: osp-session
description: Start an Open Science Pillars build session N. Loads the session plan from IMPLEMENTATION-GUIDE-v2, current state from PROGRESS-v2, and restates goals, steps, and checkpoint before any work.
disable-model-invocation: true
---

# OSP Session Bootstrap

You are starting build session $ARGUMENTS for Open Science Pillars.

1. Read build-kit/IMPLEMENTATION-GUIDE.md and extract the
   full block for Session $ARGUMENTS (goal, time, steps, checkpoint).
2. Read build-kit/PROGRESS.md. Report: items already green
   that this session depends on; anything red or yellow that blocks it.
   If a dependency is not green, STOP and say so.
3. Restate, in one screen: today's goal, the ordered steps, the
   checkpoint criteria, and this session's autonomy mode from the
   BUILD-HARNESS autonomy table. Wait for confirmation before step one.
4. During the session: cite spec sections when authoring
   ("per SPEC v0.2 §3.4"); when you and the spec disagree, flag it,
   do not improvise silently.
5. If a dataset peculiarity surfaces during testing, immediately draft
   the knowledge concept (correct type, frontmatter, links) and queue
   it for approval. This is the ingest loop; it is never deferred.
```

Invocation: `/osp-session 6` from anywhere in the workspace.

---

## 4. Session Close Skill: `osp-close`

`~/osp/harness/skills/osp-close/SKILL.md` (paste-ready):

```markdown
---
name: osp-close
description: Close an Open Science Pillars build session. Runs verification gates, updates PROGRESS-v2 and the session log truthfully, and prepares commits.
disable-model-invocation: true
---

# OSP Session Close

Run the gates, then the bookkeeping. Never reorder.

## Gates (report each as pass/fail with one line of evidence)
1. Checkpoint: walk this session's checkpoint list item by item.
2. Frontmatter: every SKILL.md touched today has valid frontmatter;
   descriptions <=200 chars. On Claude Code, run /doctor and confirm
   no skill descriptions are truncated or dropped.
3. Knowledge lint: if any knowledge/ bundle was touched, run the
   knowledge-linter agent and report its findings (the linter also
   flags high-severity gotchas lacking eval cases).
4. Golden notebooks: for every workflow skill touched, execute its
   verification/ marimo notebook headless (where one exists per the
   SPEC §6 scope rule); report green or the diff.
5. Surface matrix: list which of today's items still need Cowork and
   Claude Science verification; do not claim those columns.

## Bookkeeping
6. Update build-kit/PROGRESS.md: statuses with evidence,
   session-log row (date, actual hours, issues).
7. Stage commits per repo with messages "Session N: <summary>".
   Show me the diff summary; push only after my confirmation.
8. End with a three-line handoff note: what is green, what is yellow
   and why, and the single most important thing Session N+1 must know.
```

---

## 5. Autonomy Dial

Your call per session, but these are the defaults I would set given where correctness risk actually lives:

| Sessions | Mode | Rationale |
|---|---|---|
| 0b, 1 | **Batch-friendly.** Long leash; review at the end. | Scaffolding is mechanical; the spec fully determines the output; gates catch drift. |
| 2-5 | **Supervised checkpoints.** Autonomous within a step; pause between steps. | Skill wording quality matters; cheap to steer early. |
| 6-7 | **Tight supervision.** Review every reference doc before it lands. | ECCO grid, ShortNames, and budget formulation are the highest silent-error risk in the whole build. Verify against the ECCO tutorials yourself. |
| 8, 8b, 9 | Supervised checkpoints; knowledge concepts always human-approved before log.md. | Ingest loop discipline is being formed here. |
| 10 | Tight for the integration test; batch for fixes it surfaces. | |
| 11-14 | Batch-friendly, human review of anything public-facing before push. | |
| 15-16 | Supervised checkpoints. | New domain; concept quality being established, same as 8-9. |
| 17 | Tight supervision. | Canonical-home handoff and snapshot mechanics are one-way doors; the applied recipes anchor external trainings. |
| 18 | Supervised checkpoints; pre-registration gate before analysis work. | Runner correctness is mechanical; grading semantics are not. |
| 19 | Tight supervision. | The ablation is the headline claim; protocol deviations must be impossible or logged. |

Two force-multipliers as the golden-notebook net grows: first, once Sessions 2-5 notebooks are green, later refactors can run with a longer leash because regressions surface mechanically; second, Sessions 7 and 8 have no mutual dependency, so run them in parallel with two Claude Code instances in separate clones (or git worktrees) of ocean-science, merging Session 8 second since it touches fewer shared files.

---

## 6. The Week (historical: the original Phase-1 schedule)

| Day | Sessions | Hours | Notes |
|---|---|---|---|
| 1 | 0b, 1, start 2 | ~5.0 | Assumption smoke test and org name check first thing |
| 2 | 2 (finish), 3 | ~4 | |
| 3 | 4 (+UQ skill), 5 | ~5.5 | First three-surface pass; first golden notebook |
| 4 | 6 | ~2.5-3 | Tight supervision day; do not stack another session on ECCO day |
| 5 | 7 ∥ 8, then 8b | ~5.0 | Parallel instances if fresh; sequential if not |
| 6 | 9, 10 | ~5.0 | Ocean three-surface end-to-end; eval seed grading |
| 7 | 11, 12 | ~4.5 | |
| 8 (buffer) | 13, 14 | ~4.0 | AI-for-Science draft in 13; submit by 7/15 |

Total ~35.5 hours against your 4-5 hour days. The buffer day is real; protect it.

---

## 7. First Ten Minutes (historical; use build-kit/bootstrap.sh)

_This is the original personal-workspace bootstrap. The current, maintained
setup is `build-kit/bootstrap.sh` and the project-skill layout in §1._

```bash
mkdir -p ~/osp/docs-bootstrap ~/osp/harness/skills
# copy the five canonical .md files into ~/osp/docs-bootstrap/
# create the two harness skill dirs and paste §3 and §4 contents
ln -s ~/osp/harness/skills/osp-session ~/.claude/skills/osp-session
ln -s ~/osp/harness/skills/osp-close  ~/.claude/skills/osp-close
# paste §2 into ~/osp/CLAUDE.md
cd ~/osp && claude
> /osp-session 0b
```

From there the harness carries the week.
