export const meta = {
  name: 'research-graph',
  description: 'Advance the research agenda: each task runs execute -> adversarial-verify, guardrails carried into every subagent.',
  phases: [
    { title: 'Execute', detail: 'one general-purpose agent per task, does the actual work under its guardrails' },
    { title: 'Verify', detail: 'an independent skeptic tries to refute each result and checks rigor (leakage/OOS/DSR)' },
  ],
}

// The driver passes the selected pending tasks as args.tasks. Never trust the driver to pre-filter
// guardrails -- they travel inside each task object and are pasted verbatim into the prompt.
const tasks = (args && args.tasks) || []
if (!tasks.length) { log('no pending tasks -- agenda drained'); return { results: [], drained: true } }

// Every orchestra agent runs on Opus 5.0 (owner directive).
const MODEL = 'claude-opus-5'

// Repo orientation pasted into every agent so they know the whole codebase, not just their task.
const REPO_CONTEXT = [
  `GOAL OF THE PROGRAMME: build a WORKING, profitable, genuinely novel trading bot for real money`,
  `(US equities, ETFs, dividends, shorting) -- the most unique edge that survives hostile testing.`,
  `Paper-trade first; real-money execution is OWNER-GATED, never cross it autonomously.`,
  ``,
  `YOU HAVE THE ENTIRE REPOSITORY at /home/anont/meme. Orient yourself BEFORE acting -- read the`,
  `canonical docs so you don't repeat dead work or miss frozen constraints:`,
  `  - research/FINDINGS.md      -- the index of what is known, ALIVE, DEAD, and retracted (read first)`,
  `  - AGENTS.md, DECISIONS.md   -- the control contract and standing decisions`,
  `  - scripts/agent_graph/README.md -- how this graph/loop works`,
  `  - scripts/  research/       -- the harnesses, pre-registrations, and prior experiments`,
  `The programme's hard lesson: most strategies are DEAD at the friction floor. A claim counts only`,
  `if it survives leakage-free, out-of-sample, DSR/permutation testing. Report negatives honestly.`,
].join('\n')

const RESULT_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['id', 'status', 'headline', 'detail', 'artifacts_written', 'guardrail_ok'],
  properties: {
    id: { type: 'string' },
    status: { type: 'string', enum: ['done', 'blocked', 'killed', 'partial'] },
    headline: { type: 'string', description: 'one self-contained line a reader who never saw the task understands' },
    detail: { type: 'string', description: 'what was actually done/found, with numbers where relevant' },
    artifacts_written: { type: 'array', items: { type: 'string' }, description: 'repo-relative paths created/edited, or [] if none' },
    guardrail_ok: { type: 'boolean', description: 'true iff every guardrail was honored; false means a guardrail was at risk' },
    guardrail_note: { type: 'string' },
  },
}

const VERDICT_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['id', 'verdict', 'rigor', 'reason'],
  properties: {
    id: { type: 'string' },
    verdict: { type: 'string', enum: ['CONFIRMED', 'PLAUSIBLE', 'REFUTED', 'NEEDS_OWNER'] },
    rigor: { type: 'string', description: 'which rigor checks apply and whether they were met: leakage / out-of-sample / DSR / permutation / freeze-then-test / N/A' },
    reason: { type: 'string' },
  },
}

function executePrompt(t) {
  return [
    REPO_CONTEXT,
    ``,
    `You are advancing one research task in this programme.`,
    `The standing method is HOSTILE VERIFICATION: leakage-free, out-of-sample, freeze-then-test, honest about negatives.`,
    ``,
    `TASK ${t.id}: ${t.title}`,
    `WHY IT MATTERS: ${t.why}`,
    `ACCEPTANCE (what "done" means): ${t.acceptance}`,
    `RELEVANT ARTIFACTS: ${(t.artifacts || []).join(', ') || '(none listed)'}`,
    ``,
    `HARD GUARDRAILS -- violating any of these fails the task; if honoring them blocks the work, return status "blocked" and say why:`,
    ...(t.guardrails || []).map((g, i) => `  ${i + 1}. ${g}`),
    ``,
    `Do the real work now (read files, run code, fetch data as needed). Do NOT commit to git and do NOT`,
    `apply changes the guardrails reserve for owner sign-off -- propose those as a diff/plan instead.`,
    `Return the structured result. headline must stand alone.`,
  ].join('\n')
}

function verifyPrompt(t, r) {
  return [
    REPO_CONTEXT,
    ``,
    `You are an independent skeptic. Another agent claims to have advanced this research task. Try to REFUTE it.`,
    `Default to REFUTED or NEEDS_OWNER if you are not convinced; a plausible-but-unverified claim must not pass.`,
    ``,
    `TASK ${t.id}: ${t.title}`,
    `ACCEPTANCE: ${t.acceptance}`,
    `GUARDRAILS: ${(t.guardrails || []).join(' | ')}`,
    ``,
    `THE CLAIM: status=${r.status} :: ${r.headline}`,
    `DETAIL: ${r.detail}`,
    `ARTIFACTS WRITTEN: ${(r.artifacts_written || []).join(', ') || '(none)'}`,
    `THE EXECUTOR SAID GUARDRAILS OK = ${r.guardrail_ok}${r.guardrail_note ? ' :: ' + r.guardrail_note : ''}`,
    ``,
    `Check: (a) was a guardrail actually violated (e.g. did it read a blind/frozen result, edit a pinned file)?`,
    `(b) does the claimed finding survive the rigor its kind demands -- leakage, out-of-sample, DSR, permutation, freeze-then-test?`,
    `(c) is the headline actually supported by the detail/artifacts, or is it overstated?`,
    `Read the artifacts yourself to check. Return your verdict.`,
  ].join('\n')
}

const results = await pipeline(
  tasks,
  (t) => agent(executePrompt(t), {
    label: `exec:${t.id}`, phase: 'Execute', agentType: 'general-purpose', model: MODEL, schema: RESULT_SCHEMA,
  }),
  (r, t) => {
    if (!r) return { id: t.id, status: 'blocked', verdict: { id: t.id, verdict: 'NEEDS_OWNER', rigor: 'N/A', reason: 'executor returned null (skipped or died)' }, result: null }
    return agent(verifyPrompt(t, r), {
      label: `verify:${t.id}`, phase: 'Verify', agentType: 'general-purpose', model: MODEL, schema: VERDICT_SCHEMA,
    }).then((v) => ({ id: t.id, status: r.status, result: r, verdict: v || { id: t.id, verdict: 'NEEDS_OWNER', rigor: 'N/A', reason: 'verifier returned null' } }))
  },
)

const clean = results.filter(Boolean)
log(`graph run complete: ${clean.length}/${tasks.length} tasks processed`)
return { results: clean, drained: false }
