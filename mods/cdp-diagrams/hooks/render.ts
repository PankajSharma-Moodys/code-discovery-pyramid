// Turns a Layout into terminal lines (box-drawing characters) or an SVG
// document, and decides when a block is shown raw instead (and why).

import { layoutGraph, LIMITS, TooLarge, type Layout, type LegendRow, type PlacedBox, type Pt } from './layout.ts'
import { parseMermaid, ParseError, type Graph } from './mermaid.ts'

export type Prepared =
  | { ok: true; graph: Graph; layout: Layout; lines: string[] | null; unplaced: Set<string> }
  | { ok: false; reason: string }

/**
 * Parses and lays out one mermaid source. `maxColumns` bounds the terminal
 * drawing; `null` asks for the SVG layout (no column bound, no text canvas).
 */
export function prepare(source: string, maxColumns: number | null): Prepared {
  let graph: Graph
  try {
    graph = parseMermaid(source)
  } catch (err) {
    if (err instanceof ParseError) return { ok: false, reason: `could not parse it: ${err.message}` }
    throw err
  }
  let narrowest = Infinity
  try {
    for (const boxWidth of [24, 18, 14, 10]) {
      for (const compact of [false, true]) {
        const layout = layoutGraph(graph, { boxWidth, compact })
        if (maxColumns === null) {
          if (layout.width > 400) return { ok: false, reason: `too wide to draw (${layout.width} cells)` }
          return { ok: true, graph, layout, lines: null, unplaced: new Set() }
        }
        narrowest = Math.min(narrowest, layout.width)
        if (layout.width <= maxColumns) {
          const { lines, unplaced } = drawText(layout)
          return { ok: true, graph, layout, lines, unplaced }
        }
      }
    }
  } catch (err) {
    if (err instanceof TooLarge) return { ok: false, reason: `too large to draw: ${err.message}` }
    throw err
  }
  return { ok: false, reason: `too wide: needs ${narrowest} columns, ${maxColumns} available` }
}

// ---------------------------------------------------------------- text

const U = 1
const D = 2
const L = 4
const R = 8
const SOLID: Record<number, string> = {
  [U]: '│', [D]: '│', [U | D]: '│', [L]: '─', [R]: '─', [L | R]: '─',
  [D | R]: '┌', [D | L]: '┐', [U | R]: '└', [U | L]: '┘',
  [U | D | R]: '├', [U | D | L]: '┤', [L | R | D]: '┬', [L | R | U]: '┴', [U | D | L | R]: '┼',
}
const DASHED: Record<number, string> = { [U]: '╎', [D]: '╎', [U | D]: '╎', [L]: '╌', [R]: '╌', [L | R]: '╌' }

const BORDERS: Record<string, string> = {
  rect: '┌┐└┘─│',
  round: '╭╮╰╯─│',
  db: '╔╗╚╝═║',
  diamond: '╱╲╲╱─│',
}

class Canvas {
  fixed: (string | null)[]
  mask: number[]
  dash: boolean[]
  w: number
  h: number
  constructor(w: number, h: number) {
    this.w = w
    this.h = h
    this.fixed = new Array(w * h).fill(null)
    this.mask = new Array(w * h).fill(0)
    this.dash = new Array(w * h).fill(false)
  }
  inside(x: number, y: number) {
    return x >= 0 && y >= 0 && x < this.w && y < this.h
  }
  put(x: number, y: number, s: string) {
    for (let i = 0; i < s.length; i++) if (this.inside(x + i, y)) this.fixed[y * this.w + x + i] = s[i]!
  }
  free(x: number, y: number) {
    return this.inside(x, y) && this.fixed[y * this.w + x] === null && this.mask[y * this.w + x] === 0
  }
  link(x: number, y: number, bits: number, dashed: boolean) {
    if (!this.inside(x, y)) return
    const i = y * this.w + x
    this.mask[i]! |= bits
    if (dashed) this.dash[i] = true
  }
  lines(): string[] {
    const out: string[] = []
    for (let y = 0; y < this.h; y++) {
      let row = ''
      for (let x = 0; x < this.w; x++) {
        const i = y * this.w + x
        const m = this.mask[i]!
        row += this.fixed[i] ?? (m ? ((this.dash[i] ? DASHED[m] : undefined) ?? SOLID[m] ?? '┼') : ' ')
      }
      out.push(row.replace(/\s+$/, ''))
    }
    return out
  }
}

function drawBox(c: Canvas, b: PlacedBox) {
  if (b.shape === 'start' || b.shape === 'end') {
    c.put(b.x, b.y, b.shape === 'start' ? '●' : '◉')
    return
  }
  const [tl, tr, bl, br, hz, vt] = [...(BORDERS[b.shape] ?? BORDERS.rect!)] as [string, string, string, string, string, string]
  c.put(b.x, b.y, tl + hz.repeat(b.w - 2) + tr)
  c.put(b.x, b.y + b.h - 1, bl + hz.repeat(b.w - 2) + br)
  for (let i = 1; i < b.h - 1; i++) {
    const text = b.lines[i - 1] ?? ''
    const inner = b.w - 2
    const left = Math.floor((inner - text.length) / 2)
    c.put(b.x, b.y + i, vt + ' '.repeat(left) + text + ' '.repeat(inner - left - text.length) + vt)
  }
}

function step(a: Pt, b: Pt): [number, number] {
  return [Math.sign(b.x - a.x), Math.sign(b.y - a.y)]
}

function drawRoute(c: Canvas, pts: Pt[], dashed: boolean) {
  for (let k = 0; k + 1 < pts.length; k++) {
    const a = pts[k]!
    const b = pts[k + 1]!
    const [dx, dy] = step(a, b)
    if (dx === 0 && dy === 0) continue
    const fwd = dx > 0 ? R : dx < 0 ? L : dy > 0 ? D : U
    const back = dx > 0 ? L : dx < 0 ? R : dy > 0 ? U : D
    let x = a.x
    let y = a.y
    c.link(x, y, fwd, dashed)
    while (x !== b.x || y !== b.y) {
      x += dx
      y += dy
      c.link(x, y, back | (x === b.x && y === b.y ? 0 : fwd), dashed)
    }
  }
  // A lone first or last cell still reads as a line along the flow.
  const ends = [pts[0]!, pts[pts.length - 1]!]
  for (const p of ends) {
    const i = p.y * c.w + p.x
    if (c.inside(p.x, p.y) && c.mask[i] === 0) c.link(p.x, p.y, U | D, dashed)
  }
}

function placeTag(c: Canvas, pts: Pt[], tag: string): boolean {
  const segs: [Pt, Pt][] = []
  for (let k = 0; k + 1 < pts.length; k++) segs.push([pts[k]!, pts[k + 1]!])
  // On a horizontal run first: ──12──
  for (const [a, b] of segs) {
    if (a.y !== b.y) continue
    const lo = Math.min(a.x, b.x) + 1
    const hi = Math.max(a.x, b.x) - 1
    if (hi - lo + 1 < tag.length + 2) continue
    const x0 = Math.floor((lo + hi - tag.length + 1) / 2)
    let ok = true
    for (let i = 0; i < tag.length; i++) {
      const j = a.y * c.w + x0 + i
      if (c.fixed[j] !== null || (c.mask[j] !== (L | R) && c.mask[j] !== 0)) ok = false
    }
    if (ok) {
      c.put(x0, a.y, tag)
      return true
    }
  }
  // Else beside a vertical run, right then left, with a blank cell around it.
  for (const [a, b] of segs) {
    if (a.x !== b.x) continue
    const lo = Math.min(a.y, b.y)
    const hi = Math.max(a.y, b.y)
    const mid = Math.floor((lo + hi) / 2)
    const rows = [...Array(hi - lo + 1).keys()].map(i => lo + i).sort((p, q) => Math.abs(p - mid) - Math.abs(q - mid))
    for (const y of rows) {
      for (const x0 of [a.x + 1, a.x - tag.length]) {
        let ok = true
        for (let i = -1; i <= tag.length; i++) {
          const x = x0 + i
          if (x === a.x) continue
          if (i >= 0 && i < tag.length ? !c.free(x, y) : c.inside(x, y) && !c.free(x, y)) ok = false
        }
        if (ok) {
          c.put(x0, y, tag)
          return true
        }
      }
    }
  }
  return false
}

export function drawText(layout: Layout): { lines: string[]; unplaced: Set<string> } {
  const c = new Canvas(layout.width, layout.height)
  for (const b of layout.boxes) drawBox(c, b)
  for (const r of layout.routes) drawRoute(c, r.points, r.dashed)
  for (const r of layout.routes) {
    const p = r.head === 'end' ? r.points[r.points.length - 1] : r.head === 'start' ? r.points[0] : undefined
    if (!p) continue
    const td = layout.direction === 'TD'
    c.put(p.x, p.y, r.head === 'end' ? (td ? '▼' : '▶') : td ? '▲' : '◀')
  }
  const unplaced = new Set<string>()
  for (const r of layout.routes) if (r.tag && !placeTag(c, r.points, r.tag)) unplaced.add(r.tag)
  // A self-loop is marked beside its box: ↻5
  for (const row of layout.legend) {
    if (!row.selfLoop) continue
    const b = layout.boxes.find(x => x.id === row.fromId)
    const mark = `↻${row.tag}`
    let placed = false
    for (let dy = 0; b && dy < b.h && !placed; dy++) {
      const x = b.x + b.w + 1
      const y = b.y + Math.floor(b.h / 2) + (dy % 2 ? -1 : 1) * Math.ceil(dy / 2)
      if ([...Array(mark.length + 1).keys()].every(i => !c.inside(x - 1 + i, y) || c.free(x - 1 + i, y))) {
        c.put(x, y, mark)
        placed = true
      }
    }
    if (!placed) unplaced.add(row.tag)
  }
  return { lines: c.lines(), unplaced }
}

/** One legend row as text: the tag, the label (the file:line citations), and endpoints where needed. */
export function legendText(row: LegendRow, unplaced: Set<string>, pad = 2): string {
  const dash = row.dashed ? ' (dashed)' : ''
  const tag = row.tag.padStart(pad)
  if (row.selfLoop) return `${tag}  ↻ ${row.from}: ${row.text || '(no label)'}${dash}`
  const ends = unplaced.has(row.tag) ? `${row.from} → ${row.to}: ` : ''
  return `${tag}  ${ends}${row.text}${dash}`
}

export function summary(g: Graph): string {
  const kind = g.kind === 'state' ? 'state diagram' : `flowchart ${g.direction}`
  return `${kind} · ${g.nodes.length} nodes · ${g.edges.length} edges`
}

// ---------------------------------------------------------------- svg

const CW = 8
const CH = 18

function esc(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
}

export function toSvg(layout: Layout): string {
  const W = layout.width * CW + 2 * CW
  const H = layout.height * CH + CH
  const ox = CW
  const oy = CH / 2
  const X = (x: number) => ox + x * CW
  const Y = (y: number) => oy + y * CH
  const parts: string[] = []
  parts.push(
    `<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" font-family="ui-monospace,Menlo,Consolas,monospace" font-size="13">`,
    '<style>.t{fill:#1f2328}.l{stroke:#57606a;fill:none;stroke-width:1.3}.b{stroke:#57606a;fill:none;stroke-width:1.3}.h{fill:#57606a}.p{fill:#ddf4ff;stroke:#54aeff}.pt{fill:#0969da}' +
      '@media (prefers-color-scheme: dark){.t{fill:#e6edf3}.l,.b{stroke:#8b949e}.h{fill:#8b949e}.p{fill:#12263f;stroke:#388bfd}.pt{fill:#79c0ff}}</style>',
    '<defs><marker id="a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" class="h"/></marker></defs>',
  )
  for (const b of layout.boxes) {
    if (b.shape === 'start' || b.shape === 'end') {
      const cx = X(b.x + 0.5)
      const cy = Y(b.y + 0.5)
      parts.push(`<circle cx="${cx}" cy="${cy}" r="6" class="${b.shape === 'start' ? 'h' : 'b'}"/>`)
      if (b.shape === 'end') parts.push(`<circle cx="${cx}" cy="${cy}" r="3.5" class="h"/>`)
      continue
    }
    const x = X(b.x)
    const y = Y(b.y + 0.25)
    const w = b.w * CW
    const h = (b.h - 0.5) * CH
    if (b.shape === 'diamond') {
      const k = 8
      parts.push(`<polygon class="b" points="${x + k},${y} ${x + w - k},${y} ${x + w},${y + h / 2} ${x + w - k},${y + h} ${x + k},${y + h} ${x},${y + h / 2}"/>`)
    } else {
      const rx = b.shape === 'round' ? 10 : 3
      parts.push(`<rect class="b" x="${x}" y="${y}" width="${w}" height="${h}" rx="${rx}"/>`)
      if (b.shape === 'db') parts.push(`<path class="b" d="M${x} ${y + 5}Q${x + w / 2} ${y + 12} ${x + w} ${y + 5}"/>`)
    }
    b.lines.forEach((line, i) => {
      parts.push(`<text class="t" x="${X(b.x + b.w / 2)}" y="${Y(b.y + 1 + i) + CH * 0.7}" text-anchor="middle">${esc(line)}</text>`)
    })
  }
  const td = layout.direction === 'TD'
  for (const r of layout.routes) {
    const pts = r.points.map(p => ({ x: X(p.x + 0.5), y: Y(p.y + 0.5) }))
    const first = pts[0]!
    const last = pts[pts.length - 1]!
    if (td) {
      first.y -= CH * 0.5
      last.y += CH * 0.5
    } else {
      first.x -= CW * 0.5
      last.x += CW * 0.5
    }
    const marker = r.head === 'end' ? ' marker-end="url(#a)"' : r.head === 'start' ? ' marker-start="url(#a)"' : ''
    const dash = r.dashed ? ' stroke-dasharray="5 4"' : ''
    parts.push(`<polyline class="l" points="${pts.map(p => `${p.x},${p.y}`).join(' ')}"${dash}${marker}/>`)
    if (r.tag) {
      let at = { x: (first.x + last.x) / 2, y: (first.y + last.y) / 2 }
      let longest = -1
      for (let k = 0; k + 1 < pts.length; k++) {
        const a = pts[k]!
        const b = pts[k + 1]!
        const len = Math.abs(a.x - b.x) + Math.abs(a.y - b.y)
        if (len > longest) {
          longest = len
          at = { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 }
        }
      }
      const tw = r.tag.length * 7 + 8
      parts.push(
        `<rect class="p" x="${at.x - tw / 2}" y="${at.y - 8}" width="${tw}" height="16" rx="8"/>`,
        `<text class="pt" x="${at.x}" y="${at.y + 4.5}" text-anchor="middle" font-size="11">${esc(r.tag)}</text>`,
      )
    }
  }
  parts.push('</svg>')
  return parts.join('')
}

export function altText(g: Graph): string {
  const name = new Map(g.nodes.map(n => [n.id, n.label.join(' ')]))
  const edges = g.edges.map(e => `${name.get(e.from)} → ${name.get(e.to)}${e.label ? ` (${e.label})` : ''}`)
  return `${summary(g)}: ${edges.join('; ')}`.slice(0, 2000)
}

export { LIMITS }
