export type Tier = 'hot' | 'warm' | 'cold'

/** A model-given rating, keyed by an exchange's fingerprint. */
export type Rating = {
  value: number
  urgency: number
  stale: boolean
  summary?: string
  source: 'turn' | 'fork'
}

/** One exchange as the pane draws it. */
export type PlanRow = {
  index: number
  tier: Tier
  score: number
  tokens: number
  label: string
  rated: boolean
}

export type Status = {
  mode: 'observe' | 'active'
  contextTokens: number
  window: number
  busy: boolean
  lastRun?: {
    at: number
    trigger: string
    before: number
    after: number
    hot: number
    warm: number
    cold: number
    archive?: string
    usedFork: boolean
  }
  note?: string
  /** HOT + WARM message budget; absent = the default */
  target?: number
  /** non-message context (tools, system prompt) measured at the last plan */
  overhead?: number
  /** archived content brought back: auto-attached to prompts, and search_archive calls with results */
  hits?: { auto: number; search: number }
}

/** MCP tool tiering: idle servers go behind ToolSearch at a re-tier. */
export type McpState = {
  enabled: boolean
  /** prompts seen this session */
  turn: number
  /** server -> turn it was last called */
  lastUsed: Record<string, number>
  /** servers currently deferred */
  deferred: string[]
}

declare module 'claude-code' {
  interface PluginState {
    'context-tiers': {
      status: Shaped<Status>
      plan: Shaped<PlanRow[]>
      ratings: Shaped<Record<string, Rating>>
      staleTopics: Shaped<string[]>
      mcp: Shaped<McpState>
    }
  }
}
