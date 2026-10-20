import { describe, expect, test } from 'claude-code/testing'

import { CdpTurnTracker, isCdpToolCall } from '../hooks/detect.ts'

const bash = (command: string) => isCdpToolCall('Bash', { command })

describe('isCdpToolCall', () => {
  test('MCP CDP tools, direct and plugin-prefixed', () => {
    expect(isCdpToolCall('mcp__cdp__cdp_query', {})).toBe(true)
    expect(isCdpToolCall('mcp__cdp__cdp_help', {})).toBe(true)
    expect(isCdpToolCall('mcp__plugin_cdp_cdp__cdp_query', {})).toBe(true)
    expect(isCdpToolCall('mcp__gh__issue', {})).toBe(false)
    expect(isCdpToolCall('mcp__notcdp__query', {})).toBe(false)
    expect(isCdpToolCall('Read', { file_path: '/x/cdp' })).toBe(false)
  })

  test('Bash runs of the cdp CLI', () => {
    for (const c of [
      'cdp query symbol Foo',
      'cdp',
      'cd /repo && cdp query route /v2/orders',
      'cd x; cdp scan .',
      'CDP_HOME=/tmp cdp query table Stores',
      '/usr/local/bin/cdp query symbol X | head -40',
      'python3 -m cdp.cli query symbol X',
      'cd /repo && PYTHONPATH=. python3 -m cdp.cli query symbol X 2>&1 | tail -20',
      'uv run python -m cdp.cli help',
      'out=$(cdp query symbol X); echo "$out"',
      'git status || cdp query symbol X',
    ])
      expect({ c, hit: bash(c) }).toEqual({ c, hit: true })
  })

  test('Bash commands that only mention cdp', () => {
    for (const c of [
      'grep -rn cdp src/',
      'echo cdp',
      'echo "cd x && cdp query y"',
      "grep 'python3 -m cdp.cli' notes.md",
      'ls cdp/',
      'cat cdp/cli.py | head',
      'python3 -m pytest tests/test_cdp.py',
      'cdpx query',
    ])
      expect({ c, hit: bash(c) }).toEqual({ c, hit: false })
    expect(isCdpToolCall('Bash', {})).toBe(false)
  })
})

describe('CdpTurnTracker', () => {
  test('a main-loop CDP call marks the turn; the next turn starts clean', () => {
    const t = new CdpTurnTracker()
    t.start({})
    t.call({ tool: 'Read', file_path: 'a' } as { tool: string })
    t.call({ tool: 'mcp__cdp__cdp_query' })
    expect(t.complete({})).toBe(true)
    expect(t.lastTurnUsedCdp()).toBe(true)
    t.start({})
    t.call({ tool: 'Bash', command: 'ls' } as { tool: string })
    expect(t.complete({})).toBe(false)
    expect(t.lastTurnUsedCdp()).toBe(false)
  })

  test("a subagent's calls, starts and ends are ignored", () => {
    const t = new CdpTurnTracker()
    t.start({})
    t.call({ tool: 'mcp__cdp__cdp_query', agentId: 'a1' })
    t.call({ tool: 'Bash', command: 'cdp query x', agentId: 'a1' } as { tool: string; agentId: string })
    t.start({ agentId: 'a1' })
    expect(t.complete({ agentId: 'a1' })).toBeUndefined()
    expect(t.complete({})).toBe(false)
  })

  test('a CDP call is not carried into the next turn even without its end heard', () => {
    const t = new CdpTurnTracker()
    t.start({})
    t.call({ tool: 'Bash', command: 'cdp query x' } as { tool: string })
    t.start({})
    expect(t.complete({})).toBe(false)
  })
})

test('tool.call is observed only: the call reaches the tool unchanged and its result comes back', async ($, on) => {
  const seen: unknown[] = []
  on('tool.call', ($, e) => {
    seen.push(e)
    return { result: { stdout: 'ok', stderr: '', interrupted: false } } as never
  })
  const input = { tool: 'Bash', command: 'cd /repo && cdp query symbol X', description: 'q' } as const
  const r = await $.tool.call(input as never)
  expect(seen.length).toBe(1)
  expect((seen[0] as { command: string }).command).toBe(input.command)
  expect('deny' in r && r.deny !== undefined).toBe(false)
})
