export type StepState = 'todo' | 'run' | 'done' | 'fail'

export type Step = { label: string; state: StepState }

export type Bar = {
  key: string
  label: string
  group: string
  /** target fraction 0..1, undefined = not exposed (n/a) */
  target?: number
  /** displayed fraction 0..1, eased toward target each tick */
  shown: number
  detail: string
}

/** Which trigger got the seed accepted: the post-clear watcher, classic.SessionStart, session.end, the first turn/prompt in the new context, or a press / command. */
export type SeedPath = 'watcher' | 'session.start' | 'session.end' | 'first-turn' | 'manual'

export type HState = 'idle' | 'writing' | 'ready' | 'clearing' | 'seeded' | 'stalled' | 'failed'

/** Store `handover:<sid>`: one record per session in the chain. */
export type HRecord = {
  /** sequence number of the handover this session's next attempt creates (A->B is #1) */
  n: number
  nonce: string
  state: HState
  startedAt: number
  updatedAt: number
  briefPath?: string
  agentIds: string[]
  /** session seeded into / failure text, when known */
  to?: string
  why?: string
  /** ms from the clear request to the accepted seed, and which trigger sent it */
  seedLatencyMs?: number
  seedPath?: SeedPath
}

/** What the pane draws about the record (a snapshot; the countdown is computed at draw time). */
export type HView = { n: number; state: HState; startedAt: number; from?: string; to?: string; why?: string; pending: boolean; seedLatencyMs?: number; seedPath?: SeedPath; retry?: { k: number; reason: string } }

export type AgentRow = { id: string; name: string; type: string; status: string; description: string }

/** What the pane draws about the inbox ledger. `since` is undefined until a brief is written. */
export type InboxView = {
  enabled: boolean
  total: number
  byKind: Record<string, number>
  since?: number
  last: { seq: number; ts: number; kind: string; agentId?: string; ex: string }[]
  forwarded?: string
}

export type BriefStatus =
  | { kind: 'none' }
  | { kind: 'writing' }
  | { kind: 'written'; path: string; isFactsOnly: boolean; why?: string; lines?: number }
  | { kind: 'failed'; reason: string }

export type View = {
  isOpen: boolean
  mode: 'pane' | 'band'
  frame: number
  /** context window: tokens in use (undefined before the first response) and window size */
  ctxTokens?: number
  ctxWindow: number
  ctxPercent?: number
  ctx: Bar
  bars: Bar[]
  costUsd?: number
  agents: AgentRow[]
  steps: Step[]
  brief: BriefStatus
  note: string
  /** ms epoch until which a second Clear-and-seed press confirms; 0 = none */
  confirmUntil: number
  /** agent ids the pending confirmation was shown for */
  confirmIds: string
  updatedAt: number
  hv: HView
  /** ms epoch until which a second Reset press confirms; 0 = none */
  resetUntil: number
  inbox: InboxView
}

declare module 'claude-code' {
  interface PluginState {
    handover: { view: View; band: number }
  }
}
