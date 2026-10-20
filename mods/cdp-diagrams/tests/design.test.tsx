import { describe, expect, test } from 'claude-code/testing'

import { layoutGraph, marker } from '../hooks/layout.ts'
import { parseMermaid, shorten, splitLabel } from '../hooks/mermaid.ts'
import { edgeStyle, legendTable, plain, prepare, styledRows } from '../hooks/render.ts'
import { matchEdges, parseVerdict } from '../hooks/verify.ts'
import { FIXTURES } from './fixtures.ts'
import { ACTION_SRC, ACTION_STDOUT, FLOW_SRC, FLOW_STDOUT } from './fixtures/verify-samples.ts'

// The follow-up's label form, on the place_order shape seen live in I4.
const PLACE = `flowchart TD
  A(["place_order"]) -->|"Order(...) · orders.py:22"| B["order"]
  F -->|"return order · orders.py:28"| G(["return order"])
  B -->|"charge(order) · orders.py:23"| C{"charged?"}
  C -->|"status = CANCELLED · orders.py:27"| F["CANCELLED"]
  E -->|"return order · orders.py:28"| G
  C -->|"status = PAID · orders.py:24"| D["PAID"]
  D -->|"ship(order) · orders.py:25"| E["shipping.ship"]`

const STATE = `stateDiagram-v2
  SHIPPED --> [*]: return order · orders.py:28
  [*] --> NEW: Order() · orders.py:18
  PAID --> SHIPPED: ship(order) · shipping.py:6
  NEW --> PAID: charge ok · orders.py:24
  NEW --> CANCELLED: charge failed · orders.py:27
  CANCELLED --> [*]: return order · orders.py:28`

describe('label and cite', () => {
  test('"action · file:line" and the older forms split into what happens and where', () => {
    expect(splitLabel('charge(order) · orders.py:23')).toEqual({ action: 'charge(order)', cites: ['orders.py:23'] })
    expect(splitLabel('status = PAID · shop/orders.py:24')).toEqual({ action: 'status = PAID', cites: ['shop/orders.py:24'] })
    expect(splitLabel('Order() · orders.py:18')).toEqual({ action: 'Order()', cites: ['orders.py:18'] })
    expect(splitLabel('success: orders.py:24')).toEqual({ action: 'success', cites: ['orders.py:24'] })
    expect(splitLabel('orders.py:22')).toEqual({ action: '', cites: ['orders.py:22'] })
    expect(splitLabel('initial (JobStatus.scala:5)')).toEqual({ action: 'initial', cites: ['JobStatus.scala:5'] })
    expect(splitLabel('on exception, Handler.cs:317')).toEqual({ action: 'on exception', cites: ['Handler.cs:317'] })
    expect(splitLabel('existing key: return early, ItemService.java:61-62')).toEqual({
      action: 'existing key: return early',
      cites: ['ItemService.java:61-62'],
    })
    // seen live: the cite before a "(inferred)" the prompt asks for
    expect(splitLabel('return order · orders.py:28 (inferred)')).toEqual({ action: 'return order (inferred)', cites: ['orders.py:28'] })
    expect(splitLabel('findDue (worker, not traced)')).toEqual({ action: 'findDue (worker, not traced)', cites: [] })
  })

  test('the drawing carries the action on the edge, the legend the action and the cite', () => {
    const p = prepare(PLACE, 120)
    if (!p.ok) throw new Error(p.reason)
    const canvas = p.lines!.join('\n')
    for (const a of ['charge(order)', 'status = PAID', 'ship(order)']) expect(canvas).toContain(a)
    expect(canvas).not.toContain('orders.py')
    const rows = legendTable(p.layout.legend, p.unplaced, () => undefined, 120).map(plain)
    expect(rows[0]).toMatch(/^# │ edge +│ cite$/)
    expect(rows).toContain('② │ charge(order)      │ orders.py:23')
  })
})

describe('numbering', () => {
  for (const [name, src] of [['flowchart', PLACE], ['state', STATE], ...Object.entries(FIXTURES)] as const)
    test(`${name}: markers follow the drawing (rank, then across), and the legend reads in that order`, () => {
      const p = prepare(src, 120)
      if (!p.ok) throw new Error(p.reason)
      const td = p.layout.direction === 'TD'
      const box = new Map(p.layout.boxes.map(b => [b.id, b]))
      const key = (id: string) => {
        const b = box.get(id)!
        return td ? [b.y, b.x] : [b.x, b.y]
      }
      const keys = p.layout.legend.map(r => [...key(r.fromId), ...key(p.graph.edges[r.edge]!.to)])
      for (let i = 1; i < keys.length; i++) {
        const [a, b] = [keys[i - 1]!, keys[i]!]
        const j = a.findIndex((x, k) => x !== b[k])
        if (j >= 0) expect(a[j]!).toBeLessThan(b[j]!)
      }
      expect(p.layout.legend.map(r => r.tag)).toEqual(p.layout.legend.map((_, i) => marker(i + 1, p.layout.legend.length)))
    })

  test('place_order: 1..7 down the picture, whatever the source order', () => {
    const p = prepare(PLACE, 120)
    if (!p.ok) throw new Error(p.reason)
    // The source lists the edges out of order; CANCELLED is drawn left of
    // PAID (it is declared first), so its branch and its return come first.
    const at = (id: string) => p.layout.boxes.find(b => b.id === id)!
    expect(at('F').x).toBeLessThan(at('D').x)
    expect(p.layout.legend.map(r => `${r.tag} ${r.action}`)).toEqual([
      '① Order(...)',
      '② charge(order)',
      '③ status = CANCELLED',
      '④ status = PAID',
      '⑤ return order',
      '⑥ ship(order)',
      '⑦ return order',
    ])
    const s = prepare(STATE, 120)
    if (!s.ok) throw new Error(s.reason)
    expect(s.layout.legend.map(r => r.action)).toEqual(['Order()', 'charge ok', 'charge failed', 'ship(order)', 'return order', 'return order'])
  })

  test('circled markers up to twenty, [n] for every edge past that', () => {
    expect(marker(1, 20)).toBe('①')
    expect(marker(20, 20)).toBe('⑳')
    expect(marker(1, 21)).toBe('[1]')
    const lines = Array.from({ length: 22 }, (_, i) => `  N${i} -->|step ${i} · a.py:${i + 1}| N${i + 1}`)
    const p = prepare(`flowchart TD\n${lines.join('\n')}`, 200)
    if (!p.ok) throw new Error(p.reason)
    expect(p.layout.legend.map(r => r.tag).slice(0, 2)).toEqual(['[1]', '[2]'])
    expect(p.lines!.join('\n')).toContain('[22]')
  })
})

describe('wrapping', () => {
  test('a long action wraps beside the edge, never cut; the legend has it whole', () => {
    const src = 'flowchart TD\n  A -->|"validateAndPersistOrderLines(order) · orders.py:40"| B'
    const p = prepare(src, 120)
    if (!p.ok) throw new Error(p.reason)
    const text = p.lines!.join('\n')
    expect(text).toContain('① validateAndPersist')
    expect(text).toContain('OrderLines(order)')
    expect(text).not.toContain('…')
    expect(legendTable(p.layout.legend, p.unplaced, () => undefined, 120).map(plain)[2]).toContain('validateAndPersistOrderLines(order)')
  })

  test('a narrow legend wraps its cells instead of cutting them', () => {
    const src = 'flowchart TD\n  A -->|"validateAndPersistOrderLines(order) · shop/orders/OrderService.py:40"| B'
    const p = prepare(src, 120)
    if (!p.ok) throw new Error(p.reason)
    const rows = legendTable(p.layout.legend, p.unplaced, () => undefined, 40).map(plain)
    expect(rows.every(r => [...r].length <= 40)).toBe(true)
    expect(rows.join('')).not.toContain('…')
    expect(rows.slice(2).map(r => r.split(' │ ')[1]!.trim()).join('')).toBe('validateAndPersistOrderLines(order)')
  })

  test('decisions read as questions; branches take their outcome', () => {
    const p = prepare('flowchart TD\n  A --> D{charge result}\n  D -->|"ok → ship · a.py:1"| S[ship]\n  D -->|"fail → mark FAILED · a.py:2"| F[failed]', 120)
    if (!p.ok) throw new Error(p.reason)
    expect(p.lines!.join('\n')).toContain('charge result?')
    expect(p.layout.routes.map(r => r.outcome)).toEqual([null, 'ok', 'fail'])
    expect(p.layout.boxes.find(b => b.id === 'F')!.outcome).toBe('fail')
  })

  test('with no room for the action, the edge keeps its marker and the legend names it', () => {
    const g = parseMermaid(PLACE)
    const l = layoutGraph(g, { boxWidth: 14, labelWidth: 0 })
    expect(l.routes.every(r => r.labelLines === null)).toBe(true)
    const p = prepare(PLACE, 120)
    if (!p.ok) throw new Error(p.reason)
    // a squeezed terminal: actions shrink, then only markers are drawn
    const narrow = prepare(PLACE, 46)
    if (!narrow.ok) throw new Error(narrow.reason)
    const canvas = narrow.lines!.join('\n')
    for (const r of narrow.layout.legend) if (!narrow.unplaced.has(r.tag)) expect(canvas).toContain(r.tag)
    expect(canvas).not.toContain('status = CANCELLED')
    const rows = legendTable(narrow.layout.legend, narrow.unplaced, () => undefined, 46).map(plain)
    expect(rows.some(r => r.includes('status = CANCELLED'))).toBe(true)
  })
})

describe('verdict colours', () => {
  test('edges green when correct, red when wrong, yellow when unverified, dim when inferred', () => {
    expect(edgeStyle('correct', false)).toEqual({ color: 'success' })
    expect(edgeStyle('wrong_citation', false)).toEqual({ color: 'error' })
    for (const s of ['unsupported', 'ambiguous', 'uncited'] as const) expect(edgeStyle(s, false)).toEqual({ color: 'warning' })
    expect(edgeStyle('inferred', true)).toEqual({ dimColor: true })
    expect(edgeStyle(undefined, true)).toEqual({ dimColor: true })
  })

  test("the checker's statuses colour each edge's cells and its legend row", () => {
    const p = prepare(FLOW_SRC, 120)
    if (!p.ok) throw new Error(p.reason)
    const matched = matchEdges(p.graph, parseVerdict(FLOW_STDOUT, 3)!)
    const rows = styledRows(p, e => matched[e]?.status, e => p.graph.edges[e]!.dashed)
    const colours = new Set(rows.flat().map(r => r.style?.color).filter(Boolean))
    for (const c of ['success', 'error', 'warning']) expect(colours.has(c)).toBe(true)
    expect(rows.flat().some(r => r.style?.dimColor && /╌|╎/.test(r.text))).toBe(true)
    const legend = legendTable(p.layout.legend, p.unplaced, e => matched[e], 120)
    const wrong = legend.find(r => plain(r).includes('summarize'))!
    expect(plain(wrong)).toMatch(/✗ wrong · try verify_diagram\.py:44$/)
    expect(wrong.some(r => r.style?.color === 'error' && r.text.includes('✗'))).toBe(true)
  })

  test('the "action · file:line" form still matches the checker\'s edges (real output)', () => {
    const g = parseMermaid(ACTION_SRC)
    const v = parseVerdict(ACTION_STDOUT, 3)!
    const m = matchEdges(g, v)
    expect(m.every(Boolean)).toBe(true)
    expect(m.map(e => e!.status)).toEqual(['correct', 'correct', 'correct', 'unsupported', 'correct', 'correct'])
  })
})

describe('80 columns', () => {
  const at80 = { columns: 80, rows: 50 }
  for (const [name, src] of [['flowchart', PLACE], ['state', STATE], ...Object.entries(FIXTURES)] as const)
    test(`${name}: every drawn row and legend row fits an 80-column terminal`, async $ => {
      const text = '```mermaid\n' + src + '\n```\nOne line about it.\n'
      const ui = await $.ui.mount({ plugin: 'cdp-diagrams', surface: 'terminal', component: 'AssistantMessage', props: { text, isFirstOfReply: true }, viewport: at80 })
      const drawn = (await ui.findAll({ type: 'Text' })).filter(t => t.props.wrap === 'truncate-end')
      if (name === 'flowchart' || name === 'state') {
        expect(drawn.length).toBeGreaterThan(10)
        expect(await ui.find({ type: 'Text', text: /One line about it/ })).toBeDefined()
      }
      if (!(await ui.find({ type: 'Text', text: /not drawn/ }))) for (const t of drawn) expect([...t.text].length).toBeLessThanOrEqual(76)
      await ui.unmount()
    })
})
