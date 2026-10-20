// After a main-loop turn that used CDP ends with an answer, offers to draw a
// diagram of it: "Yes"/"No", then (on Yes) a multi-select of the kinds. Pure
// apart from the `ask` it is handed; register.tsx gives it `$.ui.ask`. It
// only records the choice (`pending()`, `onChoice`); followup.ts acts on it.

export type DiagramKind = 'flowchart' | 'state'

/** What the person chose: at least one kind; null is "no diagram". */
export type DiagramChoice = { kinds: DiagramKind[] }

export type Ask = (
  question: string,
  options: readonly string[] | { options: readonly string[]; header?: string; multiSelect?: true },
) => Promise<string>

export const QUESTION = 'Draw a diagram of that answer?'
export const KIND_PROMPT = 'Which diagrams?'
export const KIND_QUESTION = { options: ['Flowchart', 'State machine'], multiSelect: true, header: 'Diagram' } as const
const LABELS = new Map<string, DiagramKind>([
  ['Flowchart', 'flowchart'],
  ['State machine', 'state'],
])

/** Parses screen 2's answer (labels joined by ", "); only exact labels count, so typed text or none is null. */
export function parseKinds(answer: string): DiagramChoice | null {
  const kinds: DiagramKind[] = []
  for (const part of answer.split(', ')) {
    const k = LABELS.get(part)
    if (k !== undefined && !kinds.includes(k)) kinds.push(k)
  }
  return kinds.length ? { kinds } : null
}

/** Runs both screens; any rejection (dismissed, `-p`) or anything but an exact "Yes" is null. */
export async function askChoice(ask: Ask): Promise<DiagramChoice | null> {
  try {
    if ((await ask(QUESTION, ['Yes', 'No'])) !== 'Yes') return null
    return parseKinds(await ask(KIND_PROMPT, KIND_QUESTION))
  } catch {
    return null
  }
}

/** The fields of `turn.complete` the offer reads. */
export type TurnEnd = { turnId: string; reason: string; isAborted: boolean; agentId?: string; answer: string }

export type OnChoice = (choice: DiagramChoice | null, answer: string) => void

/** Decides when to offer, keeps one offer per turn and one open at a time, and holds the result. */
export class DiagramOffer {
  private offered = new Set<string>()
  private open = false
  private followUp = false
  private choice: DiagramChoice | null = null
  private settled: Promise<void> = Promise.resolve()
  onChoice: OnChoice | null = null

  /** Marks the next main-loop turn as the mod's own diagram follow-up: no offer at its end. */
  expectFollowUp(): void {
    this.followUp = true
  }

  /** Withdraws the mark when the follow-up never started (its submit dropped or failed). */
  cancelFollowUp(): void {
    this.followUp = false
  }

  /** The last choice made (null after No, a dismissal or no kinds). */
  pending(): DiagramChoice | null {
    return this.choice
  }

  /** Clears the stored choice once acted on. */
  take(): DiagramChoice | null {
    const c = this.choice
    this.choice = null
    return c
  }

  /** Resolves once the latest offer, if any, has settled. */
  idle(): Promise<void> {
    return this.settled
  }

  /** Whether this turn end should be offered; consumes the follow-up mark on a main-loop end. */
  shouldOffer(e: TurnEnd, usedCdp: boolean): boolean {
    if (e.agentId !== undefined) return false
    if (this.followUp) {
      this.followUp = false
      return false
    }
    if (e.reason !== 'answer' || e.isAborted || !e.answer.trim() || !usedCdp) return false
    return !this.open && !this.offered.has(e.turnId)
  }

  /** Offers for `e` when it qualifies; never rejects. Returns whether an offer started. */
  maybeOffer(e: TurnEnd, usedCdp: boolean, ask: Ask): boolean {
    if (!this.shouldOffer(e, usedCdp)) return false
    this.offered.add(e.turnId)
    this.open = true
    const answer = e.answer
    this.settled = askChoice(ask).then(choice => {
      this.open = false
      this.choice = choice
      try {
        this.onChoice?.(choice, answer)
      } catch {
        // a hook point's failure is its own
      }
    })
    return true
  }
}
