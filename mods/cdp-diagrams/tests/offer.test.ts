import { describe, expect, test } from 'claude-code/testing'

import { type Ask, askChoice, DiagramOffer, parseKinds, type TurnEnd } from '../hooks/offer.ts'

/** An `ask` that answers each screen in turn (an Error rejects) and records the questions. */
function scripted(...answers: (string | Error)[]) {
  const asked: { question: string; options: unknown }[] = []
  const ask: Ask = async (question, options) => {
    asked.push({ question, options })
    const a = answers.shift()
    if (a === undefined || a instanceof Error) throw a ?? new Error('no answer')
    return a
  }
  return { ask, asked }
}

const end = (over: Partial<TurnEnd> = {}): TurnEnd => ({
  turnId: 't1',
  reason: 'answer',
  isAborted: false,
  answer: 'Stores are created by CreateStoreHandler (Handler.cs:40).',
  ...over,
})

describe('parseKinds', () => {
  test('known labels, comma-space joined, in any order', () => {
    expect(parseKinds('Flowchart, State machine')).toEqual({ kinds: ['flowchart', 'state'] })
    expect(parseKinds('State machine')).toEqual({ kinds: ['state'] })
    expect(parseKinds('Flowchart')).toEqual({ kinds: ['flowchart'] })
  })

  test('typed text, near-misses and an empty selection are no diagram', () => {
    for (const a of ['', 'Other', 'draw it please', 'flowchart', 'Flowchart,State machine', ' Flowchart', 'toString'])
      expect({ a, c: parseKinds(a) }).toEqual({ a, c: null })
  })
})

describe('askChoice', () => {
  test('Yes then both kinds', async () => {
    const s = scripted('Yes', 'Flowchart, State machine')
    expect(await askChoice(s.ask)).toEqual({ kinds: ['flowchart', 'state'] })
    expect(s.asked).toEqual([
      { question: 'Draw a diagram of that answer?', options: ['Yes', 'No'] },
      { question: 'Which diagrams?', options: { options: ['Flowchart', 'State machine'], multiSelect: true, header: 'Diagram' } },
    ])
  })

  test('Yes then one kind', async () => {
    expect(await askChoice(scripted('Yes', 'State machine').ask)).toEqual({ kinds: ['state'] })
  })

  test('Yes then none is no diagram', async () => {
    expect(await askChoice(scripted('Yes', '').ask)).toBeNull()
  })

  test('No asks nothing more', async () => {
    const s = scripted('No', 'Flowchart')
    expect(await askChoice(s.ask)).toBeNull()
    expect(s.asked.length).toBe(1)
  })

  test('text typed under Other, on either screen, is no diagram', async () => {
    expect(await askChoice(scripted('yes please').ask)).toBeNull()
    expect(await askChoice(scripted('Yes', 'a sequence diagram').ask)).toBeNull()
  })

  test('a rejected ask (dismissed, or a -p run) is a silent No', async () => {
    expect(await askChoice(scripted(new Error('no one to ask')).ask)).toBeNull()
    expect(await askChoice(scripted('Yes', new Error('dismissed')).ask)).toBeNull()
  })
})

describe('DiagramOffer', () => {
  test('a CDP answer is offered and the choice is stored and handed on', async () => {
    const o = new DiagramOffer()
    const seen: unknown[] = []
    o.onChoice = (c, a) => seen.push([c, a])
    const s = scripted('Yes', 'Flowchart')
    expect(o.maybeOffer(end(), true, s.ask)).toBe(true)
    await o.idle()
    expect(o.pending()).toEqual({ kinds: ['flowchart'] })
    expect(seen).toEqual([[{ kinds: ['flowchart'] }, end().answer]])
    expect(o.take()).toEqual({ kinds: ['flowchart'] })
    expect(o.pending()).toBeNull()
  })

  test('errored, aborted, refused or empty answers are not offered', () => {
    const o = new DiagramOffer()
    const { ask, asked } = scripted()
    expect(o.maybeOffer(end({ reason: 'error' }), true, ask)).toBe(false)
    expect(o.maybeOffer(end({ reason: 'aborted', isAborted: true }), true, ask)).toBe(false)
    expect(o.maybeOffer(end({ reason: 'refusal' }), true, ask)).toBe(false)
    expect(o.maybeOffer(end({ answer: '  ' }), true, ask)).toBe(false)
    expect(asked.length).toBe(0)
  })

  test('a turn that did not use CDP is not offered', () => {
    const o = new DiagramOffer()
    expect(o.maybeOffer(end(), false, scripted('Yes').ask)).toBe(false)
  })

  test("a subagent's turn is not offered", () => {
    const o = new DiagramOffer()
    expect(o.maybeOffer(end({ agentId: 'a1' }), true, scripted('Yes').ask)).toBe(false)
  })

  test('one offer per turn, and none while one is still open', async () => {
    const o = new DiagramOffer()
    let release: (v: string) => void = () => {}
    const slow: Ask = () => new Promise(r => (release = r))
    expect(o.maybeOffer(end(), true, slow)).toBe(true)
    expect(o.maybeOffer(end({ turnId: 't2' }), true, scripted('Yes').ask)).toBe(false)
    release('No')
    await o.idle()
    expect(o.maybeOffer(end(), true, scripted('Yes').ask)).toBe(false)
    expect(o.maybeOffer(end({ turnId: 't3' }), true, scripted('No').ask)).toBe(true)
  })

  test("the mod's own follow-up turn is not offered; the turn after it is", async () => {
    const o = new DiagramOffer()
    o.expectFollowUp()
    // a subagent's end inside the follow-up does not use up the mark
    expect(o.maybeOffer(end({ agentId: 'a1' }), true, scripted().ask)).toBe(false)
    expect(o.maybeOffer(end({ turnId: 'f1' }), true, scripted('Yes').ask)).toBe(false)
    expect(o.maybeOffer(end({ turnId: 't2' }), true, scripted('No').ask)).toBe(true)
  })
})

// Through the engine: the plugin's turn.complete hook opens $.ui.ask, an
// AskUserQuestion tool.call the test's own hook answers. The engine loads its
// own copy of the module, so these tests see the asks, not the stored choice
// (that and the follow-up guard are covered on DiagramOffer above).

type Engine = Parameters<Parameters<typeof test>[1]>[0]
type Hooks = Parameters<Parameters<typeof test>[1]>[1]
type Question = { question: string; header: string; multiSelect: boolean; options: { label: string }[] }

/** Lets unawaited work (the ask chain) run; long enough for both screens, see the first test. */
async function flush() {
  for (let i = 0; i < 50; i++) await Promise.resolve()
}

/** Answers each AskUserQuestion in turn (null denies it, so ui.ask rejects); other tools say ok. */
function answering(on: Hooks, answers: (string | null)[]) {
  const asks: Question[] = []
  on('tool.call', ($, e) => {
    if (e.tool !== 'AskUserQuestion') return { result: { stdout: 'ok', stderr: '', interrupted: false } } as never
    const questions = (e as unknown as { questions: Question[] }).questions
    asks.push(questions[0]!)
    const a = answers.shift()
    if (a === null || a === undefined) return { deny: 'dismissed' } as never
    return { result: { questions, answers: { [questions[0]!.question]: a } } } as never
  })
  on('turn.start', ($, e) => ({ turnId: e.turnId }))
  on('turn.complete', ($, e) => ({ text: e.answer }))
  on('ui.log', () => ({ value: undefined }) as never)
  return asks
}

async function turn(
  $: Engine,
  turnId: string,
  o: { agentId?: string; reason?: 'answer' | 'error' | 'aborted'; tool?: string; command?: string } = {},
) {
  const loop = o.agentId ? { agentId: o.agentId } : {}
  await $.turn.start({ text: 'how are stores created?', turnId })
  await $.tool.call({ tool: o.tool ?? 'Bash', command: o.command ?? 'cdp query symbol Store', description: 'q' } as never)
  const reason = o.reason ?? 'answer'
  const r = await $.turn.complete({ turnId, reason, isAborted: reason === 'aborted', answer: 'Stores: Handler.cs:40', durationMs: 5, ...loop } as never)
  await flush()
  return r
}

describe('engine', () => {
  test('Yes: after the answer, screen 1 then the multi-select screen 2', async ($, on) => {
    const asks = answering(on, ['Yes', 'Flowchart, State machine'])
    const r = await turn($, 'e-yes')
    expect(r.text).toBe('Stores: Handler.cs:40')
    expect(asks.map(q => [q.question, q.multiSelect, q.options.map(x => x.label)])).toEqual([
      ['Draw a diagram of that answer?', false, ['Yes', 'No']],
      ['Which diagrams?', true, ['Flowchart', 'State machine']],
    ])
    expect(asks[1]!.header).toBe('Diagram')
  })

  test('No: only screen 1', async ($, on) => {
    const asks = answering(on, ['No'])
    await turn($, 'e-no')
    expect(asks.length).toBe(1)
  })

  test('a dismissed ask is a silent No and the turn still ends with its answer', async ($, on) => {
    const asks = answering(on, [null])
    const r = await turn($, 'e-dismissed')
    expect(r.text).toBe('Stores: Handler.cs:40')
    expect(asks.length).toBe(1)
  })

  test('errored and aborted turns are not offered', async ($, on) => {
    const asks = answering(on, ['Yes', 'Flowchart'])
    await turn($, 'e-err', { reason: 'error' })
    await turn($, 'e-abort', { reason: 'aborted' })
    expect(asks.length).toBe(0)
  })

  test('a turn without CDP is not offered', async ($, on) => {
    const asks = answering(on, ['Yes', 'Flowchart'])
    await turn($, 'e-plain', { command: 'grep -rn cdp src/' })
    expect(asks.length).toBe(0)
  })

  test("a subagent's turn end is not offered", async ($, on) => {
    const asks = answering(on, ['Yes', 'Flowchart'])
    await turn($, 'e-sub', { agentId: 'a1' })
    expect(asks.length).toBe(0)
  })

  test('the same turn ending twice is offered once', async ($, on) => {
    const asks = answering(on, ['No', 'No'])
    await turn($, 'e-twice')
    await turn($, 'e-twice')
    expect(asks.length).toBe(1)
  })
})
