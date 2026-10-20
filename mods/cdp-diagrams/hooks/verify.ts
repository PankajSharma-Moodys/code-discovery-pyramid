// Badges each drawn edge with what `cdp verify-diagram` says of its file:line
// citation. The checker is a host command (`$.process.run`, CLI only); its
// result is cached per fence and per directory, so a re-render never runs it
// again. It prefers the copy `cdp install` vendored into the repo (the version
// that repo was set up with), then cdp on PATH, then the module. Any failure (no cdp, not a git repo, a parse error, a timeout, no
// process API) leaves the diagram without badges. Nothing reaches the model.

import type { Graph } from './mermaid.ts'
import { splitBlocks } from './mermaid.ts'

export type EdgeStatus = 'correct' | 'wrong_citation' | 'unsupported' | 'ambiguous' | 'uncited' | 'inferred'
export type Cite = { text: string; status: string; file: string | null; hint?: string; detail?: string }
export type CheckedEdge = { id: string; from: string; to: string; label: string; status: EdgeStatus; cites: Cite[] }
/** One diagram's checked edges, in the checker's (source) order. */
export type Verdict = { edges: CheckedEdge[] }

export type RunResult = { exitCode: number; stdout: string }
export type Run = (
  argv: readonly string[],
  init: { cwd?: string; env?: Record<string, string>; stdin?: string; timeoutMs?: number },
) => Promise<RunResult>

const STATUSES = new Set<string>(['correct', 'wrong_citation', 'unsupported', 'ambiguous', 'uncited', 'inferred'])

export const MARK: Record<EdgeStatus, string> = {
  correct: '✓',
  wrong_citation: '✗',
  unsupported: '?',
  ambiguous: '?',
  uncited: '?',
  inferred: '~',
}

const str = (v: unknown): v is string => typeof v === 'string'

/**
 * The first diagram of `cdp verify-diagram --json` output, or null for
 * anything but exit 0/3 with a well-formed diagram and no parse errors.
 */
export function parseVerdict(stdout: string, exitCode: number): Verdict | null {
  if (exitCode !== 0 && exitCode !== 3) return null
  let doc: unknown
  try {
    doc = JSON.parse(stdout)
  } catch {
    return null
  }
  const d = (doc as { diagrams?: unknown })?.diagrams
  if (!Array.isArray(d) || d.length < 1) return null
  const first = d[0] as { edges?: unknown; errors?: unknown }
  if (!Array.isArray(first?.edges) || (Array.isArray(first.errors) && first.errors.length > 0)) return null
  const edges: CheckedEdge[] = []
  for (const raw of first.edges as Record<string, unknown>[]) {
    if (!raw || !str(raw.from) || !str(raw.to) || !str(raw.status) || !STATUSES.has(raw.status)) return null
    const cites: Cite[] = Array.isArray(raw.cites)
      ? (raw.cites as Record<string, unknown>[])
          .filter(c => c && str(c.text) && str(c.status))
          .map(c => ({
            text: c.text as string,
            status: c.status as string,
            file: str(c.file) ? c.file : null,
            ...(str(c.hint) ? { hint: c.hint } : {}),
            ...(str(c.detail) ? { detail: c.detail } : {}),
          }))
      : []
    edges.push({
      id: str(raw.id) ? raw.id : `E${edges.length + 1}`,
      from: raw.from,
      to: raw.to,
      label: str(raw.label) ? raw.label : '',
      status: raw.status as EdgeStatus,
      cites,
    })
  }
  return { edges }
}

const norm = (s: string) =>
  s
    .toLowerCase()
    .replace(/<br\s*\/?>/g, ' ')
    .replace(/[^a-z0-9:._\-]+/g, ' ')
    .trim()

/** `[*]` in the checker is the start/end marker, which the drawing names `[*]start`, `[*]end` or the enclosing state. */
const endScore = (checked: string, drawn: string) => (checked === drawn ? 2 : checked === '[*]' ? 1 : 0)

/**
 * For each drawn edge (by index), the checked edge it is, or null. Endpoints
 * must agree; among several, the label decides, then source order.
 */
export function matchEdges(graph: Graph, verdict: Verdict): (CheckedEdge | null)[] {
  const out: (CheckedEdge | null)[] = graph.edges.map(() => null)
  for (const c of verdict.edges) {
    const cl = norm(c.label)
    let best = -1
    let bestScore = 0
    graph.edges.forEach((d, i) => {
      if (out[i]) return
      const f = endScore(c.from, d.from)
      const t = endScore(c.to, d.to)
      if (!f || !t) return
      const dl = norm(d.label)
      let score = f + t
      if (dl === cl) score += 4
      else if (c.cites.length && c.cites.every(x => dl.includes(norm(x.text)))) score += 2
      if (score > bestScore) {
        best = i
        bestScore = score
      }
    })
    if (best >= 0) out[best] = c
  }
  return out
}

const WORD: [EdgeStatus, string][] = [
  ['wrong_citation', 'wrong'],
  ['unsupported', 'unsupported'],
  ['ambiguous', 'ambiguous'],
  ['uncited', 'uncited'],
]

/** One line for under the diagram: "verified 7/8 edges; 1 wrong: A→B @ x.java:12 (try x.java:44)". */
export function verdictLine(graph: Graph, verdict: Verdict): string {
  const name = new Map(graph.nodes.map(n => [n.id, n.label[0] ?? n.id]))
  const nm = (id: string) => name.get(id) ?? id
  const cited = verdict.edges.filter(e => e.status !== 'inferred')
  const ok = cited.filter(e => e.status === 'correct').length
  const parts = [cited.length ? `verified ${ok}/${cited.length} edges` : 'no cited edges to verify']
  for (const [st, word] of WORD) {
    const bad = verdict.edges.filter(e => e.status === st)
    if (!bad.length) continue
    const e = bad[0]!
    const cite = e.cites.find(c => c.status !== 'correct') ?? e.cites[0]
    const at = cite ? ` @ ${cite.text}${cite.hint ? ` (try ${cite.hint.split('/').pop()})` : ''}` : ''
    parts.push(`${bad.length} ${word}: ${nm(e.from)}→${nm(e.to)}${at}${bad.length > 1 ? ', …' : ''}`)
  }
  const inferred = verdict.edges.length - cited.length
  if (inferred) parts.push(`${inferred} inferred`)
  return parts.join('; ')
}

/** FNV-1a over the text, with its length. */
export function fenceHash(source: string): string {
  const s = source.replace(/\s+$/, '')
  let h = 0x811c9dc5
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i)
    h = Math.imul(h, 0x01000193) >>> 0
  }
  return `${h.toString(16)}:${s.length}`
}

/** Where `cdp install` vendors CDP in a repo; its `cdp/` package runs with PYTHONPATH set here. */
export const VENDORED = '.claude/skills/cdp'

export type Command = { argv: readonly string[]; env?: Record<string, string> }

/**
 * Checker commands for `repo`, in order: the vendored copy (when present),
 * cdp on PATH, then the module from wherever python3 finds it.
 */
export function commandsFor(repo: string, vendored: boolean): Command[] {
  const out: Command[] = []
  if (vendored) out.push({ argv: ['python3', '-m', 'cdp.cli'], env: { PYTHONPATH: `${repo}/${VENDORED}` } })
  out.push({ argv: ['cdp'] }, { argv: ['python3', '-m', 'cdp.cli'] })
  return out
}

type Entry = { done: false; settled: Promise<void> } | { done: true; verdict: Verdict | null }

const MAX_ENTRIES = 256

/**
 * A run whose reply never came back. Seen live on the fullscreen terminal: a
 * `$.process.run` asked through a ui.render dispatch that the engine drew again
 * before the command ended never settled (the command itself exited). Nothing
 * of it is cached, so a later ask starts over.
 */
class Lost extends Error {}

/** Rejects with Lost when `p` has not settled `ms` after the call. */
function withDeadline<T>(p: Promise<T>, ms: number): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const t = setTimeout(() => reject(new Lost('no reply')), ms)
    p.then(
      v => {
        clearTimeout(t)
        resolve(v)
      },
      err => {
        clearTimeout(t)
        reject(err)
      },
    )
  })
}

export class Verifier {
  private allowed = new Set<string>()
  private cache = new Map<string, Entry>()
  private roots = new Map<string, Promise<string | null>>()
  private vendored = new Map<string, Promise<boolean>>()
  /** Per repo root, the command that answered last. */
  private working = new Map<string, number>()

  private timeoutMs: number
  /** How long past a run's own timeout its reply may take before it counts as lost. */
  private graceMs: number

  /** The git root and vendored-copy probes' timeout. */
  private stepMs: number

  constructor(timeoutMs = 15000, graceMs = 5000) {
    this.timeoutMs = timeoutMs
    this.stepMs = Math.min(5000, timeoutMs)
    this.graceMs = graceMs
  }

  /** Marks the fences of a CDP or diagram turn's answer for checking; how many were new. */
  allow(answer: string): number {
    let n = 0
    for (const b of splitBlocks(answer)) {
      if (b.kind !== 'mermaid') continue
      const h = fenceHash(b.source)
      if (!this.allowed.has(h)) n++
      this.allowed.add(h)
    }
    return n
  }

  isAllowed(source: string): boolean {
    return this.allowed.has(fenceHash(source))
  }

  /**
   * Starts the check of each allowed fence of `answer` (turn.complete calls
   * this with its own `$`, so no ui.render dispatch carries the run); how many
   * fences it asked for.
   */
  prefetch(answer: string, cwd: string, run: Run, invalidate: () => void): number {
    let n = 0
    for (const b of splitBlocks(answer)) {
      if (b.kind !== 'mermaid' || !this.isAllowed(b.source)) continue
      this.lookup(b.source, cwd, run, invalidate)
      n++
    }
    return n
  }

  /**
   * The verdict for a fence drawn in `cwd`: undefined while not allowed or
   * still running (the first ask starts it; `invalidate` runs once it ends),
   * null when it could not be checked. A run whose reply was lost leaves no
   * entry, so the next ask runs it again.
   */
  lookup(source: string, cwd: string, run: Run, invalidate: () => void): Verdict | null | undefined {
    if (!this.isAllowed(source)) return undefined
    const key = `${cwd}\u0000${fenceHash(source)}`
    const hit = this.cache.get(key)
    if (hit) return hit.done ? hit.verdict : undefined
    const settled = this.check(source, cwd, run).then(
      verdict => {
        this.cache.set(key, { done: true, verdict })
        try {
          invalidate()
        } catch {
          // a redraw that cannot be asked for waits for the next one
        }
      },
      err => {
        if (err instanceof Lost) this.cache.delete(key)
        else this.cache.set(key, { done: true, verdict: null })
      },
    )
    if (this.cache.size >= MAX_ENTRIES) this.cache.delete(this.cache.keys().next().value!)
    this.cache.set(key, { done: false, settled })
    return undefined
  }

  /** Resolves once every check started so far has ended. */
  async idle(): Promise<void> {
    await Promise.all([...this.cache.values()].map(e => (e.done ? undefined : e.settled)))
  }

  private root(cwd: string, run: Run): Promise<string | null> {
    let r = this.roots.get(cwd)
    if (!r) {
      r = withDeadline(run(['git', 'rev-parse', '--show-toplevel'], { cwd, timeoutMs: this.stepMs }), this.stepMs + this.graceMs).then(
        x => (x.exitCode === 0 && x.stdout.trim() ? x.stdout.trim() : null),
        err => {
          if (!(err instanceof Lost)) return null
          this.roots.delete(cwd)
          throw err
        },
      )
      this.roots.set(cwd, r)
    }
    return r
  }

  private hasVendored(repo: string, run: Run): Promise<boolean> {
    let v = this.vendored.get(repo)
    if (!v) {
      v = withDeadline(run(['test', '-f', `${repo}/${VENDORED}/cdp/cli.py`], { cwd: repo, timeoutMs: this.stepMs }), this.stepMs + this.graceMs).then(
        x => x.exitCode === 0,
        err => {
          if (!(err instanceof Lost)) return false
          this.vendored.delete(repo)
          throw err
        },
      )
      this.vendored.set(repo, v)
    }
    return v
  }

  private async check(source: string, cwd: string, run: Run): Promise<Verdict | null> {
    const repo = await this.root(cwd, run)
    if (!repo) return null
    const commands = commandsFor(repo, await this.hasVendored(repo, run))
    const known = this.working.get(repo)
    const order = known === undefined ? commands.map((_, i) => i) : [known]
    for (const i of order) {
      const c = commands[i]!
      const argv = [...c.argv, 'verify-diagram', '-', '--repo', repo, '--json']
      const started = Date.now()
      let r: RunResult
      try {
        r = await withDeadline(
          run(argv, { cwd: repo, ...(c.env ? { env: c.env } : {}), stdin: source, timeoutMs: this.timeoutMs }),
          this.timeoutMs + this.graceMs,
        )
      } catch (err) {
        if (err instanceof Lost) throw err
        // Cannot start: try the next command. A timeout: stop.
        if (Date.now() - started >= this.timeoutMs * 0.9) return null
        continue
      }
      let json = true
      try {
        JSON.parse(r.stdout)
      } catch {
        json = false
      }
      // Started but not the checker (no such module, an old cdp): the next one.
      if (!json) continue
      this.working.set(repo, i)
      return parseVerdict(r.stdout, r.exitCode)
    }
    return null
  }
}
