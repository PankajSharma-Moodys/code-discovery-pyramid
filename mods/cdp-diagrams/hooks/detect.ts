// Detects whether a main-loop turn was answered using CDP: an MCP CDP tool
// call, or a Bash call that runs the `cdp` CLI. Pure; register.tsx feeds it
// the `turn.start`, `tool.call` and `turn.complete` events and only observes.

/** `mcp__cdp__<tool>`, or a plugin-prefixed server ending in `__cdp_<tool>`. */
const MCP_CDP = /^mcp__(cdp__.+|.+__cdp_[a-z_]+)$/

/** Words that run the command after them (`env`, `time`, `uv run`, ...). */
const WRAPPERS = new Set(['env', 'time', 'command', 'exec', 'nohup', 'sudo', 'nice'])
const RUNNERS = new Set(['uv', 'poetry', 'pipenv', 'pdm', 'hatch', 'rye'])

/** Splits a shell command into simple commands, each a list of words; quotes respected. */
export function simpleCommands(command: string): string[][] {
  const out: string[][] = []
  let words: string[] = []
  let word = ''
  let inWord = false
  let quote: '' | "'" | '"' = ''
  const endWord = () => {
    if (inWord) words.push(word)
    word = ''
    inWord = false
  }
  const endCommand = () => {
    endWord()
    if (words.length) out.push(words)
    words = []
  }
  for (let i = 0; i < command.length; i++) {
    const c = command[i]!
    if (quote) {
      if (c === quote) quote = ''
      else if (c === '\\' && quote === '"' && i + 1 < command.length) word += command[++i]
      else word += c
      continue
    }
    if (c === "'" || c === '"') {
      quote = c
      inWord = true
    } else if (c === '\\' && i + 1 < command.length) {
      word += command[++i]
      inWord = true
    } else if (c === ' ' || c === '\t') endWord()
    else if (';&|\n()`{}'.includes(c)) endCommand()
    else if (c === '$' && command[i + 1] === '(') {
      endCommand()
      i++
    } else {
      word += c
      inWord = true
    }
  }
  endCommand()
  return out
}

const base = (w: string) => w.slice(w.lastIndexOf('/') + 1)

/** True when one simple command runs the cdp CLI. */
function runsCdp(words: string[]): boolean {
  let i = 0
  for (;;) {
    const w = words[i]
    if (w === undefined) return false
    if (/^[A-Za-z_][A-Za-z0-9_]*=/.test(w) || WRAPPERS.has(w)) i++
    else if (RUNNERS.has(w) && words[i + 1] === 'run') i += 2
    else break
  }
  const cmd = base(words[i]!)
  if (cmd === 'cdp') return true
  if (/^python[0-9.]*$/.test(cmd)) {
    const m = words.indexOf('-m', i + 1)
    return m > 0 && (words[m + 1] === 'cdp.cli' || words[m + 1] === 'cdp')
  }
  return false
}

/** True when a tool call (`e.tool` and the arguments beside it) is a CDP call. */
export function isCdpToolCall(tool: string, input: Record<string, unknown>): boolean {
  if (MCP_CDP.test(tool)) return true
  if (tool !== 'Bash' || typeof input.command !== 'string') return false
  return simpleCommands(input.command).some(runsCdp)
}

type Loop = { agentId?: string }

/** Per-turn state for the main loop; subagent events (`agentId` set) are ignored. */
export class CdpTurnTracker {
  private used = false
  private last = false

  start(e: Loop): void {
    if (e.agentId !== undefined) return
    this.used = false
  }

  call(e: Loop & { tool: string }): void {
    if (e.agentId !== undefined || this.used) return
    if (isCdpToolCall(String(e.tool), e as Record<string, unknown>)) this.used = true
  }

  /** Settles the turn; undefined for a subagent's end, else whether it used CDP. */
  complete(e: Loop): boolean | undefined {
    if (e.agentId !== undefined) return undefined
    this.last = this.used
    this.used = false
    return this.last
  }

  /** Whether the last main-loop turn that completed used CDP. */
  lastTurnUsedCdp(): boolean {
    return this.last
  }
}
