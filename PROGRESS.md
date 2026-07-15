# Open Science Pillars: Build Progress

> **Historical build record.** This is no longer the live roadmap. See
> [ROADMAP.md](ROADMAP.md), generated from `roadmap/roadmap.yaml`, for current
> organization work. The rows below preserve the evidence and decisions from
> numbered Sessions 0b-19.


**Last Updated:** 2026-07-15 · **Org:** github.com/open-science-pillars
**Phase:** historical build complete; operate-and-evolve work is in the roadmap
Surface columns: Cd = Claude Code, Cw = Cowork, Sc = Claude Science.
Legend: 🟢 complete · 🟡 in progress · ⚪ not started · 🔴 blocked · 📋 proposed · n/a not applicable

## Phase 0: Documents (final set)

| Deliverable | Status |
|---|---|
| ARCHITECTURE.md (v4 + merged notes) | 🟢 |
| SPECIFICATION.md v0.5.1 (frozen) | 🟢 |
| IMPLEMENTATION-GUIDE.md v2.3.3 | 🟢 |
| BUILD-HARNESS.md | 🟢 |
| PARKING.md (seeded, 4 items) | 🟢 |
| PROGRESS.md (this file) | 🟢 |
| AI-for-Science draft (Session 13) | 🟢 draft completed 2026-07-05; submission declined by project owner 2026-07-15 |

## Infrastructure (Sessions 0b-1)

| Task | Status |
|---|---|
| Assumption smoke test: 5 items verified and recorded | 🟢 results atop surface-testing-guide.md, 2026-07-04; (d) hosted endpoint down, earthaccess-direct fallback recorded; (a) via marketplace install, PARKING #5 |
| Surface-testing guide + prompts/ | 🟢 docs/surface-testing-guide.md + docs/prompts/{start,discover-data,report}.md (moved from docs-bootstrap in Session 1) |
| Org created (name availability confirmed) | 🟢 created by Paul 2026-07-04; PaulMRamirez admin |
| 7 repos scaffolded; canonical docs in marketplace/docs/ | 🟢 all seven pushed public 2026-07-04, Session 1 commits; docs-bootstrap deleted |
| marketplace add works; both plugins install | 🟢 Cd 2026-07-04: add succeeds, core and ocean-science install; needed owner + source-object fixes vs SPEC §2.2 (PARKING #6); Cw/Sc install of the real marketplace waits for Session 5 |
| knowledge/ + verification/ present; zero commands/ | 🟢 core, ocean-science, plugin-template; `find . -type d -name commands` = 0; template golden notebook green (exit 0) |
| 5 issue templates incl. new_knowledge_concept | 🟢 .github/.github/ISSUE_TEMPLATE/{bug_report,feature_request,new_skill,new_domain_plugin,new_knowledge_concept}.yml |
| DCO app installed org-wide (step 8) | 🟡 needs Paul in the web UI: github.com/apps/dco → install for open-science-pillars, all repositories; blocking ruleset deferred to Session 14 |

## Core Plugin (Sessions 2-5)

| Item | Cd | Cw | Sc | Notes |
|---|---|---|---|---|
| data-formats | 🟢 | ⚪ | ⚪ | Cd 2026-07-04: open-and-summarize behavior test passed (magic bytes, sentinel scan, full summary) |
| xarray-fundamentals | 🟢 | ⚪ | ⚪ | Cd 2026-07-04: weighted-mean and climatology tests passed (289.06 K weighted, 6.7 K bias named, baseline stated) |
| basic-statistics | 🟢 | ⚪ | ⚪ | Cd 2026-07-04: trend-map test passed (Hamed-Rao + FDR, inverted stippling); worked example verified on fixture (0.199 vs 0.20 K/decade) |
| uncertainty-quantification | 🟢 | ⚪ | ⚪ | user-invocable; Cd 2026-07-04: block-bootstrap CI test passed (12-month blocks, detrended residuals, method/level/seed stated) |
| cartography (+UQ viz) | 🟢 | ⚪ | ⚪ | Cd 2026-07-04: seasonal panels shared-colorbar and anomaly interval-band tests passed; captions define test, level, method |
| quality-control | 🟢 | ⚪ | ⚪ | user-invocable; Cd 2026-07-04: bad-data fixture fully flagged blind (300 sentinels, 400 K value located, 6-month gap), six checks reported |
| reproducibility | 🟢 | ⚪ | ⚪ | Cd 2026-07-04: authored with DOI quick table; exercised indirectly (seeds and env recorded in test transcripts) |
| analysis-review (+3 UQ checks) | 🟢 | ⚪ | ⚪ | user-invocable; Cd 2026-07-04: uncovered-trend claim blocked (missing uncertainty 🔴, uncorrected OLS 🔴); also caught fixture provenance and a non-reproducing claimed number |
| start | 🟢 | ⚪ | ⚪ | Cd 2026-07-04 slash+conv: five parts, one screen, one next step |
| discover-data (surfaces gotchas) | 🟢 | ⚪ | ⚪ | Cd 2026-07-04 slash+conv: fallback named, table, one question; honestly reported ghrsst-mur placeholder status |
| report (gate; concept cites; uncertainty rule) | 🟢 | ⚪ | ⚪ | Cd 2026-07-04: gate held unconfirmed (variant A), honored pre-authorization (B), refused empty session (C); uncertainty rule enforced; concept-vs-skill citation nuance to re-verify in Session 10 |
| knowledge-linter agent | 🟢 | n/a | n/a | Cd 2026-07-04 first real run: 3 real 🔴 caught (strict-YAML frontmatter) plus dead URL and CF section drift; proposed diffs only |
| core knowledge bundle (3 concepts) lint-clean | 🟢 | n/a | n/a | zero 🔴; steward-verified by Paul Ramirez; standing 🟡 eval case (PARKING #8) |
| /doctor description budget clean | 🟢 | n/a | n/a | via /skills per PARKING #7: 30 skills loaded, no truncation |
| Core golden notebook (analysis_pipeline) green headless | 🟢 | n/a | n/a | exit 0; asserts six sections, 3 concept citations, uncertainty on headline (0.199 +/- 0.002 K/decade) |
| Core evals seed: 3 methodology cases | 🟢 | n/a | n/a | graded 2026-07-04 in RESULTS-seed.md: area-weighting pass, trend-method pass with note, uncertainty-statement FAIL recorded honestly |
| Core 3-surface integration test | 🟢 | 🟡 | 🟡 | Cd complete 2026-07-04 (all prompt files, both forms); Cw/Sc deferred by Paul, prompts and setup ready in docs/prompts/ (report.md carries the inline two-step) |

## Ocean Science (Sessions 6-10)

| Item | Cd | Cw | Sc | Notes |
|---|---|---|---|---|
| ecco skill + 3 references (ShortNames verified, OCEAN_VEL) | 🟢 | ⚪ | ⚪ | Cd 2026-07-04: 19 ShortNames CMR-audited (51-collection sweep), geometry+THETA granule-verified live, budget formulation tutorial-quoted; refusal test passed (regridded-budget-refusal.md) |
| swot skill + reference | 🟢 | ⚪ | ⚪ | Cd 2026-07-04: C/D version families CMR-audited, cal/val-only-in-D probed, granule-verified structure |
| ocean-grids / budget-closure / meridional-transport | 🟢 | ⚪ | ⚪ | read recipes; Cd 2026-07-04 authored under tight supervision, zero hardcoded expected values (verified by review) |
| water-masses / mixed-layer / sea-level / ocean-indices | 🟢 | ⚪ | ⚪ | Cd 2026-07-04 authored+reviewed; definition-sensitivity framing; V4R4B rule in sea-level, ONI/PDO/AMO convention traps in indices |
| load-ecco / load-swot (volume gates) | 🟢 | ⚪ | ⚪ | both Cd-green: load-swot gate held on 7.25 TB; load-ecco spot test passed (cache hit, merge contract, snapshot foresight) |
| ocean-budget (native-grid 🔴 rule) | 🟢 | ⚪ | ⚪ | Cd 2026-07-04 authored; refusal already demonstrated Session 6 (regridded-budget-refusal.md); formulation verified by the golden |
| transport-analysis / compare-obs | 🟢 | ⚪ | ⚪ | Cd 2026-07-04; transport spot test reproduced anchor AND caught the global-vs-Atlantic scope error (recipe corrected under steward review) |
| water-mass / mixed-layer / sea-level analysis | 🟢 | ⚪ | ⚪ | Cd 2026-07-04 authored+reviewed per one-paragraph specs |
| ecco-scout (cites concepts) / budget-auditor (geothermal check) | 🟢 | n/a | n/a | Cd 2026-07-04: scout read-only with in-plan citations required; auditor recipe-sourced tolerance, geothermal-first; scout plan exercised in the e2e |
| local config filled (SWOT + Knowledge blocks) | 🟢 | n/a | n/a | filled in the e2e project 2026-07-04; the e2e run honored its 2 GB gate autonomously (narrowed its own window) |
| podaac-arc bundle: 4 datasets (+Uncertainty), 5 gotchas, 2 recipes; lint-clean | 🟢 | n/a | n/a | 11 of 11 steward-verified 2026-07-04; three full lints, zero 🔴; Uncertainty sections on all four datasets |
| All seed gotchas: evidence links + status: verified (verified_by set) | 🟢 | n/a | n/a | 5 of 5, every one evidence-linked, verified_by Paul Ramirez; GIA severity medium per recorded rationale |
| 4 ocean golden notebooks green headless | 🟢 | n/a | n/a | all four green 2026-07-04: load_swot, load_ecco, transport_analysis (both anchors + basin-sum identity), ocean_budget (abs residual max 5.0e-11 degC/s over 3.34M cell-months) |
| Live ingest practiced (concept in log.md) | 🟢 | n/a | n/a | rapid-mocha ingested via the operational loop during the e2e (SharePoint dead-end, DOI-first rule), steward-verified same session |
| evals/ SCHEMA + 5 gotcha/rejection cases | 🟢 | n/a | n/a | all five real cases 2026-07-04; plus core's three methodology cases |
| Manual grading pass recorded (RESULTS-seed) | 🟢 | n/a | n/a | both plugins, model claude-fable-5 and dates recorded: ocean 5/5 pass; core 2/3 pass, uncertainty-statement FAIL recorded honestly as the seed finding |
| Ocean 3-surface end-to-end | 🟢 | 🟡 | 🟡 | Cd 2026-07-04: anchors reproduced, gate honored autonomously, real RAPID/MOCHA data compared (r=0.94, offset inside recipe spread), report with uncertainty statements; Cw/Sc packet handed to Paul |

## Tutorials, Community, Launch (Sessions 11-14)

| Deliverable | Status |
|---|---|
| Tutorial 1 / 2 (+SWOT) / 3 (Quarto; surfaces recorded) | 🟢 all three pushed 2026-07-05, fresh-walkthrough timed (4.6 / 15.0 / 12.3 min vs 10/20/30 targets); headers record surfaces (T1/T2 Cw/Sc pending with the packet; T3 Code-side by nature); in-plugin quickstarts (core, ocean-science) were missed by the Session 11 checkpoint and filled 2026-07-05 on steward catch |
| arset-style template; knowledge-, eval-, and verification-authoring guides | 🟢 2026-07-05, plus skill/agent/connector/testing guides: zero placeholder docs remain in marketplace/docs |
| steward-playbook.md + CODEOWNERS (knowledge paths) | 🟢 2026-07-05; playbook with §5.4 checklist and interview script; CODEOWNERS in core and ocean-science map /knowledge/ to @PaulMRamirez |
| knowledge-seeder agent (drafts with evidence; never merges) | 🟢 2026-07-05 test-passed on PO.DAAC SWOT docs: 4 evidence-linked drafts, 7 open questions, redirects off-domain refused, nothing merged |
| Demo recording + WASM companion | 🟡 script + WASM companion pushed 2026-07-05 (notebook headless-green, export linked from tutorials index); recording is Paul's take |
| AI-for-Science submission | n/a declined by project owner 2026-07-15; no submission issue will be seeded |
| Fresh-install ×3 surfaces; known-limitations | 🟡 Code fresh-install re-verified 2026-07-05 (add + both installs in 8 s, smoke green); known-limitations.md published; Cw/Sc install rides Paul's packet |
| Announcement (Pangeo / Openscapes / ESIP) | 🟡 draft in docs/announcement-draft.md (success criteria stated per PARKING #1); posting is Paul's call after the human-side items land |

## Phase 2 (SPEC v0.6 §10; sessions per guide v2.4)

| Item | Status |
|---|---|
| SPEC v0.6 published (PARKING triage executed; hydrology §10; Session 15-19 blocks; autonomy rows) | 🟢 2026-07-05 |
| Phase-2 pre-registration published before results | 🟢 docs/phase2-preregistration.md, 2026-07-05 |
| S15 hydrology scaffold + SWOT river/lake | 🟢 2026-07-05: repo live (8th public), skill+loader authored, 2 concepts steward-verified from live granule evidence, golden green (random-vs-systematic gap asserted) |
| S16 GRACE groundwater + NWIS + SMAP | 🟢 2026-07-05: 3 skills + 2 loaders, 4 concepts steward-verified from live evidence (P/A transition observed; SPL3SMAP bounded span), §5.7 snapshot demonstrated with provenance + restructure fix, load_nwis golden green |
| S17 applied pack + canonical home | 🟢 2026-07-05: recipes with measured anchors (regulated-gauge gotcha ingested from a natural experiment), 4 goldens green, canonical home live (nasa-daac-knowledge@a0c84fff959f, round-trip byte-identical), eval seed 6/6, Cd e2e PASS (falsified and fixed a recipe month label) |
| S18 evals runner + ocean-bundle v0.6 completion | 🟢 2026-07-05: §10.5 done (3 gotchas promoted + eval cases, core fill-value case, salt+volume recipes with MEASURED round-off residuals and green goldens); evals runner repo built (package + selftest green + scoreboard rendered from real seed grades); live N=20 sweep is the CI job |
| S19 ablation published with intervals | 🟡 2026-07-05: harness built (ablate.sh strips knowledge/ + restores), CI wired (evals selftest + core golden, SHA-pinned, no secrets; commands green locally), N=3 Opus PILOT run (Fable 5 quota-exhausted): null ON-OFF delta exposed a design confound (skills carry the gotcha rules), logged as a pre-reg amendment. Powered N=20 on recorded model is the CI/cloud job |

## Phase 2+ snapshot (historical; superseded by ROADMAP.md)

| Item | Status | Champion |
|---|---|---|
| hydrology (S15-17; ARSET reservoir anchor) | 📋 | |
| nasa-daac-knowledge (podaac promoted; steward handoff) | 📋 | PO.DAAC steward needed |
| earthaccess-mcp | 📋 | |
| remote-sensing / models-and-reanalysis (ensembles skill) / applied-science | 📋 | |
| planetary-science + pds-knowledge | 📋 | Bessel tie-in |
| evals repo: runner, graders, scoreboard (S18) | 🟢 2026-07-05: run_evals/graders/judge/stats/scoreboard, self-test green (12 graders + aggregation), manifests for all 3 plugins, seed-baseline scoreboard rendered | |
| Bundle ablation with headline numbers (S19) | 🟡 pilot done (null at N=3, confound found); powered N=20 pending CI/cloud + revised design | before outreach |

## Session Log

| Session | Date | Actual hrs | Issues |
|---|---|---|---|
| 0b | 2026-07-04 | ~1.0 | osp conda env did not exist, created per guide prerequisites; hosted earthdata-mcp endpoint unreachable (local/Docker paths documented, fallback recorded); Science installs plugins via unlisted marketplace like Cowork (PARKING #5); ecco_access has no top-level ecco_podaac_download (use ecco_download / ecco_podaac_download_subset) |
| 1 | 2026-07-04 | ~0.7 | marketplace.json needed two schema fixes vs SPEC §2.2 verbatim (owner object; source objects instead of repository), PARKING #6; DCO app install left as a manual web-UI step; /doctor is TUI-only headless, description budget verified by count (28 skills, 3575 chars), interactive /doctor lands in Session 2; README-START-HERE.md retained in docs/ rather than deleted with docs-bootstrap |
| 2 | 2026-07-04 | ~1.0 | plugin updates are version-gated at 0.3.0, mid-build refreshes need uninstall/reinstall (decide: patch bumps per session or keep reinstalling); /doctor 2.1.201 has no skills section, /skills carries the budget check now (PARKING #7); ERA5-like fixture generated not committed per §6; behavior-test agent wrote a stray file beside the fixture, removed |
| 3 | 2026-07-04 | ~1.0 | pymannkendall hamed_rao returns NaN variance on ~1.5% of cells in per-cell map use; failure mode and deliberate-fallback rule captured in basic-statistics (ingest loop); figure-producing behavior tests take several minutes per headless agent run, plan Session 5 accordingly |
| 4 | 2026-07-04 | ~1.2 | none blocking; QC test kept honest by copying the bad fixture to a neutral name away from the README; plugin reinstall hot-loads skills into a running session (observed), useful for Session 5; T2 review caught the deliberately wrong 0.21 claim by recomputation |
| 5 | 2026-07-04 | ~1.8 | linter's first run caught 3 real frontmatter 🔴s (strict YAML vs Claude Code's lenient parser) plus a dead evidence URL; report-gate nuance: an explicit "saved as X" reads as confirmation given (recorded in behavior/report-gate.md); report Provenance cited skills rather than knowledge concepts, re-verify at Session 10; discover-data honestly surfaced ghrsst-mur placeholder status; Earthdata ~/.netrc set up and validated, ECCO velocity ShortName pre-verified in live CMR; behavior-test prompt class added (10 files) per Paul; Cw/Sc integration deferred |
| 6 | 2026-07-04 | ~1.5 | live PO.DAAC fast (209 MB in 7 s), tutorial-sample fallback never needed; ecco_access 0.3.1 quirks found and worked around: static collections get guessed nonexistent filenames (use earthaccess) and bare variable-name queries open an interactive picker that hangs scripts (use exact ShortNames), PARKING #10; V4R4B B-release rows for SSH/OBP discovered in the sweep, PARKING #9; linter check-11 rewordings applied on steward decision; ECCO data cache primed at ~/ECCO_V4r4 for Session 7 |
| 7 | 2026-07-04 | ~1.1 | MHT 26.5N live-validated: 2010 mean 1.098 PW inside 0.8-1.4, flux year downloaded in 15 s; close lint caught a real self-contradiction (budget-formulation's 1e-9-relative float32 claim vs epsilon ~1.2e-7), reconciled to round-off/epsilon framing with 1e-6 as explicit pass tolerance; conda-run heredoc stdin failure reconfirmed, scripts-from-files is the rule |
| 8 | 2026-07-04 | ~0.5 | no issues; ran sequentially rather than parallel-worktree (Session 7 momentum made the parallel split unnecessary); all nine ocean knowledge skills now authored |
| 8b | 2026-07-04 | ~1.9 | SWOT version-family split discovered by probe (cal/val only in D; C returns empty silently) and became verified gotcha evidence; crid drift within collections recorded; live loads cheap (8 regional granules ~9.4 MB each); volume gate demonstrated on a 7.25 TB request; linter caught three more check-11 phrasings (my recurring drafting habit, all reworded); load_swot golden's own sanity assert caught a fixture-magnitude bug before ship |
| 9 | 2026-07-04 | ~2.3 | two verified concepts corrected by the verification loop itself: heat-budget tolerance re-grounded on measurement (relative criteria meaningless below float32 quantization; now absolute 1e-10 degC/s), and the MHT recipe anchor rescoped after a skill-following test agent discovered it was the global circle not the Atlantic (basin decomposition verified: 0.666+0.430+0.002=1.098), PARKING #11; ecco_v4_py basin masks need binary data installed (env quirk, noted in recipe) |
| 10 | 2026-07-04 | ~1.6 | e2e exceeded spec: fetched real RAPID/MOCHA obs via DOI after the official page dead-ended in SharePoint (that discovery became the build's first operational ingest, rapid-mocha.md); e2e honored the local-config gate autonomously by narrowing its own window; eval seed finding: the house uncertainty rule does not reliably fire on uncoached computation prompts outside the report workflow (core uncertainty-statement FAIL, recorded for Phase-2 tuning); Cw/Sc surface pass remains with Paul |
| 11 | 2026-07-05 | ~1.2 | Quarto wasn't installed (prerequisite gap; user-space tarball install, no sudo); timing claims drafted before measurement were caught and replaced with measured values pre-review; T2 walkthrough ingested the SWOT crossover-calibration finding (ssha arrives uncorrected, +/-2.9 m ramp on flag-gated data) and the whole-pass spatial-match nuance; close lint then showed both SWOT skills routed around the new fact, accommodation diffs applied (PARKING #13 for gotcha promotion) |
| 12 | 2026-07-05 | ~1.4 | seeder test surfaced enrichment candidates our bundle lacks (C-to-D transition dates, 2024 telemetry window; drafts preserved as test artifacts for optional steward promotion); T3 walkthrough independently rediscovered both known ecosystem wrinkles and negative-tested its golden; Quarto book now three chapters |
| 13 | 2026-07-05 | ~0.9 | WASM export path exercised for the first time (marimo export html-wasm; embedded verified numbers, no credentials in-browser); application draft leans on built-Phase-1 evidence (closure numbers, RAPID episode, the scope catch); recording and submission remain with Paul |
| 14 | 2026-07-05 | ~0.8 | machine-side launch complete: READMEs polished, known-limitations honest (Code-verified-only list, the kept eval failure, ecosystem wrinkles), announcement drafted with pre-stated success criteria; T3 test's tide-gauges demo plugin found installed and cleaned up; human-side punch list handed to Paul (Cw/Sc packet, non-author Tutorial 2, directory submission, DCO, recording, AI4S submission) |
| 15 (v0.6 spec session) | 2026-07-05 | ~1.0 | Session 15's preconditions were unmet (outline only, no spec detail, triage queued); replanned on steward decision into the v0.6 revision: 13-item PARKING triage executed, SPEC 0.6.0 with §10, guide 2.4.0 with full S15-19 blocks, autonomy rows 15-19, pre-registration published before any Phase-2 result |
| 15 (build) | 2026-07-05 | ~1.3 | CMR audit found the reach/node collection split, the C/D repeat, LakeSP obs/prior/unassigned, L4 discharge, and SIMULATED pre-launch products in the same catalog (trap recorded); live granule pulls verified anatomy (127-attr reach, 57-attr node, 8x volume asymmetry); close gate caught a scaffold frontmatter escaping bug |
| 16 | | | |
| 16 | 2026-07-05 | ~1.2 | live NWIS pull delivered textbook P/A evidence (trailing month 100% P vs 2023 100% A) plus a bonus ingest (dataretrieval nwis.get_dv deprecated for 2027 removal, recorded in skill+concept); close lint caught the flat-snapshot layout breaking pinned relative links (restructured to canonical shape, files byte-identical); steward ruling: rule-9 eval coverage for pinned copies is owned by the canonical bundle |
| 17 | 2026-07-05 | ~2.3 | recipe-anchor measurement exposed the regulated-gauge trap (Lees Ferry classified drought and record-snowpack years identically; ingested with the Roaring Fork natural experiment as evidence); e2e falsified the reservoir recipe's minimum-month label (Feb->Apr 13-14, steward-approved erratum); seed case 1 needed a rerun (12-turn cap produced no output, recorded in RESULTS); placeholder sweep now a standing close gate, first org-wide zero |
| doc-pass | 2026-07-05 | ~2.0 | documentation and continuity pass (SPEC v0.6.1): five-persona doc-review workflow (zero confirmed blockers; corroborated the leaks and found new ones: broken cross-repo evidence links in the canonical bundle, governance pro-tem-review gap, guide summary table stopping at Session 14); aggressive build-era cleanup (session stamps, stale v0.5.1 cites, PARKING refs, build hedges, verified_by -> role, seed-prose reframe); newcomer path repaired (glossary, README rewrites, per-repo status); contributor path repaired (CONTRIBUTING de-stale, episode-with-lesson retrofits, docs map); new build-kit repo closes the harness single-point-of-failure |
| 18 | 2026-07-05 | ~3.0 | §10.5 bundle completion: the volume budget surfaced a real formulation trap (WVELMASS already carries the surface freshwater flux, so a separate oceFWflx forcing term double-counts and blows the k=0 residual to ~1e-8; correct budget is transport-convergence only, closes to 4.6e-12), recorded in the recipe and reference; salt closes to 7.2e-11 g/kg/s. Evals runner built and self-tested; live agentic trials are slow (a planning-case trial took 3+ min), so the full N=20 sweep is documented as the CI job, not a laptop run. Lint zero red; one yellow (draft-vs-verified log wording) fixed |
| 19 | 2026-07-05 | ~2.0 | the pilot earned its keep: it caught that Fable 5 was quota-exhausted (all trials returned the limit message; runner hardened to track infra errors separately) AND, re-run on Opus, that the ablation shows ZERO ON-OFF delta because the skills duplicate the gotcha rules, so stripping only knowledge/ changes nothing: a design confound found before spending N=20 compute. Harness (strip/restore verified), CI (SHA-pinned, no secrets, green locally), and the amendment all landed; the powered run is a CI/cloud job with the revised design |
