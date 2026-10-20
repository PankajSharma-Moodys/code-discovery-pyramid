// Parser for the Mermaid subset Claude writes in answers: flowchart/graph
// (TD/TB/LR) and stateDiagram(-v2). Anything outside the subset throws
// ParseError with a reason the caller shows beside the raw block.

export type Shape = 'rect' | 'round' | 'db' | 'diamond' | 'start' | 'end'
export type GNode = { id: string; label: string[]; shape: Shape }
export type GEdge = { from: string; to: string; label: string; dashed: boolean; arrow: boolean }
export type Graph = {
  kind: 'flowchart' | 'state'
  direction: 'TD' | 'LR'
  nodes: GNode[]
  edges: GEdge[]
  notes: string[]
}

export class ParseError extends Error {}

export type Block = { kind: 'text'; text: string } | { kind: 'mermaid'; source: string; raw: string }

const FENCE = /^ {0,3}(```|~~~)[ \t]*mermaid[^\n]*\n([\s\S]*?)^ {0,3}\1[ \t]*$/gm

/** Splits markdown into text and closed ```mermaid blocks (an unclosed fence stays text). */
export function splitBlocks(md: string): Block[] {
  const out: Block[] = []
  let at = 0
  for (const m of md.matchAll(FENCE)) {
    const start = m.index ?? 0
    if (start > at) out.push({ kind: 'text', text: md.slice(at, start) })
    out.push({ kind: 'mermaid', source: m[2] ?? '', raw: m[0] })
    at = start + m[0].length
  }
  if (at < md.length) out.push({ kind: 'text', text: md.slice(at) })
  return out
}

export function hasMermaid(md: string): boolean {
  FENCE.lastIndex = 0
  const found = FENCE.test(md)
  FENCE.lastIndex = 0
  return found
}

function decode(s: string): string {
  return s
    .replace(/#quot;/g, '"')
    .replace(/&quot;/g, '"')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&amp;/g, '&')
    .replace(/#(\d+);/g, (_, n: string) => String.fromCharCode(Number(n)))
}

const BR = /<br\s*\/?>|\\n/gi

function unquote(s: string): string {
  const t = s.trim()
  return t.length >= 2 && t.startsWith('"') && t.endsWith('"') ? t.slice(1, -1) : t
}

function labelLines(s: string): string[] {
  return decode(unquote(s))
    .split(BR)
    .map(x => x.trim())
    .filter(x => x.length > 0)
}

function edgeLabel(s: string): string {
  return decode(unquote(s)).replace(BR, ' ').replace(/\s+/g, ' ').trim()
}

/** A file:line citation: `orders.py:24`, `shop/orders.py:24`, `Job.scala:39-45`. */
const CITE = /(?:[\w.\-]+\/)*[\w\-]+(?:\.[\w\-]+)*\.[A-Za-z]\w*:\d+(?:[-–]\d+)?/g

/**
 * Splits an edge label into what happens (`charge(order)`) and the file:line
 * citations that say where (`orders.py:23`): `charge(order) · orders.py:23`,
 * `success: orders.py:24`, `initial (Job.scala:5)` and a bare `orders.py:22`.
 */
export function splitLabel(label: string): { action: string; cites: string[] } {
  const cites = label.match(CITE) ?? []
  // Parentheses that only held citations go with them: `initial (Job.scala:5)`.
  let a = label.replace(CITE, '\u0000')
  a = a.replace(/\(\s*\u0000(?:\s*[,;]\s*\u0000)*\s*\)/g, ' ').replace(/\u0000/g, ' ').replace(/\s+/g, ' ')
  // A separator left before another, a note in parentheses, or the end goes:
  // `return order · orders.py:28 (inferred)` reads `return order (inferred)`.
  a = a.replace(/\s*[·•]\s*(?=[·•,;]|$)/g, '').replace(/\s*[·•]\s*(?=\()/g, ' ')
  a = a.replace(/^[\s·•,;:|\-–—]+|[\s·•,;:|(@\-–—]+$/g, '')
  return { action: a, cites: [...cites] }
}

/** `s` cut to `n` characters with an ellipsis. */
export function shorten(s: string, n: number): string {
  const cs = [...s]
  if (cs.length <= n) return s
  if (n <= 1) return '…'
  return cs.slice(0, n - 1).join('').trimEnd() + '…'
}

class Builder {
  nodes = new Map<string, GNode>()
  explicit = new Set<string>()
  edges: GEdge[] = []
  notes: string[] = []

  node(id: string, label?: string[], shape?: Shape): GNode {
    let n = this.nodes.get(id)
    if (!n) {
      n = { id, label: [id], shape: shape ?? 'rect' }
      this.nodes.set(id, n)
    }
    if (label && label.length > 0 && !this.explicit.has(id)) {
      n.label = label
      this.explicit.add(id)
    }
    if (shape) n.shape = shape
    return n
  }

  graph(kind: Graph['kind'], direction: Graph['direction']): Graph {
    return { kind, direction, nodes: [...this.nodes.values()], edges: this.edges, notes: this.notes }
  }
}

function stripComment(line: string): string {
  return /^\s*%%/.test(line) ? '' : line
}

export function parseMermaid(src: string): Graph {
  const lines = src.replace(/\r/g, '').split('\n').map(stripComment)
  const first = lines.findIndex(l => l.trim() !== '')
  if (first < 0) throw new ParseError('empty diagram')
  const header = (lines[first] ?? '').trim()
  const rest = lines.slice(first + 1)
  const fc = /^(flowchart|graph)\s*(TD|TB|LR|RL|BT)?\s*;?$/i.exec(header)
  if (fc) return parseFlowchart(rest, (fc[2] ?? 'TD').toUpperCase())
  if (/^stateDiagram(-v2)?\s*$/.test(header)) return parseState(rest)
  throw new ParseError(`unsupported diagram type "${header.split(/\s/)[0]}"`)
}

// ---------------------------------------------------------------- flowchart

const SHAPES: [string, string, Shape][] = [
  ['([', '])', 'round'],
  ['[(', ')]', 'db'],
  ['((', '))', 'round'],
  ['[[', ']]', 'rect'],
  ['{{', '}}', 'diamond'],
  ['[/', '/]', 'rect'],
  ['[\\', '\\]', 'rect'],
  ['[/', '\\]', 'rect'],
  ['[\\', '/]', 'rect'],
  ['>', ']', 'rect'],
  ['[', ']', 'rect'],
  ['(', ')', 'round'],
  ['{', '}', 'diamond'],
]

const ID = /[A-Za-z0-9_][A-Za-z0-9_\-]*/y

class Cursor {
  s: string
  i = 0
  constructor(s: string) {
    this.s = s
  }
  ws() {
    while (this.i < this.s.length && /\s/.test(this.s[this.i] ?? '')) this.i++
  }
  done() {
    this.ws()
    return this.i >= this.s.length
  }
  peek(t: string) {
    return this.s.startsWith(t, this.i)
  }
  re(r: RegExp): RegExpExecArray | null {
    r.lastIndex = this.i
    const m = r.exec(this.s)
    if (m) this.i = r.lastIndex
    return m
  }
  fail(what: string): never {
    throw new ParseError(`${what} at "${this.s.slice(this.i, this.i + 24)}"`)
  }
}

function readNode(c: Cursor, b: Builder): string {
  c.ws()
  // An id must not swallow a link that follows it with no space (A-->B).
  const save = c.i
  const m = c.re(ID)
  if (!m) c.fail('expected a node id')
  let id = m[0]
  const link = /(-{2,}|-\.|={2,})/.exec(id)
  if (link) {
    id = id.slice(0, link.index)
  }
  id = id.replace(/-+$/, '')
  if (id.length !== m[0].length) {
    c.i = save + id.length
    if (!id) c.fail('expected a node id')
  }
  for (const [open, close, shape] of SHAPES) {
    if (!c.peek(open)) continue
    const from = c.i + open.length
    let end: number
    if (c.s[from] === '"') {
      const q = c.s.indexOf('"', from + 1)
      if (q < 0) c.fail('unclosed quote')
      end = c.s.indexOf(close, q + 1)
    } else {
      end = c.s.indexOf(close, from)
    }
    if (end < 0) continue
    b.node(id, labelLines(c.s.slice(from, end)), shape)
    c.i = end + close.length
    c.re(/:::[A-Za-z0-9_\-]+/y)
    return id
  }
  c.re(/:::[A-Za-z0-9_\-]+/y)
  b.node(id)
  return id
}

function readNodes(c: Cursor, b: Builder): string[] {
  const ids = [readNode(c, b)]
  for (;;) {
    c.ws()
    if (!c.peek('&')) return ids
    c.i++
    ids.push(readNode(c, b))
  }
}

type Link = { label: string; dashed: boolean; arrow: boolean }

function readLink(c: Cursor): Link | null {
  c.ws()
  // Text form: A -- text --> B, A -. text .-> B, A == text ==> B
  const open = c.re(/(<?)(--|==|-\.)(?![-=.>]|[ox](?![A-Za-z0-9_]))/y)
  if (open) {
    const dashed = open[2] === '-.'
    const closeRe = dashed ? /\.-+(>?)/g : open[2] === '==' ? /={2,}(>?)/g : /-{2,}(>?)/g
    c.ws()
    let label: string
    if (c.peek('"')) {
      const q = c.s.indexOf('"', c.i + 1)
      if (q < 0) c.fail('unclosed quote')
      label = c.s.slice(c.i, q + 1)
      c.i = q + 1
      c.ws()
      closeRe.lastIndex = c.i
      const m = closeRe.exec(c.s)
      if (!m || m.index !== c.i) c.fail('expected link end')
      c.i = closeRe.lastIndex
      return { label: edgeLabel(label), dashed, arrow: m[1] === '>' }
    }
    closeRe.lastIndex = c.i
    const m = closeRe.exec(c.s)
    if (!m) c.fail('expected link end')
    label = c.s.slice(c.i, m.index)
    c.i = closeRe.lastIndex
    return { label: edgeLabel(label), dashed, arrow: m[1] === '>' }
  }
  const m = c.re(/(<?)(-{2,}|={2,}|-\.+-)(>?)/y)
  if (!m) return null
  if (/^[ox]/.test(c.s[c.i] ?? '') && !/[A-Za-z0-9_]/.test(c.s[c.i + 1] ?? '')) c.i++
  const link: Link = { label: '', dashed: m[2]?.includes('.') ?? false, arrow: m[3] === '>' }
  c.ws()
  if (c.peek('|')) {
    const end = c.s.indexOf('|', c.i + 1)
    if (end < 0) c.fail('unclosed |label|')
    link.label = edgeLabel(c.s.slice(c.i + 1, end))
    c.i = end + 1
  }
  return link
}

const FC_SKIP = /^(classDef|class|style|linkStyle|click|direction|accTitle|accDescr)\b/

function parseFlowchart(lines: string[], dir: string): Graph {
  const b = new Builder()
  let depth = 0
  for (const raw of lines) {
    const line = raw.trim()
    if (!line || FC_SKIP.test(line)) continue
    if (/^subgraph\b/.test(line)) {
      depth++
      continue
    }
    if (/^end\s*;?$/.test(line)) {
      if (depth === 0) throw new ParseError('"end" with no open subgraph')
      depth--
      continue
    }
    const c = new Cursor(line)
    while (!c.done()) {
      let from = readNodes(c, b)
      for (;;) {
        const link = readLink(c)
        if (!link) break
        const to = readNodes(c, b)
        for (const f of from) for (const t of to) b.edges.push({ from: f, to: t, ...link })
        from = to
      }
      c.ws()
      if (c.peek(';')) c.i++
      else if (!c.done()) c.fail('unexpected text')
    }
  }
  if (b.nodes.size === 0) throw new ParseError('no nodes')
  return b.graph('flowchart', dir === 'LR' || dir === 'RL' ? 'LR' : 'TD')
}

// ---------------------------------------------------------------- state

function parseState(lines: string[]): Graph {
  const b = new Builder()
  const scopes: string[] = []
  let direction: Graph['direction'] = 'TD'
  let noteOpen: string | null = null
  const ref = (id: string, asSource: boolean): { id: string; dashed: boolean; extra: string } => {
    if (id !== '[*]') return { id, dashed: false, extra: '' }
    const scope = scopes[scopes.length - 1]
    if (scope) return { id: scope, dashed: true, extra: asSource ? `enters ${scope}` : `leaves ${scope}` }
    const nid = asSource ? '[*]start' : '[*]end'
    b.node(nid, [asSource ? '●' : '◉'], asSource ? 'start' : 'end')
    return { id: nid, dashed: false, extra: '' }
  }
  const declare = (id: string) => {
    const n = b.node(id)
    if (n.shape === 'rect') n.shape = 'round'
    const scope = scopes[scopes.length - 1]
    if (scope && !b.explicit.has(id) && n.label.length === 1) n.label = [id, `in ${scope}`]
    return n
  }
  for (const raw of lines) {
    const line = raw.trim()
    if (noteOpen !== null) {
      if (/^end\s+note$/.test(line)) {
        b.notes.push(noteOpen)
        noteOpen = null
      } else if (line) noteOpen += (noteOpen.endsWith(': ') ? '' : ' ') + line
      continue
    }
    if (!line || /^(classDef|class|accTitle|accDescr)\b/.test(line) || line === '--') continue
    let m: RegExpExecArray | null
    if ((m = /^direction\s+(LR|RL|TB|TD|BT)$/.exec(line))) {
      if (scopes.length === 0) direction = m[1] === 'LR' || m[1] === 'RL' ? 'LR' : 'TD'
      continue
    }
    if ((m = /^note\s+(left|right)\s+of\s+(\S+)\s*:\s*(.*)$/.exec(line))) {
      b.notes.push(`${m[2]}: ${decode(m[3] ?? '')}`)
      continue
    }
    if ((m = /^note\s+(left|right)\s+of\s+(\S+)\s*$/.exec(line))) {
      noteOpen = `${m[2]}: `
      continue
    }
    if (line === '}') {
      if (!scopes.pop()) throw new ParseError('"}" with no open state')
      continue
    }
    if ((m = /^state\s+"([^"]*)"\s+as\s+([A-Za-z0-9_\-.]+)\s*(\{)?$/.exec(line))) {
      const n = declare(m[2] ?? '')
      n.label = labelLines(m[1] ?? '')
      b.explicit.add(n.id)
      if (m[3]) scopes.push(n.id)
      continue
    }
    if ((m = /^state\s+([A-Za-z0-9_\-.]+)\s*(<<\w+>>)?\s*(\{)?$/.exec(line))) {
      const n = declare(m[1] ?? '')
      if (m[2]) n.shape = 'diamond'
      if (m[3]) scopes.push(n.id)
      continue
    }
    if ((m = /^(\S+?)\s*-->\s*(\S+?)\s*(?::\s*(.*))?$/.exec(line))) {
      const a = ref(m[1] ?? '', true)
      const z = ref(m[2] ?? '', false)
      if (a.id === m[1]) declare(a.id)
      if (z.id === m[2]) declare(z.id)
      const text = [a.extra, z.extra, edgeLabel(m[3] ?? '')].filter(Boolean).join('; ')
      b.edges.push({ from: a.id, to: z.id, label: text, dashed: a.dashed || z.dashed, arrow: true })
      continue
    }
    if ((m = /^([A-Za-z0-9_\-.]+)\s*:\s*(.+)$/.exec(line))) {
      const n = declare(m[1] ?? '')
      const extra = labelLines(m[2] ?? '')
      n.label = b.explicit.has(n.id) ? [...n.label, ...extra] : [n.id, ...extra]
      b.explicit.add(n.id)
      continue
    }
    if ((m = /^([A-Za-z0-9_\-.]+)$/.exec(line))) {
      declare(m[1] ?? '')
      continue
    }
    throw new ParseError(`unsupported state line "${line.slice(0, 40)}"`)
  }
  if (scopes.length) throw new ParseError(`state ${scopes[scopes.length - 1]} is never closed`)
  if (b.nodes.size === 0) throw new ParseError('no states')
  return b.graph('state', direction)
}
