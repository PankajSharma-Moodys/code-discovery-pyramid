// A small layered (Sugiyama-style) layout on a character grid:
// cycle breaking -> longest-path layers -> dummy nodes for long edges ->
// barycenter ordering -> cross placement -> ports -> per-channel tracks.
// Coordinates are grid cells; the SVG renderer scales the same layout.

import type { GEdge, GNode, Graph, Shape } from './mermaid.ts'

export type Pt = { x: number; y: number }
export type PlacedBox = { id: string; x: number; y: number; w: number; h: number; lines: string[]; shape: Shape }
export type Route = {
  edge: number
  points: Pt[]
  dashed: boolean
  head: 'end' | 'start' | 'none'
  tag: string | null
}
export type LegendRow = { tag: string; text: string; fromId: string; from: string; to: string; dashed: boolean; selfLoop: boolean }
export type Layout = {
  direction: 'TD' | 'LR'
  width: number
  height: number
  boxes: PlacedBox[]
  routes: Route[]
  legend: LegendRow[]
}

export const LIMITS = { nodes: 60, edges: 120 }

export class TooLarge extends Error {}

export function wrap(lines: string[], width: number): string[] {
  const out: string[] = []
  for (const line of lines) {
    let cur = ''
    for (let word of line.split(/\s+/)) {
      if (cur && word.length > width && cur.length + 1 + word.length > width) {
        out.push(cur)
        cur = ''
      }
      while (word.length > width) {
        // Break an identifier after a separator where one is near the end.
        let cut = 0
        for (let k = width; k > width / 3; k--) {
          if ('./#:_,(-'.includes(word[k - 1] ?? '')) {
            cut = k
            break
          }
        }
        for (let k = width; !cut && k > width / 3; k--) {
          if (/[a-z]/.test(word[k - 1] ?? '') && /[A-Z]/.test(word[k] ?? '')) cut = k
        }
        if (!cut) cut = width
        out.push(word.slice(0, cut))
        word = word.slice(cut)
      }
      if (!word) continue
      if (!cur) cur = word
      else if (cur.length + 1 + word.length <= width) cur += ' ' + word
      else {
        out.push(cur)
        cur = word
      }
    }
    if (cur) out.push(cur)
  }
  return out.length ? out : ['']
}

type VNode = {
  id: string
  real: GNode | null
  layer: number
  lines: string[]
  cs: number // size across layers (width in TD)
  ms: number // size along the flow (height in TD)
  pos: number // cross position of its first cell
  order: number
}
type Seg = { from: VNode; to: VNode; edge: number; a: number; b: number; track: number }

function firstLine(n: GNode | undefined): string {
  return (n?.label[0] ?? n?.id ?? '?').slice(0, 30)
}

export function layoutGraph(g: Graph, opts: { boxWidth: number; compact?: boolean }): Layout {
  if (g.nodes.length > LIMITS.nodes) throw new TooLarge(`${g.nodes.length} nodes (limit ${LIMITS.nodes})`)
  if (g.edges.length > LIMITS.edges) throw new TooLarge(`${g.edges.length} edges (limit ${LIMITS.edges})`)
  const td = g.direction === 'TD'
  const byId = new Map(g.nodes.map(n => [n.id, n]))

  // Tags and legend, in source order, so the numbers read top to bottom.
  const legend: LegendRow[] = []
  const tags: (string | null)[] = g.edges.map(e => {
    const self = e.from === e.to
    if (!e.label && !self) return null
    const tag = String(legend.length + 1)
    legend.push({
      tag,
      text: e.label,
      fromId: e.from,
      from: firstLine(byId.get(e.from)),
      to: firstLine(byId.get(e.to)),
      dashed: e.dashed,
      selfLoop: self,
    })
    return tag
  })

  // Cycle breaking by DFS: an edge into a node on the stack is reversed.
  const out = new Map<string, number[]>()
  g.edges.forEach((e, i) => {
    if (e.from !== e.to) out.set(e.from, [...(out.get(e.from) ?? []), i])
  })
  const reversed = new Set<number>()
  const state = new Map<string, number>()
  const visit = (id: string) => {
    state.set(id, 1)
    for (const i of out.get(id) ?? []) {
      const to = g.edges[i]!.to
      const s = state.get(to) ?? 0
      if (s === 1) reversed.add(i)
      else if (s === 0) visit(to)
    }
    state.set(id, 2)
  }
  const hasIn = new Set(g.edges.filter(e => e.from !== e.to).map(e => e.to))
  for (const n of g.nodes) if (!hasIn.has(n.id) && !state.get(n.id)) visit(n.id)
  for (const n of g.nodes) if (!state.get(n.id)) visit(n.id)

  const dag: { u: string; v: string; edge: number }[] = []
  g.edges.forEach((e, i) => {
    if (e.from === e.to) return
    dag.push(reversed.has(i) ? { u: e.to, v: e.from, edge: i } : { u: e.from, v: e.to, edge: i })
  })

  // Longest-path layering.
  const layer = new Map<string, number>(g.nodes.map(n => [n.id, 0]))
  for (let pass = 0; pass < g.nodes.length; pass++) {
    let changed = false
    for (const d of dag) {
      const want = (layer.get(d.u) ?? 0) + 1
      if ((layer.get(d.v) ?? 0) < want) {
        layer.set(d.v, want)
        changed = true
      }
    }
    if (!changed) break
  }

  const vnodes: VNode[] = []
  const vmap = new Map<string, VNode>()
  for (const n of g.nodes) {
    const isDot = n.shape === 'start' || n.shape === 'end'
    const lines = isDot ? [n.label[0] ?? '●'] : wrap(n.label, opts.boxWidth)
    const w = isDot ? 1 : Math.max(...lines.map(l => l.length)) + 4
    const h = isDot ? 1 : lines.length + 2
    const v: VNode = { id: n.id, real: n, layer: layer.get(n.id) ?? 0, lines, cs: td ? w : h, ms: td ? h : w, pos: 0, order: 0 }
    vnodes.push(v)
    vmap.set(n.id, v)
  }

  // Dummy nodes so every segment joins adjacent layers.
  const segs: Seg[] = []
  const chains = new Map<number, Seg[]>()
  for (const d of dag) {
    let prev = vmap.get(d.u)!
    const end = vmap.get(d.v)!
    const chain: Seg[] = []
    for (let l = prev.layer + 1; l < end.layer; l++) {
      const dummy: VNode = { id: `~${d.edge}.${l}`, real: null, layer: l, lines: [], cs: 1, ms: 0, pos: 0, order: 0 }
      vnodes.push(dummy)
      chain.push({ from: prev, to: dummy, edge: d.edge, a: 0, b: 0, track: 0 })
      prev = dummy
    }
    chain.push({ from: prev, to: end, edge: d.edge, a: 0, b: 0, track: 0 })
    segs.push(...chain)
    chains.set(d.edge, chain)
  }

  const depth = Math.max(0, ...vnodes.map(v => v.layer)) + 1
  const layers: VNode[][] = Array.from({ length: depth }, () => [])
  for (const v of vnodes) layers[v.layer]!.push(v)
  const renumber = () => layers.forEach(l => l.forEach((v, i) => (v.order = i)))
  renumber()

  // Barycenter ordering; keep the sweep with the fewest crossings.
  const preds = new Map<VNode, VNode[]>()
  const succs = new Map<VNode, VNode[]>()
  for (const s of segs) {
    preds.set(s.to, [...(preds.get(s.to) ?? []), s.from])
    succs.set(s.from, [...(succs.get(s.from) ?? []), s.to])
  }
  const crossings = () => {
    let n = 0
    for (let i = 0; i < segs.length; i++)
      for (let j = i + 1; j < segs.length; j++) {
        const p = segs[i]!
        const q = segs[j]!
        if (p.from.layer !== q.from.layer) continue
        if ((p.from.order - q.from.order) * (p.to.order - q.to.order) < 0) n++
      }
    return n
  }
  const sortBy = (l: VNode[], near: Map<VNode, VNode[]>) => {
    const key = new Map<VNode, number>()
    for (const v of l) {
      const ns = near.get(v) ?? []
      key.set(v, ns.length ? ns.reduce((s, x) => s + x.order, 0) / ns.length : v.order)
    }
    l.sort((p, q) => key.get(p)! - key.get(q)! || p.order - q.order)
    l.forEach((v, i) => (v.order = i))
  }
  let best = crossings()
  let bestOrder = layers.map(l => [...l])
  for (let it = 0; it < 8 && best > 0; it++) {
    if (it % 2 === 0) for (let i = 1; i < depth; i++) sortBy(layers[i]!, preds)
    else for (let i = depth - 2; i >= 0; i--) sortBy(layers[i]!, succs)
    const c = crossings()
    if (c < best) {
      best = c
      bestOrder = layers.map(l => [...l])
    }
  }
  bestOrder.forEach((l, i) => (layers[i] = l))
  renumber()

  // Cross placement: pack each layer, pulled toward its predecessors' centres.
  const GAP = 2
  const center = (v: VNode) => v.pos + (v.cs - 1) / 2
  const place = (l: VNode[], near: Map<VNode, VNode[]> | null) => {
    let end = -GAP
    for (const v of l) {
      const ns = near?.get(v) ?? []
      const want = ns.length && !opts.compact ? Math.round(ns.reduce((s, x) => s + center(x), 0) / ns.length - (v.cs - 1) / 2) : 0
      v.pos = Math.max(want, end + GAP)
      end = v.pos + v.cs
    }
  }
  place(layers[0]!, null)
  for (let i = 1; i < depth; i++) place(layers[i]!, preds)
  if (opts.compact) {
    const span = (l: VNode[]) => (l.length ? l[l.length - 1]!.pos + l[l.length - 1]!.cs : 0)
    const widest = Math.max(...layers.map(span))
    for (const l of layers) {
      const shift = Math.floor((widest - span(l)) / 2)
      for (const v of l) v.pos += shift
    }
  }

  // Ports: spread a node's outgoing and incoming segments along its side.
  const spread = (v: VNode, list: Seg[], side: 'a' | 'b', other: (s: Seg) => VNode) => {
    list.sort((p, q) => center(other(p)) - center(other(q)))
    const inner = v.cs >= 3 ? v.cs - 2 : 1
    const base = v.cs >= 3 ? v.pos + 1 : v.pos
    list.forEach((s, k) => {
      s[side] = base + Math.min(inner - 1, Math.floor(((k + 0.5) * inner) / list.length))
    })
  }
  for (const v of vnodes) {
    spread(v, segs.filter(s => s.from === v), 'a', s => s.to)
    spread(v, segs.filter(s => s.to === v), 'b', s => s.from)
  }

  // Tracks per channel: one row per bend; a segment leaving column c bends
  // above any segment arriving at column c, so their verticals never overlap.
  const channelTracks: number[] = []
  for (let i = 0; i + 1 < depth; i++) {
    const bends = segs.filter(s => s.from.layer === i && s.a !== s.b)
    const before = new Map<Seg, Seg[]>(bends.map(s => [s, bends.filter(p => p !== s && p.a === s.b)]))
    const rows: [number, number][][] = []
    const done = new Set<Seg>()
    const assign = (s: Seg, guard: Set<Seg>) => {
      if (done.has(s)) return
      guard.add(s)
      let min = 1
      for (const p of before.get(s) ?? []) {
        if (!guard.has(p)) assign(p, guard)
        if (done.has(p)) min = Math.max(min, p.track + 1)
      }
      const lo = Math.min(s.a, s.b) - 1
      const hi = Math.max(s.a, s.b) + 1
      let t = min
      while ((rows[t] ?? []).some(([x, y]) => x <= hi && lo <= y)) t++
      ;(rows[t] ??= []).push([lo, hi])
      s.track = t
      done.add(s)
    }
    for (const s of bends) assign(s, new Set())
    channelTracks.push(Math.max(0, ...bends.map(s => s.track)))
  }

  // Main-axis positions: layer extents and the channels between them.
  const mainStart: number[] = []
  const extent = layers.map(l => Math.max(1, ...l.map(v => v.ms)))
  let m = 0
  for (let i = 0; i < depth; i++) {
    mainStart.push(m)
    m += extent[i]!
    if (i + 1 < depth) m += channelTracks[i]! + 2
  }
  const mainSize = m
  const crossSize = Math.max(1, ...vnodes.map(v => v.pos + v.cs))
  const pt = (main: number, cross: number): Pt => (td ? { x: cross, y: main } : { x: main, y: cross })

  const routes: Route[] = []
  g.edges.forEach((e: GEdge, i) => {
    const chain = chains.get(i)
    if (!chain) return
    const src = chain[0]!.from
    const dst = chain[chain.length - 1]!.to
    const points: Pt[] = [pt(mainStart[src.layer]! + src.ms, chain[0]!.a)]
    for (const s of chain) {
      if (s.a === s.b) continue
      const ch = mainStart[s.from.layer]! + extent[s.from.layer]! + s.track
      points.push(pt(ch, s.a), pt(ch, s.b))
    }
    points.push(pt(mainStart[dst.layer]! - 1, chain[chain.length - 1]!.b))
    const head = !e.arrow ? 'none' : reversed.has(i) ? 'start' : 'end'
    routes.push({ edge: i, points, dashed: e.dashed, head, tag: tags[i] ?? null })
  })

  const boxes: PlacedBox[] = vnodes
    .filter(v => v.real)
    .map(v => {
      const p = pt(mainStart[v.layer]!, v.pos)
      return {
        id: v.id,
        x: p.x,
        y: p.y,
        w: td ? v.cs : v.ms,
        h: td ? v.ms : v.cs,
        lines: v.lines,
        shape: v.real!.shape,
      }
    })

  return {
    direction: g.direction,
    width: td ? crossSize : mainSize,
    height: td ? mainSize : crossSize,
    boxes,
    routes,
    legend,
  }
}
