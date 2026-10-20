// Where a diagram follow-up's drawing goes. Render props carry no turnId, so
// rows are told apart by their text: the answer row by the text the follow-up
// was for, the reply row by the follow-up's own answer (both whitespace-
// normalised). Only the fullscreen terminal redraws a row printed earlier
// (RESEARCH_M0 §2), so only there does the drawing move above the answer; on
// the main screen, desktop and anywhere the mode is not reported it stays in
// the reply row. Moving is a handshake per surface, so one drawing shows:
//   1. the follow-up completes: `complete` records the pair (invalidate);
//   2. the reply row draws, sees the pair: `replyRow` marks it seen (invalidate);
//   3. the answer row draws, the reply seen and its text unique: `answerRow`
//      claims the pair and draws it above (invalidate);
//   4. the reply row draws again: claimed, so a one-line pointer.
// Until step 3 the reply row draws the diagram itself, so an answer row that
// never draws again (no match, or matched twice) leaves the fallback standing.
// Pure: register.tsx hands it the render facts and invalidates on `true`.

/** Whitespace runs folded to one space, ends trimmed. */
export const norm = (s: string): string => s.replace(/\s+/g, ' ').trim()

/** Whether this drawing can redraw earlier rows: the terminal under fullscreen, said by `RenderViewport.isFullscreen`. */
export const canPlaceAbove = (surface: string, viewport: { isFullscreen?: boolean } | undefined): boolean =>
  surface === 'terminal' && viewport?.isFullscreen === true

export const POINTER = 'diagram drawn above the answer ↑'

type Pair = { answer: string; reply: string; replyText: string; seen: Set<string>; claimed: Set<string> }

export type ReplyRow = { kind: 'pointer' } | { kind: 'draw' }

export class DiagramPlacement {
  /** Normalised answer → how many main-loop turns ended with it. */
  private answers = new Map<string, number>()
  /** One pair per answer: a later follow-up for the same answer replaces it. */
  private pairs = new Map<string, Pair>()

  /**
   * Every main-loop turn.complete: counts answers so a repeated one is not
   * matched. True when that made a placed pair ambiguous (invalidate: it falls back).
   */
  count(answer: string): boolean {
    const a = norm(answer)
    if (!a) return false
    const n = (this.answers.get(a) ?? 0) + 1
    this.answers.set(a, n)
    return n === 2 && [...this.pairs.values()].some(p => p.answer === a || p.reply === a)
  }

  /** A diagram follow-up completed with `reply`, drawing `answer`. True when a pair was recorded. */
  complete(answer: string, reply: string): boolean {
    const a = norm(answer)
    const r = norm(reply)
    if (!a || !r || a === r) return false
    this.pairs.set(a, { answer: a, reply: r, replyText: reply, seen: new Set(), claimed: new Set() })
    return true
  }

  private unique(s: string): boolean {
    return (this.answers.get(s) ?? 0) <= 1
  }

  private pairForReply(r: string): Pair | null {
    let hit: Pair | null = null
    for (const p of this.pairs.values()) if (p.reply === r) {
      if (hit) return null
      hit = p
    }
    return hit
  }

  /**
   * A row with text `text` drawn on `surface`: when it is a recorded reply, whether
   * it draws a pointer or the diagram, and whether it changed state (invalidate).
   * Null when the row is no reply.
   */
  replyRow(text: string, surface: string, above: boolean): { row: ReplyRow; changed: boolean } | null {
    const p = this.pairForReply(norm(text))
    if (!p) return null
    if (!above || !this.unique(p.answer) || !this.unique(p.reply)) return { row: { kind: 'draw' }, changed: false }
    if (p.claimed.has(surface)) return { row: { kind: 'pointer' }, changed: false }
    const changed = !p.seen.has(surface)
    p.seen.add(surface)
    return { row: { kind: 'draw' }, changed }
  }

  /**
   * A row with text `text` on `surface`: when it is the answer of a pair whose
   * reply row was seen there, the reply text to draw above it and whether this
   * claimed it (invalidate). Null to leave the row as it is.
   */
  answerRow(text: string, surface: string, above: boolean): { reply: string; changed: boolean } | null {
    if (!above) return null
    const a = norm(text)
    const p = this.pairs.get(a)
    if (!p || !this.unique(a) || !this.unique(p.reply) || !p.seen.has(surface)) return null
    const changed = !p.claimed.has(surface)
    p.claimed.add(surface)
    return { reply: p.replyText, changed }
  }
}
