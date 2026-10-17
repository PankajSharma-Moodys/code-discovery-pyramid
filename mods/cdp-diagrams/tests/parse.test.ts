import { describe, expect, test } from 'claude-code/testing'

import { parseMermaid, splitBlocks } from '../hooks/mermaid.ts'
import { prepare } from '../hooks/render.ts'
import { problems } from './check.ts'
import { FIXTURES } from './fixtures.ts'

describe('parse', () => {
  test('flowchart: |label| edges, <br/> labels, db nodes, dashed edges', () => {
    const g = parseMermaid(FIXTURES.request_chain!)
    expect(g.kind).toBe('flowchart')
    expect(g.direction).toBe('TD')
    expect(g.nodes.length).toBe(9)
    expect(g.edges.length).toBe(8)
    const a = g.nodes.find(n => n.id === 'A')!
    expect(a.label).toEqual(['POST /v2/orders/{id}/items', 'OrderResource#addItem'])
    expect(g.nodes.find(n => n.id === 'E')!.shape).toBe('db')
    expect(g.edges[0]).toEqual({ from: 'A', to: 'B', label: 'OrderResource.java:120', dashed: false, arrow: true })
    expect(g.edges[3]!.label).toBe('@Entity @Table ItemEntity.java:9')
    expect(g.edges.filter(e => e.dashed).length).toBe(3)
  })

  test('flowchart: "-- label -->" and "-. label .->" forms; ; inside a quoted label', () => {
    const g = parseMermaid(FIXTURES.create_db_decls!)
    expect(g.nodes.length).toBe(6)
    expect(g.nodes.find(n => n.id === 'T')!.label).toEqual(['table Stores', 'DbContext.cs:486; Initial.cs:40'])
    expect(g.edges[0]).toEqual({ from: 'C', to: 'H1', label: 'v4/StoreController.cs:79', dashed: false, arrow: true })
    expect(g.edges[4]).toEqual({ from: 'H2', to: 'X', label: 'on exception, Handler.cs:317', dashed: true, arrow: true })
  })

  test('flowchart LR, shapes, an open link', () => {
    const g = parseMermaid(FIXTURES.left_right!)
    expect(g.direction).toBe('LR')
    expect(g.nodes.find(n => n.id === 'B')!.shape).toBe('diamond')
    expect(g.nodes.find(n => n.id === 'E')!.shape).toBe('round')
    expect(g.edges[3]).toEqual({ from: 'C', to: 'E', label: '', dashed: false, arrow: false })
  })

  test('flowchart: a self-loop and A-->B with no spaces', () => {
    expect(parseMermaid(FIXTURES.event_fanout!).edges.some(e => e.from === 'C' && e.to === 'C')).toBe(true)
    const g = parseMermaid('graph LR\nA-->B;B-.->C')
    expect(g.edges.map(e => `${e.from}${e.to}${e.dashed}`)).toEqual(['ABfalse', 'BCtrue'])
  })

  test('state: [*] start and end, labels after the colon', () => {
    const g = parseMermaid(FIXTURES.job_states!)
    expect(g.kind).toBe('state')
    expect(g.nodes.some(n => n.shape === 'start')).toBe(true)
    expect(g.nodes.some(n => n.shape === 'end')).toBe(true)
    expect(g.edges[0]!.label).toBe('initial (JobStatus.scala:5)')
    expect(g.edges.length).toBe(15)
  })

  test('state: composite states and notes', () => {
    const g = parseMermaid(FIXTURES.instance_states!)
    const idle = g.nodes.find(n => n.id === 'Idle')!
    expect(idle.label).toEqual(['Idle', 'in Warm_pool'])
    const enter = g.edges.find(e => e.to === 'Idle' && e.from === 'Warm_pool')!
    expect(enter.dashed).toBe(true)
    expect(parseMermaid(FIXTURES.instance_states_note!).notes).toEqual([
      'Broken: Broken and Retiring slots are never leased (SlotPool.kt:45-46)',
    ])
  })

  test('unsupported input says why', () => {
    expect(() => parseMermaid('sequenceDiagram\nA->>B: hi')).toThrow(/unsupported diagram type "sequenceDiagram"/)
    expect(() => parseMermaid('flowchart TD\nA --> B ]]] ???')).toThrow(/unexpected text|expected/)
    expect(() => parseMermaid('stateDiagram-v2\nstate X {\nX --> Y')).toThrow(/never closed/)
  })

  test('splitBlocks keeps the text around a closed fence; an unclosed fence stays text', () => {
    const md = 'Intro\n\n```mermaid\nflowchart TD\nA-->B\n```\n\nOutro'
    const blocks = splitBlocks(md)
    expect(blocks.map(b => b.kind)).toEqual(['text', 'mermaid', 'text'])
    expect(splitBlocks('x\n```mermaid\nflowchart TD\nA-->B\n').map(b => b.kind)).toEqual(['text'])
  })
})

describe('layout', () => {
  for (const [name, source] of Object.entries(FIXTURES)) {
    test(`${name}: terminal at 120 and 100 columns, and SVG`, () => {
      expect(problems(source, 120)).toEqual([])
      expect(problems(source, 100)).toEqual([])
      expect(problems(source, null)).toEqual([])
    })
  }

  test('a diagram wider than the terminal falls back with the width it needs', () => {
    const p = prepare(FIXTURES.event_fanout!, 30)
    expect(p.ok).toBe(false)
    if (!p.ok) expect(p.reason).toMatch(/too wide: needs \d+ columns, 30 available/)
  })

  test('a graph past the node limit falls back as too large', () => {
    const lines = Array.from({ length: 70 }, (_, i) => `  N${i} --> N${i + 1}`)
    const p = prepare(`flowchart TD\n${lines.join('\n')}`, 200)
    expect(p.ok).toBe(false)
    if (!p.ok) expect(p.reason).toMatch(/too large to draw: 71 nodes/)
  })

  test('dashed edges draw dashed and citations are in the legend', () => {
    const p = prepare(FIXTURES.create_db_decls!, 120)
    expect(p.ok).toBe(true)
    if (!p.ok) return
    expect(p.lines!.join('\n')).toMatch(/╌|╎/)
    expect(p.layout.legend.map(r => r.text)).toContain('on exception, Handler.cs:317')
  })
})
