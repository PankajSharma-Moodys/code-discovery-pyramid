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

export type AgentRow = { id: string; name: string; type: string; status: string; description: string }

export type BriefStatus =
  | { kind: 'none' }
  | { kind: 'writing' }
  | { kind: 'written'; path: string; isFactsOnly: boolean; why?: string }
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
}

declare module 'claude-code' {
  interface PluginState {
    handover: { view: View }
  }
}
