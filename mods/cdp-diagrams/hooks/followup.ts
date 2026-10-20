// After the person chose diagrams (offer.ts), starts one follow-up turn asking
// Claude to draw them from its previous answer: the mod's one deliberate
// message to the model. While that turn runs, main-loop tool calls are denied
// (the diagram draws from what is already in context). Pure apart from the
// `submit` it is handed; register.tsx gives it `$.prompt.submit`.

import type { DiagramChoice, DiagramKind } from './offer.ts'

const FENCE: Record<DiagramKind, string> = {
  flowchart: '```mermaid flowchart',
  state: '```mermaid stateDiagram-v2',
}

export const DENY = 'cdp-diagrams: diagram turn draws from the answer already given; no tools'

/** The follow-up prompt for the chosen kinds, in the order given; wording follows cdp/guide.py DIAGRAM_RULE. */
export function followUpPrompt(kinds: readonly DiagramKind[]): string {
  const ks = kinds.filter((k, i) => kinds.indexOf(k) === i)
  if (!ks.length) throw new RangeError('followUpPrompt: no diagram kinds')
  const blocks = ks.map(k => `a ${FENCE[k]} block`).join(', then ')
  const inferred: string[] = []
  if (ks.includes('flowchart')) inferred.push('dash inferred edges (`-.->`)')
  // stateDiagram-v2 cannot dash edges, so the label says it.
  if (ks.includes('state')) inferred.push('end inferred transition labels with "(inferred)"')
  return [
    `Draw your previous answer as ${blocks}.`,
    'Use only facts already in that answer and the CDP results above it; use no tools.',
    'Label each edge with the file:line that performs it (a call, assignment or transition, never a declaration);',
    `${inferred.join('; ')}.`,
    'No prose beyond one line per diagram, ending "+N not shown: ..." when items are left out.',
  ].join(' ')
}

/** The answer a follow-up turn draws, and what it was asked to draw. */
export type DiagramLink = { answerTurnId: string; answer: string; kinds: DiagramKind[] }

export type Submit = (text: string) => Promise<{ drop?: string } | unknown>

type Loop = { agentId?: string }

/**
 * One follow-up at a time. The flag is set before `submit` (the plugin's own
 * prompt.submit hook is skipped for its own submit), claims the next main-loop
 * turn.start as the follow-up, and clears at that loop's next turn.complete
 * whatever its reason, on a dropped submit, and on a rejected one.
 */
export class DiagramFollowUp {
  private armed: DiagramLink | null = null
  private activeTurn: string | null = null
  private turns = new Map<string, DiagramLink>()

  /** Whether a follow-up is armed or running. */
  busy(): boolean {
    return this.armed !== null
  }

  /**
   * Arms the flag, runs `before` (M2's expectFollowUp), then submits once.
   * Resolves true when the prompt entered; on a drop or rejection the flag is
   * cleared and `undo` runs. Never rejects.
   */
  async begin(choice: DiagramChoice, answerTurnId: string, answer: string, submit: Submit, before = () => {}, undo = () => {}): Promise<boolean> {
    if (this.armed || !choice.kinds.length) return false
    const link: DiagramLink = { answerTurnId, answer, kinds: [...choice.kinds] }
    this.armed = link
    let ok = false
    try {
      before()
      const r = (await submit(followUpPrompt(link.kinds))) as { drop?: string } | undefined
      ok = !(r && typeof r === 'object' && typeof r.drop === 'string')
    } catch {
      ok = false
    }
    if (!ok && this.armed === link) {
      this.clear()
      try {
        undo()
      } catch {
        // the undo's failure is its own
      }
    }
    return ok
  }

  /** turn.start: the first main-loop turn while armed is the follow-up. */
  start(e: Loop & { turnId: string }): void {
    if (e.agentId !== undefined || !this.armed || this.activeTurn !== null) return
    this.activeTurn = e.turnId
    this.turns.set(e.turnId, this.armed)
  }

  /** The deny reason for a tool call, or null to let it run: main loop only, while armed. */
  denies(e: Loop): string | null {
    return e.agentId === undefined && this.armed ? DENY : null
  }

  /** turn.complete: any main-loop end while armed ends the follow-up. */
  complete(e: Loop): void {
    if (e.agentId === undefined && this.armed) this.clear()
  }

  /** Whether `turnId` is a follow-up turn this mod started. */
  isDiagramTurn(turnId: string): boolean {
    return this.turns.has(turnId)
  }

  /** The answer and kinds a follow-up turn was for, or null. */
  diagramFor(turnId: string): DiagramLink | null {
    return this.turns.get(turnId) ?? null
  }

  private clear(): void {
    this.armed = null
    this.activeTurn = null
  }
}
