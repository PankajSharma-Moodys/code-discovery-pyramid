import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import type { Bar, View } from '../types'
import {
  ACTIVE, BRIEF_REL, CONFIRM_MS, DEFAULT_WINDOW, FRAME_MS, PANE, REFRESH_MS, SPIN,
  activeAgents, assembleBrief, barRuns, condense, ctxColor, ease, emptyBar, freshView, initialSteps,
  isAnimating, modelPrompt, MODEL_SYSTEM, parseModelReply, parseRepoHandover, seedText, shortId,
  statusColor, tok, toRows, BAND_FRAMES, bandReveal, bandText, factsBlock, toastText,
} from './lib'
import type { BandState, Facts } from './lib'

const viewAtom = atom({ plugin: 'handover', key: 'view' } as const, freshView())
// Redraw trigger for the confirmation band; what the band shows lives in $.store ('band'), which survives /clear.
const bandAtom = atom({ plugin: 'handover', key: 'band' } as const, 0)

// Not drawing state, so module variables (a hot reload only loses the timer handle).
let tick: { cancel(): void } | undefined
let bandTick: { cancel(): void } | undefined
let tickN = 0
let isStepping = false
let isRefreshing = false
let isWriting = false
let turnRunning = false
let isClosingForBand = false
let breakdownBars: Bar[] = []

type UI = { Box: any; Text: any; Button: any }

// ------------------------------------------------------------------ data

const setView = ($: EngineInterface, fn: (v: View) => View) => update($, viewAtom, fn)
const note = ($: EngineInterface, text: string) => setView($, v => ({ ...v, note: text }))

function carry(prev: Bar[], next: Bar[]): Bar[] {
  return next.map(b => ({ ...b, shown: prev.find(p => p.key === b.key)?.shown ?? 0 }))
}

function bar(key: string, label: string, group: string, target: number | undefined, detail: string): Bar {
  return { key, label, group, target, shown: 0, detail }
}

async function refreshData($: EngineInterface, withBreakdown: boolean) {
  if (isRefreshing) return
  isRefreshing = true
  try {
    let usage
    try {
      usage = await $.session.usage(withBreakdown ? { breakdown: 'summary' } : undefined)
    } catch {
      usage = undefined
    }
    if (usage && withBreakdown) {
      const bd = usage.context.breakdown
      const out: Bar[] = []
      const api = bd?.apiUsage
      const g1 = 'Last response (API-counted)'
      const rows: [string, string, number | undefined][] = [
        ['in', 'input', api?.input_tokens], ['out', 'output', api?.output_tokens],
        ['cr', 'cache read', api?.cache_read_input_tokens], ['cw', 'cache write', api?.cache_creation_input_tokens],
      ]
      const max = Math.max(1, ...rows.map(r => r[2] ?? 0))
      for (const [k, l, n] of rows) out.push(bar(k, l, g1, n === undefined ? undefined : n / max, tok(n)))
      const cats = (bd?.categories ?? []).filter(c => c.kind === 'used' && c.tokens > 0).sort((a, b) => b.tokens - a.tokens).slice(0, 5)
      const cmax = Math.max(1, ...cats.map(c => c.tokens))
      for (const c of cats) out.push(bar(`cat:${c.name}`, c.name.slice(0, 18), 'Context by category (estimate)', c.tokens / cmax, tok(c.tokens)))
      breakdownBars = out
    }
    const rate: Bar[] = (usage?.rateLimits ?? []).map(r =>
      bar(`rl:${r.kind}`, r.kind, 'Rate limits', r.percentUsed / 100, `${r.percentUsed}%${r.resetsAt ? ` resets ${r.resetsAt.slice(11, 16)}Z` : ''}`),
    )
    if (!rate.length) rate.push(bar('rl:none', 'rate limits', 'Rate limits', undefined, 'n/a'))
    let agents
    try {
      agents = toRows(await $.agent.list())
    } catch {
      agents = undefined
    }
    const now = await $.clock.now()
    await setView($, v => {
      const w = usage?.context.window || DEFAULT_WINDOW
      const tokens = usage?.context.tokens
      const pct = tokens === undefined ? undefined : (tokens / w) * 100
      const ctx = {
        ...v.ctx,
        target: pct === undefined ? undefined : pct / 100,
        detail: tokens === undefined ? 'n/a (no response yet)' : `${pct!.toFixed(1)}%  ${tok(tokens)} / ${tok(w)}`,
      }
      const bars = carry(v.bars, [...breakdownBars, ...rate])
      const expired = v.confirmUntil > 0 && now > v.confirmUntil
      return {
        ...v, ctx, bars, ctxTokens: tokens, ctxWindow: w, ctxPercent: pct,
        costUsd: usage?.cost?.usd, agents: agents ?? v.agents, updatedAt: now,
        confirmUntil: expired ? 0 : v.confirmUntil, confirmIds: expired ? '' : v.confirmIds,
        note: expired ? 'Confirmation window ended; nothing was cleared.' : v.note,
      }
    })
  } finally {
    isRefreshing = false
  }
}

// ------------------------------------------------------------------ animation clock

function startTick($: EngineInterface) {
  if (tick) return
  tickN = 0
  tick = $.clock.every(FRAME_MS, () => void step($))
}

function stopTick() {
  tick?.cancel()
  tick = undefined
}

async function step($: EngineInterface) {
  if (isStepping) return // guard: never queue frames behind a slow redraw
  isStepping = true
  try {
    const v = await read($, viewAtom)
    if (!v.isOpen) return stopTick()
    tickN++
    const isRefresh = tickN % Math.round(REFRESH_MS / FRAME_MS) === 0
    if (isRefresh) await refreshData($, tickN % (50 * 1) === 0)
    const w = await read($, viewAtom)
    if (!isAnimating(w) && !isRefresh) return // idle frames cost nothing
    await setView($, x => ({
      ...x,
      frame: x.frame + 1,
      ctx: { ...x.ctx, shown: ease(x.ctx.shown, x.ctx.target) },
      bars: x.bars.map(b => ({ ...b, shown: ease(b.shown, b.target) })),
    }))
  } finally {
    isStepping = false
  }
}

// ------------------------------------------------------------------ brief

async function homeOf($: EngineInterface) {
  return (await $.env.get('HOME')) || (await $.env.get('USERPROFILE')) || ''
}

async function gitFacts($: EngineInterface): Promise<Pick<Facts, 'git' | 'gitNote'>> {
  try {
    const run = async (argv: string[], raw = false) => {
      const r = await $.process.run(argv, { timeoutMs: 8000 })
      return r.exitCode === 0 ? (raw ? r.stdout : r.stdout.trim()) : undefined
    }
    const branch = await run(['git', 'branch', '--show-current'])
    const head = await run(['git', 'rev-parse', '--short', 'HEAD'])
    const st = await run(['git', 'status', '--short'], true)
    if (branch === undefined && head === undefined) return { gitNote: 'not a git repository or git failed', git: undefined }
    return { git: { branch, head, status: (st ?? '').split('\n').filter(Boolean) }, gitNote: '' }
  } catch (err) {
    return { gitNote: `process.run refused: ${String(err).slice(0, 80)}`, git: undefined }
  }
}

async function writeBrief($: EngineInterface) {
  if (isWriting) return
  isWriting = true
  const setStep = (i: number, state: 'todo' | 'run' | 'done' | 'fail') =>
    setView($, v => ({ ...v, steps: v.steps.map((s, j) => (j === i ? { ...s, state } : s)) }))
  try {
    await setView($, v => ({ ...v, brief: { kind: 'writing' }, note: '', steps: initialSteps().map((s, i) => (i === 0 ? { ...s, state: 'run' } : s)) }))
    // 1. Collect state (facts, in code)
    const sessionId = await $.session.id()
    const cwd = await $.session.cwd()
    let handover: string | undefined
    try { handover = (await $.fs.read(`${cwd}/HANDOVER.md`)) as string } catch { handover = undefined }
    const g = await gitFacts($)
    const msgs = await $.session.messages()
    const rows = Array.isArray(msgs) ? msgs : []
    const prompts = rows
      .filter(m => m.role === 'user' && m.text.trim() && !m.text.startsWith('<'))
      .slice(-8).map(m => m.text.trim().replace(/\s+/g, ' ').slice(0, 220))
    const agents = toRows(await $.agent.list())
    const facts: Facts = {
      sessionId, cwd, nowIso: new Date(await $.clock.now()).toISOString(), repo: parseRepoHandover(handover),
      git: g.git, gitNote: g.gitNote, agents, prompts,
      briefPath: `${await homeOf($)}/${BRIEF_REL}/${sessionId}.md`,
    }
    await setStep(0, 'done')
    // 2. Write brief (one model call for the narrative; ids stay with code)
    await setStep(1, 'run')
    let narrative: Record<string, string> | undefined
    let why = ''
    try {
      const r = await $.model.complete({
        model: 'haiku', system: MODEL_SYSTEM, prompt: modelPrompt(condense(rows), factsBlock(facts)), maxTokens: 3000, timeoutMs: 60_000,
      })
      if (!r.isAnswered) why = `model call failed: ${r.reason}`
      else {
        narrative = parseModelReply(r.text)
        if (!narrative) why = 'model reply lacked the required headings'
      }
    } catch (err) {
      why = `model call threw: ${String(err).slice(0, 80)}`
    }
    const text = assembleBrief(facts, narrative, why)
    const path = facts.briefPath!
    await $.fs.write(path, text)
    await setView($, v => ({
      ...v, brief: { kind: 'written', path, isFactsOnly: !narrative, why: why || undefined, lines: text.split('\n').length },
      steps: v.steps.map((s, i) => (i === 1 ? { ...s, state: 'done' } : s)),
      note: narrative ? 'Brief written.' : `Brief written (facts only): ${why}`,
    }))
  } catch (err) {
    await setView($, v => ({
      ...v, brief: { kind: 'failed', reason: String(err).slice(0, 120) },
      steps: v.steps.map(s => (s.state === 'run' ? { ...s, state: 'fail' } : s)),
    }))
  } finally {
    isWriting = false
  }
}

// ------------------------------------------------------------------ guarded clear and seed

async function clearAndSeed($: EngineInterface) {
  const v = await read($, viewAtom)
  if (turnRunning) return note($, 'Refused: a turn is running. Wait for it to finish.')
  if (isWriting) return note($, 'Refused: the brief is still being written.')
  if (v.brief.kind !== 'written') return note($, 'Refused: write the brief first.')
  const id = await $.session.id()
  const fired = await $.store.get(`fired:${id}`)
  if (typeof fired === 'string' && !fired.startsWith('failed')) return note($, `Refused: this session already handed over (${fired}).`)
  const rows = toRows(await $.agent.list())
  const active = activeAgents(rows)
  const ids = active.map(a => a.id).join(',')
  const now = await $.clock.now()
  if (active.length && !(v.confirmUntil > now && v.confirmIds === ids)) {
    await setView($, x => ({
      ...x, agents: rows, confirmUntil: now + CONFIRM_MS, confirmIds: ids,
      note:
        `${active.length} agent(s) still ${[...ACTIVE].join('/')}: ${active.map(a => a.id).join(', ')}. ` +
        'It is NOT determined whether their results reach the fresh context; each agent should write its results to a file. ' +
        `Press Confirm again within ${CONFIRM_MS / 1000}s to clear anyway.`,
    }))
    return
  }
  await $.store.set(`fired:${id}`, 'clearing')
  await $.store.set('seed-pending', { old: id, path: v.brief.path, ids: active.map(a => a.id), lines: v.brief.lines ?? 0, done: false })
  await setView($, x => ({
    ...x, confirmUntil: 0, confirmIds: '', note: 'Clearing: the seed prompt follows in the fresh context.',
    steps: x.steps.map((s, i) => (i === 2 ? { ...s, state: 'run' } : s)),
  }))
  $.command.run({ command: 'clear' }).catch(async (err: unknown) => {
    await $.store.set(`fired:${id}`, `failed:${String(err).slice(0, 60)}`)
    await $.store.set('seed-pending', { old: id, done: true })
    await setView($, x => ({ ...x, note: `/clear was rejected: ${String(err).slice(0, 80)}`, steps: x.steps.map((s, i) => (i === 2 ? { ...s, state: 'fail' } : s)) }))
  })
}

// ------------------------------------------------------------------ confirmation band

async function startBand($: EngineInterface, b: BandState) {
  await $.store.set('band', b)
  bandTick?.cancel()
  await update($, bandAtom, () => 0)
  let n = 0
  bandTick = $.clock.every(FRAME_MS, () => {
    n++
    if (n >= BAND_FRAMES) { bandTick?.cancel(); bandTick = undefined } // clock stops when the fade is done
    void update($, bandAtom, () => n)
  })
}

async function endBand($: EngineInterface) {
  bandTick?.cancel()
  bandTick = undefined
  const b = (await $.store.get('band')) as BandState | undefined
  if (!b || b.cleared) return
  await $.store.set('band', { ...b, cleared: true })
  await update($, bandAtom, n => n + 1) // redraw without the band
}

// ------------------------------------------------------------------ drawing

const width = (cols: number | undefined, taken: number) => Math.max(8, Math.min(40, (cols ?? 40) - taken))

function BarRow(ui: UI, label: string, b: Bar, w: number, labelW: number, color: string, sweep?: number) {
  const { Box, Text } = ui
  const na = b.target === undefined
  const runs = barRuns(na ? 0 : b.shown, w, color, sweep)
  return (
    <Box>
      <Text>{label.padEnd(labelW).slice(0, labelW)} </Text>
      {runs.map(r => (
        <Text color={r.color} dimColor={r.dim}>{r.text}</Text>
      ))}
      <Text dimColor={na}> {b.detail}</Text>
    </Box>
  )
}

function Title(ui: UI, v: View) {
  const { Box, Text } = ui
  const anim = isAnimating(v)
  const word = 'HANDOVER'
  const p = v.frame % (word.length + 6)
  return (
    <Box>
      <Text color={anim ? 'warning' : 'success'}>{anim ? SPIN[v.frame % SPIN.length] : '◆'} </Text>
      {word.split('').map((ch, i) => (
        <Text bold color={anim && (i === p || i === p - 1) ? 'claude' : undefined} dimColor={anim && i !== p && i !== p - 1}>{ch}</Text>
      ))}
      <Text dimColor>  supervisor to fresh context</Text>
    </Box>
  )
}

function Buttons($: EngineInterface, ui: UI, v: View, now: number) {
  const { Box, Button } = ui
  const confirm = v.confirmUntil > now
  const label = confirm ? `Confirm clear (${Math.max(0, Math.ceil((v.confirmUntil - now) / 1000))}s)` : 'Clear and seed'
  return (
    <Box gap={1}>
      <Button key="refresh" label="Refresh" hotkey="r" onPress={async () => { await setView($, x => ({ ...x, confirmUntil: 0, confirmIds: '', note: 'Refreshed.' })); await refreshData($, true) }} />
      <Button key="write" label="Write brief" hotkey="w" onPress={() => writeBrief($)} />
      <Button key="clear" label={label} onPress={() => clearAndSeed($)} />
      <Button key="close" label="Close" hotkey="x" onPress={() => closeAll($)} />
    </Box>
  )
}

async function closeAll($: EngineInterface) {
  const v = await read($, viewAtom)
  stopTick()
  await setView($, x => ({ ...x, isOpen: false }))
  if (v.mode === 'pane') await $.ui.close({ id: PANE })
}

function PaneTree($: EngineInterface, ui: UI, v: View, cols: number | undefined, now: number) {
  const { Box, Text } = ui
  const w = width(cols, 30)
  const groups = [...new Set(v.bars.map(b => b.group))]
  const stepIcon = (s: string) => (s === 'done' ? '✓' : s === 'run' ? SPIN[v.frame % SPIN.length] : s === 'fail' ? '✗' : '·')
  const stepColor = (s: string) => (s === 'done' ? 'success' : s === 'run' ? 'warning' : s === 'fail' ? 'error' : 'inactive')
  const briefLine =
    v.brief.kind === 'none' ? 'not written'
      : v.brief.kind === 'writing' ? 'writing'
        : v.brief.kind === 'written' ? `written ${v.brief.path}${v.brief.isFactsOnly ? ' (facts only)' : ''}`
          : `failed ${v.brief.reason}`
  return (
    <Box flexDirection="column">
      {Title(ui, v)}
      <Text bold>CONTEXT WINDOW</Text>
      {BarRow(ui, 'context', v.ctx, w, 8, ctxColor(v.ctxPercent))}
      <Text dimColor>window {tok(v.ctxWindow)} (from usage().context.window)</Text>
      <Text bold>USAGE</Text>
      {groups.map(g => (
        <Box flexDirection="column">
          <Text dimColor>{g}</Text>
          {v.bars.filter(b => b.group === g).map(b => BarRow(ui, b.label, b, w, 12, b.key.startsWith('rl:') ? ctxColor((b.target ?? 0) * 100) : 'suggestion'))}
        </Box>
      ))}
      {!groups.length && <Text dimColor>n/a (usage not read yet)</Text>}
      <Text>cost: {v.costUsd === undefined ? 'n/a' : `$${v.costUsd.toFixed(2)}`}</Text>
      <Text bold>AGENTS ({v.agents.length})</Text>
      {v.agents.length === 0 && <Text dimColor>none listed</Text>}
      {v.agents.slice(0, 8).map(a => (
        <Box>
          <Text color={statusColor(a.status)}>● </Text>
          <Text>{shortId(a.id)} {(a.name || a.type).slice(0, 16).padEnd(16)} </Text>
          <Text color={statusColor(a.status)}>{a.status.padEnd(9)}</Text>
          <Text dimColor> {a.description.slice(0, Math.max(0, (cols ?? 40) - 40))}</Text>
        </Box>
      ))}
      {v.agents.length > 8 && <Text dimColor>+{v.agents.length - 8} more</Text>}
      <Text bold>HANDING OVER</Text>
      {v.steps.map(s =>
        BarRow(ui, `${stepIcon(s.state)} ${s.label}`, { key: s.label, label: s.label, group: 's', shown: s.state === 'done' ? 1 : 0, target: s.state === 'done' ? 1 : 0, detail: s.state }, Math.max(8, w - 8), 24, stepColor(s.state), s.state === 'run' ? v.frame : undefined),
      )}
      <Text>STATE: <Text color={v.brief.kind === 'failed' ? 'error' : v.brief.kind === 'written' ? 'success' : 'warning'}>{briefLine}</Text></Text>
      {Buttons($, ui, v, now)}
      {v.note !== '' && <Text color={v.confirmUntil > now ? 'warning' : undefined}>{v.note}</Text>}
    </Box>
  )
}

function BandTree($: EngineInterface, ui: UI, v: View, cols: number | undefined, now: number) {
  const { Box, Text } = ui
  const anim = isAnimating(v)
  const runs = barRuns(v.ctx.shown, 10, ctxColor(v.ctxPercent), anim ? v.frame : undefined)
  const act = activeAgents(v.agents).length
  return (
    <Box flexDirection="column">
      <Box>
        <Text color={anim ? 'warning' : 'success'}>{anim ? SPIN[v.frame % SPIN.length] : '◆'} handover </Text>
        {runs.map(r => <Text color={r.color} dimColor={r.dim}>{r.text}</Text>)}
        <Text> {v.ctx.detail}  agents {act}/{v.agents.length} active  brief {v.brief.kind}</Text>
      </Box>
      {Buttons($, ui, v, now)}
      {v.note !== '' && <Text>{v.note}</Text>}
    </Box>
  )
}

// ------------------------------------------------------------------ register

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    await $.command.register({ name: 'handover', description: 'Hand the supervisor role to a fresh context (pane with bars, agents, brief)' })
    return next(e)
  })

  on('command.run', { command: 'handover' }, async $ => {
    const opened = await $.ui.open({ id: PANE, title: 'Handover', focus: true, closeOnEscape: true })
    let mode: 'pane' | 'band' = 'pane'
    if (!opened.isPlaced) {
      mode = 'band'
      isClosingForBand = true
      try { await $.ui.close({ id: PANE }) } finally { isClosingForBand = false }
    }
    await setView($, v => ({ ...v, isOpen: true, mode, note: '' }))
    await refreshData($, true)
    startTick($)
    return { text: mode === 'pane' ? 'Handover pane opened.' : 'Pane not placed at this width; showing the handover band above the prompt.' }
  })

  on('ui.close', async ($, e, next) => {
    if (e.id === PANE && !isClosingForBand) {
      stopTick()
      await setView($, v => ({ ...v, isOpen: false }))
    }
    return next(e)
  }).catch(($, e, next) => (next.called ? undefined : next(e)))

  on('turn.start', async ($, e, next) => {
    if (!e.agentId) turnRunning = true
    return next(e)
  })
  on('turn.complete', async ($, e, next) => {
    if (!e.agentId) turnRunning = false
    return next(e)
  })

  on('ui.render', { component: 'Pane', requestId: 'handover' }, async ($, e) => {
    const ui = $.ui.resolve(e)
    const v = await read($, viewAtom)
    return PaneTree($, ui, v, e.props.bodyColumns, await $.clock.now())
  })

  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    const frame = await read($, bandAtom)
    const b = (await $.store.get('band')) as BandState | undefined
    if (b && !b.cleared && !e.props.hasSurvey) {
      const { Box, Text } = $.ui.resolve(e)
      const done = frame >= BAND_FRAMES
      return (
        <Box>
          <Text color="success" dimColor={!done}>{bandReveal(bandText(b), frame)}</Text>
        </Box>
      )
    }
    const v = await read($, viewAtom)
    if (!v.isOpen || v.mode !== 'band' || e.props.hasSurvey) return next(e)
    return BandTree($, $.ui.resolve(e), v, e.props.bodyColumns, await $.clock.now())
  })

  // After /clear: seed the fresh context with one line pointing at the brief, then confirm visibly.
  on('classic.SessionStart', async ($, e, next) => {
    const r = await next(e)
    if (e.source !== 'clear') return r
    const p = (await $.store.get('seed-pending')) as { old: string; path?: string; ids?: string[]; lines?: number; done: boolean } | undefined
    if (!p || p.done || !p.path) return r
    await $.store.set('seed-pending', { ...p, done: true })
    const fresh = await $.session.id()
    await $.store.set(`fired:${p.old}`, `seeded:${fresh}`)
    const ids = p.ids ?? []
    const lines = p.lines ?? 0
    // the old pane's third step turns done (the pane may be gone: setView only writes the atom)
    await setView($, v => ({ ...v, note: `Seeded ${shortId(fresh)} from ${shortId(p.old)}.`, steps: v.steps.map((s, i) => (i === 2 ? { ...s, state: 'done' } : s)) }))
    $.prompt.submit({ text: seedText(p.old, p.path, ids) }).catch(async () => {
      await note($, `Seed prompt rejected: paste the brief path to carry on: ${p.path}`)
    })
    $.ui.toast(toastText(lines, ids.length))
    await startBand($, { old: p.old, lines, agents: ids.length, cleared: false })
    return r
  }).catch(($, e, next) => next(e))

  // The band stays until the person's first prompt (the plugin's own seed is not one).
  on('prompt.submit', async ($, e, next) => {
    const kind = (e as { origin?: { kind?: string } }).origin?.kind
    if (kind === 'composer' || kind === 'bridge') await endBand($)
    return next(e)
  }).catch(($, e, next) => (next.called ? undefined : next(e)))
}
