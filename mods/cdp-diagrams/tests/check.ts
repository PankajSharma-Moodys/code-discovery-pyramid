// Invariants every drawn diagram must hold; shared by the synthetic tests
// and the local run over real answers (dev/test-samples.sh).

import type { PlacedBox, Pt } from '../hooks/layout.ts'
import { legendText, prepare } from '../hooks/render.ts'

const inBox = (p: Pt, b: PlacedBox) => p.x >= b.x && p.x < b.x + b.w && p.y >= b.y && p.y < b.y + b.h
const touches = (p: Pt, b: PlacedBox) =>
  !inBox(p, b) && [[0, 1], [0, -1], [1, 0], [-1, 0]].some(([dx, dy]) => inBox({ x: p.x + dx!, y: p.y + dy! }, b))

/** Problems found drawing `source` in `columns` (or as SVG with null); [] when it holds. */
export function problems(source: string, columns: number | null): string[] {
  const p = prepare(source, columns)
  if (!p.ok) return [`not drawn: ${p.reason}`]
  const out: string[] = []
  const { graph, layout } = p
  const boxes = new Map(layout.boxes.map(b => [b.id, b]))
  if (boxes.size !== graph.nodes.length) out.push(`${graph.nodes.length} nodes, ${boxes.size} boxes`)
  for (const a of layout.boxes)
    for (const b of layout.boxes)
      if (a !== b && a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h)
        out.push(`boxes ${a.id} and ${b.id} overlap`)
  for (const n of graph.nodes) {
    const b = boxes.get(n.id)
    if (!b || n.shape === 'start' || n.shape === 'end') continue
    const want = n.label.join('').replace(/\s/g, '')
    if (b.lines.join('').replace(/\s/g, '') !== want) out.push(`box ${n.id} lost label text`)
  }
  for (const r of layout.routes) {
    const e = graph.edges[r.edge]!
    for (let k = 0; k + 1 < r.points.length; k++) {
      const a = r.points[k]!
      const b = r.points[k + 1]!
      if (a.x !== b.x && a.y !== b.y) out.push(`edge ${r.edge} has a diagonal step`)
      const n = Math.abs(a.x - b.x) + Math.abs(a.y - b.y)
      for (let s = 0; s <= n; s++) {
        const q = { x: a.x + Math.sign(b.x - a.x) * s, y: a.y + Math.sign(b.y - a.y) * s }
        for (const box of layout.boxes) if (inBox(q, box)) out.push(`edge ${r.edge} runs through box ${box.id}`)
      }
    }
    const first = r.points[0]!
    const last = r.points[r.points.length - 1]!
    const [from, to] = [boxes.get(e.from)!, boxes.get(e.to)!]
    const ok = r.head === 'start' ? touches(first, to) && touches(last, from) : touches(first, from) && touches(last, to)
    if (!ok) out.push(`edge ${r.edge} (${e.from}->${e.to}) does not join its boxes`)
  }
  const legend = layout.legend.map(row => legendText(row, p.unplaced))
  for (const e of graph.edges)
    if (e.label && !legend.some(l => l.includes(e.label))) out.push(`label "${e.label}" missing from the legend`)
  if (p.lines) {
    const canvas = p.lines.join('\n')
    for (const line of p.lines) if (columns !== null && [...line].length > columns) out.push(`line wider than ${columns}`)
    for (const row of layout.legend) {
      const mark = row.selfLoop ? `↻${row.tag}` : row.tag
      if (!p.unplaced.has(row.tag) && !canvas.includes(mark)) out.push(`tag ${row.tag} not on the drawing`)
    }
  }
  return out
}
