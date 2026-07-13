export const meta = {
  name: 'local-haiku-eval',
  description:
    'Local NON-NORMATIVE Haiku eval over the committed corpus: setup sandbox workspaces, fan out one claude-haiku-4-5 episode per fixture in parallel (auto-capped), then score with check_evals.score_episode.',
  whenToUse:
    'A quick indicative pre-check of the eval corpus under the gate model, without the credentialed §11.8 dispatch. Not a substitute for scripts/eval_harness.py + evals/runner.json.',
  phases: [
    { title: 'Setup', detail: 'scripts/local_eval.py setup -> one sandbox workspace per fixture' },
    { title: 'Eval', detail: 'one sandboxed claude-haiku-4-5 episode per fixture (parallel)' },
    { title: 'Score', detail: 'scripts/local_eval.py score -> per-bucket rates' },
  ],
}

// args = { repo: "<repo root abs path>", dir: "<fresh empty workspace root>",
//          only?: [id-prefix, ...], limit?: N }
// `args` may arrive as an object or as a JSON string depending on the caller —
// normalize both.
let A = args
if (typeof A === 'string') {
  try { A = JSON.parse(A) } catch (e) { A = {} }
}
if (!A || typeof A !== 'object') A = {}
const REPO = A.repo
const DIR = A.dir
if (!REPO || !DIR) {
  throw new Error('args must include {repo: <repo root>, dir: <fresh workspace root>}')
}
const PY = `${REPO}/.venv/bin/python`
const onlyFlag = A.only && A.only.length ? ` --only ${A.only.join(' ')}` : ''
const limitFlag = A.limit ? ` --limit ${A.limit}` : ''

// --- Setup: an agent runs local_eval.py setup and hands back the manifest -----
// (the workflow script itself has no shell/fs; the setup agent does the I/O.)
const MANIFEST_SCHEMA = {
  type: 'object',
  required: ['fixtures'],
  properties: {
    fixtures: {
      type: 'array',
      items: {
        type: 'object',
        required: ['id', 'ws'],
        properties: { id: { type: 'string' }, ws: { type: 'string' } },
      },
    },
  },
}

phase('Setup')
const setup = await agent(
  `Run this shell command exactly once:\n\n  ${PY} ${REPO}/scripts/local_eval.py setup --out ${DIR}${onlyFlag}${limitFlag}\n\n` +
    `Then read ${DIR}/manifest.json and return {"fixtures": <the JSON array from that file>}. Do nothing else.`,
  { label: 'setup', phase: 'Setup', agentType: 'general-purpose', schema: MANIFEST_SCHEMA }
)
const fixtures = setup && setup.fixtures ? setup.fixtures : []
if (!fixtures.length) throw new Error('setup produced no fixtures — check the corpus / --only filter')
log(`prepared ${fixtures.length} sandbox workspaces under ${DIR}`)

// --- Eval: one sandboxed Haiku episode per fixture, parallel + auto-capped ----
const sandboxPrompt = (ws) =>
  `You are an automated agent under evaluation. Read \`${ws}/task.md\` IN FULL first and do EXACTLY ` +
  `what it says, following the \`SKILL.md\` in that same workspace. Your workspace is \`${ws}\`. ` +
  `Write your graded \`result.json\` there. Do not read any file outside your workspace except via ` +
  `the transon_authoring CLI.`

phase('Eval')
log(`fanning out ${fixtures.length} claude-haiku-4-5 episodes (concurrency auto-capped by the runner)`)
await parallel(
  fixtures.map((f) => () =>
    agent(sandboxPrompt(f.ws), {
      label: `haiku:${f.id}`,
      phase: 'Eval',
      model: 'haiku', // claude-haiku-4-5-20251001 — the NFR-010 gate pin
      agentType: 'general-purpose',
    }).catch(() => null) // a dead episode just leaves no result.json -> scored NO-RESULT
  )
)

// --- Score: an agent runs local_eval.py score and returns the report ----------
phase('Score')
const report = await agent(
  `Run this shell command exactly once and return its FULL stdout verbatim as your final message, ` +
    `with no extra commentary:\n\n  ${PY} ${REPO}/scripts/local_eval.py score --dir ${DIR}`,
  { label: 'score', phase: 'Score', agentType: 'general-purpose' }
)
return report
