import { atom, read, update } from 'claude-code'
import type { EngineInterface as Engine, Register, SessionMessage } from 'claude-code'

import type { McpState, PlanRow, Rating, Status, Tier } from '../types'

// ---- knobs -------------------------------------------------------------
const THRESHOLD = 200_000 // total context tokens (tools + system + messages) at which re-tiering fires
const HOT_TOKENS = 30_000 // newest exchanges always kept verbatim
const DEFAULT_TARGET = 60_000 // HOT + WARM message budget after re-tiering (/tiers target N)
const MIN_HEADROOM = 50_000 // after a re-tier, at least this much growth before the next one
const FORK_MAX = 120 // most exchanges the fork pass rates at once
const FORK_TIMEOUT_MS = 90_000
const MCP_IDLE_TURNS = 10 // an MCP server unused for this many prompts is deferred at a re-tier
const MCP_PINNED = new Set(['context-tiers'])
const W = { recency: 0.35, refs: 0.15, value: 0.3, urgency: 0.2, stale: 0.4 }

const PLUGIN = 'context-tiers'
const PANE = 'context-tiers'
const MARK = 'context-tiers:retier'
const TOOL = 'mcp__context-tiers__rate_context'
const SEARCH_TOOL = 'mcp__context-tiers__search_archive'
const AUTO_HITS = 4 // archived snippets attached per prompt
const AUTO_CHARS = 8_000 // ~2K tokens

const status = atom({ plugin: 'context-tiers', key: 'status' } as const,
  { mode: 'observe', contextTokens: 0, window: 0, busy: false } as Status,
  { shape: 'status-1' })
const plan = atom({ plugin: 'context-tiers', key: 'plan' } as const, [] as PlanRow[],
  { shape: 'plan-1' })
const ratings = atom({ plugin: 'context-tiers', key: 'ratings' } as const,
  {} as Record<string, Rating>, { shape: 'ratings-1' })
const staleTopics = atom({ plugin: 'context-tiers', key: 'staleTopics' } as const,
  [] as string[], { shape: 'stale-1' })
const mcp = atom({ plugin: 'context-tiers', key: 'mcp' } as const,
  { enabled: false, turn: 0, lastUsed: {}, deferred: [] } as McpState, { shape: 'mcp-1' })

// ---- exchanges -----------------------------------------------------------
type Exchange = {
  index: number
  messages: SessionMessage[]
  tokens: number
  label: string
  fp: string
  ids: string[]
  text: string
}

const isPromptStart = (m: SessionMessage) =>
  m.role === 'user' && m.text.trim() !== '' && !(m.toolResults?.length)

const msgChars = (m: SessionMessage) =>
  m.text.length +
  (m.role === 'assistant'
    ? m.toolUses.reduce((n, t) => n + JSON.stringify(t.input ?? {}).length, 0)
    : (m.toolResults ?? []).reduce((n, r) => n + (r.text?.length ?? 0), 0))

const fullText = (m: SessionMessage) =>
  [
    m.text,
    ...m.toolUses.map(t => `[${t.tool}] ${JSON.stringify(t.input ?? {})}`),
    ...(m.toolResults ?? []).map(r => r.text ?? ''),
  ].join('\n')

const hash = (s: string) => {
  let h = 5381
  for (let i = 0; i < s.length; i++) h = ((h << 5) + h + s.charCodeAt(i)) | 0
  return (h >>> 0).toString(36)
}

// The lookbehind starts a match only at a token's start and the run is
// bounded: `[\w./-]+` alone backtracks from every position of a long token
// (logs, minified JSON, base64), which made re-tiering quadratic.
const ID_RE =
  /(?<![\w./-])[\w./-]{1,200}\.(?:tsx?|jsx?|java|kt|py|go|ya?ml|json|md|sql|xml|sh|gradle|properties)\b|`[^`\n]{3,60}`/g
const ID_SCAN_CHARS = 60_000

function toExchanges(messages: readonly SessionMessage[]): Exchange[] {
  const groups: SessionMessage[][] = []
  for (const m of messages) {
    if (groups.length === 0 || isPromptStart(m)) groups.push([m])
    else groups[groups.length - 1]?.push(m)
  }
  return groups.map((msgs, index) => {
    const first = msgs.find(isPromptStart) ?? msgs[0] ?? { role: 'user' as const, text: '', toolUses: [] }
    const text = msgs.map(fullText).join('\n')
    const label = first.text.replace(/\s+/g, ' ').trim().slice(0, 70) || '(no text)'
    const ids = [...new Set((text.slice(0, ID_SCAN_CHARS).match(ID_RE) ?? []).map(s => s.toLowerCase()))].slice(0, 30)
    return {
      index,
      messages: msgs,
      tokens: Math.ceil(msgs.reduce((n, m) => n + msgChars(m), 0) / 4),
      label,
      fp: hash(first.text.slice(0, 400)),
      ids,
      text: text.slice(0, 20_000).toLowerCase(),
    }
  })
}

// ---- scoring & planning --------------------------------------------------
type Scored = Exchange & { score: number; tier: Tier; rated: boolean; stale: boolean }

function score(exs: Exchange[], rated: Record<string, Rating>, stale: string[]): Scored[] {
  const n = exs.length
  const staleLc = stale.map(s => s.toLowerCase()).filter(s => s.length >= 3)
  return exs.map((ex, i) => {
    const refs = ex.ids.length === 0 ? 0
      : exs.slice(i + 1).filter(later => ex.ids.some(id => later.text.includes(id))).length
    const r = rated[ex.fp]
    const isStale = (r?.stale ?? false) || staleLc.some(t => ex.text.includes(t))
    const s =
      W.recency * (n <= 1 ? 1 : i / (n - 1)) +
      W.refs * Math.min(1, refs / 3) +
      W.value * (r?.value ?? 0.5) +
      W.urgency * (r?.urgency ?? 0.3) -
      (isStale ? W.stale : 0)
    return { ...ex, score: Math.round(s * 100) / 100, tier: 'cold', rated: r !== undefined, stale: isStale }
  })
}

// The message budget after a re-tier. THRESHOLD counts the whole context, so
// the budget leaves room for the non-message overhead (tool schemas, system
// prompt) plus MIN_HEADROOM; otherwise a re-tier lands just under the
// threshold and fires again a few turns later.
function budgetFor(st: Status): number {
  const target = st.target ?? DEFAULT_TARGET
  const room = THRESHOLD - (st.overhead ?? 0) - MIN_HEADROOM
  return Math.max(HOT_TOKENS + 10_000, Math.min(target, room))
}

function assignTiers(scored: Scored[], budget: number): Scored[] {
  const out = scored.map(s => ({ ...s }))
  let used = 0
  let hotCount = 0
  for (let i = out.length - 1; i >= 0; i--) {
    if (used >= HOT_TOKENS && hotCount >= 2) break
    const x = out[i]!
    x.tier = 'hot'
    used += x.tokens
    hotCount++
  }
  for (const s of out) {
    if (s.tier === 'cold' && !s.stale && s.score >= 0.75 && s.tokens < HOT_TOKENS / 2) {
      // urgent/high value: pin
      s.tier = 'hot'
      used += s.tokens
    }
  }
  const rest = out.filter(s => s.tier === 'cold').sort((a, b) => b.score - a.score)
  for (const s of rest) {
    if (used + s.tokens <= budget) {
      s.tier = 'warm'
      used += s.tokens
    }
  }
  return out
}

const toRows = (s: Scored[]): PlanRow[] =>
  s.map(x => ({ index: x.index, tier: x.tier, score: x.score, tokens: x.tokens, label: x.label, rated: x.rated }))

// ---- fork rating pass ----------------------------------------------------
function forkPrompt(exs: Exchange[]): string {
  const lines = exs.map(e => `#${e.index}: ${e.label}`).join('\n')
  return [
    'Context-manager request. You have no tools: answer at once, without deliberating.',
    'The conversation above is split into exchanges, each opened by a user prompt:',
    lines,
    '',
    'Return ONLY a JSON array, one object per listed exchange:',
    '{"i":<number>,"value":<0..1, how much it still matters to the current work>,',
    '"urgency":<0..1, unresolved asks or open loops>,"stale":<true if superseded or no longer relevant>,',
    '"summary":"<=25 words: the concrete facts, decisions, paths or numbers worth keeping"}',
  ].join('\n')
}

async function forkRate($: Engine, exs: Exchange[]): Promise<boolean> {
  if (exs.length === 0) return false
  const batch = exs.slice(-FORK_MAX)
  const reply = await Promise.race([
    $.model.fork({ prompt: forkPrompt(batch) }),
    $.clock.sleep(FORK_TIMEOUT_MS).then(() => ({ isAnswered: false as const, reason: 'timeout' })),
  ])
  if (!reply.isAnswered) return false
  const raw: string = reply.text ?? ''
  const start = raw.indexOf('[')
  const end = raw.lastIndexOf(']')
  if (start < 0 || end <= start) return false
  let parsed: unknown
  try {
    parsed = JSON.parse(raw.slice(start, end + 1))
  } catch {
    return false
  }
  if (!Array.isArray(parsed)) return false
  const byIndex = new Map(batch.map(e => [e.index, e]))
  const fresh: Record<string, Rating> = {}
  for (const item of parsed as Record<string, unknown>[]) {
    const ex = byIndex.get(Number(item.i))
    if (!ex) continue
    fresh[ex.fp] = {
      value: clamp01(item.value),
      urgency: clamp01(item.urgency),
      stale: item.stale === true,
      summary: typeof item.summary === 'string' ? item.summary.slice(0, 300) : undefined,
      source: 'fork',
    }
  }
  await update($, ratings, old => ({ ...old, ...fresh }))
  return Object.keys(fresh).length > 0
}

// What the fork should rate: only exchanges whose rating could change the
// outcome and that lack one. Nothing at all when every exchange fits the
// budget, since then nothing can be archived whatever the ratings say.
function forkCandidates(tiered: Scored[], rated: Record<string, Rating>, budget: number): Exchange[] {
  const total = tiered.reduce((n, x) => n + x.tokens, 0)
  if (total <= budget) return []
  return tiered.filter(x => x.tier !== 'hot' && !rated[x.fp]?.summary && (x.tier === 'cold' || !x.rated))
}

const clamp01 = (v: unknown) => {
  const n = Number(v)
  return Number.isFinite(n) ? Math.min(1, Math.max(0, n)) : 0.5
}

// ---- building the re-tiered transcript -----------------------------------
function fallbackSummary(ex: Exchange): string {
  const lastAssistant = [...ex.messages].reverse().find(m => m.role === 'assistant' && m.text.trim())
  const answer = lastAssistant?.text.replace(/\s+/g, ' ').trim().slice(0, 160) ?? ''
  return `asked "${ex.label}"${answer ? ` → ${answer}` : ''}`
}

function archiveMarkdown(cold: Exchange[]): string {
  return cold
    .map(ex => {
      const body = ex.messages
        .map(m => `### ${m.role}\n\n${fullText(m)}`)
        .join('\n\n')
      return `## Exchange #${ex.index}: ${ex.label}\n\n${body}`
    })
    .join('\n\n---\n\n')
}

function stubFor(ex: Scored, rated: Record<string, Rating>, archive: string): string {
  return [
    `[context-tiers] My earlier work on exchange #${ex.index} was archived (score ${ex.score.toFixed(2)}).`,
    `Summary: ${rated[ex.fp]?.summary ?? fallbackSummary(ex)}`,
    `For details call search_archive, or Read "Exchange #${ex.index}" in ${archive}.`,
  ].join('\n')
}

// COLD exchanges keep the user's own prompt verbatim (instructions are never
// evicted) and replace only Claude's work with an assistant-role stub.
function rebuild(tiered: Scored[], rated: Record<string, Rating>, archive: string): SessionMessage[] {
  const out: SessionMessage[] = []
  for (const ex of tiered) {
    if (ex.tier !== 'cold') {
      out.push(...ex.messages)
      continue
    }
    const prompts = ex.messages.filter(isPromptStart)
    out.push(...prompts)
    const lastRole = out[out.length - 1]?.role
    out.push({ role: lastRole === 'assistant' ? 'user' : 'assistant', text: stubFor(ex, rated, archive), toolUses: [] })
  }
  return out
}

// ---- system prompt section -----------------------------------------------
const SECTION = [
  '# Context rating (context-tiers mod)',
  'A context manager re-tiers this conversation when it grows large: high-value exchanges stay verbatim, low-value ones are replaced with short summaries pointing at an archive file.',
  `Help it by calling \`${TOOL}\` to rate the current exchange (the user's latest prompt and your work on it):`,
  '- value: 0..1, how much this exchange will matter for later work; urgency: 0..1, open loops left unresolved; stale_topics: short phrases from EARLIER discussion this exchange superseded.',
  '- Call it at most once per turn, and only in the same batch as another tool call you are already making. Do not make a turn longer just to rate it. Never mention the rating to the user.',
  'When you see a "[context-tiers] ... archived" message and need its details, call search_archive.',
].join('\n')

// ---- search index (SQLite FTS5 via the sqlite3 CLI) ----------------------
const SECRET_RE =
  /eyJ[\w-]{10,}\.[\w-]{10,}\.[\w-]{10,}|\b(?:sk-|ghp_|gho_|github_pat_|xox[abpr]-|AKIA)[\w-]{12,}|-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----|\b(?:token|secret|password|passwd|api[_-]?key)(["']?\s*[:=]\s*)["']?[^\s"']{8,}/gi
const mask = (t: string) => t.replace(SECRET_RE, (m, sep?: string) => (sep ? `${m.split(sep)[0]}${sep}[REDACTED]` : '[REDACTED]'))
const sq = (t: string) => `'${t.replace(/'/g, "''")}'`
const STOP = new Set('the and for are but not you your with this that have from was were what when where which will would could should about into then than them they their there here been just also can how why who our out use any all its it\'s let get got yes okay please thanks make like want need does did done more some such only very'.split(' '))
const CHUNK = 2000

type Hit = { session: string; exchange: number; role: string; label: string; at: number; archive: string; snip: string }

const dbPath = (home: string) => `${home}/.claude/context-tiers/archive.db`

async function sql($: Engine, home: string, script: string, json = false): Promise<string> {
  const argv = json ? ['sqlite3', '-json', dbPath(home)] : ['sqlite3', dbPath(home)]
  const r = await $.process.run(argv, { stdin: script, timeoutMs: 30_000 })
  if (r.exitCode !== 0) throw new Error(`sqlite3: ${r.stderr.slice(0, 200)}`)
  return r.stdout
}

const SCHEMA =
  "CREATE VIRTUAL TABLE IF NOT EXISTS docs USING fts5(text, session UNINDEXED, exchange UNINDEXED, role UNINDEXED, label UNINDEXED, at UNINDEXED, archive UNINDEXED, tokenize='porter unicode61');"

async function indexCold($: Engine, home: string, sid: string, at: number, archive: string, cold: Exchange[]): Promise<number> {
  const rows: string[] = []
  for (const ex of cold) {
    for (const m of ex.messages) {
      const parts: [string, string][] = []
      if (m.text.trim()) parts.push([m.role, m.text])
      for (const t of m.toolUses) parts.push(['tool-call', `[${t.tool}] ${JSON.stringify(t.input ?? {})}`])
      for (const r of m.toolResults ?? []) if (r.text?.trim()) parts.push(['tool-result', r.text])
      for (const [role, text] of parts) {
        const clean = mask(text)
        for (let i = 0; i < clean.length && i < CHUNK * 20; i += CHUNK) {
          rows.push(`(${sq(clean.slice(i, i + CHUNK))},${sq(sid)},${ex.index},${sq(role)},${sq(ex.label)},${at},${sq(archive)})`)
        }
      }
    }
  }
  if (rows.length === 0) return 0
  await sql($, home, `${SCHEMA}\nBEGIN;\nINSERT INTO docs(text,session,exchange,role,label,at,archive) VALUES\n${rows.join(',\n')};\nCOMMIT;\n`)
  return rows.length
}

const queryWords = (text: string) =>
  [...new Set((text.toLowerCase().match(/[a-z0-9_]{3,}/g) ?? []).filter(w => !STOP.has(w)))].slice(0, 16)

async function searchArchive($: Engine, query: string, limit: number, snipTokens: number, strict: boolean): Promise<Hit[]> {
  const home = (await $.env.get('HOME')) ?? '.'
  if (!(await $.fs.exists(dbPath(home)))) return []
  const words = queryWords(query)
  if (words.length === 0) return []
  const sid = await $.session.id()
  const match = words.map(w => `"${w}"`).join(' OR ')
  const out = await sql($, home,
    `SELECT session, exchange, role, label, at, archive, lower(text) AS lc, snippet(docs, 0, '«', '»', '…', ${snipTokens}) AS snip FROM docs WHERE docs MATCH ${sq(match)} ORDER BY bm25(docs) - (CASE WHEN session = ${sq(sid)} THEN 1.0 ELSE 0 END) LIMIT ${limit * 4};`, true)
  if (!out.trim()) return []
  const rows = JSON.parse(out) as (Hit & { lc: string })[]
  // keep hits that share enough distinct words with the query (OR-matching alone is noisy)
  const need = strict ? Math.max(2, Math.ceil(words.length * 0.3)) : 1
  const seen = new Set<string>()
  const hits: Hit[] = []
  for (const r of rows) {
    const overlap = words.filter(w => r.lc.includes(w)).length
    const key = `${r.session}#${r.exchange}#${r.snip}`
    if (overlap < need || seen.has(key)) continue
    seen.add(key)
    hits.push({ session: r.session, exchange: Number(r.exchange), role: r.role, label: r.label, at: Number(r.at), archive: r.archive, snip: r.snip })
    if (hits.length >= limit) break
  }
  return hits
}

const formatHits = (hits: Hit[], sid: string) =>
  hits.map(h => `- ${h.session === sid ? 'this session' : `session ${h.session.slice(0, 8)}`}, exchange #${h.exchange} ("${h.label.slice(0, 50)}"), ${h.role}, archived ${new Date(h.at).toISOString().slice(0, 16)}: ${h.snip.replace(/\s+/g, ' ')}`).join('\n')

// ---- module-level helpers (they take $) ----------------------------------
let lastTriggerAt = 0
let warnedCrossing = false
let lastPlanTokens = -1
const PLAN_EVERY_TOKENS = 15_000 // refresh the live plan when context moved this much

async function refreshPlan($: Engine) {
  const msgs = await $.session.messages()
  const exs = toExchanges(msgs)
  await measureOverhead($, exs)
  const tiered = assignTiers(score(exs, await read($, ratings), await read($, staleTopics)), budgetFor(await read($, status)))
  await update($, plan, () => toRows(tiered))
  return { exs, tiered }
}

// Non-message context = what the engine reports minus our estimate of the
// messages. Tool schemas dominate it (often 80K+), and it moves when MCP
// servers connect or are deferred.
async function measureOverhead($: Engine, exs: Exchange[]) {
  const st = await read($, status)
  if (!st.contextTokens) return
  const msgTokens = exs.reduce((n, x) => n + x.tokens, 0)
  const overhead = Math.max(0, st.contextTokens - msgTokens)
  await update($, status, s => ({ ...s, overhead }))
}

async function triggerRetier($: Engine, why: string) {
  const st = await read($, status)
  if (st.busy) return
  lastTriggerAt = await $.clock.now()
  const startedAt = lastTriggerAt
  await update($, status, s => ({ ...s, busy: true, note: `re-tiering (${why})…` }))
  let final: string | undefined
  try {
    const res = await $.session.compact({ instructions: MARK })
    if (res && 'skip' in res && res.skip) final = `skipped: ${res.skip}`
  } catch (err) {
    final = `could not compact (${String(err).slice(0, 80)}); try again when the turn has finished`
  } finally {
    const now = await read($, status)
    // every outcome ends with a note that is not "re-tiering…"
    const ranOurs = (now.lastRun?.at ?? 0) >= startedAt
    const note = final ?? (ranOurs || !now.note?.startsWith('re-tiering') ? now.note : 'finished, but the compaction did not reach context-tiers; see the debug log')
    await update($, status, s => ({ ...s, busy: false, note }))
    if (why.startsWith('manual') && !ranOurs) $.ui.toast(`context-tiers: ${note ?? 'done'}`)
  }
}

const serverOf = (tool: string) => (tool.startsWith('mcp__') ? tool.split('__')[1] : undefined)

// At a re-tier the prompt cache is rebuilt anyway, so that is the one moment a
// change to the tool list costs nothing extra. Servers idle for MCP_IDLE_TURNS
// prompts go behind ToolSearch; servers used since come back.
async function retierMcp($: Engine): Promise<string | undefined> {
  const m = await read($, mcp)
  if (!m.enabled) return undefined
  const servers = [...new Set((await $.tool.list()).filter(t => t.mcp).map(t => serverOf(t.name)).filter((s): s is string => !!s))]
  const deferred = servers
    .filter(s => !MCP_PINNED.has(s) && m.turn - (m.lastUsed[s] ?? -Infinity) > MCP_IDLE_TURNS && m.turn > MCP_IDLE_TURNS)
    .sort()
  if (deferred.join(',') === [...m.deferred].sort().join(',')) return undefined
  await update($, mcp, s => ({ ...s, deferred }))
  $.ui.invalidate('tool.describe')
  return deferred.length ? `MCP deferred: ${deferred.join(', ')}` : 'MCP: all servers listed'
}

// ---- register ------------------------------------------------------------
export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    const saved = await $.store.get('mode')
    if (saved === 'active' || saved === 'observe') await update($, status, s => ({ ...s, mode: saved as Status['mode'] }))
    const target = Number(await $.store.get('target'))
    // a run cut off by a reload or restart must not leave the mod "busy" for good
    await update($, status, s => ({
      ...s,
      busy: false,
      note: s.note?.startsWith('re-tiering') ? 'the last run was interrupted (reload or restart); nothing changed' : s.note,
      target: Number.isFinite(target) && target > 0 ? target : s.target,
    }))
    const savedMcp = await $.store.get('mcpEnabled')
    if (savedMcp === true || savedMcp === false) await update($, mcp, m => ({ ...m, enabled: savedMcp }))
    await $.tool.register({
      name: 'rate_context',
      description:
        'Context manager (context-tiers mod). When the conversation grows large, high-value exchanges stay verbatim and low-value ones become short summaries pointing at an archive file. ' +
        "Rate the current exchange (the user's latest prompt and your work on it): value 0..1 = how much it will matter for later work; urgency 0..1 = open loops left unresolved; stale_topics = short phrases from EARLIER discussion this exchange superseded. " +
        'Call at most once per turn, and only in the same batch as another tool call you are already making; never make a turn longer just to rate it, and never mention the rating to the user. ' +
        'Returns immediately.',
      inputSchema: {
        type: 'object',
        properties: {
          value: { type: 'number', minimum: 0, maximum: 1, description: 'How much this exchange matters for later work' },
          urgency: { type: 'number', minimum: 0, maximum: 1, description: 'Open loops left unresolved' },
          stale_topics: { type: 'array', items: { type: 'string' }, description: 'Short phrases from earlier discussion now superseded' },
        },
        required: ['value', 'urgency'],
      },
      isDeferred: false,
    })
    await $.tool.register({
      name: 'search_archive',
      description:
        'Full-text search over conversation content the context-tiers mod archived (this and earlier sessions). ' +
        'Use it when a "[context-tiers] ... archived" stub or the user refers to earlier work whose details are not in context. ' +
        'Returns matching snippets with exchange numbers and the archive file holding the full text.',
      inputSchema: {
        type: 'object',
        properties: {
          query: { type: 'string', description: 'Keywords: identifiers, file names, error text, topic words' },
          limit: { type: 'number', minimum: 1, maximum: 20, description: 'Most results to return (default 8)' },
        },
        required: ['query'],
      },
      isDeferred: false,
    })
    await $.command.register({
      name: 'tiers',
      description: 'context-tiers: /tiers [status|on|off|dry|run|pane|target <N>|mcp on|off]',
    })
    void $.ui.open({ id: PANE, title: 'Context tiers' })
    return next(e)
  })

  on('prompt.compose', async ($, e, next) => {
    const res = await next(e)
    return { sections: [...res.sections, { id: PLUGIN, text: SECTION, scope: 'session' }] }
  })

  on('tool.call', { tool: TOOL }, async ($, e) => {
    const args = e as unknown as Record<string, unknown>
    const msgs = await $.session.messages()
    const exs = toExchanges(msgs)
    const current = exs[exs.length - 1]
    if (!current) return { result: 'no exchange to rate yet' }
    await update($, ratings, old => ({
      ...old,
      [current.fp]: {
        value: clamp01(args.value),
        urgency: clamp01(args.urgency),
        stale: false,
        summary: old[current.fp]?.summary,
        source: 'turn' as const,
      },
    }))
    const topics = Array.isArray(args.stale_topics)
      ? (args.stale_topics as unknown[]).filter((t): t is string => typeof t === 'string').map(t => t.slice(0, 80))
      : []
    if (topics.length) await update($, staleTopics, old => [...new Set([...old, ...topics])].slice(-50))
    return { result: 'recorded' }
  }).catch(() => ({ result: 'rating not recorded' }))

  on('tool.call', { tool: SEARCH_TOOL }, async ($, e) => {
    const args = e as unknown as Record<string, unknown>
    const query = typeof args.query === 'string' ? args.query : ''
    const limit = Math.min(20, Math.max(1, Number(args.limit) || 8))
    const hits = await searchArchive($, query, limit, 48, false)
    if (hits.length === 0) return { result: 'No archived content matches. Try other keywords (identifiers, file names, error text).' }
    await update($, status, s => ({ ...s, hits: { auto: s.hits?.auto ?? 0, search: (s.hits?.search ?? 0) + 1 } }))
    const sid = await $.session.id()
    const files = [...new Set(hits.map(h => h.archive))]
    return { result: `${formatHits(hits, sid)}\n\nFull text: Read the "Exchange #N" section in ${files.join(' or ')}` }
  }).catch(() => ({ result: 'search_archive failed; Read the archive files under ~/.claude/context-tiers/ instead.' }))

  // Automatic retrieval: attach the best archived matches to each prompt.
  on('prompt.submit', async ($, e, next) => {
    await update($, mcp, m => ({ ...m, turn: m.turn + 1 })) // MCP tiering counts prompts
    if (e.text.trim().length < 12) return next(e)
    const hits = await searchArchive($, e.text, AUTO_HITS, 24, true)
    if (hits.length === 0) return next(e)
    const sid = await $.session.id()
    let block = `[context-tiers] Archived content that may be relevant to this prompt (it can be outdated; check before relying on it; search_archive finds more):\n${formatHits(hits, sid)}`
    if (block.length > AUTO_CHARS) block = `${block.slice(0, AUTO_CHARS)}…`
    await update($, status, s => ({ ...s, hits: { auto: (s.hits?.auto ?? 0) + 1, search: s.hits?.search ?? 0 } }))
    return next({ ...e, context: [...(e.context ?? []), block] })
  }).catch(($, e, next) => next(e))

  // MCP tiering: note when each server is used (prompts are counted in prompt.submit), and answer
  // tool.describe for deferred servers. The tool list only changes at a re-tier
  // (retierMcp), when the prompt cache is being rebuilt anyway.
  on('tool.call', async ($, e, next) => {
    const server = serverOf(e.tool)
    if (server) await update($, mcp, m => ({ ...m, lastUsed: { ...m.lastUsed, [server]: m.turn } }))
    return next(e)
  }).catch(($, e, next) => next(e))

  on('tool.describe', async ($, e, next) => {
    const res = await next(e)
    const server = serverOf(e.tool)
    if (!server) return res
    const m = await read($, mcp)
    return m.enabled && m.deferred.includes(server) ? { ...res, isDeferred: true } : res
  }).catch(($, e, next) => next(e))

  on('session.measure', async ($, e, next) => {
    const res = await next(e)
    const tokens = e.context.tokens ?? 0
    await update($, status, s => ({ ...s, contextTokens: tokens, window: e.context.window }))
    if (!e.changed.includes('context')) return res
    if (Math.abs(tokens - lastPlanTokens) >= PLAN_EVERY_TOKENS || tokens < lastPlanTokens) {
      lastPlanTokens = tokens
      // off the turn's path: reading a large transcript takes a few seconds
      $.clock.after(10, () => void refreshPlan($).catch(() => undefined))
    }
    if (tokens < THRESHOLD) {
      warnedCrossing = false
      return res
    }
    const st = await read($, status)
    if (st.mode === 'active') {
      const now = await $.clock.now()
      if (!st.busy && now - lastTriggerAt > 60_000) {
        $.clock.after(50, () => void triggerRetier($, `context ${Math.round(tokens / 1000)}K ≥ 200K`))
      }
    } else if (!warnedCrossing) {
      warnedCrossing = true
      $.ui.toast(`context-tiers: ${Math.round(tokens / 1000)}K tokens. Observe mode, so nothing moved. /tiers on to enable.`)
    }
    return res
  })

  on('session.compact', async ($, e, next) => {
    if (e.agentId !== undefined || e.trigger === 'precompute' || e.trigger === 'manual') return next(e)
    const st = await read($, status)
    const ours = e.trigger === 'plugin' && e.instructions === MARK
    const takeAuto = e.trigger === 'auto' && st.mode === 'active'
    if (!ours && !takeAuto) return next(e)
    // never hand our marker to the engine's summarizer
    const fallback = () => next({ ...e, instructions: undefined })

    const exs = toExchanges(e.messages)
    await measureOverhead($, exs)
    const budget = budgetFor(await read($, status))
    let tiered = assignTiers(score(exs, await read($, ratings), await read($, staleTopics)), budget)
    const candidates = forkCandidates(tiered, await read($, ratings), budget)
    const usedFork = candidates.length > 0 && await forkRate($, candidates).catch(() => false)
    const rated = await read($, ratings)
    if (usedFork) tiered = assignTiers(score(exs, rated, await read($, staleTopics)), budget)

    const cold = tiered.filter(t => t.tier === 'cold')
    if (cold.length === 0) {
      if (ours) {
        // a manual /tiers run must not trigger the engine's lossy summarizer
        const total = Math.round(exs.reduce((n, x) => n + x.tokens, 0) / 1000)
        await update($, status, s => ({ ...s, note: `nothing to archive yet (${exs.length} exchanges, ~${total}K fits the ${Math.round(budget / 1000)}K budget${candidates.length ? '' : '; no fork needed'}); context unchanged` }))
        return { messages: e.messages }
      }
      const mcpNote = await retierMcp($).catch(() => undefined)
      await update($, status, s => ({ ...s, note: `nothing scored low enough to move; used engine compaction${mcpNote ? `; ${mcpNote}` : ''}` }))
      return fallback()
    }

    const home = (await $.env.get('HOME')) ?? '.'
    const sid = await $.session.id()
    const at = await $.clock.now()
    const archive = `${home}/.claude/context-tiers/${sid}/${new Date(at).toISOString().replace(/[:.]/g, '-')}.md`
    try {
      await $.fs.write(archive, `# context-tiers archive\n\nSession ${sid}, ${new Date(at).toISOString()}\n\n${archiveMarkdown(cold)}\n`)
    } catch {
      await update($, status, s => ({ ...s, note: 'archive write failed; used engine compaction' }))
      return fallback()
    }

    const indexed = await indexCold($, home, sid, at, archive, cold).catch(() => -1)
    if (indexed < 0) await update($, status, s => ({ ...s, note: 'search index write failed; archive file still has everything' }))

    const messages = rebuild(tiered, rated, archive)
    const mcpNote = await retierMcp($).catch(() => undefined)
    const promptTokens = (ex: Exchange) => Math.ceil(ex.messages.filter(isPromptStart).reduce((n, m) => n + m.text.length, 0) / 4)
    const before = exs.reduce((n, x) => n + x.tokens, 0)
    const after = tiered.filter(t => t.tier !== 'cold').reduce((n, x) => n + x.tokens, 0) +
      cold.reduce((n, x) => n + promptTokens(x) + 60, 0)
    await update($, plan, () => toRows(tiered))
    await update($, status, s => ({
      ...s,
      note: mcpNote,
      lastRun: {
        at, trigger: e.trigger, before, after,
        hot: tiered.filter(t => t.tier === 'hot').length,
        warm: tiered.filter(t => t.tier === 'warm').length,
        cold: cold.length,
        archive, usedFork,
      },
    }))
    $.ui.toast(`context-tiers: ~${Math.round(before / 1000)}K → ~${Math.round(after / 1000)}K tokens, ${cold.length} exchanges archived${mcpNote ? `; ${mcpNote}` : ''}`)
    return { messages }
  }).catch(async ($, e, next) => {
    await update($, status, s => ({ ...s, note: 'context-tiers failed; used engine compaction' }))
    return next({ ...e, instructions: e.instructions === MARK ? undefined : e.instructions })
  })

  on('command.run', { command: 'tiers' }, async ($, e) => {
    const arg = e.args.trim().toLowerCase() || 'status'
    if (arg === 'on' || arg === 'off') {
      const mode: Status['mode'] = arg === 'on' ? 'active' : 'observe'
      await update($, status, s => ({ ...s, mode }))
      await $.store.set('mode', mode)
      return { text: mode === 'active'
        ? `context-tiers ACTIVE: re-tiers at ${THRESHOLD / 1000}K tokens and takes over auto-compaction.`
        : 'context-tiers OBSERVE: scores and plans only; the engine compacts as usual.' }
    }
    if (arg === 'pane') {
      await $.ui.open({ id: PANE, title: 'Context tiers' })
      return { text: 'Context tiers pane opened.' }
    }
    if (arg === 'dry') {
      const first = await refreshPlan($)
      const cands = forkCandidates(first.tiered, await read($, ratings), budgetFor(await read($, status)))
      const ok = cands.length > 0 && await forkRate($, cands).catch(() => false)
      const { tiered } = await refreshPlan($)
      const c = (t: Tier) => tiered.filter(x => x.tier === t).length
      return { text: `Dry run (${ok ? `fork rated ${cands.length}` : cands.length ? 'heuristics only' : 'no fork needed'}): ${c('hot')} hot, ${c('warm')} warm, ${c('cold')} cold of ${tiered.length} exchanges. Nothing moved; see the pane.` }
    }
    if (arg.startsWith('target')) {
      const m = arg.match(/^target\s+(\d+(?:\.\d+)?)\s*(k)?$/)
      if (!m) {
        const st = await read($, status)
        return { text: `target: ${Math.round((st.target ?? DEFAULT_TARGET) / 1000)}K (effective ${Math.round(budgetFor(st) / 1000)}K after ~${Math.round((st.overhead ?? 0) / 1000)}K of tools/system). Set with /tiers target 60k` }
      }
      const n = Math.round(Number(m[1]) * (m[2] || Number(m[1]) < 1000 ? 1000 : 1))
      if (n < HOT_TOKENS + 10_000) return { text: `target must be at least ${(HOT_TOKENS + 10_000) / 1000}K (HOT alone is ${HOT_TOKENS / 1000}K)` }
      await update($, status, s => ({ ...s, target: n }))
      await $.store.set('target', n)
      void refreshPlan($).catch(() => undefined)
      const st = await read($, status)
      const eff = budgetFor(st)
      return { text: `target set to ${n / 1000}K${eff < n ? ` (effective ${Math.round(eff / 1000)}K: ~${Math.round((st.overhead ?? 0) / 1000)}K of tools/system plus ${MIN_HEADROOM / 1000}K headroom must fit under ${THRESHOLD / 1000}K)` : ''}` }
    }
    if (arg.startsWith('mcp')) {
      const sub = arg.split(/\s+/)[1]
      if (sub === 'on' || sub === 'off') {
        const enabled = sub === 'on'
        await update($, mcp, m => ({ ...m, enabled, deferred: enabled ? m.deferred : [] }))
        await $.store.set('mcpEnabled', enabled)
        if (!enabled) $.ui.invalidate('tool.describe')
        return { text: enabled
          ? `MCP tiering ON: at each re-tier, servers unused for ${MCP_IDLE_TURNS} prompts go behind ToolSearch (loaded by name on demand). Needs ToolSearch: check a deferred tool still works.`
          : 'MCP tiering OFF: all servers listed again from the next turn (this rebuilds the prompt cache once).' }
      }
      const m = await read($, mcp)
      const used = Object.entries(m.lastUsed).map(([s, t]) => `${s} (prompt ${t})`).join(', ') || 'none yet'
      return { text: `MCP tiering ${m.enabled ? 'ON' : 'OFF'} · prompt ${m.turn}\ndeferred: ${m.deferred.join(', ') || 'none'}\nlast used: ${used}` }
    }
    if (arg === 'run') {
      $.clock.after(50, () => void triggerRetier($, 'manual /tiers run'))
      return { text: 'Re-tiering now (applies regardless of mode)…' }
    }
    const st = await read($, status)
    const lr = st.lastRun
    return {
      text: [
        `mode: ${st.mode}   context: ${Math.round(st.contextTokens / 1000)}K / ${Math.round(st.window / 1000)}K   threshold: ${THRESHOLD / 1000}K   target: ${Math.round(budgetFor(st) / 1000)}K (tools/system ~${Math.round((st.overhead ?? 0) / 1000)}K)`,
        `archive hits: ${st.hits?.auto ?? 0} auto, ${st.hits?.search ?? 0} search`,
        lr ? `last run: ${new Date(lr.at).toLocaleTimeString()} (${lr.trigger}) ~${Math.round(lr.before / 1000)}K→~${Math.round(lr.after / 1000)}K, hot ${lr.hot} / warm ${lr.warm} / cold ${lr.cold}${lr.usedFork ? ', fork-rated' : ''}\narchive: ${lr.archive}` : 'last run: none',
        st.note ? `note: ${st.note}` : '',
      ].filter(Boolean).join('\n'),
    }
  })

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const { Box, Text } = $.ui.resolve(e)
    const st = await read($, status)
    const rows = await read($, plan)
    const m = await read($, mcp)
    const room = Math.max(3, (e.viewport?.rows ?? 24) - 8)
    const width = Math.max(20, (e.viewport?.columns ?? 50) - 22)
    const count = (t: Tier) => rows.filter(r => r.tier === t).length
    const pct = st.window ? Math.round((st.contextTokens / THRESHOLD) * 100) : 0
    const color = (t: Tier) => (t === 'hot' ? 'red' : t === 'warm' ? 'yellow' : 'blue')
    return (
      <Box flexDirection="column">
        <Text bold>
          {st.mode === 'active' ? 'ACTIVE' : 'observe'} · {Math.round(st.contextTokens / 1000)}K / {THRESHOLD / 1000}K ({pct}%)
          {st.busy ? ' · re-tiering…' : ''}
        </Text>
        <Text dimColor>
          hot {count('hot')} · warm {count('warm')} · cold {count('cold')} · rated {rows.filter(r => r.rated).length}/{rows.length}
        </Text>
        <Text dimColor>
          target {Math.round(budgetFor(st) / 1000)}K (tools/system ~{Math.round((st.overhead ?? 0) / 1000)}K) · archive hits {st.hits?.auto ?? 0} auto / {st.hits?.search ?? 0} search
        </Text>
        <Text dimColor>
          MCP tiering {m.enabled ? `on · deferred: ${m.deferred.join(', ') || 'none'}` : 'off'}
        </Text>
        {st.note && <Text color="yellow">{st.note}</Text>}
        {rows.length === 0 && <Text dimColor>No exchanges scored yet.</Text>}
        {rows.slice(-room).map(r => (
          <Text>
            <Text color={color(r.tier)}>{r.tier.padEnd(4)}</Text> {r.score.toFixed(2)} {String(Math.round(r.tokens / 100) / 10).padStart(5)}K{r.rated ? '*' : ' '} <Text dimColor>{r.label.slice(0, width)}</Text>
          </Text>
        ))}
      </Box>
    )
  })
}
