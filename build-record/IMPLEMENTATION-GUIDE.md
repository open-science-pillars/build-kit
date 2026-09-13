# Open Science Pillars: Implementation Guide

> **Build record (historical).** This is the session-by-session build order. Continuing developers use it through the [build-kit](https://github.com/open-science-pillars/build-kit) repo; users want the [tutorials](https://github.com/open-science-pillars/tutorials).


**Version:** 2.4.0 (Phase-2 detail) · **Aligned to:** SPECIFICATION.md v0.6.0, ARCHITECTURE.md, BUILD-HARNESS.md
**Merged in 2.4.0 (2026-07-05):** Phase-2 outline expanded into full Session 15-19 blocks per SPEC v0.6 §10; ocean-bundle v0.6 completion scheduled into Session 18; pre-registration gate before Session 18-19 analysis work.
**Merged in 2.3.3:** Session 6 live-access fallback; Session 14 non-author validation restored; PARKING.md seeded (freeze mechanism in use); Session 1 moves PARKING.md with the canonical docs; consistency errata (versions, hours, punctuation) applied same date.
**Merged in 2.3.2 (last pre-build round):** assumption smoke test in Session 0b; scope-freeze rule (harness rule 11); MVP cut-line (README); Phase-1 total ~35.5 hr.
**Merged in 2.3.1:** launch hygiene: Discussions and DCO (Session 1); model-version recording in RESULTS-seed (Session 10); official plugin-directory submission (Session 14).
**Merged in 2.3:** knowledge stewardship: evidence links and status fields on Phase-1 concepts (Sessions 6, 8b, 10); knowledge-seeder agent, steward-playbook, and CODEOWNERS (Session 12); Session 17 rewritten to canonical-home plus pinned snapshot; Phase-1 total ~35.0 hr.
**Merged in 2.2:** evals seed: schema plus eight cases (Sessions 8b and 10), manual grading pass, eval-authoring guide (Session 12); runner and bundle ablation as Phase 2 Sessions 18-19.
**Merged in 2.1:** uncertainty-quantification skill (Session 4); golden notebooks woven through Sessions 5-10; Uncertainty sections in all dataset concepts (Sessions 6, 8b); ARSET-style template (Session 12); WASM demo (Session 13); Phase-1 total ~33.5 hr.

**Prerequisites:** Claude Code; GitHub org rights; git; NASA Earthdata Login; the Python 3.11 environment from the setup block below; Node 18+; Quarto CLI; `pip install marimo`; access to Claude Cowork and a Claude Science workspace for surface testing.

**Environment setup (once):**
```bash
conda create -n osp python=3.11 -y && conda activate osp
conda install -c conda-forge xarray dask netcdf4 h5netcdf scipy matplotlib \
  cartopy rioxarray cfgrib eccodes zarr geopandas pyproj rasterio \
  xesmf esmpy -y
pip install ecco_v4_py ecco_access earthaccess pymannkendall xgcm \
  cmocean marimo
# Earthdata: ~/.netrc with urs.earthdata.nasa.gov credentials, chmod 600
```

**Session protocol:** if using BUILD-HARNESS.md (recommended), `/osp-session N` opens and `/osp-close` closes every session; the blocks below are what those skills read. Otherwise cd into the repo, run `claude`, and paste the session's context manually.

---

## Session 0b: Three-Surface Test Harness (1.5 hr)

**Assumption smoke test first (30 min, before anything else).** Verify the five load-bearing assumptions and record results at the top of surface-testing-guide.md: (a) a third-party skill imports into your Claude Science workspace and triggers; (b) Cowork installs a plugin from an unlisted marketplace or direct upload (if only directory-listed plugins install, surface-parity claims change and Session 14's directory submission moves earlier); (c) `python <marimo-notebook>.py` exits nonzero on an assertion failure; (d) the nasa/earthdata-mcp server exists in usable form (else record the earthaccess-direct fallback); (e) `ecco_v4_py` and `ecco_access` import cleanly and their access functions match the spec's call pattern. Any failure triggers a targeted spec amendment before Session 1, the one exception to the freeze (harness rule 11).

Then write `marketplace/docs/surface-testing-guide.md`: the standard prompt set (per workflow skill: the slash form for Code and one conversational phrasing used verbatim on all three surfaces, with expected-behavior summary); per-surface install/import steps; the PROGRESS recording convention (Cd/Cw/Sc columns). Create `marketplace/docs/prompts/` with one file per core workflow skill (ocean prompts added in Session 9).

**Checkpoint:** five assumptions verified with results recorded; guide complete; prompt files for start, discover-data, report; access confirmed on all three surfaces.

---

## Session 1: Org, Repos, Marketplace (1.5 hr)

**Context for Claude Code:** "Open Science Pillars, Session 1, per SPECIFICATION.md §1-§2. Rules: NO commands/ directories; every plugin has knowledge/ and verification/ directories; plugins self-contained."

1. Create the GitHub org `open-science-pillars` manually (check name availability first).
2. Scaffold all seven Phase-1 repos per SPEC trees; placeholders carry name, purpose, authoring session, spec reference.
3. Write full-content files: marketplace.json (§2.2); both plugin.json; LICENSE + CITATION.cff everywhere; GOVERNANCE.md (provider-maintainer clause); CoC; the five issue templates including new_knowledge_concept (type, dataset, severity, evidence links); READMEs ("install core first" in ocean-science); ocean-science.local.md.template (SWOT + Knowledge blocks); both `.mcp.json` files as placeholders whose server entries are verified against the nasa/earthdata-mcp repository at authoring time (never trust URLs from earlier drafts).
4. knowledge-template: conformant empty bundle with one annotated example per concept type (dataset example includes the Uncertainty section); README walking §5 conformance.
5. plugin-template: skills-only structure with annotated example workflow skill, knowledge/, verification/ (one trivial green golden notebook as the pattern), README.
6. Move the canonical docs into `marketplace/docs/` (single source of truth from here on), including PARKING.md.
7. Init, commit, push all repos; test `claude plugin marketplace add open-science-pillars/marketplace`.
8. Enable GitHub Discussions on the marketplace repo and add the DCO sign-off check to PR requirements org-wide.

**Checkpoint:** org + 7 repos live; marketplace add lists both plugins; zero commands/; knowledge/ and verification/ present where specified; fifth issue template exists.

---

## Sessions 2-4: Core Knowledge Skills

Author each SKILL.md frontmatter-first (SPEC §0.3; descriptions from the §3.3 table; `user-invocable: false` except quality-control, analysis-review, uncertainty-quantification).

**Session 2 (2.0 hr): data-formats, xarray-fundamentals.** Content per SPEC §3.3 including magic-byte detection and per-format failure guidance. Build the synthetic ERA5-like NetCDF test fixture (script it into `core/verification/fixtures/make_fixtures.py` so it is reproducible). Tests: open and summarize; area-weighted global mean (never unweighted); baseline stated on climatology. Check `/doctor` shows no truncation.

**Session 3 (2.0 hr): basic-statistics, cartography.** Include the trend decision tree, pymannkendall worked example, cmocean table, figure sizes, and the uncertainty-visualization section (interval bands, spread/agreement maps, hatching; uncertainty map required beside interpolated or ML surfaces). Tests: Mann-Kendall trend map with stippling; seasonal panels with shared colorbar; anomaly series with interval band.

**Session 4 (2.5 hr): quality-control, uncertainty-quantification, reproducibility, analysis-review.** QC with the 20+ variable bounds table and MODIS/Landsat/Sentinel-2 QA decoding. **uncertainty-quantification per SPEC §3.3 full scope** (block bootstrap, ensemble-spread caveat, conformal prediction, native uncertainty fields, the reporting rule, the carbon-credit lower-bound example). reproducibility with the DOI quick table. analysis-review with the smell-test list AND the three UQ checks. Tests: bad-data fixture (unmasked -9999, impossible value, 6-month gap) fully flagged; a trend reported without uncertainty gets flagged by analysis-review; a bootstrap CI produced on request.

**Checkpoints (each):** frontmatter valid; budget clean; knowledge skills out of the menu, the three exceptions in it; behavior tests pass.

---

## Session 5: Core Workflow Skills, Linter, Knowledge, Golden Notebooks (3.0 hr)

1. Author start, discover-data, report per SPEC §3.4 (report's confirmation gate, concept-citing provenance, and the Results uncertainty rule; discover-data's bundle consultation).
2. Author agents/knowledge-linter per SPEC §3.5.
3. Seed core/knowledge (three concepts, index, log); run the linter; fix findings.
4. **Golden notebook:** `verification/analysis_pipeline.py` in marimo: runs the Session 2-4 fixture pipeline end to end (load → QC → anomaly → Mann-Kendall trend → figure) and asserts section-complete report content, a citation, and an uncertainty statement on the headline trend. Green via `python verification/analysis_pipeline.py`. start and discover-data are pure orchestration; the three-surface harness covers them (SPEC §6 scope rule).
5. **Three-surface integration test** with the Session 0b prompts: Code (slash + conversational), Cowork (conversational), Science (import + conversational). Record Cd/Cw/Sc; log surface friction in surface-testing-guide.md Known Differences; fix wording, re-test failures only.

**Checkpoint:** three workflow skills pass on all three surfaces; gate and provenance behaviors verified; linter clean; the core golden notebook green headless.

---

## Session 6: ECCO Skill + References + Knowledge Seed (2.5 hr; tight supervision)

1. Author references first (llc90-grid, variable-catalog, budget-formulation) per SPEC §4.2. **ShortName audit against live PO.DAAC; velocity = ECCO_L4_OCEAN_VEL_LLC0090GRID_MONTHLY_V4R4; record the verification date in the catalog.** Verify budget formulation against the ECCO v4 tutorial notebook line by line.
2. Author ecco/SKILL.md (reference-heavy, "Knowledge first" section).
3. Test data access: grid parameters load and merge; THETA 2010 native with Dask; regridded-budget request refused 🔴. If live PO.DAAC access fails or crawls, proceed against the ecco_v4_py tutorial sample dataset, mark the affected checkpoints yellow with a note, and retry live access during Session 10; do not let an outage consume the supervised ECCO day.
4. Seed knowledge: datasets/ecco-v4r4.md (Uncertainty section: no formal error fields; dynamical consistency stated plainly) and the two ECCO gotchas, each claim carrying an evidence link (ECCO tutorial section, PO.DAAC page, or your reproducing test) and `status: verified` with `verified_by` set after your own review (you are steward pro tem until the PO.DAAC handoff); log entries.

**Checkpoint:** references verified; access tests pass; refusal intact; three concepts lint-clean.

---

## Session 7: Ocean Grids, Budget Closure, Meridional Transport (2.0 hr; tight supervision)

Author the three skills per v0.1 scope. Author `recipes/ecco-mht-26n.md` (expected 0.8-1.4 PW mean range AND expected-uncertainty: the RAPID-comparison spread, with validation provenance) and `recipes/ecco-heat-budget.md` (expected residual: machine precision); meridional-transport and budget-closure read the recipes, not hardcoded numbers. If ECCO access is live: compute MHT at 26.5N and confirm against the recipe.

---

## Session 8: Water Masses, Mixed Layer, Sea Level, Indices (2.0 hr)

Four knowledge skills per v0.1 scope, frontmatter `user-invocable: false`. May run in parallel with Session 7 (separate clone or worktree; merge second).

---

## Session 8b: SWOT + PO.DAAC-Arc Knowledge (3.0 hr)

1. Author swot/SKILL.md + references/swot-products.md per SPEC §4.3.
2. Author load-swot workflow (parse region/cycles/tier; volume gate; flag decode; swath-aware summary).
3. Knowledge: datasets/swot-karin.md (current processing baseline with verification date; Uncertainty section: ssha uncertainty variables and caveats); gotchas/swot-calval-orbit-phases.md; datasets/grace-fo-mascons.md (Uncertainty: mascon error grids) with both GRACE gotchas; datasets/ghrsst-mur.md (Uncertainty: analysis-error field). Every gotcha links its dataset and carries at least one evidence link; set `status: verified` with `verified_by` after your review.
4. **Golden notebook** `verification/load_swot.py`: small regional SSH fixture; asserts flag decoding and swath structure.
5. Tests: small live regional load; cal/val gotcha surfaces when the date range spans it; volume gate fires on a large request. Lint the bundle.
6. **Eval seed (schema + first cases):** author `ocean-science/evals/SCHEMA.md` (case format per SPEC §8) and the first four cases: native-grid-refusal, geothermal-omission, swot-calval-window, grace-leakage.

**Checkpoint:** SWOT skill + workflow working; nine concepts lint-clean with Uncertainty sections on all four datasets; load_swot.py green; SCHEMA.md plus four eval cases drafted.

---

## Session 9: Ocean Workflow Skills (2.5 hr)

1. Author the seven workflow skills per SPEC §4.4 (no ocean start; core's start covers listing). Gates on the loaders; ocean-budget native-grid rule; transport reads the recipe; the three analysis skills authored fully.
2. **Golden notebooks:** `verification/{load_ecco,transport_analysis,ocean_budget}.py` on small fixtures (the ecco_v4_py tutorial sample or a scripted, cached subset per SPEC §6 fixtures policy): assert grid-merge structure, MHT within the recipe's range and spread, and budget residual at machine precision pointwise on the fixture cells (domain-integrated closure only on closed domains, per SPEC §6).
3. Add ocean prompt files to marketplace/docs/prompts/; spot-test slash + conversational on Code.

**Checkpoint:** seven skills authored; four ocean golden notebooks green headless; prompts filed.

---

## Session 10: Agents, Local Config, Three-Surface Ocean Integration (2.5 hr)

Agents per SPEC §4.5 (scout cites concepts; auditor checks the geothermal gotcha first). Fill the local config. Run the end-to-end (question → scout plan → load → MHT 26.5N → RAPID comparison → report) on Code, Cowork, and Science; practice one live ingest to log.md. Then the eval seed pass: add ocean's volume-gate case and core's three methodology cases (area-weighting, uncertainty-statement, trend-method); run each of the eight cases once manually on Code and rubric-grade by hand, recording results in each plugin's `evals/RESULTS-seed.md` (record the model version and date alongside each result).

**Checkpoint:** end-to-end green per surface; one ingested concept in log.md; report shows uncertainty statements; eight eval cases seeded with a recorded manual grading pass.

---

## Session 11: Tutorials 1-2 (2.0 hr)

Quarto. Tutorial 1 (Getting Started, ~10 min): install core, start, load fixture, QC, anomaly + map. Tutorial 2 (ECCO MHT, ~20 min): local config, load, transport at 26.5N with the uncertainty framing, overturning plot, report; plus the SWOT section (load a regional SSH scene, orbit-phase note). Headers record surfaces verified. Test both from fresh installs, timed.

---

## Session 12: Contributing, Templates, Tutorial 3 (2.5 hr)

knowledge-authoring-guide.md (concept types, Uncertainty-section requirement, evidence and status fields, trainings: frontmatter, ingest etiquette); eval-authoring-guide.md (case schema, graders, trials and CI reporting per SPEC §8); steward-playbook.md (duties, the review checklist from SPEC §5.4, the top-five-traps interview script, onboarding, Zenodo credit); CODEOWNERS in core and ocean-science mapping knowledge/ paths to stewards (you pro tem); `agents/knowledge-seeder/agent.md` per SPEC §3.5, tested by pointing it at the SWOT user-guide URL and confirming evidence-linked `status: draft` output with no merge; verification-guide.md (golden-notebook practice); skill/agent guides updated for frontmatter; **tutorials/templates/arset-style.md** per SPEC §7; finalize both template repos; Tutorial 3 (Build a Domain Plugin, ~30 min): scaffold from plugin-template, one skill, one knowledge concept (with evidence), one trivial golden notebook, install, test; its applied variant demonstrates the arset-style template.

---

## Session 13: Demos + AI-for-Science Draft (2.0 hr)

Surface-neutral demo script and recording (the ECCO-to-report story); **WASM companion**: export a trimmed MHT demo marimo notebook to browser-runnable form, linked from tutorials. Draft the AI-for-Science application from ARCHITECTURE.md Part 6 ("One Mission, Two Sciences"); half-day cap; submit before 2026-07-15.

---

## Session 14: Launch (2.0 hr)

README polish across repos; fresh-install test on all three surfaces; at least one non-author (a colleague or friendly scientist) completes Tutorial 2 unaided, with their friction notes captured; known-limitations doc (include surface deltas, which items are Code-verified only, and the non-author friction notes); submit both plugins to the Anthropic official plugin directory; announcement for Pangeo Discourse, Openscapes, ESIP leading with the knowledge-bundle + verification-layer story; PROGRESS final pass.

---

## Session 15: Hydrology Scaffold + SWOT River/Lake (2.5 hr)

Per SPEC v0.6 §10. 1. Scaffold the hydrology repo from plugin-template
(§10.1 tree; placeholders carry name/purpose/session/spec-ref). 2. Live
audit of SWOT hydrology collections (river reach/node, lake) against
CMR with dates recorded; author swot-hydro/SKILL.md + reference
(ocean/hydro product split; reach-vs-node scope as a first-class
fact). 3. Author load-swot-hydro (gate contract as load-swot). 4. Seed
datasets/swot-river-lake.md (+Uncertainty: node vs reach uncertainty
variables) and gotchas/swot-reach-node-scope.md, evidence-linked,
steward-reviewed. 5. Golden: load_swot_hydro.py on a synthetic
reach/node fixture. **Checkpoint:** scaffold live; skill + loader
authored; two concepts verified; golden green.

## Session 16: GRACE Groundwater + NWIS + SMAP (2.5 hr)

1. grace-groundwater skill (TWS-to-groundwater partitioning caveats)
reusing the 8b GRACE concepts via a §5.7 pinned snapshot (source and
commit recorded in index.md). 2. nwis skill + load-nwis via
dataretrieval (gotcha: provisional data revised after approval;
verified against a live gauge pull). 3. smap skill + load-smap
(radar-loss lineage). 4. Concepts: nwis-streamflow, smap-l3 datasets
(+Uncertainty), nwis-provisional-data and smap-radar-loss gotchas
(severity high, eval ids reserved). 5. Golden: load_nwis.py on a
cached gauge subset. **Checkpoint:** three skills + two loaders; four
concepts verified; snapshot mechanics demonstrated; golden green.

## Session 17: Applied Pack + Canonical Home (2.5 hr; tight supervision)

1. drought-analysis and reservoir-analysis workflows reading
recipes/{drought-index, reservoir-storage-change}.md (ARSET
reservoir-management anchor, linked with credit); recipes carry
expected values AND expected-uncertainty validated against gauge
records. 2. Goldens: drought_analysis.py, reservoir_storage.py.
3. Create nasa-daac-knowledge as the CANONICAL HOME: move podaac
concepts under a PO.DAAC steward CODEOWNERS entry (you pro tem until
the handoff), pin snapshots back into ocean-science and hydrology with
source repo + commit in index.md (§5.7), demonstrate the release-time
sync step. 4. Hydrology three-surface end-to-end with prompt files.
**Checkpoint:** applied pack green; canonical home live with snapshot
round-trip; e2e recorded per surface.

## Session 18: Evals Runner + Bundle Completion (3.0 hr)

GATE: docs/phase2-preregistration.md must be published BEFORE this
session's analysis work. 1. Org evals repo: Agent SDK headless runs of
Claude Code with plugins installed; programmatic graders plus the
rubric judge; suite manifests; N-trial execution (default 20) with
binomial-CI pass rates; scoreboard as versioned JSON plus a static
page. 2. Ocean-bundle v0.6 completion (SPEC §10.5): promote V4R4B,
MHT-scope, and crossover gotchas with matching eval cases; core
fill-value case; salt/volume recipes with measured residuals.
3. Hydrology eval seed graded into RESULTS-seed.md. **Checkpoint:**
runner reproduces the Phase-1 manual grades within CI bounds; bundle
completion lint-clean; scoreboard renders.

## Session 19: The Ablation (2.0 hr; tight supervision)

Per the pre-registration, no deviations without a logged amendment:
gotcha-avoidance suite bundle-on vs bundle-off, same model, same N=20,
trap-hit-rate delta with binomial intervals, published to the
scoreboard and PROGRESS regardless of outcome. Wire goldens and evals
into per-PR CI (actions SHA-pinned, no secrets). Lands before
Openscapes/ESIP outreach so the announcement carries numbers.
**Checkpoint:** ablation published with intervals; CI green on a test
PR; announcement updated with the numbers (or the null result).

---

## Session Summary

| Session | Focus | Hours |
|---|---|---|
| 0b | Surface harness + assumption smoke test | 1.5 |
| 1 | Org, repos, marketplace, templates | 1.5 |
| 2 | data-formats, xarray | 2.0 |
| 3 | statistics, cartography (+UQ viz) | 2.0 |
| 4 | QC, UQ skill, repro, review | 2.5 |
| 5 | Core workflows, linter, knowledge, 3 goldens, 3-surface | 3.0 |
| 6 | ECCO + references + seed | 2.5 |
| 7 | grids, budgets, transport (+recipes) | 2.0 |
| 8 | 4 ocean knowledge skills | 2.0 |
| 8b | SWOT + arc knowledge + golden + eval schema/cases | 3.0 |
| 9 | Ocean workflows + 3 goldens | 2.5 |
| 10 | Agents + 3-surface integration + eval seed pass | 2.5 |
| 11 | Tutorials 1-2 | 2.0 |
| 12 | Contributing + templates + seeder + playbook + T3 | 2.5 |
| 13 | Demos + WASM + AI4S | 2.0 |
| 14 | Launch | 2.0 |
| **Phase 1** | | **~35.5** |
| v0.6 | Spec revision: PARKING triage, hydrology §10, Session 15-19 blocks, pre-registration | 1.0 |
| 15 | Hydrology scaffold + SWOT river/lake | 2.5 |
| 16 | GRACE groundwater + NWIS + SMAP | 2.5 |
| 17 | Applied pack + canonical home | 2.5 |
| 18 | Evals runner + ocean-bundle completion | 3.0 |
| 19 | The ablation | 2.0 |
| **Phase 2** | | **~13.5** |
