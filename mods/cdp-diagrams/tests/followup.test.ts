import { describe, expect, test } from 'claude-code/testing'

import { DENY, DiagramFollowUp, followUpPrompt, type Submit } from '../hooks/followup.ts'

const words = (s: string) => s.split(/\s+/).filter(Boolean).length

describe('followUpPrompt', () => {
  test('flowchart only', () => {
    const p = followUpPrompt(['flowchart'])
    expect(p).toBe(
      'Draw your previous answer as a ```mermaid flowchart block. Use only facts already in that answer and the CDP results above it; use no tools. Label each edge with the file:line that performs it (a call, assignment or transition, never a declaration); dash inferred edges (`-.->`). No prose beyond one line per diagram, ending "+N not shown: ..." when items are left out.',
    )
    expect(p).not.toContain('stateDiagram')
    expect(words(p)).toBeLessThanOrEqual(80)
  })

  test('state only', () => {
    const p = followUpPrompt(['state'])
    expect(p).toContain('a ```mermaid stateDiagram-v2 block.')
    expect(p).toContain('"(inferred)"')
    expect(p).not.toContain('flowchart')
    expect(p).not.toContain('-.->')
    expect(words(p)).toBeLessThanOrEqual(80)
  })

  test('both, in the order chosen, duplicates dropped', () => {
    const p = followUpPrompt(['flowchart', 'state', 'flowchart'])
    expect(p).toContain('a ```mermaid flowchart block, then a ```mermaid stateDiagram-v2 block.')
    expect(p).toContain('dash inferred edges (`-.->`); end inferred transition labels with "(inferred)".')
    expect(followUpPrompt(['state', 'flowchart'])).toContain('stateDiagram-v2 block, then a ```mermaid flowchart')
    expect(words(p)).toBeLessThanOrEqual(80)
  })

  test('no kinds is a caller error', () => {
    expect(() => followUpPrompt([])).toThrow()
  })
})

describe('DiagramFollowUp', () => {
  const choice = { kinds: ['flowchart' as const] }

  test('the flag is set and M2 told before the one submit; the next main turn is the follow-up', async () => {
    const f = new DiagramFollowUp()
    const order: string[] = []
    const texts: string[] = []
    const submit: Submit = async text => {
      order.push(`submit denies=${f.denies({}) !== null}`)
      texts.push(text)
      return { text }
    }
    expect(f.denies({})).toBeNull()
    expect(await f.begin(choice, 'a1', 'Stores: Handler.cs:40', submit, () => order.push('before'))).toBe(true)
    expect(order).toEqual(['before', 'submit denies=true'])
    expect(texts).toEqual([followUpPrompt(['flowchart'])])
    f.start({ agentId: 'sub', turnId: 's1' })
    f.start({ turnId: 'f1' })
    expect(f.isDiagramTurn('f1')).toBe(true)
    expect(f.isDiagramTurn('s1')).toBe(false)
    expect(f.diagramFor('f1')).toEqual({ answerTurnId: 'a1', answer: 'Stores: Handler.cs:40', kinds: ['flowchart'] })
    expect(f.diagramFor('a1')).toBeNull()
  })

  test('main-loop tools denied during the follow-up only; subagent calls pass', async () => {
    const f = new DiagramFollowUp()
    await f.begin(choice, 'a1', 'x', async t => ({ text: t }))
    f.start({ turnId: 'f1' })
    expect(f.denies({})).toBe(DENY)
    expect(f.denies({ agentId: 'sub' })).toBeNull()
    f.complete({ agentId: 'sub' })
    expect(f.denies({})).toBe(DENY)
    f.complete({})
    expect(f.denies({})).toBeNull()
    f.start({ turnId: 't2' })
    expect(f.isDiagramTurn('t2')).toBe(false)
    expect(f.isDiagramTurn('f1')).toBe(true)
  })

  test('cleared at the end whatever the reason (errored or aborted turn: complete is reason-blind)', async () => {
    const f = new DiagramFollowUp()
    await f.begin(choice, 'a1', 'x', async t => ({ text: t }))
    f.start({ turnId: 'f1' })
    f.complete({})
    expect(f.busy()).toBe(false)
  })

  test('a rejected submit clears the flag and undoes the M2 mark; never rejects', async () => {
    const f = new DiagramFollowUp()
    let undone = 0
    const ok = await f.begin(choice, 'a1', 'x', async () => { throw new Error('busy') }, () => {}, () => undone++)
    expect(ok).toBe(false)
    expect(undone).toBe(1)
    expect(f.denies({})).toBeNull()
    f.start({ turnId: 't2' })
    expect(f.isDiagramTurn('t2')).toBe(false)
  })

  test('a dropped submit clears the flag and undoes the M2 mark', async () => {
    const f = new DiagramFollowUp()
    let undone = 0
    expect(await f.begin(choice, 'a1', 'x', async () => ({ drop: 'no' }), () => {}, () => undone++)).toBe(false)
    expect(undone).toBe(1)
    expect(f.busy()).toBe(false)
  })

  test('one follow-up at a time', async () => {
    const f = new DiagramFollowUp()
    let calls = 0
    const submit: Submit = async t => (calls++, { text: t })
    await f.begin(choice, 'a1', 'x', submit)
    expect(await f.begin(choice, 'a2', 'y', submit)).toBe(false)
    expect(calls).toBe(1)
  })
})

// Through the engine: Yes + kinds on the two asks, then the plugin's one
// $.prompt.submit reaches the test's prompt.submit hook; the test plays the
// follow-up turn's events and its tool calls.

type Hooks = Parameters<Parameters<typeof test>[1]>[1]
type Engine = Parameters<Parameters<typeof test>[1]>[0]
type Question = { question: string; options: { label: string }[] }

/** Lets the ask chain and the submit (a drop settles a macrotask later) run. */
async function flush() {
  for (let i = 0; i < 80; i++) await Promise.resolve()
  await new Promise(r => setTimeout(r, 0))
}

/** Engine stand-in: answers asks in turn, records submits (or drops them), says ok to other tools. */
function engine(on: Hooks, answers: string[], o: { drop?: boolean } = {}) {
  const asks: string[] = []
  const submits: string[] = []
  on('tool.call', ($, e) => {
    if (e.tool !== 'AskUserQuestion') return { result: { stdout: 'ok', stderr: '', interrupted: false } } as never
    const questions = (e as unknown as { questions: Question[] }).questions
    asks.push(questions[0]!.question)
    const a = answers.shift()
    if (a === undefined) return { deny: 'dismissed' } as never
    return { result: { questions, answers: { [questions[0]!.question]: a } } } as never
  })
  on('prompt.submit', ($, e) => {
    submits.push(e.text)
    return (o.drop ? { drop: 'blocked' } : { text: e.text }) as never
  })
  on('turn.start', ($, e) => ({ turnId: e.turnId }))
  on('turn.complete', ($, e) => ({ text: e.answer }))
  on('ui.log', () => ({ value: undefined }) as never)
  return { asks, submits }
}

async function cdpTurn($: Engine, turnId: string) {
  await $.turn.start({ text: 'how are stores created?', turnId })
  await $.tool.call({ tool: 'Bash', command: 'cdp query symbol Store', description: 'q' } as never)
  await $.turn.complete({ turnId, reason: 'answer', isAborted: false, answer: 'Stores: Handler.cs:40', durationMs: 5 } as never)
  await flush()
}

const bash = ($: Engine, agentId?: string) =>
  $.tool.call({ tool: 'Bash', command: 'ls', description: 'l', ...(agentId ? { agentId } : {}) } as never) as Promise<Record<string, unknown>>

const denied = (r: Record<string, unknown>) => String(r.deny ?? (r.isError ? r.text : '')).includes('no tools')

describe('engine follow-up', () => {
  for (const [label, kinds] of [
    ['Flowchart', ['flowchart']],
    ['State machine', ['state']],
    ['Flowchart, State machine', ['flowchart', 'state']],
  ] as const) {
    test(`${label}: one submit with that prompt`, async ($, on) => {
      const s = engine(on, ['Yes', label])
      await cdpTurn($, `a-${label}`)
      expect(s.submits).toEqual([followUpPrompt(kinds)])
    })
  }

  test('tools allowed before, denied on the main loop during, allowed after; no second offer', async ($, on) => {
    const s = engine(on, ['Yes', 'Flowchart', 'No'])
    expect(denied(await bash($))).toBe(false)
    await cdpTurn($, 'a1')
    expect(s.submits.length).toBe(1)
    expect(s.asks.length).toBe(2)
    await $.turn.start({ text: s.submits[0]!, turnId: 'f1' })
    expect(denied(await bash($))).toBe(true)
    expect(denied(await bash($, 'sub1'))).toBe(false)
    await $.tool.call({ tool: 'Bash', command: 'cdp query symbol Store', description: 'q' } as never)
    await $.turn.complete({ turnId: 'f1', reason: 'answer', isAborted: false, answer: '```mermaid\nflowchart TD\nA-->B\n```', durationMs: 5 } as never)
    await flush()
    expect(s.asks.length).toBe(2)
    expect(s.submits.length).toBe(1)
    expect(denied(await bash($))).toBe(false)
    // the next CDP answer is offered again
    await cdpTurn($, 'a2')
    expect(s.asks.length).toBe(3)
  })

  test('an errored or aborted follow-up clears the flag', async ($, on) => {
    const s = engine(on, ['Yes', 'Flowchart', 'Yes', 'Flowchart'])
    for (const [i, reason] of (['error', 'aborted'] as const).entries()) {
      await cdpTurn($, `a-${reason}`)
      expect(s.submits.length).toBe(i + 1)
      await $.turn.start({ text: s.submits[i]!, turnId: `f-${reason}` })
      expect(denied(await bash($))).toBe(true)
      await $.turn.complete({ turnId: `f-${reason}`, reason, isAborted: reason === 'aborted', answer: '', durationMs: 1 } as never)
      expect(denied(await bash($))).toBe(false)
    }
  })

  test('No or a dismissal submits nothing', async ($, on) => {
    const s = engine(on, ['No'])
    await cdpTurn($, 'a-no')
    await cdpTurn($, 'a-dismiss')
    expect(s.asks.length).toBe(2)
    expect(s.submits).toEqual([])
    expect(denied(await bash($))).toBe(false)
  })

  test('a dropped submit leaves tools allowed and the next CDP answer offered', async ($, on) => {
    const s = engine(on, ['Yes', 'Flowchart', 'No'], { drop: true })
    await cdpTurn($, 'a1')
    expect(s.submits.length).toBe(1)
    expect(denied(await bash($))).toBe(false)
    await cdpTurn($, 'a2')
    expect(s.asks.length).toBe(3)
  })
})
