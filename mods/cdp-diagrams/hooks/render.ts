// Turns a Layout into terminal lines (box-drawing characters) or an SVG
// document, and decides when a block is shown raw instead (and why).

import { LABEL_WIDTH, layoutGraph, LIMITS, TooLarge, wrap, type Layout, type LegendRow, type Outcome, type PlacedBox, type Pt, type Role } from './layout.ts'
import { parseMermaid, ParseError, type Graph } from './mermaid.ts'
import type { CheckedEdge, EdgeStatus } from './verify.ts'

/** Who drew a cell of the terminal drawing, so the mod can colour it. */
export type Owner =
  | { k: 'edge'; edge: number }
  | { k: 'tag'; edge: number; mark: boolean; outcome: Outcome | null }
  | { k: 'box'; id: string; role: Role; shape: string; label: boolean; outcome: Outcome | null }

export type Prepared =
  | { ok: true; graph: Graph; layout: Layout; lines: string[] | null; owners: (Owner | null)[][]; unplaced: Set<string> }
  | { ok: false; reason: string }

/**
 * Layouts tried in order until one fits: boxes narrow first, then the
 * actions drawn on edges, then edges keep only their markers.
 */
const TRIES: [boxWidth: number, labelWidth: number, roomy?: boolean][] = [
  [24, LABEL_WIDTH, true],
  [18, LABEL_WIDTH, true],
  [24, LABEL_WIDTH],
  [18, LABEL_WIDTH],
  [14, LABEL_WIDTH],
  [18, 12],
  [14, 12],
  [14, 8],
  [10, 8],
  [14, 0],
  [10, 0],
]

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
    // A wide left-to-right diagram reflows top-down before anything is cut.
    for (const dir of graph.direction === 'LR' && maxColumns !== null ? (['LR', 'TD'] as const) : ([graph.direction] as const))
    for (const [boxWidth, labelWidth, roomy] of TRIES) {
      for (const compact of [false, true]) {
        if (dir !== graph.direction) graph.direction = dir
        const layout = layoutGraph(graph, { boxWidth, compact, labelWidth, roomy: roomy ?? false })
        if (maxColumns === null) {
          if (layout.width > 400) return { ok: false, reason: `too wide to draw (${layout.width} cells)` }
          return { ok: true, graph, layout, lines: null, owners: [], unplaced: new Set() }
        }
        narrowest = Math.min(narrowest, layout.width)
        if (layout.width <= maxColumns) {
          const { lines, owners, unplaced } = drawText(layout)
          return { ok: true, graph, layout, lines, owners, unplaced }
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
  rect: '╭╮╰╯─│',
  round: '╭╮╰╯─│',
  db: '╔╗╚╝═║',
  diamond: '╱╲╲╱─│',
}

class Canvas {
  fixed: (string | null)[]
  mask: number[]
  dash: boolean[]
  owner: (Owner | null)[]
  w: number
  h: number
  constructor(w: number, h: number) {
    this.w = w
    this.h = h
    this.fixed = new Array(w * h).fill(null)
    this.mask = new Array(w * h).fill(0)
    this.dash = new Array(w * h).fill(false)
    this.owner = new Array(w * h).fill(null)
  }
  inside(x: number, y: number) {
    return x >= 0 && y >= 0 && x < this.w && y < this.h
  }
  put(x: number, y: number, s: string, who: Owner | ((i: number) => Owner) | null = null) {
    const cs = [...s]
    for (let i = 0; i < cs.length; i++) {
      if (!this.inside(x + i, y)) continue
      const j = y * this.w + x + i
      this.fixed[j] = cs[i]!
      this.owner[j] = typeof who === 'function' ? who(i) : who
    }
  }
  free(x: number, y: number) {
    return this.inside(x, y) && this.fixed[y * this.w + x] === null && this.mask[y * this.w + x] === 0
  }
  link(x: number, y: number, bits: number, dashed: boolean, edge: number) {
    if (!this.inside(x, y)) return
    const i = y * this.w + x
    this.mask[i]! |= bits
    if (dashed) this.dash[i] = true
    if (this.fixed[i] === null) this.owner[i] = { k: 'edge', edge }
  }
  cells(): { lines: string[]; owners: (Owner | null)[][] } {
    const lines: string[] = []
    const owners: (Owner | null)[][] = []
    for (let y = 0; y < this.h; y++) {
      const row: string[] = []
      const who: (Owner | null)[] = []
      for (let x = 0; x < this.w; x++) {
        const i = y * this.w + x
        const m = this.mask[i]!
        row.push(this.fixed[i] ?? (m ? ((this.dash[i] ? DASHED[m] : undefined) ?? SOLID[m] ?? '┼') : ' '))
        who.push(this.fixed[i] !== null || m ? this.owner[i]! : null)
      }
      while (row.length && row[row.length - 1] === ' ') {
        row.pop()
        who.pop()
      }
      lines.push(row.join(''))
      owners.push(who)
    }
    return { lines, owners }
  }
}

/** The border a box draws with: a start or end step is rounded. */
function borderOf(b: PlacedBox): string {
  if (b.shape === 'rect' && (b.role === 'entry' || b.role === 'end')) return BORDERS.round!
  return BORDERS[b.shape] ?? BORDERS.rect!
}

function drawBox(c: Canvas, b: PlacedBox) {
  const edge: Owner = { k: 'box', id: b.id, role: b.role, shape: b.shape, label: false, outcome: b.outcome }
  const text: Owner = { k: 'box', id: b.id, role: b.role, shape: b.shape, label: true, outcome: b.outcome }
  if (b.shape === 'start' || b.shape === 'end') {
    c.put(b.x, b.y, b.shape === 'start' ? '●' : '◉', edge)
    return
  }
  const [tl, tr, bl, br, hz, vt] = [...borderOf(b)] as [string, string, string, string, string, string]
  c.put(b.x, b.y, tl + hz.repeat(b.w - 2) + tr, edge)
  c.put(b.x, b.y + b.h - 1, bl + hz.repeat(b.w - 2) + br, edge)
  for (let i = 1; i < b.h - 1; i++) {
    const line = b.lines[i - 1] ?? ''
    const inner = b.w - 2
    const left = Math.floor((inner - line.length) / 2)
    const row = vt + ' '.repeat(left) + line + ' '.repeat(inner - left - line.length) + vt
    const last = row.length - 1
    c.put(b.x, b.y + i, row, k => (k === 0 || k === last ? edge : text))
  }
}

function step(a: Pt, b: Pt): [number, number] {
  return [Math.sign(b.x - a.x), Math.sign(b.y - a.y)]
}

function drawRoute(c: Canvas, pts: Pt[], dashed: boolean, edge: number) {
  for (let k = 0; k + 1 < pts.length; k++) {
    const a = pts[k]!
    const b = pts[k + 1]!
    const [dx, dy] = step(a, b)
    if (dx === 0 && dy === 0) continue
    const fwd = dx > 0 ? R : dx < 0 ? L : dy > 0 ? D : U
    const back = dx > 0 ? L : dx < 0 ? R : dy > 0 ? U : D
    let x = a.x
    let y = a.y
    c.link(x, y, fwd, dashed, edge)
    while (x !== b.x || y !== b.y) {
      x += dx
      y += dy
      c.link(x, y, back | (x === b.x && y === b.y ? 0 : fwd), dashed, edge)
    }
  }
  // A lone first or last cell still reads as a line along the flow.
  const ends = [pts[0]!, pts[pts.length - 1]!]
  for (const p of ends) {
    const i = p.y * c.w + p.x
    if (c.inside(p.x, p.y) && c.mask[i] === 0) c.link(p.x, p.y, U | D, dashed, edge)
  }
}

/** Owners for a drawn label: the marker's cells, then the action's. */
const tagOwner = (edge: number, mark: string, outcome: Outcome | null = null) => (i: number): Owner => ({ k: 'tag', edge, mark: i < [...mark].length, outcome })

/** Draws a label block (one row per line) at x0, y; the marker is on the first row. */
function putBlock(c: Canvas, x0: number, y: number, lines: string[], edge: number, mark: string, outcome: Outcome | null) {
  lines.forEach((l, r) => c.put(x0, y + r, l, tagOwner(edge, r === 0 ? mark : '', outcome)))
}

function placeTag(c: Canvas, pts: Pt[], lines: string[], edge: number, mark: string, outcome: Outcome | null): boolean {
  const n = Math.max(...lines.map(l => [...l].length))
  const k = lines.length
  const segs: [Pt, Pt][] = []
  for (let k = 0; k + 1 < pts.length; k++) segs.push([pts[k]!, pts[k + 1]!])
  // On a horizontal run first: ──① success──
  for (const [a, b] of segs) {
    if (a.y !== b.y) continue
    const lo = Math.min(a.x, b.x) + 1
    const hi = Math.max(a.x, b.x) - 1
    if (hi - lo + 1 < n + 2) continue
    const x0 = Math.floor((lo + hi - n + 1) / 2)
    if (k === 1) {
      let ok = true
      for (let i = 0; i < n; i++) {
        const j = a.y * c.w + x0 + i
        if (c.fixed[j] !== null || (c.mask[j] !== (L | R) && c.mask[j] !== 0)) ok = false
      }
      if (ok) {
        putBlock(c, x0, a.y, lines, edge, mark, outcome)
        return true
      }
    } else {
      // A wrapped label stacks above the run, else below it.
      for (const y0 of [a.y - k, a.y + 1]) {
        let ok = true
        for (let r = 0; r < k && ok; r++) for (let i = 0; i < n; i++) if (!c.free(x0 + i, y0 + r)) ok = false
        if (ok) {
          putBlock(c, x0, y0, lines, edge, mark, outcome)
          return true
        }
      }
    }
  }
  // Else beside a vertical run, the one nearest the arrow first, right then
  // left, a blank cell around it; a row inside the run before its bends.
  for (const [a, b] of [...segs].reverse()) {
    if (a.x !== b.x) continue
    const lo = Math.min(a.y, b.y)
    const hi = Math.max(a.y, b.y)
    const mid = Math.floor((lo + hi) / 2)
    const end = (y: number) => (y === lo || y === hi ? 1 : 0)
    if (hi - lo + 1 < k) continue
    const rows = [...Array(hi - lo + 2 - k).keys()].map(i => lo + i).sort((p, q) => end(p) - end(q) || Math.abs(p - mid) - Math.abs(q - mid))
    for (const y of rows) {
      for (const x0 of [a.x + 2, a.x + 1, a.x - n - 1, a.x - n]) {
        let ok = true
        for (let r = 0; r < k && ok; r++) {
          for (let i = -1; i <= n; i++) {
            const x = x0 + i
            if (x === a.x) continue
            if (i >= 0 && i < n ? !c.free(x, y + r) : c.inside(x, y + r) && !c.free(x, y + r)) ok = false
          }
          // The gap beside the line, when there is one, stays blank too.
          if (x0 === a.x + 2 && !c.free(a.x + 1, y + r)) ok = false
          if (x0 === a.x - n - 1 && !c.free(a.x - 1, y + r)) ok = false
        }
        if (ok) {
          putBlock(c, x0, y, lines, edge, mark, outcome)
          return true
        }
      }
    }
  }
  return false
}

export type Drawing = { lines: string[]; owners: (Owner | null)[][]; unplaced: Set<string> }

export function drawText(layout: Layout): Drawing {
  const c = new Canvas(layout.width, layout.height)
  for (const b of layout.boxes) drawBox(c, b)
  for (const r of layout.routes) drawRoute(c, r.points, r.dashed, r.edge)
  for (const r of layout.routes) {
    const p = r.head === 'end' ? r.points[r.points.length - 1] : r.head === 'start' ? r.points[0] : undefined
    if (!p) continue
    const td = layout.direction === 'TD'
    c.put(p.x, p.y, r.head === 'end' ? (td ? '▼' : '▶') : td ? '▲' : '◀', { k: 'edge', edge: r.edge })
  }
  const unplaced = new Set<string>()
  // Labelled edges first get their action; then the rest, and any that did
  // not fit, get their marker alone.
  const pending = layout.routes.filter(r => r.tag && !(r.labelLines && placeTag(c, r.points, r.labelLines, r.edge, r.tag, r.outcome)))
  for (const r of pending) if (!placeTag(c, r.points, [r.tag!], r.edge, r.tag!, r.outcome)) unplaced.add(r.tag!)
  // A self-loop is marked beside its box: ↻⑤
  for (const row of layout.legend) {
    if (!row.selfLoop) continue
    const b = layout.boxes.find(x => x.id === row.fromId)
    const mark = `↻${row.tag}`
    let placed = false
    for (let dy = 0; b && dy < b.h && !placed; dy++) {
      const x = b.x + b.w + 1
      const y = b.y + Math.floor(b.h / 2) + (dy % 2 ? -1 : 1) * Math.ceil(dy / 2)
      const n = [...mark].length
      if ([...Array(n + 1).keys()].every(i => !c.inside(x - 1 + i, y) || c.free(x - 1 + i, y))) {
        c.put(x, y, mark, tagOwner(row.edge, mark, row.outcome))
        placed = true
      }
    }
    if (!placed) unplaced.add(row.tag)
  }
  return { ...c.cells(), unplaced }
}

// ---------------------------------------------------------------- styles

/** A run's look, as Text props: a theme colour, dim, bold. */
export type Style = { color?: string; dimColor?: boolean; bold?: boolean }
export type Run = { text: string; style: Style | null }

/** An edge's colour by what the checker said of it; unchecked edges draw grey, dashed ones dim. */
export function edgeStyle(status: EdgeStatus | null | undefined, dashed: boolean): Style | null {
  switch (status) {
    case 'correct':
      return { color: 'success' }
    case 'wrong_citation':
      return { color: 'error' }
    case 'unsupported':
    case 'ambiguous':
    case 'uncited':
      return { color: 'warning' }
    case 'inferred':
      return { dimColor: true }
    default:
      return dashed ? { dimColor: true } : { color: 'subtle' }
  }
}

/**
 * Outcome roles as theme colours (green, red, amber), so they follow the
 * person's theme, dark or light. Roles named as in prismantis ({ok:}/{warn:}),
 * which also resolves them from the theme (MIT, github.com/NahumLitvin/prismantis).
 */
const OUTCOME_COLOR: Record<Outcome, string> = { ok: 'success', fail: 'error', warn: 'warning' }

/**
 * A box's look by role (theme colours, so they follow the person's theme):
 * where the flow starts bold in the accent, a branch bold in purple, a step
 * or state in blue or teal, a store in blue; where it ends takes the colour
 * of the outcome reaching it (dim when it has none).
 */
export function boxStyle(role: Role, label: boolean, shape = 'rect', outcome: Outcome | null = null): Style | null {
  switch (role) {
    case 'entry':
      return label ? { bold: true } : { color: 'claude', bold: true }
    case 'decision':
      return label ? { bold: true, color: 'autoAccept' } : { color: 'autoAccept' }
    case 'end':
      if (outcome) return label ? { bold: true, color: OUTCOME_COLOR[outcome] } : { color: OUTCOME_COLOR[outcome] }
      return label ? null : { dimColor: true }
    default:
      if (label) return null
      if (shape === 'db') return { color: 'ide' }
      return shape === 'round' ? { color: 'planMode' } : { color: 'permission' }
  }
}

const sameStyle = (a: Style | null, b: Style | null) =>
  a === b || (!!a && !!b && a.color === b.color && !!a.dimColor === !!b.dimColor && !!a.bold === !!b.bold)

/** Joins neighbouring cells of one look into runs. */
export function toRuns(cells: { ch: string; style: Style | null }[]): Run[] {
  const out: Run[] = []
  for (const { ch, style } of cells) {
    const last = out[out.length - 1]
    if (last && sameStyle(last.style, style)) last.text += ch
    else out.push({ text: ch, style })
  }
  return out
}

/**
 * The drawing's rows as styled runs. `statusOf` gives each edge's checked
 * status (undefined while unchecked); `dashed` whether the edge is dashed.
 */
export function styledRows(
  d: { lines: string[]; owners: (Owner | null)[][]; outcomes?: (Outcome | null)[] },
  statusOf: (edge: number) => EdgeStatus | null | undefined,
  dashed: (edge: number) => boolean,
): Run[][] {
  return d.lines.map((line, y) => {
    const chars = [...line]
    const who = d.owners[y] ?? []
    return toRuns(
      chars.map((ch, x) => {
        const o = who[x] ?? null
        if (!o || ch === ' ') return { ch, style: null }
        if (o.k === 'box') return { ch, style: boxStyle(o.role, o.label, o.shape, o.outcome) }
        const st = edgeStyle(statusOf(o.edge), dashed(o.edge))
        // An unchecked branch's line takes its outcome's colour.
        const out = o.k === 'edge' ? null : o.outcome
        if (o.k === 'edge') {
          const oc = (d.outcomes ?? [])[o.edge] ?? null
          return { ch, style: oc && !statusOf(o.edge) && !dashed(o.edge) ? { color: OUTCOME_COLOR[oc] } : st }
        }
        if (out) return { ch, style: { color: OUTCOME_COLOR[out], bold: true } }
        if (o.mark) return { ch, style: { ...(st ?? {}), bold: true } }
        return { ch, style: st?.color === 'error' ? st : st?.dimColor ? st : null }
      }),
    )
  })
}

/** Plain text of a row of runs. */
export const plain = (runs: Run[]): string => runs.map(r => r.text).join('')

const VERDICT_WORD: Record<EdgeStatus, string> = {
  correct: '✓ correct',
  wrong_citation: '✗ wrong',
  unsupported: '? unsupported',
  ambiguous: '? ambiguous',
  uncited: '? uncited',
  inferred: '~ inferred',
}

/** The legend's check cell for one edge. */
export function verdictCell(checked: CheckedEdge | null | undefined, dashed: boolean): Run {
  if (!checked) return dashed ? { text: '╌ inferred', style: { dimColor: true } } : { text: '', style: null }
  let text = VERDICT_WORD[checked.status]
  if (checked.status === 'wrong_citation') {
    const hint = checked.cites.find(c => c.status !== 'correct')?.hint
    if (hint) text += ` · try ${hint.split('/').pop()}`
  }
  return { text, style: edgeStyle(checked.status, dashed) }
}

/** The label cell: the action; with the endpoints when the marker is not on the drawing. */
export function labelCell(row: LegendRow, unplaced: Set<string>): string {
  const act = row.action || (row.cites.length ? '' : row.text)
  if (row.selfLoop) return `↻ ${row.from}${act ? `: ${act}` : ''}`
  // An edge with only a citation is named by where it goes.
  if (unplaced.has(row.tag) || !act) return `${row.from} → ${row.to}${act ? `: ${act}` : ''}`
  return act
}

const SEP = ' │ '
const pad = (s: string, n: number) => s + ' '.repeat(Math.max(0, n - [...s].length))

/**
 * The legend as an aligned table, marker │ label │ cite │ check, at most
 * `width` columns: cells wrap onto further rows rather than being cut. A
 * header row and a rule open it; the check column is left out when no row
 * has one.
 */
export function legendTable(
  legend: LegendRow[],
  unplaced: Set<string>,
  checkedOf: (edge: number) => CheckedEdge | null | undefined,
  width: number,
): Run[][] {
  if (!legend.length) return []
  const rows = legend.map(r => ({
    row: r,
    mark: r.tag,
    label: labelCell(r, unplaced),
    cite: r.cites.join(', '),
    check: verdictCell(checkedOf(r.edge), r.dashed),
  }))
  const hasCheck = rows.some(r => r.check.text)
  const len = (s: string) => [...s].length
  const mw = Math.max(1, ...rows.map(r => len(r.mark)))
  const w = { l: Math.max(5, ...rows.map(r => len(r.label))), c: Math.max(4, ...rows.map(r => len(r.cite))), v: hasCheck ? Math.max(5, ...rows.map(r => len(r.check.text))) : 0 }
  const floor = { l: 14, c: 12, v: 10 }
  const total = () => mw + SEP.length + w.l + SEP.length + w.c + (hasCheck ? SEP.length + w.v : 0)
  // Narrow the widest column still above its floor, then the floors themselves.
  for (const fl of [floor, { l: 6, c: 6, v: 6 }]) {
    while (total() > width) {
      const keys = (['l', 'c', 'v'] as const).filter(k => (k !== 'v' || hasCheck) && w[k] > fl[k])
      if (!keys.length) break
      keys.sort((p, q) => w[q] - w[p])
      w[keys[0]!]--
    }
  }
  const dim: Style = { dimColor: true }
  const sep: Run = { text: SEP, style: dim }
  const flat = (xs: Run[]) => toRuns(xs.flatMap(x => [...x.text].map(ch => ({ ch, style: x.style }))))
  const head: Run[] = [
    { text: pad('#', mw), style: dim },
    sep,
    { text: pad('edge', w.l), style: dim },
    sep,
    { text: hasCheck ? pad('cite', w.c) : 'cite', style: dim },
    ...(hasCheck ? [sep, { text: 'check', style: dim }] : []),
  ]
  const bar = (n: number) => '─'.repeat(n)
  const rule: Run[] = [
    { text: `${bar(mw)}─┼─${bar(w.l)}─┼─${bar(w.c)}${hasCheck ? `─┼─${bar(w.v)}` : ''}`, style: dim },
  ]
  const body = rows.flatMap(r => {
    const st = edgeStyle(checkedOf(r.row.edge)?.status, r.row.dashed)
    const oc = r.row.outcome ? { color: OUTCOME_COLOR[r.row.outcome], bold: true } : null
    const label = wrap([r.label], w.l)
    const cite = wrap([r.cite || '—'], w.c)
    const check = hasCheck ? wrap([r.check.text], w.v) : ['']
    const n = Math.max(label.length, cite.length, check.length)
    return Array.from({ length: n }, (_, i) => {
      const out: Run[] = [
        { text: pad(i === 0 ? r.mark : '', mw), style: { ...(st ?? {}), bold: true } },
        sep,
        { text: pad(label[i] ?? '', w.l), style: oc ?? (r.row.dashed && !st?.color ? dim : null) },
        sep,
        { text: hasCheck ? pad(cite[i] ?? '', w.c) : (cite[i] ?? ''), style: r.cite ? null : dim },
      ]
      if (hasCheck) out.push(sep, { text: check[i] ?? '', style: r.check.style })
      return flat(out)
    })
  })
  return [flat(head), flat(rule), ...body]
}

/** Each legend row as plain text (tests and the checker's invariants). */
export function legendLines(layout: Layout, unplaced: Set<string>, width = 200): string[] {
  return legendTable(layout.legend, unplaced, () => undefined, width).map(plain)
}

/** The colour of the line under the legend: red with a wrong cite, yellow with an unverified one, else green. */
export function verdictStyle(edges: CheckedEdge[]): Style {
  if (edges.some(e => e.status === 'wrong_citation')) return { color: 'error' }
  if (edges.some(e => e.status === 'unsupported' || e.status === 'ambiguous' || e.status === 'uncited')) return { color: 'warning' }
  return { color: 'success' }
}

const KIND: Record<Graph['kind'], string> = { flowchart: 'Flowchart', state: 'State machine' }

/** The title's diagram kind. */
export function kindName(g: Graph): string {
  return KIND[g.kind]
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
      const rx = b.shape === 'round' || b.role === 'entry' || b.role === 'end' ? 10 : 3
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
    const pill = r.label ?? r.tag
    if (pill) {
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
      const tw = [...pill].length * 7 + 8
      parts.push(
        `<rect class="p" x="${at.x - tw / 2}" y="${at.y - 8}" width="${tw}" height="16" rx="8"/>`,
        `<text class="pt" x="${at.x}" y="${at.y + 4.5}" text-anchor="middle" font-size="11">${esc(pill)}</text>`,
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
