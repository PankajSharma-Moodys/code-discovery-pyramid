import { describe, expect, test } from 'claude-code/testing'

import { canPlaceAbove, DiagramPlacement, norm, POINTER } from '../hooks/placement.ts'
import { verifySettled } from '../hooks/register.tsx'
import { FLOW_SRC, FLOW_STDOUT } from './fixtures/verify-samples.ts'

const ANSWER = 'Stores are created by CreateStoreHandler (Handler.cs:40), then saved.'
const REPLY = 'The flow:\n\n```mermaid\n' + FLOW_SRC + '```\n'
const FULL = { columns: 120, rows: 40, isFullscreen: true }
const MAIN = { columns: 120, rows: 40, isFullscreen: false }
const UNKNOWN = { columns: 120, rows: 40 }

describe('DiagramPlacement', () => {
  test('the mode: terminal with isFullscreen true only', () => {
    expect(canPlaceAbove('terminal', FULL)).toBe(true)
    expect(canPlaceAbove('terminal', MAIN)).toBe(false)
    expect(canPlaceAbove('terminal', UNKNOWN)).toBe(false)
    expect(canPlaceAbove('terminal', undefined)).toBe(false)
    expect(canPlaceAbove('desktop', FULL)).toBe(false)
  })

  test('handshake: reply seen, then answer claims, then the reply points', () => {
    const p = new DiagramPlacement()
    p.count(ANSWER)
    p.count(REPLY)
    expect(p.complete(ANSWER, REPLY)).toBe(true)
    // the answer row first: the reply not yet seen, so it stays as it is
    expect(p.answerRow(ANSWER, 'terminal', true)).toBeNull()
    expect(p.replyRow(REPLY, 'terminal', true)).toEqual({ row: { kind: 'draw' }, changed: true })
    expect(p.answerRow('  ' + ANSWER.replace(/ /g, '\n') + '\n', 'terminal', true)).toEqual({ reply: REPLY, changed: true })
    expect(p.answerRow(ANSWER, 'terminal', true)).toEqual({ reply: REPLY, changed: false })
    expect(p.replyRow(REPLY, 'terminal', true)).toEqual({ row: { kind: 'pointer' }, changed: false })
    // another surface keeps its own fallback
    expect(p.replyRow(REPLY, 'desktop', false)).toEqual({ row: { kind: 'draw' }, changed: false })
    expect(p.answerRow(ANSWER, 'desktop', false)).toBeNull()
    expect(p.replyRow('unrelated', 'terminal', true)).toBeNull()
  })

  test('an answer seen twice is ambiguous: no placement, and a placed one falls back', () => {
    const p = new DiagramPlacement()
    p.count(ANSWER)
    p.count(ANSWER)
    p.complete(ANSWER, REPLY)
    expect(p.replyRow(REPLY, 'terminal', true)?.row).toEqual({ kind: 'draw' })
    expect(p.answerRow(ANSWER, 'terminal', true)).toBeNull()

    const q = new DiagramPlacement()
    q.count(ANSWER)
    q.complete(ANSWER, REPLY)
    q.replyRow(REPLY, 'terminal', true)
    expect(q.answerRow(ANSWER, 'terminal', true)?.changed).toBe(true)
    expect(q.replyRow(REPLY, 'terminal', true)?.row).toEqual({ kind: 'pointer' })
    expect(q.count(ANSWER)).toBe(true)
    expect(q.answerRow(ANSWER, 'terminal', true)).toBeNull()
    expect(q.replyRow(REPLY, 'terminal', true)?.row).toEqual({ kind: 'draw' })
  })

  test('empty or identical texts record nothing', () => {
    const p = new DiagramPlacement()
    expect(p.complete('', REPLY)).toBe(false)
    expect(p.complete(REPLY, '  ' + REPLY)).toBe(false)
    expect(norm(' a \n\n b ')).toBe('a b')
  })
})

// Through the engine: a CDP answer, Yes + Flowchart, the follow-up turn's
// reply, then both rows mounted as the transcript draws them.

type Hooks = Parameters<Parameters<typeof test>[1]>[1]
type Engine = Parameters<Parameters<typeof test>[1]>[0]
type Question = { question: string; options: { label: string }[] }

async function flush() {
  for (let i = 0; i < 80; i++) await Promise.resolve()
  await new Promise(r => setTimeout(r, 0))
}

function engine(on: Hooks, answers: string[]) {
  const submits: string[] = []
  on('tool.call', ($, e) => {
    if (e.tool !== 'AskUserQuestion') return { result: { stdout: 'ok', stderr: '', interrupted: false } } as never
    const questions = (e as unknown as { questions: Question[] }).questions
    const a = answers.shift()
    if (a === undefined) return { deny: 'dismissed' } as never
    return { result: { questions, answers: { [questions[0]!.question]: a } } } as never
  })
  on('prompt.submit', ($, e) => {
    submits.push(e.text)
    return { text: e.text } as never
  })
  on('turn.start', ($, e) => ({ turnId: e.turnId }))
  on('turn.complete', ($, e) => ({ text: e.answer }))
  on('ui.log', () => ({ value: undefined }) as never)
  // the engine's own drawing of a row: its text, as it was
  on('ui.render', { component: 'AssistantMessage' }, ($, e) => {
    const { Markdown } = $.ui.resolve(e)
    return <Markdown key="engine" text={e.props.text} />
  })
  on('session.cwd', () => ({ value: '/repo' }) as never)
  on('process.run', ($, e) => {
    const argv = (e as unknown as { argv: string[] }).argv
    if (argv[0] === 'git') return { value: { exitCode: 0, stdout: '/repo\n', stderr: '' } } as never
    return { value: { exitCode: 3, stdout: FLOW_STDOUT, stderr: '' } } as never
  })
  return { submits }
}

const done = (turnId: string, answer: string) =>
  ({ turnId, reason: 'answer', isAborted: false, answer, durationMs: 5 }) as never

/** A CDP answer, the offer taken, and the follow-up turn ending with `reply`. */
async function diagramTurn($: Engine, on: Hooks, answer = ANSWER, reply = REPLY, before = async () => {}) {
  const s = engine(on, ['Yes', 'Flowchart'])
  await before()
  await $.turn.start({ text: 'how are stores created?', turnId: 'a1' })
  await $.tool.call({ tool: 'Bash', command: 'cdp query symbol Store', description: 'q' } as never)
  await $.turn.complete(done('a1', answer))
  await flush()
  expect(s.submits.length).toBe(1)
  await $.turn.start({ text: s.submits[0]!, turnId: 'f1' })
  await $.turn.complete(done('f1', reply))
  await flush()
}

const row = (text: string) => ({ text, isFirstOfReply: true })

/** Mounts the answer row then the reply row on `surface` at `viewport`; returns both. */
async function rows($: Engine, surface: 'terminal' | 'desktop', viewport: object, answer = ANSWER, reply = REPLY, replyFirst = false) {
  const mount = (text: string) => $.ui.mount({ plugin: 'cdp-diagrams', surface, component: 'AssistantMessage', props: row(text), viewport })
  const r0 = replyFirst ? await mount(reply) : null
  const a = await mount(answer)
  const r = r0 ?? (await mount(reply))
  await verifySettled()
  await flush()
  return { a, r }
}

const DIAGRAM = { type: 'Text', text: /flowchart TD · \d+ nodes/ } as const
const BADGES = { type: 'Text', text: /verified \d+\/\d+ edges/ } as const

describe('placement through the engine', () => {
  for (const replyFirst of [false, true])
    test(`fullscreen (${replyFirst ? 'reply' : 'answer'} row drawn first): the diagram, badged, is drawn above the answer row; the reply row is one pointer`, async ($, on) => {
      await diagramTurn($, on)
      const { a, r } = await rows($, 'terminal', FULL, ANSWER, REPLY, replyFirst)
      // the handshake settles without the engine drawing either row again
      expect(await a.findAll(DIAGRAM)).toHaveLength(1)
      expect(await r.findAll(DIAGRAM)).toHaveLength(0)
      await a.redraw()
      await r.redraw()
      expect(await a.findAll(DIAGRAM)).toHaveLength(1)
      expect(await a.find(BADGES)).toBeDefined()
      expect(await r.findAll(DIAGRAM)).toHaveLength(0)
      expect(await r.drawn()).toMatchObject({ type: 'Text', children: [POINTER] })
      expect(await r.findAll({ type: 'Markdown' })).toHaveLength(0)
      // the diagram comes first, the answer text after it, unchanged
      const tree = JSON.stringify(await a.drawn())
      expect(tree.indexOf('flowchart TD ·')).toBeGreaterThanOrEqual(0)
      expect(tree.indexOf('flowchart TD ·')).toBeLessThan(tree.indexOf(ANSWER.slice(0, 20)))
      expect(await a.find({ type: 'Markdown', key: 'engine', text: ANSWER })).toBeDefined()
      await a.unmount()
      await r.unmount()
    })

  test('main screen, unknown mode and desktop: drawn in the reply row only, answer row untouched', async ($, on) => {
    await diagramTurn($, on)
    for (const [surface, viewport] of [['terminal', MAIN], ['terminal', UNKNOWN], ['desktop', FULL]] as const) {
      const { a, r } = await rows($, surface, viewport)
      await a.redraw()
      await r.redraw()
      expect(await a.findAll(DIAGRAM)).toHaveLength(0)
      expect(JSON.stringify(await a.drawn())).not.toContain('diagram of this answer')
      expect(await r.findAll(DIAGRAM)).toHaveLength(1)
      expect(await r.find(BADGES)).toBeDefined()
      expect(await r.find({ type: 'Text', text: POINTER })).toBeUndefined()
      expect(await a.find({ type: 'Markdown', key: 'engine', text: ANSWER })).toBeDefined()
      await a.unmount()
      await r.unmount()
    }
  })

  test('no answer row matches: the reply row keeps the drawing', async ($, on) => {
    await diagramTurn($, on)
    const { a, r } = await rows($, 'terminal', FULL, 'A different answer with Handler.cs:40.')
    await a.redraw()
    await r.redraw()
    expect(await a.findAll(DIAGRAM)).toHaveLength(0)
    expect(await r.findAll(DIAGRAM)).toHaveLength(1)
  })

  test('an answer given twice (several rows match): fallback in the reply row', async ($, on) => {
    await diagramTurn($, on, ANSWER, REPLY, async () => {
      await $.turn.start({ text: 'earlier', turnId: 'a0' })
      await $.turn.complete(done('a0', ANSWER))
    })
    const { a, r } = await rows($, 'terminal', FULL)
    await a.redraw()
    await r.redraw()
    expect(await a.findAll(DIAGRAM)).toHaveLength(0)
    expect(await r.findAll(DIAGRAM)).toHaveLength(1)
  })

  test('a row that is neither answer nor reply is left to the engine', async ($, on) => {
    await diagramTurn($, on)
    await rows($, 'terminal', FULL)
    const other = await $.ui.mount({ plugin: 'cdp-diagrams', surface: 'terminal', component: 'AssistantMessage', props: row('Plain other text.'), viewport: FULL })
    expect(await other.drawn()).toMatchObject({ type: 'Markdown', props: { key: 'engine', text: 'Plain other text.' } })
  })
})
