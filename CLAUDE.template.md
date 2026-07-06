# Open Science Pillars: Workspace

This directory is the build workspace for the Open Science Pillars
organization (github.com/open-science-pillars). You are building the
plugins, knowledge bundles, and tutorials defined by the canonical
documents. Those documents are law; when this file and a canonical
document disagree, the canonical document wins, and you flag the
discrepancy instead of silently choosing.

<!-- Version pins: keep these current, or reference the docs by name
     without a version so they never go stale. As of this template the
     spec is v0.6.x and the implementation guide is v2.4.x. -->

## Canonical documents (read before acting, cite by section)
- marketplace/docs/SPECIFICATION.md          (what to build)
- marketplace/docs/IMPLEMENTATION-GUIDE.md   (in what order)
- marketplace/docs/PROGRESS.md               (current state; you update it)
- marketplace/docs/ARCHITECTURE.md           (why; strategy)
- marketplace/docs/phase2-preregistration.md (go/stop conditions; a gate)

## Repo map
core, ocean-science, hydrology: plugins (skills/, agents/, knowledge/,
verification/, evals/). marketplace: catalog + docs. tutorials: Quarto
book. plugin-template, knowledge-template: scaffolds.
nasa-daac-knowledge: canonical knowledge bundles (plugins pin snapshots).
build-kit: this harness. .github: org files.

## Global rules (non-negotiable)
1. NO commands/ directories. Everything is a skill.
2. Every SKILL.md starts with frontmatter: name; description <=200 chars,
   keyword-first, quoting any value containing a colon. Knowledge skills
   set user-invocable: false (exceptions: quality-control, analysis-review,
   uncertainty-quantification).
3. Workflow skills keep both invocation paths open; side effects are
   guarded by in-skill confirmation gates, never disable-model-invocation.
4. Plugins are self-contained: no ../ paths across repos, ever. Cross-repo
   references use full URLs; embedded knowledge is a pinned snapshot.
5. Every knowledge concept: type in frontmatter; datasets also carry
   title, description, tags, timestamp, resource, and an ## Uncertainty
   section. Gotchas link to their dataset. Update the bundle log.md.
6. Every workflow skill ships a marimo golden notebook in verification/
   that runs headless. A skill without a green golden notebook is not done.
7. Writing style in all prose: no em dashes. Use commas, colons,
   parentheses, or semicolons.
8. Never mark a PROGRESS item complete without its checkpoint evidence.
9. Every high-severity gotcha ships a matching eval case in the plugin's
   evals/ (the linter enforces this); seed cases are manually graded and
   recorded in evals/RESULTS-seed.md.
10. Every gotcha claim carries an evidence link and a status field; the
    seeder drafts, humans merge (draft becomes verified only through
    steward review with verified_by set).
11. Scope discipline: the current spec revision is frozen during a build
    arc. New ideas and discovered gaps go to marketplace/docs/PARKING.md
    with a one-line rationale, triaged into the next spec revision only at
    the scheduled window. The build writes the next spec revision;
    forethought does not.
12. Knowledge coupling (see marketplace/docs/design-knowledge-coupling.md):
    skills are deterministic procedures plus hard refusals; they carry NO
    dataset facts, inlined numbers, gotcha rules, or named-concept lists.
    Dataset knowledge lives in exactly one concept and is consulted
    dynamically (agents, and skills through an agent or a standing "discover
    and consult the bundle for this dataset" step; discover by glob, never a
    fixed list). A behavior stays hardcoded ONLY if it passes all three
    tests: invariant across products and time; a refusal or gate (not
    inform/adjust); and universal (wrong or unsafe regardless of dataset).
    When uncertain, it is knowledge. No concept content is duplicated into a
    skill.

## Session protocol
Start every session with /osp-session <N>. End every session with
/osp-close. Do not skip the close, even on a bad day; a truthful
yellow status beats a false green. See build-kit/DEVELOPING.md for how to
author a new session block and set its autonomy mode.
