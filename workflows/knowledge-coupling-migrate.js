export const meta = {
  name: 'knowledge-coupling-migrate',
  description: 'Migrate skills/agents to the knowledge-coupling model: slim each to procedure plus hard refusals, move dataset-specific knowledge to concepts (draft), add a dynamic consult step. One agent per file, editing distinct files.',
  phases: [{ title: 'Migrate' }],
}

let A = args
if (typeof A === 'string') { try { A = JSON.parse(A) } catch (e) { A = {} } }
const ROOT = (A && A.root) || '.'
const FILES = (A && A.files) || []
// Existing concepts that mirror the canonical podaac bundle: NEVER edit (byte-identity).
const PROTECTED = (A && A.protected) || 'ecco-v4r4, swot-karin, grace-fo-mascons, grace-coastal-leakage, grace-gia-correction, ghrsst-mur, rapid-mocha, ecco-native-vs-regridded, ecco-geothermal-flux, swot-calval-orbit-phases, ecco-release-mixing, ecco-mht-basin-scope, swot-crossover-unapplied, ecco-heat-budget, ecco-mht-26n, ecco-salt-budget, ecco-volume-budget'

const RULE = `THE KNOWLEDGE-COUPLING RULE. Skills are deterministic PROCEDURES plus HARD
REFUSALS; they carry NO dataset facts, inlined numbers, gotcha rules, or
named-concept lists. Dataset knowledge lives in exactly one concept, consulted
dynamically. A behavior stays hardcoded ONLY if it passes all three tests:
(1) invariant across products and time; (2) refusal- or gate-shaped (stop /
require confirmation), NOT inform/adjust; (3) universal (wrong or unsafe
regardless of dataset). Invariant METHOD physics that is not a refusal (e.g.
"a section is cell faces, not a j=const row"; "MLD depends on the density
criterion") STAYS as procedure: it is not a dataset fact. When uncertain,
move it to knowledge.`

const SCHEMA = {
  type: 'object', additionalProperties: false,
  properties: {
    migrated: { type: 'boolean' },
    kept_hard_refusals: { type: 'array', items: { type: 'string' } },
    kept_method: { type: 'array', items: { type: 'string' } },
    concepts_created: { type: 'array', items: { type: 'string', description: 'path of each new draft concept authored' } },
    deferred_to_existing: { type: 'array', items: { type: 'string' } },
    belongs_in_protected_concept: { type: 'array', items: { type: 'string', description: 'content that belongs in an existing byte-identical concept you must NOT edit; left in place, flagged for the steward to add to both copies' } },
    notes: { type: 'string' },
  },
  required: ['migrated', 'concepts_created', 'notes'],
}

phase('Migrate')
const results = await parallel(
  FILES.map((rel) => () =>
    agent(
      `Migrate ONE file to the knowledge-coupling model. You have Read, Edit, Write, Glob, Grep. Edit ONLY the file ${ROOT}/${rel} and CREATE new concept files under ${rel.split('/')[0]}/knowledge/ ; touch no other skill/agent file.

${RULE}

The worked pattern (already done): ${ROOT}/ocean-science/skills/ecco/SKILL.md and ocean-budget/SKILL.md keep the hard refusal and the procedure, replace the "Knowledge first, restated: [named list]" with a "Consult the bundle for this analysis: discover (glob/grep knowledge/) and read the applicable concepts, restate and cite, do not carry these facts here" step, and drop the Must-NOT items that restate a gotcha.

Steps for ${rel}:
1. Read the file. Identify hard refusals (keep), invariant method/procedure (keep), and dataset-specific knowledge (move).
2. For each dataset fact/number/gotcha-rule/named-concept-restatement: FIRST glob ${rel.split('/')[0]}/knowledge/ for an existing concept that owns it.
   - If found and it is NOT in this protected list [${PROTECTED}]: make the skill DEFER (dynamic consult + cite); do not edit the concept.
   - If found but it IS protected (byte-identical podaac mirror): make the skill defer to it; if the fact is NOT yet in that concept, DO NOT edit it, instead list the fact under belongs_in_protected_concept for the steward.
   - If no concept exists: CREATE a new draft concept file under ${rel.split('/')[0]}/knowledge/{datasets|gotchas|recipes|conventions}/ with FULL valid frontmatter (type; title/description/tags/timestamp; status: draft; for gotchas severity + a dataset link; for datasets an ## Uncertainty section; evidence: use the source the skill cited, or the note "internal: relocated from ${rel} during the knowledge-coupling migration, needs a steward evidence link" as a single evidence entry). Put the moved content in the concept. Then make the skill defer to it.
3. Edit the skill: remove the moved content, add ONE standing "consult the bundle for this dataset/analysis, discovering concepts by glob, restating and citing" step, keep procedure + hard refusals. Mark hard refusals as such.
4. Prose style: NO em dashes (use commas/colons/parentheses/semicolons).

Return the structured summary. Be conservative: when unsure whether something is invariant method (keep) or dataset knowledge (move), and it is general physics the model already knows, keeping it as a one-line method note is acceptable; the goal is single-source for DATASET-SPECIFIC facts and numbers.`,
      { label: `migrate:${rel.split('/').slice(-2)[0]}`, phase: 'Migrate', schema: SCHEMA, agentType: 'general-purpose' }
    ).then((r) => ({ file: rel, ...r }))
  )
)

const clean = results.filter(Boolean)
return {
  migrated: clean.filter((r) => r.migrated).length,
  files: clean.length,
  concepts_created: clean.flatMap((r) => r.concepts_created || []),
  belongs_in_protected: clean.flatMap((r) => (r.belongs_in_protected_concept || []).map((c) => ({ file: r.file, content: c }))),
  per_file: clean.map((r) => ({ file: r.file, migrated: r.migrated, new_concepts: (r.concepts_created || []).length, deferred: (r.deferred_to_existing || []).length, notes: r.notes })),
}
