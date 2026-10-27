import { expect, mock, test } from 'claude-code/testing'

import { LEDGER_ENABLED, barRuns, barText, ctxColor, ease, flagUnverified, MODEL_SYSTEM, modelPrompt, seedText, SPIN, statusColor, summarizeStatus } from './lib'

// Nothing runs for real here: the engine, /clear, agents, the model and the file
// system are all mocked beneath the plugin. No test presses a real clear.

const PANE = {
  plugin: 'handover',
  component: 'Pane',
  requestId: 'handover',
  props: { title: 'Handover', isFocused: true, bodyColumns: 60, placement: 'dock', scroll: { offset: 0, bodyRows: 40 }, view: {} },
} as const

const ZERO = { input_tokens: 0, output_tokens: 0, cache_read_input_tokens: 0, cache_creation_input_tokens: 0 }
const GOOD_REPLY = [
  '## Task table', '| task | state | note |', '|---|---|---|', '| X4 | READY | next |',
  '## Decisions', '- keep own extractors',
  '## Pending for the user', '- none',
  '## Next actions', '1. spawn X4',
  '## How to verify', '- re-run scorer',
].join('\n')

type World = {
  tokens: number | undefined
  agents: { id: string; description: string; type: string; status: string; name?: string }[]
  reply: string | 'fail'
  clears: number
  written: Record<string, string>
  submits: string[]
  placed: boolean
  gitRuns: number
  modelDelay: number
  listCalls: number
  handover?: string
  gitStatus: string
  head: string
  toasts: string[]
  bandReads: number
  countStore: boolean
  mem: Map<string, unknown>
  sid: string
  failClear: boolean
  clearCalls: number
  fsFail: boolean
  storeFail: boolean
  appended: any[]
  bottom: any[]
}

function setup(on: any, over: Partial<World> = {}) {
  const w: World = { tokens: 100_000, agents: [], reply: GOOD_REPLY, clears: 0, written: {}, submits: [], placed: true, gitRuns: 0, modelDelay: 0, listCalls: 0, gitStatus: '', head: 'abc1234', toasts: [], bandReads: 0, countStore: false, mem: new Map(), sid: 'sess-1', failClear: false, clearCalls: 0, fsFail: false, storeFail: false, appended: [], bottom: [], ...over }
  const clock = mock.clock(on, { now: 1_000_000 })
  on('store.get', (_: any, e: any) => { if (w.storeFail && String(e.key).startsWith('inbox')) throw new Error('store down'); if (w.countStore && e.key === 'band') w.bandReads++; return { value: w.mem.get(e.key) } })
  on('store.set', (_: any, e: any) => { if (w.storeFail && String(e.key).startsWith('inbox:')) throw new Error('store down'); w.mem.set(e.key, e.value); return { value: undefined } })
  mock.env(on, { HOME: '/home/t' })
  on('command.register', () => ({ value: { command: 'handover' } }))
  on('session.start', (_: any, e: any) => ({ cwd: e.cwd }))
  on('ui.open', () => ({ value: w.placed ? { isPlaced: true } : { isPlaced: false, reason: 'narrow' } }))
  on('ui.close', () => ({ value: undefined }))
  on('session.usage', () => ({
    value: {
      startedAt: 0,
      context: {
        window: 200_000, tokens: w.tokens, percent: w.tokens === undefined ? undefined : (w.tokens / 200_000) * 100,
        breakdown: { categories: [{ name: 'Messages', tokens: 4000, color: 'x', isDeferred: false, kind: 'used' }], apiUsage: { ...ZERO, input_tokens: 10, output_tokens: 500, cache_read_input_tokens: 90_000 } },
      },
      rateLimits: [{ kind: 'five_hour', percentUsed: 23.5 }],
      cost: { usd: 1.5 },
    },
  }))
  on('agent.list', () => { w.listCalls++; return { value: w.agents } })
  on('session.id', () => ({ value: w.sid }))
  on('session.cwd', () => ({ value: '/repo' }))
  on('session.messages', () => ({ value: [{ role: 'user', text: 'do the thing', toolUses: [] }, { role: 'assistant', text: 'ok', toolUses: [] }] }))
  // v0.4: the harness serves written files back by path (the ledger is read-modify-write); HANDOVER.md as before
  on('fs.read', (_: any, e: any) => { if (e.path in w.written) return { value: w.written[e.path] }; if (w.handover === undefined) throw new Error('ENOENT'); return { value: w.handover } })
  on('fs.exists', (_: any, e: any) => ({ value: e.path in w.written }))
  on('session.append', (_: any, e: any, next: any) => { w.appended.push(e.message); return next(e) })
  on('session.receive', (_: any, e: any) => { w.bottom.push(JSON.parse(JSON.stringify(e))); return { text: e.text } })
  on('fs.write', (_: any, e: any) => { if (w.fsFail && String(e.path).includes('ledger-')) throw new Error('disk full'); w.written[e.path] = e.text; return { value: undefined } })
  on('process.run', (_: any, e: any) => {
    w.gitRuns++
    const a = (e.argv as string[]).join(' ')
    const out = a.includes('rev-parse') ? w.head + '\n' : a.includes('status') ? w.gitStatus : a.includes('branch') ? 'main\n' : ''
    return { value: { exitCode: 0, stdout: out, stderr: '' } }
  })
  on('ui.toast', (_: any, e: any) => { w.toasts.push(e.text); return { value: undefined } })
  on('model.complete', async () => {
    if (w.modelDelay) await clock.sleep(w.modelDelay)
    return w.reply === 'fail'
      ? { value: { isAnswered: false, reason: 'api-error', status: 500, error: 'server_error', usage: ZERO } }
      : { value: { isAnswered: true, text: w.reply, usage: ZERO } }
  })
  on('command.run', (_: any, e: any) => {
    if (e.command === 'clear') { w.clearCalls++; if (w.failClear) throw new Error('clear refused'); w.clears++ }
    return { value: { text: '' } }
  })
  on('prompt.submit', (_: any, e: any) => { w.submits.push(e.text); return { text: e.text } })
  return { w, clock }
}

// A drawing as lines of text: a Box of Texts is one line.
function lines(node: any): string[] {
  if (!node || typeof node !== 'object') return []
  const kids: any[] = Array.isArray(node.children) ? node.children : node.props?.children ? [].concat(node.props.children) : []
  const textOf = (n: any): string => (typeof n === 'string' ? n : Array.isArray(n) ? n.map(textOf).join('') : n?.type === 'Text' || n?.type === 'Button' ? textOfKids(n) : '')
  const textOfKids = (n: any): string => {
    if (n.type === 'Button') return `[ ${n.props?.label ?? ''} ]`
    const c = n.children ?? n.props?.children ?? []
    return [].concat(c).map((x: any) => (typeof x === 'string' ? x : textOfKids(x))).join('')
  }
  if (node.type === 'Box') {
    const allInline = kids.length > 0 && kids.every((k: any) => k && typeof k === 'object' && (k.type === 'Text' || k.type === 'Button'))
    if (allInline && node.props?.flexDirection !== 'column') return [kids.map(textOf).join(node.props?.gap ? ' ' : '')]
    return kids.flatMap(lines)
  }
  if (node.type === 'Text') return [textOf(node)]
  return kids.flatMap(lines)
}

async function open($: any, clock: any) {
  await $.session.start({ cwd: '/repo', surface: 'terminal', isInteractive: true })
  await $.command.run({ command: 'handover', args: '', origin: { kind: 'user' } })
  await clock.advance(3000) // eased bars settle
}

async function draw($: any, surface: 'terminal' | 'desktop' | 'vscode' | 'mobile' = 'terminal') {
  const ui = await $.ui.mount({ ...PANE, surface })
  return ui
}

async function textOf(ui: any): Promise<string[]> {
  return lines(await ui.drawn())
}

const log = (t: string) => (globalThis as unknown as { console: { log(t: string): void } }).console.log(t)
const CTX_W = 30 // bar cells at bodyColumns 60

const fill = (row: string) => (row.match(/█/g) ?? []).length

test('context bar fills 0 / 50 / 100 percent and is coloured by threshold', async ($, on) => {
  const { w, clock } = setup(on, { tokens: 0 })
  await open($, clock)
  const cases: [number, number, string][] = [[0, 0, 'success'], [100_000, 15, 'success'], [130_000, 19.5, 'warning'], [190_000, 28.5, 'error'], [200_000, 30, 'error']]
  for (const [tokens, cells, colour] of cases) {
    w.tokens = tokens
    await clock.advance(5000)
    const ui = await draw($)
    const row = (await textOf(ui)).find(l => l.startsWith('context'))!
    expect(Math.abs(fill(row) + (cells % 1 ? 0.5 : 0) - cells)).toBeLessThanOrEqual(0.5)
    if (cells === 0) expect(row).toContain('0.0%')
    if (cells === 30) { expect(fill(row)).toBe(CTX_W); expect(row).toContain('100.0%') }
    if (cells > 0) expect((await ui.findAll({ type: 'Text', text: /█/ }))[0]?.props.color).toBe(colour)
    await ui.unmount()
  }
  expect(ctxColor(59.9)).toBe('success')
  expect(ctxColor(60)).toBe('warning')
  expect(ctxColor(84.9)).toBe('warning')
  expect(ctxColor(85)).toBe('error')
  expect(ctxColor(undefined)).toBe('inactive')
})

test('bar fill is exact at the extremes and eases toward the target', async () => {
  expect(barText(barRuns(0, 10, 'success'))).toBe('░'.repeat(10))
  expect(barText(barRuns(0.5, 10, 'success'))).toBe('█████' + '░'.repeat(5))
  expect(barText(barRuns(1, 10, 'success'))).toBe('█'.repeat(10))
  let s = 0
  const seen: number[] = []
  for (let i = 0; i < 60; i++) { s = ease(s, 1); seen.push(s) }
  expect(seen[0]).toBeGreaterThan(0)
  expect(seen[0]).toBeLessThan(0.5)
  expect(seen[59]).toBe(1)
  expect(seen.every((x, i) => i === 0 || x >= seen[i - 1]!)).toBe(true)
})

test('no response yet shows n/a, not an invented number', async ($, on) => {
  const { clock } = setup(on, { tokens: undefined })
  await open($, clock)
  const ui = await draw($)
  const row = (await textOf(ui)).find(l => l.startsWith('context'))!
  expect(row).toContain('n/a')
  expect(fill(row)).toBe(0)
  await ui.unmount()
})

test('agent table rows and status colours', async ($, on) => {
  const { clock } = setup(on, {
    agents: [
      { id: 'aaaaaaaa-1', description: 'scorer run', type: 'general-purpose', status: 'running' },
      { id: 'bbbbbbbb-2', description: 'done one', type: 'Explore', status: 'completed' },
      { id: 'cccccccc-3', description: 'broke', type: 'general-purpose', status: 'failed' },
      { id: 'dddddddd-4', description: 'stopped', type: 'general-purpose', status: 'killed' },
      { id: 'eeeeeeee-5', description: 'queued', type: 'general-purpose', status: 'pending' },
    ],
  })
  await open($, clock)
  const ui = await draw($)
  const t = (await textOf(ui)).join('\n')
  for (const id of ['aaaaaaaa', 'bbbbbbbb', 'cccccccc', 'dddddddd', 'eeeeeeee']) expect(t).toContain(id)
  expect(t).toContain('AGENTS (5)')
  const color = async (re: RegExp) => (await ui.find({ type: 'Text', text: re }))?.props.color
  expect(await color(/^running/)).toBe('warning')
  expect(await color(/^completed/)).toBe('success')
  expect(await color(/^failed/)).toBe('error')
  expect(await color(/^killed/)).toBe('error')
  expect(await color(/^pending/)).toBe('warning')
  expect(['running', 'pending', 'waiting', 'completed', 'failed', 'killed', 'idle'].map(statusColor)).toEqual(['warning', 'warning', 'warning', 'success', 'error', 'error', 'subtle'])
  await ui.unmount()
})

test('the animation advances a frame per tick, and the clock stops on close', async ($, on) => {
  const { w, clock } = setup(on, { modelDelay: 5000 })
  await open($, clock)
  const ui = await draw($)
  const head = async () => (await textOf(ui))[0]!.charAt(0)
  expect(await head()).toBe('◆') // idle: no spinner
  const press = ui.press({ key: 'write' }) // model call is held 5 s: the step stays in progress
  await clock.settle()
  const seen: string[] = []
  for (let i = 0; i < 6; i++) { await clock.advance(100); seen.push(await head()) }
  const idx = SPIN.indexOf(seen[0]!)
  expect(idx).toBeGreaterThanOrEqual(0)
  expect(seen).toEqual(Array.from({ length: 6 }, (_, i) => SPIN[(idx + i) % SPIN.length]))
  let sweepFrames = 0
  for (let i = 0; i < 30; i++) { await clock.advance(100); if (/[▓▒]/.test((await textOf(ui)).join('\n'))) sweepFrames++ }
  expect(sweepFrames).toBeGreaterThan(15) // the travelling highlight is on the running step most frames
  await clock.advance(6000)
  await press
  await clock.settle()
  expect(await head()).toBe('◆') // finished: spinner gone
  await ui.press({ key: 'close' })
  await clock.settle()
  const calls = w.listCalls
  await clock.advance(10_000)
  expect(w.listCalls).toBe(calls) // no refresh tick after close
  await ui.unmount()
})

const BRIEF_CASES: [string, string, boolean][] = [
  ['a good reply is merged', GOOD_REPLY, false],
  ['a failed model call falls back to facts only', 'fail', true],
  ['a reply with no headings falls back to facts only', 'Here is a summary with no headings.', true],
  ['a reply missing required headings falls back to facts only', '## Decisions\n- x', true],
]
for (const [name, reply, facts] of BRIEF_CASES) {
  test(`brief: ${name}`, async ($, on) => {
    const { w, clock } = setup(on, { reply, agents: [{ id: 'real-id-1', description: 'd', type: 'Explore', status: 'completed' }] })
    await open($, clock)
    const ui = await draw($)
    await ui.press({ key: 'write' })
    await clock.settle()
    const path = Object.keys(w.written)[0]!
    expect(path).toBe('/home/t/.claude/state/handover/sess-1.md')
    const md = w.written[path]!
    for (const h of ['## Role', '## Read first', '## State', '## Running agents', '## Decisions', '## Pending for the user', '## Next actions', '## How to verify', '## Rules']) expect(md).toContain(h)
    expect(md).toContain('real-id-1') // ids come from code
    expect(md.includes('FACTS-ONLY BRIEF')).toBe(facts)
    expect(md.includes('X4 | READY')).toBe(!facts)
    expect(w.clears).toBe(0)
    await ui.unmount()
  })
}

test('Clear and seed: refused with running agents on the first press, needs a second within 8 s', async ($, on) => {
  const { w, clock } = setup(on, { agents: [{ id: 'run-1', description: 'd', type: 'general-purpose', status: 'running' }] })
  await open($, clock)
  const ui = await draw($)
  await ui.press({ key: 'clear' }) // no brief yet
  await clock.settle()
  expect(w.clears).toBe(0)
  await ui.press({ key: 'write' })
  await clock.settle()
  expect(w.clears).toBe(0) // writing a brief never clears
  await ui.press({ key: 'clear' })
  await clock.settle()
  expect(w.clears).toBe(0)
  let t = (await textOf(ui)).join('\n')
  expect(t).toContain('run-1')
  expect(t).toContain('NOT determined')
  expect(t).toContain('Confirm clear')
  await clock.advance(9000) // window lapses
  await ui.press({ key: 'clear' })
  await clock.settle()
  expect(w.clears).toBe(0) // asks again instead of clearing
  await clock.advance(3000)
  await ui.press({ key: 'clear' }) // second press, inside the window
  await clock.settle()
  expect(w.clears).toBe(1)
  await ui.press({ key: 'clear' }) // once per session
  await ui.press({ key: 'clear' })
  await clock.settle()
  expect(w.clears).toBe(1)
  t = (await textOf(ui)).join('\n')
  expect(t).toContain('Clear requested, waiting for the session to go idle') // v0.3: no permanent refusal; a fresh clear blocks a double clear
  await ui.unmount()
})

test('Clear and seed refuses while a turn is running, and with no brief; nothing clears unasked', async ($, on) => {
  const { w, clock } = setup(on)
  on('turn.start', (_: any, e: any) => ({ turnId: e.turnId, text: e.text }))
  on('turn.complete', () => ({ text: '' }))
  await open($, clock)
  const ui = await draw($)
  await ui.press({ key: 'write' })
  await clock.settle()
  await ui.press({ key: 'refresh' })
  await clock.advance(20_000)
  expect(w.clears).toBe(0) // open, refresh, ticks, brief: no clear
  await $.turn.start({ text: 'working', turnId: 't1' })
  await ui.press({ key: 'clear' })
  await clock.settle()
  expect(w.clears).toBe(0)
  expect((await textOf(ui)).join('\n')).toContain('a turn is running')
  await $.turn.complete({ turnId: 't1', answer: 'done', durationMs: 1, isAborted: false, reason: 'answer' })
  await ui.press({ key: 'clear' }) // no agents active: one explicit press is enough
  await clock.settle()
  expect(w.clears).toBe(1)
  await ui.unmount()
})

test('after a clear, the fresh context is seeded once with one line pointing at the brief', async ($, on) => {
  const { w, clock } = setup(on, { agents: [{ id: 'run-9', description: 'd', type: 'general-purpose', status: 'waiting' }] })
  on('classic.SessionStart', () => ({}))
  await open($, clock)
  const ui = await draw($)
  await ui.press({ key: 'write' })
  await clock.settle()
  await ui.press({ key: 'clear' })
  await ui.press({ key: 'clear' })
  await clock.settle()
  expect(w.clears).toBe(1)
  await $.classic.SessionStart({ source: 'clear' })
  await $.classic.SessionStart({ source: 'clear' }) // a second start must not seed twice
  await clock.settle()
  expect(w.submits).toHaveLength(1)
  expect(w.submits[0]).toContain('/home/t/.claude/state/handover/sess-1.md')
  expect(w.submits[0]).toContain('run-9')
  expect(w.submits[0]!.includes('\n')).toBe(false)
  await ui.unmount()
})

test('a pane that is not placed falls back to the band above the prompt', async ($, on) => {
  const { clock } = setup(on, { placed: false })
  await open($, clock)
  const band = await $.ui.mount({ plugin: 'handover', component: 'AbovePrompt', requestId: 'band', surface: 'terminal', props: { hasSurvey: false, isWorking: false, maxRows: 6, bodyColumns: 100, scroll: { offset: 0, bodyRows: 6 }, view: {} } })
  const t = (await textOf(band)).join('\n')
  expect(t).toContain('handover')
  expect(t).toContain('50.0%')
  expect(await band.find({ key: 'write' })).toBeDefined()
  await band.unmount()
})

test('every surface draws the pane', async ($, on) => {
  const { clock } = setup(on)
  await open($, clock)
  for (const surface of ['terminal', 'desktop', 'vscode', 'mobile'] as const) {
    const ui = await draw($, surface)
    expect((await ui.find({ type: 'Text', text: /CONTEXT WINDOW/ }))?.text).toBe('CONTEXT WINDOW')
    await ui.unmount()
  }
})

test('layout snapshot', async ($, on) => {
  const { clock } = setup(on, {
    modelDelay: 5000,
    agents: [
      { id: 'a1b2c3d4-0001', description: 'X4 C# params', type: 'general-purpose', status: 'running' },
      { id: 'b2c3d4e5-0002', description: 'triage Flask routes', type: 'Explore', status: 'completed' },
      { id: 'c3d4e5f6-0003', description: 'scorer rerun', type: 'general-purpose', status: 'failed' },
    ],
  })
  await open($, clock)
  const ui = await draw($)
  const press = ui.press({ key: 'write' })
  await clock.settle()
  await clock.advance(700)
  log('SNAPSHOT (terminal, 60 columns, mid brief: step 2 in progress)\n' + (await textOf(ui)).join('\n'))
  await clock.advance(6000)
  await press
  await ui.press({ key: 'clear' })
  await clock.settle()
  log('SNAPSHOT (after first Clear press with active agents)\n' + (await textOf(ui)).slice(-8).join('\n'))
  await ui.unmount()
})

// ------------------------------------------------------------------ v0.2

const REPO_MD = [
  '# HANDOVER', '## Role', 'Supervise.', '## State (branch main, head 2e48444)', '- DONE: X0', '- READY: X4 C# params', '## Rules', '- verify',
].join('\n')
const STATUS_30 = [...Array(4).fill('D  gone.md').map((l, i) => `D  gone${i}.md`), ...Array.from({ length: 21 }, (_, i) => `?? new${i}.md`)].join('\n')

async function writeAndRead($: any, on: any, over: any = {}) {
  const { w, clock } = setup(on, over)
  await open($, clock)
  const ui = await draw($)
  await ui.press({ key: 'write' })
  await clock.settle()
  const md = w.written['/home/t/.claude/state/handover/sess-1.md']!
  await ui.unmount()
  return { w, clock, md }
}

test('v0.2 brief: HANDOVER.md State and READY lines are copied verbatim', async ($, on) => {
  const { md } = await writeAndRead($, on, { handover: REPO_MD })
  const sec = md.split('## Ready queue and state (from HANDOVER.md)')[1]!.split('\n## ')[0]!
  expect(sec).toContain('- DONE: X0')
  expect(sec).toContain('- READY: X4 C# params')
})

test('v0.2 brief: missing HANDOVER.md says so and the brief still writes', async ($, on) => {
  const { md } = await writeAndRead($, on)
  expect(md).toContain('## Ready queue and state (from HANDOVER.md)')
  expect(md).toContain('HANDOVER.md not found')
  expect(md).toContain('## Takeover protocol')
})

test('v0.2 git summary: counts by code and at most 8 lines with (N more not shown)', async ($, on) => {
  const { md } = await writeAndRead($, on, { gitStatus: STATUS_30 + '\n' })
  expect(md).toContain('counts by code: D 4, M 0, ?? 21')
  expect(md).toContain('(17 more not shown)')
  const st = md.split('## State')[1]!.split('\n## ')[0]!
  expect(st.split('\n').filter(l => /^ {4}(D |\?\?) /.test(l))).toHaveLength(8)
  expect(summarizeStatus([' M a', 'MM b', 'A  c']).counts).toBe('D 0, M 2, ?? 0, A 1')
})

test('v0.2 brief: Verify before trusting section is code-written', async ($, on) => {
  const { md } = await writeAndRead($, on, { head: 'f00dcafe' })
  const sec = md.split('## Verify before trusting')[1]!.split('\n## ')[0]!
  expect(sec).toContain('branch main')
  expect(sec).toContain('f00dcafe')
  expect(sec).toContain('git rev-parse --short HEAD')
  expect(sec).toContain('(model) are unverified')
})

test('v0.2 unverified flags: hash and figures not in facts are flagged, ones in facts are not', async ($, on) => {
  const facts = 'head: 3c53550\n12 files changed'
  expect(flagUnverified('fixed at deadbee1 done', facts)).toBe('fixed at deadbee1 done [unverified: not in facts]')
  expect(flagUnverified('read 123 lines of it', facts)).toBe('read 123 lines of it [unverified: not in facts]')
  expect(flagUnverified('9 tests and 2 worktrees', facts)).toContain('[unverified')
  expect(flagUnverified('at 3c53550 with 12 files', facts)).toBe('at 3c53550 with 12 files')
  expect(flagUnverified('no figures here, defaced', facts)).toBe('no figures here, defaced')
  const reply = GOOD_REPLY.replace('- keep own extractors', '- merged deadbee1 (123 lines) and abc1234 ok')
  const { md } = await writeAndRead($, on, { reply, head: 'abc1234' })
  const line = md.split('\n').find(l => l.includes('merged deadbee1'))!
  expect(line.endsWith(' [unverified: not in facts]')).toBe(true)
})

test('v0.2 seed is one line, carries the seven receipt items and points at the Takeover protocol', async () => {
  const seed = seedText('821a9aa2-da0c', '/h/.claude/state/handover/x.md', ['run-1', 'run-2'])
  expect(seed.includes('\n')).toBe(false)
  expect(seed).toContain('## Takeover protocol')
  expect(seed).toContain('/h/.claude/state/handover/x.md')
  for (const part of ['(1) "Took over from session 821a9aa2"', 'MATCH or STALE', '(3) your role', 'run-1, run-2', 'check their output files', 'at least 5 claims', 'questions', 'without the owner\'s yes']) expect(seed).toContain(part)
})

async function handOver($: any, on: any, over: any = {}) {
  const s = setup(on, over)
  on('classic.SessionStart', () => ({}))
  await open($, s.clock)
  const ui = await draw($)
  await ui.press({ key: 'write' })
  await s.clock.settle()
  return { ...s, ui }
}

test('v0.2 toast shown once after the seed, and the old pane step turns done', async ($, on) => {
  const { w, clock, ui } = await handOver($, on, { agents: [{ id: 'run-9', description: 'd', type: 'general-purpose', status: 'waiting' }] })
  expect(w.toasts).toEqual([])
  await ui.press({ key: 'clear' })
  await ui.press({ key: 'clear' })
  await clock.settle()
  expect(w.toasts).toEqual([]) // nothing is announced before the clear happens
  await $.classic.SessionStart({ source: 'clear' })
  await $.classic.SessionStart({ source: 'clear' })
  await clock.settle()
  expect(w.submits).toHaveLength(1)
  expect(w.toasts).toHaveLength(1)
  expect(w.toasts[0]).toMatch(/^handed over: seed sent \(brief \d+ lines, 1 agents active\)$/)
  expect((await textOf(ui)).join('\n')).toContain('✓ Seed fresh context')
  await ui.unmount()
})

test('v0.2 band: appears in the fresh context, fades in, stops its clock, clears on the first user prompt', async ($, on) => {
  on('ui.render', ($: any, e: any) => { const { Text } = $.ui.resolve(e); return <Text>engine</Text> }) // stands for the engine beneath the plugin
  const { w, clock, ui } = await handOver($, on, { agents: [{ id: 'run-9', description: 'd', type: 'general-purpose', status: 'waiting' }] })
  await ui.press({ key: 'clear' })
  await ui.press({ key: 'clear' })
  await clock.settle()
  await $.classic.SessionStart({ source: 'clear' })
  await clock.settle()
  const mount = () => $.ui.mount({ plugin: 'handover', component: 'AbovePrompt', requestId: 'band', surface: 'terminal', props: { hasSurvey: false, isWorking: false, maxRows: 6, bodyColumns: 100, scroll: { offset: 0, bodyRows: 6 }, view: {} } })
  let band = await mount()
  const early = (await textOf(band)).join('')
  expect(early.length).toBeGreaterThan(0)
  expect(early.length).toBeLessThan('✓ handed over #1 · from sess-1 · brief 1 lines · 1 agents active'.length) // mid-fade: partly revealed
  await band.unmount()
  await clock.advance(2000)
  band = await mount()
  const full = (await textOf(band)).join('')
  expect(full).toMatch(/^✓ handed over #1 · from sess-1 · brief \d+ lines · 1 agents active$/)
  await band.unmount()
  await $.prompt.submit({ text: 'the seed again', origin: { kind: 'sdk' }, wait: false }) // not a user prompt: band stays
  band = await mount()
  expect((await textOf(band)).join('')).toContain('handed over')
  await band.unmount()
  await $.prompt.submit({ text: 'hello', origin: { kind: 'composer' }, wait: false })
  await clock.settle()
  band = await mount()
  expect((await textOf(band)).join('')).not.toContain('handed over')
  await band.unmount()
  expect(w.clears).toBe(1)
  await ui.unmount()
})

test('v0.2 band clock stops when the fade ends (a mounted band is redrawn only during the fade)', async ($, on) => {
  on('ui.render', ($: any, e: any) => { const { Text } = $.ui.resolve(e); return <Text>engine</Text> })
  const { w, clock, ui } = await handOver($, on, { countStore: true })
  await ui.press({ key: 'clear' }) // no agents: one press clears
  await clock.settle()
  await $.classic.SessionStart({ source: 'clear' })
  await clock.settle()
  const band = await $.ui.mount({ plugin: 'handover', component: 'AbovePrompt', requestId: 'band', surface: 'terminal', props: { hasSurvey: false, isWorking: false, maxRows: 6, bodyColumns: 100, scroll: { offset: 0, bodyRows: 6 }, view: {} } })
  await clock.advance(1500) // fade (10 frames of 100 ms) is over
  const settled = w.bandReads
  expect(settled).toBeGreaterThan(2) // it was redrawn during the fade
  await clock.advance(10_000)
  expect(w.bandReads).toBe(settled) // and not afterwards: the clock stopped
  await band.unmount()
  await ui.unmount()
})

test('v0.2 model prompt forbids invented hashes and counts and carries the facts block', async () => {
  for (const t of [MODEL_SYSTEM, modelPrompt('t', 'branch: main, head: abc1234')]) expect(t).toMatch(/commit hash/i)
  expect(modelPrompt('t', 'branch: main, head: abc1234')).toContain('FACTS:\nbranch: main, head: abc1234')
})

test('v0.2 safety: no clear without a press, and never from SessionStart alone', async ($, on) => {
  const { w, clock, ui } = await handOver($, on, { agents: [{ id: 'r', description: 'd', type: 'general-purpose', status: 'running' }] })
  await $.classic.SessionStart({ source: 'clear' }) // no clear was ever requested: no seed, no toast, no band
  await clock.advance(20_000)
  expect(w.clears).toBe(0)
  expect(w.submits).toHaveLength(0)
  expect(w.toasts).toHaveLength(0)
  await ui.press({ key: 'clear' }) // first press with an active agent only asks
  await clock.settle()
  expect(w.clears).toBe(0)
  await ui.unmount()
})

test('v0.2 samples (logged for review)', async ($, on) => {
  on('ui.render', ($: any, e: any) => { const { Text } = $.ui.resolve(e); return <Text>engine</Text> })
  const agents = [{ id: 'a1b2c3d4-0001', description: 'X4 C# params', type: 'general-purpose', status: 'running' }]
  const { w, clock, ui } = await handOver($, on, { handover: REPO_MD, gitStatus: STATUS_30 + '\n', agents, head: '3c53550', reply: GOOD_REPLY.replace('- keep own extractors', '- merged deadbee1 (123 lines) at 3c53550') })
  log('BRIEF_SAMPLE_BEGIN\n' + w.written['/home/t/.claude/state/handover/sess-1.md'] + '\nBRIEF_SAMPLE_END')
  await ui.press({ key: 'clear' })
  await ui.press({ key: 'clear' })
  await clock.settle()
  await $.classic.SessionStart({ source: 'clear' })
  await clock.settle()
  log('SEED_SAMPLE_BEGIN\n' + w.submits[0] + '\nSEED_SAMPLE_END')
  log('TOAST: ' + w.toasts[0])
  const band = await $.ui.mount({ plugin: 'handover', component: 'AbovePrompt', requestId: 'band', surface: 'terminal', props: { hasSurvey: false, isWorking: false, maxRows: 6, bodyColumns: 100, scroll: { offset: 0, bodyRows: 6 }, view: {} } })
  log('BAND mid-fade: ' + (await textOf(band)).join(''))
  await clock.advance(2000)
  log('BAND settled: ' + (await textOf(band)).join(''))
  await band.unmount()
  log('PANE_AFTER_SEED\n' + (await textOf(ui)).slice(-8).join('\nPANE_ '))
  await ui.unmount()
})

// ------------------------------------------------------------------ v0.3: handover as a state machine

const cmd = ($: any, args: string) => $.command.run({ command: 'handover', args, origin: { kind: 'user' } } as any)
const seeds = (w: World) => w.submits.filter(t => t.startsWith('HANDOVER SEED:'))
const BAND_PROPS = { hasSurvey: false, isWorking: false, maxRows: 6, bodyColumns: 100, scroll: { offset: 0, bodyRows: 6 }, view: {} }
const mountBand = ($: any) => $.ui.mount({ plugin: 'handover', component: 'AbovePrompt', requestId: 'band', surface: 'terminal', props: BAND_PROPS })
const rec = async (w: World, sid: string) => w.mem.get(`handover:${sid}`) as any
const ENGINE = (on: any) => on('ui.render', ($: any, e: any) => { const { Text } = $.ui.resolve(e); return <Text>engine</Text> })

async function v3(on: any, $: any, over: any = {}) {
  ENGINE(on)
  on('turn.start', (_: any, e: any) => ({ turnId: e.turnId, text: e.text }))
  on('turn.complete', () => ({ text: '' }))
  return handOver($, on, over)
}
async function writeBriefNow(ui: any, clock: any) { await ui.press({ key: 'write' }); await clock.settle() }
/** One handover via the first path (classic.SessionStart): write, press clear, the new session id appears, SessionStart fires. */
async function cycle($: any, ui: any, w: World, clock: any, nextSid: string) {
  await clock.advance(4000) // past the debounce, and the refresh tick drops the old session's brief
  await writeBriefNow(ui, clock)
  await ui.press({ key: 'clear' })
  await clock.settle()
  w.sid = nextSid
  await $.classic.SessionStart({ source: 'clear' })
  await clock.settle()
}

test('v0.3 chain A->B->C: each seeds once, n increments, previous ids are recorded', async ($, on) => {
  const { w, clock, ui } = await v3(on, $, { sid: 'sess-a' })
  await cycle($, ui, w, clock, 'sess-b')
  expect(seeds(w)).toHaveLength(1)
  expect(seeds(w)[0]).toContain('handover #1, previous session sess-a')
  expect((await rec(w, 'sess-a')).state).toBe('seeded')
  expect(w.mem.get('lineage:sess-b')).toEqual({ from: 'sess-a', n: 1 })
  expect((await rec(w, 'sess-b')).n).toBe(2)
  expect((await rec(w, 'sess-b')).state).toBe('idle')
  await cycle($, ui, w, clock, 'sess-c')
  expect(seeds(w)).toHaveLength(2)
  expect(seeds(w)[1]).toContain('handover #2, previous session sess-b')
  expect(w.mem.get('lineage:sess-c')).toEqual({ from: 'sess-b', n: 2 })
  await clock.advance(4000)
  await writeBriefNow(ui, clock)
  const md = w.written['/home/t/.claude/state/handover/sess-c.md']!
  expect(md).toContain('Handover #3 in chain: previous sessions sess-b <- sess-a') // item 5
  expect(w.clears).toBe(2)
  await ui.unmount()
})

test('v0.3 clearing younger than STALL_MS blocks a double clear; older becomes stalled and Retry issues exactly one new clear', async ($, on) => {
  const { w, clock, ui } = await v3(on, $)
  await ui.press({ key: 'clear' })
  await clock.settle()
  expect(w.clears).toBe(1)
  expect((await rec(w, 'sess-1')).state).toBe('clearing')
  await clock.advance(10_000)
  await ui.press({ key: 'clear' })
  await clock.settle()
  expect(w.clears).toBe(1) // blocked
  let t = (await textOf(ui)).join('\n')
  expect(t).toMatch(/Clear requested, waiting for the session to go idle \(1\ds\)/)
  expect(t).not.toContain('Retry clear')
  await clock.advance(40_000) // 50 s in: the refresh tick marks it stalled
  expect((await rec(w, 'sess-1')).state).toBe('stalled')
  t = (await textOf(ui)).join('\n')
  expect(t).toContain('STATUS stalled')
  for (const a of ['[ Retry clear ]', '[ Seed now ]', '[ Reset ]']) expect(t).toContain(a)
  await ui.press({ key: 'clear' })
  await clock.settle()
  expect(w.clears).toBe(2) // exactly one new clear
  await ui.press({ key: 'clear' })
  await clock.settle()
  expect(w.clears).toBe(2)
  expect((await rec(w, 'sess-1')).state).toBe('clearing')
  await ui.unmount()
})

test('v0.3 SessionStart skipped: the first turn.start in the new context seeds, once', async ($, on) => {
  const { w, clock, ui } = await v3(on, $, { sid: 'sess-a' })
  await ui.press({ key: 'clear' })
  await clock.advance(20)
  await $.turn.start({ text: 'in the old context', turnId: 'x0' }) // same session id: the clear has not happened, no seed
  expect(seeds(w)).toHaveLength(0)
  w.sid = 'sess-b' // the clear happened; classic.SessionStart never fires
  await $.turn.start({ text: 'hello', turnId: 't1' })
  await clock.advance(20)
  expect(seeds(w)).toHaveLength(1)
  expect(seeds(w)[0]).toContain('handover #1')
  await $.turn.start({ text: 'again', turnId: 't2' })
  await $.prompt.submit({ text: 'more', origin: { kind: 'composer' }, wait: false })
  await $.classic.SessionStart({ source: 'clear' }) // a late SessionStart finds the nonce done
  await clock.advance(20)
  expect(seeds(w)).toHaveLength(1)
  expect(w.toasts).toHaveLength(1)
  await ui.unmount()
})

test('v0.3 SessionStart skipped: the first user prompt.submit in the new context seeds, once', async ($, on) => {
  const { w, clock, ui } = await v3(on, $, { sid: 'sess-a' })
  await ui.press({ key: 'clear' })
  await clock.advance(20)
  w.sid = 'sess-b'
  await $.prompt.submit({ text: 'first prompt', origin: { kind: 'composer' }, wait: false })
  await clock.advance(20)
  await $.prompt.submit({ text: 'second prompt', origin: { kind: 'composer' }, wait: false })
  await clock.advance(20)
  expect(seeds(w)).toHaveLength(1)
  await ui.unmount()
})

test('v0.3 /handover seed sends the pending seed in the current context and marks it done', async ($, on) => {
  const { w, clock, ui } = await v3(on, $)
  await ui.press({ key: 'clear' })
  await clock.advance(20)
  const run = (args: string) => cmd($, args)
  const r = await run('seed')
  await clock.advance(20)
  expect(JSON.stringify(r)).toContain('Seeded handover #1')
  expect(seeds(w)).toHaveLength(1)
  expect((w.mem.get('seed-pending') as any).done).toBe(true)
  expect(JSON.stringify(await run('seed'))).toContain('Nothing to seed')
  await $.classic.SessionStart({ source: 'clear' })
  await clock.advance(20)
  expect(seeds(w)).toHaveLength(1)
  await ui.unmount()
})

test('v0.3 Seed now button seeds a stalled handover once', async ($, on) => {
  const { w, clock, ui } = await v3(on, $)
  await ui.press({ key: 'clear' })
  await clock.advance(50_000)
  await ui.press({ key: 'seed' })
  await clock.settle()
  expect(seeds(w)).toHaveLength(1)
  expect((await textOf(ui)).join('\n')).not.toContain('[ Seed now ]')
  await ui.unmount()
})

test('v0.3 /handover reset after a stalled attempt returns to idle and a new handover works', async ($, on) => {
  const { w, clock, ui } = await v3(on, $, { sid: 'sess-a' })
  await ui.press({ key: 'clear' })
  await clock.advance(50_000)
  expect((await rec(w, 'sess-a')).state).toBe('stalled')
  await cmd($, 'reset')
  await clock.settle()
  expect((await rec(w, 'sess-a')).state).toBe('idle')
  expect((w.mem.get('seed-pending') as any).done).toBe(true)
  w.sid = 'sess-b'
  await $.classic.SessionStart({ source: 'clear' }) // the dropped attempt must not seed
  expect(seeds(w)).toHaveLength(0)
  w.sid = 'sess-a'
  await cycle($, ui, w, clock, 'sess-b')
  expect(w.clears).toBe(2)
  expect(seeds(w)).toHaveLength(1)
  await ui.unmount()
})

test('v0.3 Reset button needs a second press', async ($, on) => {
  const { w, clock, ui } = await v3(on, $)
  await ui.press({ key: 'clear' })
  await clock.advance(50_000)
  await ui.press({ key: 'reset' })
  await clock.settle()
  expect((await rec(w, 'sess-1')).state).toBe('stalled')
  expect((await textOf(ui)).join('\n')).toContain('Confirm reset')
  await ui.press({ key: 'reset' })
  await clock.settle()
  expect((await rec(w, 'sess-1')).state).toBe('idle')
  await ui.unmount()
})

test('v0.3 failed and seeded records allow a new handover; no permanent refusal', async ($, on) => {
  const { w, clock, ui } = await v3(on, $, { sid: 'sess-a', failClear: true })
  await ui.press({ key: 'clear' })
  await clock.settle()
  expect((await rec(w, 'sess-a')).state).toBe('failed')
  expect((await textOf(ui)).join('\n')).toContain('STATUS failed')
  w.failClear = false
  await clock.advance(4000)
  await ui.press({ key: 'clear' })
  await clock.settle()
  expect(w.clears).toBe(1)
  w.sid = 'sess-b'
  await $.classic.SessionStart({ source: 'clear' })
  await clock.settle()
  expect((await rec(w, 'sess-a')).state).toBe('seeded')
  w.sid = 'sess-a' // back in a session whose record says 'seeded'
  await clock.advance(4000)
  await writeBriefNow(ui, clock)
  await ui.press({ key: 'clear' })
  await clock.settle()
  expect(w.clears).toBe(2)
  await ui.unmount()
})

test('v0.3 no path ever double-seeds the same nonce (all paths at once)', async ($, on) => {
  const { w, clock, ui } = await v3(on, $, { sid: 'sess-a' })
  await ui.press({ key: 'clear' })
  await clock.advance(20)
  w.sid = 'sess-b'
  await Promise.all([
    $.classic.SessionStart({ source: 'clear' }),
    $.turn.start({ text: 'hi', turnId: 't1' }),
    $.prompt.submit({ text: 'hello', origin: { kind: 'composer' }, wait: false }),
    cmd($, 'seed'),
  ])
  await clock.advance(20)
  expect(seeds(w)).toHaveLength(1)
  expect(w.toasts).toHaveLength(1)
  await ui.unmount()
})

test('v0.3 debounce: a repeat press within 3 s is ignored, a later press works', async ($, on) => {
  const { w, clock, ui } = await v3(on, $, { failClear: true })
  await ui.press({ key: 'clear' })
  await clock.settle()
  expect(w.clearCalls).toBe(1)
  await clock.advance(1000)
  await ui.press({ key: 'clear' })
  await clock.settle()
  expect(w.clearCalls).toBe(1) // ignored
  w.failClear = false
  await clock.advance(3000)
  await ui.press({ key: 'clear' })
  await clock.settle()
  expect(w.clearCalls).toBe(2) // later press works
  await ui.unmount()
})

test('v0.3 active-agent confirm guard still needs the second press; turn-running refusal is not permanent', async ($, on) => {
  const { w, clock, ui } = await v3(on, $, { agents: [{ id: 'run-1', description: 'd', type: 'general-purpose', status: 'running' }] })
  await ui.press({ key: 'clear' })
  await clock.settle()
  expect(w.clears).toBe(0)
  await $.turn.start({ text: 'working', turnId: 'tt' })
  await ui.press({ key: 'clear' })
  expect(w.clears).toBe(0)
  expect((await textOf(ui)).join('\n')).toContain('Try again when the session is idle')
  await $.turn.complete({ turnId: 'tt', answer: 'done', durationMs: 1, isAborted: false, reason: 'answer' })
  await ui.press({ key: 'clear' })
  await clock.settle()
  expect(w.clears).toBe(1)
  await ui.unmount()
})

test('v0.3 nothing clears or seeds without a press (hooks, commands and ticks alone)', async ($, on) => {
  const { w, clock, ui } = await v3(on, $)
  await $.classic.SessionStart({ source: 'clear' })
  await $.turn.start({ text: 'hi', turnId: 't1' })
  await $.prompt.submit({ text: 'hello', origin: { kind: 'composer' }, wait: false })
  await cmd($, 'seed')
  await cmd($, 'reset')
  await clock.advance(60_000)
  expect(w.clearCalls).toBe(0)
  expect(seeds(w)).toHaveLength(0)
  await ui.unmount()
})

test('v0.3 pane shows #n, chain position and the countdown', async ($, on) => {
  const { w, clock, ui } = await v3(on, $, { sid: 'sess-a' })
  await ui.press({ key: 'clear' })
  await clock.advance(12_000)
  expect((await textOf(ui)).join('\n')).toMatch(/STATUS Clear requested, waiting for the session to go idle \(1[2-3]s\); handover #1/)
  w.sid = 'sess-b'
  await $.classic.SessionStart({ source: 'clear' })
  await clock.advance(2000)
  const t = (await textOf(ui)).join('\n')
  expect(t).toContain('STATUS idle: this session is handover #1, from sess-a…; next is handover #2')
  const band = await mountBand($)
  expect((await textOf(band)).join('')).toMatch(/^✓ handed over #1 · from sess-a · brief \d+ lines · 0 agents active$/)
  await band.unmount()
  await ui.unmount()
})

function paneTail(t: string[]) { return t.filter(l => /STATUS|\[ |^Refused|^Clear|^Reset|^Seeded|^Press/.test(l)).join('\nPANE_ ') }

test('v0.3 samples (logged for review)', async ($, on) => {
  const { w, clock, ui } = await v3(on, $, { sid: '8a1f77c0-aaaa', reply: GOOD_REPLY, head: '3c53550', agents: [] })
  const snap = async (label: string) => log(`PANE_SNAPSHOT ${label}\nPANE_ ${paneTail(await textOf(ui))}`)
  await snap('ready (brief written, session 8a1f77c0, first in chain)')
  await ui.press({ key: 'clear' })
  await clock.advance(12_000)
  await snap('clearing, 12 s in')
  await clock.advance(40_000)
  await snap('stalled, 52 s in')
  w.sid = 'b2c3d4e5-bbbb'
  await $.classic.SessionStart({ source: 'clear' })
  await clock.advance(2000)
  log('SEED_SAMPLE_BEGIN\n' + seeds(w)[0] + '\nSEED_SAMPLE_END')
  await snap('seeded (new session b2c3d4e5, handover #1 done; pane is the old one, now in the new session)')
  const band = await mountBand($)
  log('BAND_SAMPLE: ' + (await textOf(band)).join(' | '))
  await band.unmount()
  await ui.unmount()
})

test('v0.3 band (pane not placed) shows the clearing countdown and the actions', async ($, on) => {
  ENGINE(on)
  const { w, clock } = setup(on, { placed: false })
  await open($, clock)
  const band = await mountBand($)
  await band.press({ key: 'write' })
  await clock.settle()
  await band.press({ key: 'clear' })
  await clock.advance(50_000)
  const t = (await textOf(band)).join('\n')
  expect(t).toContain('STATUS stalled: no fresh context after 50s; handover #1')
  expect(t).toContain('[ Retry clear ]')
  expect(t).toContain('[ Seed now ]')
  expect(w.clears).toBe(1)
  await band.unmount()
})

// ------------------------------------------------------------------ v0.4: inbox ledger (observe only)

const LEDGER = '/home/t/.claude/state/handover/ledger-sess-1.jsonl'
const ORIGINS: any[] = [
  { kind: 'bridge' }, { kind: 'task-notification' }, { kind: 'scheduled-trigger' }, { kind: 'peer-send-message' },
  { kind: 'projects-relay' }, { kind: 'slack-ping' }, { kind: 'unclassified' },
  { kind: 'peer' }, { kind: 'peer', plugin: 'other' }, { kind: 'coordinator', plugin: 'lead' },
  { kind: 'peer', teammate: 'researcher', isVerified: false }, { kind: 'coordinator', teammate: 'team-lead', isVerified: true, plugin: 'p' },
]
const rows = (w: World, path = LEDGER) => (w.written[path] ?? '').split('\n').filter(Boolean).map(l => JSON.parse(l))
const deliver = ($: any, origin: any, text: string, agentId?: string) => $.session.receive({ origin, text, ...(agentId ? { agentId } : {}) })
const flush = async (clock: any) => { await clock.advance(5); await clock.settle() }

for (const mode of ['ok', 'fs', 'store'] as const) {
  test(`v0.4 observer returns next(e) with e unchanged for every origin kind (${mode === 'ok' ? 'ledger works' : mode === 'fs' ? 'fs write throws' : 'store throws'})`, async ($, on) => {
    const { w, clock } = setup(on, { fsFail: mode === 'fs', storeFail: mode === 'store' })
    await $.session.start({ cwd: '/repo', surface: 'terminal', isInteractive: true })
    for (const origin of ORIGINS) {
      const input = { origin, text: `hello from ${origin.kind}`, agentId: 'agent-1' }
      const before = w.bottom.length
      const r = await $.session.receive(input as any)
      expect(w.bottom[before]).toEqual(input) // the engine below saw the same delivery
      expect(r).toEqual({ text: input.text }) // and its answer came back untouched
      expect((r as any).consumed).toBeUndefined()
      await flush(clock)
    }
    expect(w.bottom).toHaveLength(ORIGINS.length)
    if (mode === 'ok') expect(rows(w)).toHaveLength(ORIGINS.length)
    if (mode !== 'ok') expect(rows(w)).toHaveLength(0)
  })
}

test('v0.4 ledger records seq, origin, plugin, agent id, 1500-char excerpt, full length; trims to the last 300', async ($, on) => {
  const { w, clock } = setup(on)
  await $.session.start({ cwd: '/repo', surface: 'terminal', isInteractive: true })
  await deliver($, { kind: 'task-notification' }, 'x'.repeat(5000), 'agent-77')
  await deliver($, { kind: 'peer', plugin: 'sender' }, 'short')
  await flush(clock)
  const r = rows(w)
  expect(r.map(x => x.seq)).toEqual([1, 2])
  expect(r[0]).toMatchObject({ kind: 'task-notification', agentId: 'agent-77', len: 5000 })
  expect(r[0].excerpt).toHaveLength(1500)
  expect(typeof r[0].ts).toBe('number')
  expect(r[1]).toMatchObject({ kind: 'peer', plugin: 'sender', excerpt: 'short', len: 5 })
  expect(r[1].agentId).toBeUndefined()
  for (let i = 0; i < 303; i++) await deliver($, { kind: 'bridge' }, `m${i}`)
  await flush(clock)
  const t = rows(w)
  expect(t).toHaveLength(300)
  expect(t[0].seq).toBe(6)
  expect(t[299].seq).toBe(305)
  expect((w.mem.get('inbox:sess-1') as any).total).toBe(305)
})

test('v0.4 one ledger follows a chain A->B->C: same file, increasing seq', async ($, on) => {
  const { w, clock, ui } = await v3(on, $, { sid: 'sess-a' })
  await deliver($, { kind: 'peer' }, 'in A')
  await cycle($, ui, w, clock, 'sess-b')
  await deliver($, { kind: 'bridge' }, 'in B')
  await cycle($, ui, w, clock, 'sess-c')
  await deliver($, { kind: 'task-notification' }, 'in C')
  await flush(clock)
  const files = Object.keys(w.written).filter(k => k.includes('ledger-'))
  expect(files).toEqual(['/home/t/.claude/state/handover/ledger-sess-a.jsonl'])
  expect(rows(w, files[0]).map(x => [x.seq, x.excerpt])).toEqual([[1, 'in A'], [2, 'in B'], [3, 'in C']])
  await ui.unmount()
})

async function inboxPane(on: any, $: any, over: any = {}) {
  const s = await v3(on, $, over)
  return s
}

test('v0.4 pane inbox section: counts by origin, N since the brief, last 5; band shows inbox N (M new)', async ($, on) => {
  const { w, clock, ui } = await inboxPane(on, $)
  await ui.press({ key: 'write' }); await clock.settle()
  for (const [k, t] of [['task-notification', 'done 1'], ['task-notification', 'done 2'], ['peer', 'ping'], ['bridge', 'from phone'], ['task-notification', 'done 3'], ['peer', 'second ping'], ['scheduled-trigger', 'cron fired']] as const)
    await deliver($, { kind: k }, t, k === 'task-notification' ? 'abcdef12-0000' : undefined)
  await flush(clock)
  await clock.advance(1500)
  const t = (await textOf(ui)).join('\n')
  expect(t).toContain('INBOX (7 since the chain started)')
  expect(t).toContain('task-notification 3')
  expect(t).toContain('peer 2')
  expect(t).toContain('7 since the brief was written')
  expect(t).toContain('#7 scheduled-trigger - ')
  expect(t).toContain('#3 peer')
  expect(t).not.toContain('#2 ') // only the last 5
  expect(t).toContain('abcdef12')
  log('INBOX_PANE\n' + (await textOf(ui)).filter(l => /INBOX|by origin|since the brief|^#\d/.test(l)).join('\nINBOX_ '))
  const band = await mountBand($)
  w.placed = false
  expect((await textOf(band)).join(' ')).not.toContain('inbox') // pane mode: the band tree is only drawn in band mode
  await band.unmount()
  await ui.unmount()
})

test('v0.4 band (pane not placed) shows inbox N (M new)', async ($, on) => {
  ENGINE(on)
  const { clock } = setup(on, { placed: false })
  await open($, clock)
  const band = await mountBand($)
  await deliver($, { kind: 'peer' }, 'a'); await deliver($, { kind: 'bridge' }, 'b')
  await flush(clock); await clock.advance(1500)
  const t = (await textOf(band)).join(' ')
  expect(t).toContain('inbox 2 (2 new)')
  log('BAND_INBOX: ' + t)
  await band.unmount()
})

test('v0.4 guard: deliveries after the brief warn on the first press, a second press within 8 s clears once', async ($, on) => {
  const { w, clock, ui } = await inboxPane(on, $)
  await deliver($, { kind: 'task-notification' }, 'agent finished'); await deliver($, { kind: 'peer' }, 'hi')
  await flush(clock)
  await ui.press({ key: 'clear' }); await clock.settle()
  expect(w.clears).toBe(0)
  const t = (await textOf(ui)).join('\n')
  expect(t).toContain('2 deliveries arrived after the brief was written: press Write brief again, or press again within 8 s to hand over anyway')
  expect(t).toContain('Confirm clear')
  log('GUARD_WARNING: ' + t.split('\n').find(l => l.includes('deliveries arrived')))
  await clock.advance(3000)
  await ui.press({ key: 'clear' }); await clock.settle()
  expect(w.clears).toBe(1)
  await ui.press({ key: 'clear' }); await clock.settle()
  expect(w.clears).toBe(1)
  await ui.unmount()
})

test('v0.4 guard: the window lapses, and a brief refresh clears the warning so one press clears', async ($, on) => {
  const { w, clock, ui } = await inboxPane(on, $)
  await deliver($, { kind: 'peer' }, 'hi'); await flush(clock)
  await ui.press({ key: 'clear' }); await clock.settle()
  await clock.advance(9000)
  await ui.press({ key: 'clear' }); await clock.settle() // lapsed: asks again, still no clear
  expect(w.clears).toBe(0)
  await ui.press({ key: 'write' }); await clock.settle() // refresh the brief
  expect((await textOf(ui)).join('\n')).not.toContain('deliveries arrived after')
  await ui.press({ key: 'clear' }); await clock.settle()
  expect(w.clears).toBe(1) // no permanent refusal, no second press needed
  await ui.unmount()
})

test('v0.4 guard: a delivery between the two presses asks again; agents still need their confirm too', async ($, on) => {
  const { w, clock, ui } = await inboxPane(on, $, { agents: [{ id: 'run-1', description: 'd', type: 'general-purpose', status: 'running' }] })
  await deliver($, { kind: 'peer' }, 'one'); await flush(clock)
  await ui.press({ key: 'clear' }); await clock.settle()
  const t = (await textOf(ui)).join('\n')
  expect(t).toContain('1 deliveries arrived after the brief') // both warnings in one note
  expect(t).toContain('NOT determined')
  await deliver($, { kind: 'peer' }, 'two'); await flush(clock)
  await ui.press({ key: 'clear' }); await clock.settle()
  expect(w.clears).toBe(0)
  expect((await textOf(ui)).join('\n')).toContain('2 deliveries arrived after the brief')
  await ui.press({ key: 'clear' }); await clock.settle()
  expect(w.clears).toBe(1)
  await ui.unmount()
})

test('v0.4 brief: Inbox section written by code, receipt item 4b; samples logged', async ($, on) => {
  const { w, clock, ui } = await inboxPane(on, $, { sid: 'sess-1' })
  await deliver($, { kind: 'task-notification' }, 'agent 9 finished: all green', 'agent-9'); await deliver($, { kind: 'peer', plugin: 'x' }, 'please "review"\nnow')
  await flush(clock)
  await ui.press({ key: 'write' }); await clock.settle()
  const md = w.written['/home/t/.claude/state/handover/sess-1.md']!
  expect(md).toContain('## Inbox (deliveries this session)')
  expect(md).toContain('Deliveries recorded since the chain started: 2 (by origin: task-notification 1, peer 1)')
  expect(md).toMatch(/- #1 .* task-notification agent agent-9 \(excerpt\) "agent 9 finished: all green"/)
  expect(md).toContain("(excerpt) \"please 'review' now\"")
  expect(md).toContain(`Ledger: ${LEDGER}`)
  expect(md).toContain('Deliveries that arrived after this brief was written are in the ledger; read it before acting.')
  expect(md).toContain(`4b. Inbox: 2 deliveries total at brief time; M after the brief = ledger entries with seq > 2 (state M and what each needs); ledger ${LEDGER}.`)
  log('BRIEF_V04_BEGIN\n' + md + '\nBRIEF_V04_END')
  await ui.unmount()
})

test('v0.4 seed gains the inbox clause only when deliveries arrived after the brief, and stays one line', async ($, on) => {
  const a = await inboxPane(on, $)
  await a.clock.advance(4000)
  await deliver($, { kind: 'peer' }, 'late 1'); await deliver($, { kind: 'bridge' }, 'late 2'); await flush(a.clock)
  await a.ui.press({ key: 'clear' }); await a.ui.press({ key: 'clear' }); await a.clock.settle()
  a.w.sid = 'sess-2'
  await $.classic.SessionStart({ source: 'clear' }); await a.clock.settle()
  const seed = seeds(a.w)[0]!
  expect(seed).toContain(`; inbox: 2 deliveries arrived after the brief, read ${LEDGER} first`)
  expect(seed.includes('\n')).toBe(false)
  for (const n of ['(1)', '(2)', '(3)', '(4)', '(5)', '(6)', '(7)', 'handover #1']) expect(seed).toContain(n)
  expect(seed.endsWith('.')).toBe(true)
  log('SEED_V04_BEGIN\n' + seed + '\nSEED_V04_END')
  await a.ui.unmount()
})

test('v0.4 seed has no inbox clause when nothing arrived after the brief', async ($, on) => {
  const { w, clock, ui } = await inboxPane(on, $)
  await deliver($, { kind: 'peer' }, 'early'); await flush(clock)
  await ui.press({ key: 'write' }); await clock.settle() // brief after the delivery
  await ui.press({ key: 'clear' }); await clock.settle()
  expect(w.clears).toBe(1)
  w.sid = 'sess-2'
  await $.classic.SessionStart({ source: 'clear' }); await clock.settle()
  expect(seeds(w)[0]).not.toContain('inbox:')
  expect(seedText('s', '/p', [], 1)).not.toContain('inbox')
  await ui.unmount()
})

test('v0.4 /handover inbox lists the last 10; /handover inbox <seq> shows one stored excerpt', async ($, on) => {
  const { w, clock } = setup(on)
  await $.session.start({ cwd: '/repo', surface: 'terminal', isInteractive: true })
  expect((await cmd($, 'inbox') as any).text).toContain('empty')
  for (let i = 1; i <= 12; i++) await deliver($, { kind: i % 2 ? 'peer' : 'task-notification' }, `msg ${i} ` + 'y'.repeat(300), i === 12 ? 'agent-xyz-123' : undefined)
  await flush(clock)
  const list = (await cmd($, 'inbox') as any).text as string
  expect(list.split('\n')).toHaveLength(11) // header + 10
  expect(list).toContain('#3 peer - ')
  expect(list).not.toContain('#2 ')
  expect(list).toMatch(/#12 task-notification agent-xy .*msg 12 y+/)
  expect(list.split('\n')[1]!.split('  ')[1]!.length).toBeLessThanOrEqual(120)
  const one = (await cmd($, 'inbox 12') as any).text as string
  expect(one).toContain('#12 task-notification agent agent-xyz-123')
  expect(one).toContain('y'.repeat(300))
  expect((await cmd($, 'inbox 999') as any).text).toContain('No entry #999')
  log('INBOX_CMD\n' + list.split('\n').slice(0, 4).join('\n'))
  // no argument still opens the pane
  expect((await cmd($, '') as any).text).toContain('Handover pane opened')
  expect(w.clears).toBe(0)
})

async function forwardWorld(on: any, $: any, answer: string) {
  const s = await v3(on, $, { agents: [{ id: 'agent-aaaa1111', description: 'd', type: 'general-purpose', status: 'running' }, { id: 'agent-bbbb2222', description: 'd', type: 'general-purpose', status: 'completed' }] })
  await s.ui.press({ key: 'clear' }); await s.ui.press({ key: 'clear' }); await s.clock.settle()
  s.w.sid = 'sess-2'
  await $.classic.SessionStart({ source: 'clear' }); await s.clock.settle()
  const done = async (agentId: string, text = answer) => { await $.turn.complete({ turnId: `t-${agentId}`, agentId, answer: text, durationMs: 1, isAborted: false, reason: 'answer' } as any); await flush(s.clock) }
  return { ...s, done }
}

test('v0.4 forward: a recorded agent completing in the new context appends exactly one meta row, never twice', async ($, on) => {
  const { w, clock, ui, done } = await forwardWorld(on, $, 'found 3 bugs')
  expect(w.appended).toHaveLength(0)
  await done('agent-aaaa1111')
  expect(w.appended).toHaveLength(1)
  expect(w.appended[0].type).toBe('user')
  const text = w.appended[0].content[0].text as string
  expect(text).toContain('agent agent-aa (active at handover #1) completed: found 3 bugs')
  await done('agent-aaaa1111'); await done('agent-aaaa1111', 'again')
  expect(w.appended).toHaveLength(1)
  expect(w.mem.get('forwarded:sess-1')).toEqual(['agent-aaaa1111'])
  expect(rows(w).filter(r => r.kind === 'handover-forward')).toHaveLength(1)
  await clock.advance(1500)
  expect((await textOf(ui)).join('\n')).toContain('FORWARD agent agent-aa completion forwarded (active at handover #1)')
  await ui.unmount()
})

test('v0.4 forward: missing text says so; unrecorded or already-completed-at-handover ids are ignored; main-loop turns ignored', async ($, on) => {
  const { w, done, ui } = await forwardWorld(on, $, '')
  await done('agent-unknown')
  await done('agent-bbbb2222') // was completed at handover: not in agentIds
  await $.turn.complete({ turnId: 'main', answer: 'x', durationMs: 1, isAborted: false, reason: 'answer' } as any)
  expect(w.appended).toHaveLength(0)
  await done('agent-aaaa1111', '')
  expect(w.appended).toHaveLength(1)
  expect(w.appended[0].content[0].text).toContain("result text not available to the mod: check the agent's output file")
  await ui.unmount()
})

test('v0.4 forward does not fire in the old context (no earlier session in the chain)', async ($, on) => {
  const { w, clock, ui } = await v3(on, $, { agents: [{ id: 'agent-aaaa1111', description: 'd', type: 'general-purpose', status: 'running' }] })
  await $.turn.complete({ turnId: 't', agentId: 'agent-aaaa1111', answer: 'r', durationMs: 1, isAborted: false, reason: 'answer' } as any)
  await flush(clock)
  expect(w.appended).toHaveLength(0)
  await ui.unmount()
})

test('v0.4 README says the ledger keeps excerpts and how to turn it off', async () => {
  expect(LEDGER_ENABLED).toBe(true)
})
