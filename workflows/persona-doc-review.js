export const meta = {
  name: 'persona-doc-review',
  description: 'Review Open Science Pillars documentation through five user and contributor personas, then adversarially verify each blocker before it becomes a fix task',
  whenToUse: 'Run before and after a documentation pass to find and then confirm-cleared journey-level blockers across the org repos',
  phases: [
    { title: 'Personas', detail: 'five personas walk their journeys read-only' },
    { title: 'Verify', detail: 'one skeptic per blocker confirms it is real' },
  ],
}

// The local workspace root holding all nine repos, read-only for this review.
const ROOT = (args && args.root) || '/Users/pramirez/Development/ClaudeCode/osp'

const FINDINGS_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  properties: {
    findings: {
      type: 'array',
      items: {
        type: 'object',
        additionalProperties: false,
        properties: {
          journey_step: { type: 'string', description: 'where in the journey this was hit' },
          severity: { type: 'string', enum: ['blocker', 'friction', 'nit'] },
          file: { type: 'string', description: 'repo-relative path, e.g. marketplace/README.md' },
          locator: { type: 'string', description: 'line number or section heading' },
          issue: { type: 'string', description: 'one sentence: what is wrong for THIS persona' },
          suggested_fix: { type: 'string', description: 'one sentence concrete fix' },
          evidence_quote: { type: 'string', description: 'short quote from the file that shows the issue' },
        },
        required: ['journey_step', 'severity', 'file', 'issue', 'suggested_fix'],
      },
    },
  },
  required: ['findings'],
}

const VERDICT_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  properties: {
    is_real_blocker: { type: 'boolean', description: 'true only if this genuinely stops the persona from proceeding' },
    corrected_severity: { type: 'string', enum: ['blocker', 'friction', 'nit'] },
    reasoning: { type: 'string', description: 'one or two sentences' },
  },
  required: ['is_real_blocker', 'corrected_severity', 'reasoning'],
}

const COMMON = `You are reviewing the Open Science Pillars documentation entirely READ-ONLY (Read, Glob, Grep only; do not edit anything). The nine repos live under ${ROOT}/ : marketplace, core, ocean-science, hydrology, tutorials, plugin-template, knowledge-template, nasa-daac-knowledge, .github, plus a build-kit repo under construction. Walk your journey as the persona below, opening the files a real person would open in order. Report only what YOUR persona actually hits on THEIR path. severity: blocker = you cannot proceed or cannot tell what to do next; friction = you proceed but confused or slowed; nit = cosmetic. Give file paths repo-relative (e.g. marketplace/README.md) and a short evidence quote. Do not invent problems to be thorough; an empty findings list is a valid answer if the path is clean.`

const PERSONAS = [
  {
    key: 'newcomer',
    prompt: `${COMMON}

PERSONA N, newcomer scientist finding the org cold. You have never heard of this project. Your journey: (1) .github/profile/README.md (the org landing page), (2) the repo it points you to: marketplace/README.md, (3) you try to understand install and what you'd get, (4) you click into a plugin repo (core/README.md, ocean-science/README.md) and maybe hydrology/README.md out of curiosity, (5) you look for "where do I start" and land on tutorials/README.md or tutorials/index.qmd. Judge: can you tell WHAT this is, WHO it is for, HOW to install, and WHERE to go first, without hitting undefined jargon (skill, knowledge bundle, golden notebook, gated skill, surface, connector, eval, fixture, OKF, marimo) or internal build vocabulary (Session N, Phase 1/2, SPEC section numbers, MVP cut-line, PROGRESS/BUILD-HARNESS/IMPLEMENTATION-GUIDE, seed)? A dead-end repo with no user framing is a blocker.`,
  },
  {
    key: 'grad-student',
    prompt: `${COMMON}

PERSONA G, graduate student on the ocean path. You know Python and xarray but not this project. Your journey: (1) tutorials/tutorial-1-getting-started.qmd, (2) tutorials/tutorial-2-ecco-mht.qmd, (3) ocean-science/README.md, (4) you look for prerequisites (Python env, Earthdata login) and the config template step. Judge: can each numbered tutorial step be followed AS WRITTEN to a real first result, are prerequisites stated where you need them (not buried or pointed to an internal build doc), and does anything assume context you don't have? A step that cannot be completed as written is a blocker.`,
  },
  {
    key: 'contributor',
    prompt: `${COMMON}

PERSONA C, outside domain contributor. You want to add ONE new skill and ONE knowledge concept to a plugin. Your journey: (1) marketplace/CONTRIBUTING.md, (2) plugin-template/README.md and knowledge-template/README.md, (3) the authoring guides in marketplace/docs/ (skill-authoring-guide, knowledge-authoring-guide, agent-authoring-guide, eval-authoring-guide, verification-guide, testing-guide, connector-guide), (4) the issue templates in .github. Judge: is each instruction actionable for someone who was NOT part of the build? Flag any stale instruction (e.g. text saying guides don't exist yet when they do), any guide that name-drops a build episode ("the MHT basin-scope correction", "check 11", "PARKING #7") without teaching the lesson inline, and any reference you cannot resolve from public files. A stale or unresolvable instruction that would misdirect you is a blocker.`,
  },
  {
    key: 'steward',
    prompt: `${COMMON}

PERSONA S, data-provider steward (e.g. a PO.DAAC staffer) evaluating whether to own a knowledge bundle. Your journey: (1) marketplace/docs/steward-playbook.md, (2) .github/GOVERNANCE.md, (3) nasa-daac-knowledge/README.md and its podaac/ bundle (index.md, log.md, one dataset, one gotcha), (4) how review, credit, and the handoff work. Judge: can you tell your DUTIES, the REVIEW PATH, how CREDIT/authorship works, and what "steward pro tem" implies for you taking over? Flag build-internal state that reads as confusing (Session N, Phase 2, pre-registration jargon) and anything that would make a real provider hesitate. Missing duties/review-path/credit is a blocker.`,
  },
  {
    key: 'future-dev',
    prompt: `${COMMON}

PERSONA D, future core developer with an AI assistant, wanting to continue the build (e.g. open "Session 20" for a new domain). Your journey: (1) the build-kit repo under ${ROOT}/build-kit/ (README.md, DEVELOPING.md, bootstrap.sh, CLAUDE.template.md, harness/skills/), (2) marketplace/docs/BUILD-HARNESS.md, (3) marketplace/docs/IMPLEMENTATION-GUIDE.md (session-block format) and PROGRESS.md (current state) and phase2-preregistration.md (the Phase-3 gate). Judge: could you actually stand up the harness (clone the org, wire the session/close skills) and know how to author the next session block, set the autonomy dial, and respect the phase gate, from what is written? Flag layout drift (docs describing a harness/ symlink layout that does not match reality), single-points-of-failure, and any missing step that blocks booting the next session. If build-kit files are absent or empty, report that as a blocker for this persona (it is being built this pass).`,
  },
]

phase('Personas')
const perPersona = await parallel(
  PERSONAS.map((p) => () =>
    agent(p.prompt, { label: `persona:${p.key}`, phase: 'Personas', schema: FINDINGS_SCHEMA })
      .then((r) => ({ key: p.key, findings: (r && r.findings) || [] }))
  )
)

// Tag each finding with its persona, flatten.
const all = perPersona.filter(Boolean).flatMap((r) =>
  r.findings.map((f) => ({ ...f, persona: r.key }))
)

// Dedup by file + normalized issue prefix so two personas hitting the same
// leak collapse to one fix task (but keep which personas raised it).
const byKey = new Map()
for (const f of all) {
  const k = (f.file || 'unknown') + '::' + (f.issue || '').toLowerCase().replace(/\s+/g, ' ').slice(0, 70)
  if (byKey.has(k)) {
    byKey.get(k).personas.push(f.persona)
  } else {
    byKey.set(k, { ...f, personas: [f.persona] })
  }
}
const deduped = Array.from(byKey.values())
const blockers = deduped.filter((f) => f.severity === 'blocker')
log(`personas raised ${all.length} findings, ${deduped.length} after dedup, ${blockers.length} blockers to verify`)

phase('Verify')
const verified = await parallel(
  blockers.map((f) => () =>
    agent(
      `${COMMON}

You are an adversarial VERIFIER. A persona review flagged the following as a BLOCKER. Open the file and decide, skeptically, whether it genuinely blocks that persona or is an over-reach (a nit or friction dressed up as a blocker, or a claim the file does not actually support). Default to NOT a blocker unless the evidence is clear.

Persona: ${f.persona}
File: ${f.file} (${f.locator || 'no locator'})
Journey step: ${f.journey_step || 'n/a'}
Claimed issue: ${f.issue}
Claimed evidence: ${f.evidence_quote || '(none provided)'}
Proposed fix: ${f.suggested_fix}

Read ${ROOT}/${f.file} and judge.`,
      { label: `verify:${f.file}`, phase: 'Verify', schema: VERDICT_SCHEMA }
    ).then((v) => ({ ...f, verdict: v }))
  )
)

const confirmedBlockers = verified
  .filter(Boolean)
  .filter((v) => v.verdict && v.verdict.is_real_blocker)
const demotedBlockers = verified
  .filter(Boolean)
  .filter((v) => v.verdict && !v.verdict.is_real_blocker)
const nonBlockers = deduped.filter((f) => f.severity !== 'blocker')

return {
  confirmed_blockers: confirmedBlockers,
  demoted_blockers: demotedBlockers.map((v) => ({ file: v.file, issue: v.issue, reasoning: v.verdict.reasoning })),
  friction_and_nits: nonBlockers.map((f) => ({ severity: f.severity, file: f.file, issue: f.issue, suggested_fix: f.suggested_fix, personas: f.personas })),
  counts: {
    raw: all.length,
    deduped: deduped.length,
    blockers_claimed: blockers.length,
    blockers_confirmed: confirmedBlockers.length,
  },
}
