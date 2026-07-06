export const meta = {
  name: 'knowledge-coupling-review',
  description: 'Classify every skill and agent against the knowledge-coupling rule (invariance / response-shape / universality) and emit a per-file migration plan: what stays as procedure or hard-refusal, and what dataset knowledge moves to a concept',
  whenToUse: 'Before and during the migration to the skills-are-procedures / knowledge-is-single-source / agents-consult-dynamically model; re-run to catch drift',
  phases: [{ title: 'Classify' }],
}

let A = args
if (typeof A === 'string') {
  try { A = JSON.parse(A) } catch (e) { A = {} }
}
const ROOT = (A && A.root) || '/Users/pramirez/Development/ClaudeCode/osp'
const FILES = (A && A.files) || []

const RULE = `THE KNOWLEDGE-COUPLING RULE. A behavior stays HARDCODED in a skill only if
it passes ALL THREE tests; otherwise it is DATASET KNOWLEDGE, must live in
exactly one knowledge concept, and is consulted dynamically. The default is
knowledge; hardcoding is the exception that must justify itself.
  1. Invariance: it does not change with a product version, a new dataset, or
     new learning. ("A budget on regridded fields never closes" is invariant
     math; "ssha_karin needs height_cor_xover" is a product-baseline fact that
     can change, so it is knowledge.)
  2. Response shape: the correct response is to REFUSE or GATE (stop / require
     confirmation), NOT to inform or adjust. Refusals/gates are binary safety
     valves; informing or adjusting is reasoning that should use current
     knowledge.
  3. Universality: violating it is wrong or unsafe regardless of the dataset or
     task, so it must fire every time (a correctness invariant, safety gate, or
     security rule).
Agreed hard-refusals that stay: regridded-budget refusal, download volume
gates, credential handling. Invariant METHOD physics that is not a refusal
(e.g. "a section is a set of cell faces, not a j=const row") may stay as
procedure. Anything dataset-specific, changeable, or whose right response is
inform/adjust is knowledge. When uncertain, classify as knowledge.`

const SCHEMA = {
  type: 'object',
  additionalProperties: false,
  properties: {
    verdict: { type: 'string', enum: ['compliant', 'needs-migration'] },
    hard_refusals_kept: {
      type: 'array',
      items: {
        type: 'object', additionalProperties: false,
        properties: {
          rule: { type: 'string' },
          passes_all_tests: { type: 'boolean' },
          justification: { type: 'string', description: 'which of the 3 tests it passes; if it does NOT pass all, this rule should actually move to knowledge' },
        },
        required: ['rule', 'passes_all_tests', 'justification'],
      },
    },
    move_to_knowledge: {
      type: 'array',
      items: {
        type: 'object', additionalProperties: false,
        properties: {
          item: { type: 'string', description: 'the dataset fact / number / gotcha rule / named-concept restatement to remove from the skill' },
          kind: { type: 'string', enum: ['inlined-number', 'gotcha-rule', 'dataset-fact', 'named-concept-restatement', 'uncertainty-detail'] },
          target_concept: { type: 'string', description: 'the concept it belongs in (existing path if known, else a proposed one)' },
          concept_exists: { type: 'boolean' },
        },
        required: ['item', 'kind', 'target_concept', 'concept_exists'],
      },
    },
    add_dynamic_consult_step: { type: 'boolean', description: 'does this skill need a standing "discover and consult the bundle for this dataset" step to replace named references?' },
    keep_as_procedure: { type: 'array', items: { type: 'string' }, description: 'short list of the genuinely procedural/method content that stays' },
    effort: { type: 'string', enum: ['none', 'low', 'medium', 'high'] },
    notes: { type: 'string' },
  },
  required: ['verdict', 'move_to_knowledge', 'add_dynamic_consult_step', 'effort'],
}

phase('Classify')
log(`classifying ${FILES.length} skill/agent files against the coupling rule`)

const results = await parallel(
  FILES.map((rel) => () =>
    agent(
      `You are classifying ONE skill or agent file for a migration to a cleaner knowledge-coupling model.

${RULE}

Read the file at ${ROOT}/${rel} (read-only). Classify its content:
- hard_refusals_kept: rules the file states that genuinely PASS all three tests and should stay in the skill. For each, say which tests it passes. If a stated rule does NOT pass all three (e.g. it is a dataset-specific "never" that is really a gotcha), do NOT list it here; list its content under move_to_knowledge instead.
- move_to_knowledge: every dataset-specific fact, inlined number, gotcha rule, uncertainty detail, or restatement of a named concept that should be removed from the skill body and owned by a single concept. Name the target concept (existing path if you can infer it under ${rel.split('/')[0]}/knowledge/, else propose one) and whether it already exists.
- add_dynamic_consult_step: true if the skill currently names specific concepts or restates their content and should instead carry a standing "discover and consult the bundle for the dataset in play" step.
- keep_as_procedure: the genuinely procedural/method content (ordered steps, invariant method physics) that stays.
- effort and a one-line note.

A file that is already a clean procedure-plus-justified-refusals (no dataset knowledge inlined) is "compliant" with empty move_to_knowledge. Be strict: inlined numbers and restated gotcha rules are the main thing to catch.`,
      { label: `classify:${rel.replace(/\//g, '.').replace('.SKILL.md', '').replace('.agent.md', '.agent')}`, phase: 'Classify', schema: SCHEMA }
    ).then((r) => ({ file: rel, plugin: rel.split('/')[0], ...r }))
  )
)

const clean = results.filter(Boolean)
const needMig = clean.filter((r) => r.verdict === 'needs-migration' || (r.move_to_knowledge && r.move_to_knowledge.length))
const compliant = clean.filter((r) => !(r.move_to_knowledge && r.move_to_knowledge.length) && r.verdict === 'compliant')
const totalMoves = clean.reduce((n, r) => n + (r.move_to_knowledge ? r.move_to_knowledge.length : 0), 0)
const suspectRefusals = clean.flatMap((r) =>
  (r.hard_refusals_kept || []).filter((h) => !h.passes_all_tests).map((h) => ({ file: r.file, rule: h.rule, why: h.justification })))

return {
  summary: {
    files: clean.length,
    needs_migration: needMig.length,
    compliant: compliant.length,
    total_items_to_move: totalMoves,
    suspect_hardcodes: suspectRefusals.length,
  },
  needs_migration: needMig.map((r) => ({
    file: r.file, effort: r.effort, add_consult: r.add_dynamic_consult_step,
    moves: r.move_to_knowledge, notes: r.notes,
  })),
  suspect_hardcodes: suspectRefusals,
  compliant: compliant.map((r) => r.file),
}
