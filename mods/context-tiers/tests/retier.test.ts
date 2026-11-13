import { expect, test } from 'claude-code/testing'

const big = (n: number) => 'x'.repeat(n)

// 12 exchanges of ~10K tokens each (~120K): too big for the 90K budget.
function transcript() {
  const out: Record<string, unknown>[] = []
  for (let i = 0; i < 12; i++) {
    out.push({ role: 'user', text: `question ${i} about topic${i}`, toolUses: [], handle: `u${i}` })
    out.push({ role: 'assistant', text: `answer ${i} ${big(40_000)}`, toolUses: [], handle: `a${i}` })
  }
  return out
}

test('re-tier keeps the newest exchanges verbatim and archives the rest', { timeoutMs: 30_000 }, async ($, on) => {
  const writes: string[] = []
  on('env.get', () => ({ value: '/home/t' }))
  on('session.id', () => ({ value: 'sid1' }))
  on('clock.now', () => ({ value: 1_700_000_000_000 }))
  on('fs.write', (_, e) => {
    writes.push(String((e as unknown as { path: string }).path))
    return { value: undefined }
  })
  // Fork rates exchange #1 high value; everything else unremarkable.
  on('model.fork', () => ({
    value: {
      isAnswered: true,
      text: '[{"i":1,"value":1,"urgency":1,"stale":false,"summary":"key decision"},{"i":2,"value":0,"urgency":0,"stale":true,"summary":"old idea"}]',
    },
  }) as never)
  on('session.compact', () => ({ messages: [] }))
  on('ui.toast', () => ({ value: undefined }))
  // the fork's 90s timeout: a real timer, which the fork beats
  on('clock.sleep', () => new Promise(() => undefined) as never)
  const sqlRuns: string[] = []
  on('process.run', (_, e) => {
    sqlRuns.push(String((e as unknown as { init?: { stdin?: string } }).init?.stdin ?? ''))
    return { value: { exitCode: 0, stdout: '', stderr: '' } } as never
  })

  const res = (await $.session.compact({
    instructions: 'context-tiers:retier',
    messages: transcript(),
    trigger: 'plugin',
  } as never)) as { messages?: { role: string; text: string; handle?: string }[] }

  const msgs = res.messages ?? []
  expect(msgs.length > 0).toBe(true)
  const handles = msgs.map(m => m.handle).filter(Boolean)
  // newest exchange always kept verbatim
  expect(handles.includes('u11')).toBe(true)
  expect(handles.includes('a11')).toBe(true)
  // stale exchange #2: Claude's work archived, the user's prompt kept
  expect(handles.includes('a2')).toBe(false)
  expect(handles.includes('u2')).toBe(true)
  // fork rated #1 high: pinned, kept verbatim
  expect(handles.includes('u1')).toBe(true)
  const summary = msgs.find(m => m.role === 'assistant' && m.text.startsWith('[context-tiers]') && m.text.includes('exchange #2 '))
  expect(summary !== undefined).toBe(true)
  expect(summary!.text.includes('old idea')).toBe(true)
  expect(writes.length).toBe(1)
  // archived content went into the search index
  expect(sqlRuns.some(q => q.includes('INSERT INTO docs') && q.includes('answer 2'))).toBe(true)
})

test('a manual run with nothing cold leaves the context unchanged', async ($, on) => {
  let engineCalled = false
  on('session.compact', () => { engineCalled = true; return { messages: [] } })
  on('model.fork', () => ({ value: { isAnswered: true, text: '[]' } }) as never)
  const small = [
    { role: 'user', text: 'q0', toolUses: [], handle: 'u0' },
    { role: 'assistant', text: 'a0', toolUses: [], handle: 'a0' },
  ]
  const res = (await $.session.compact({ instructions: 'context-tiers:retier', messages: small, trigger: 'plugin' } as never)) as { messages?: { handle?: string }[] }
  expect(engineCalled).toBe(false)
  expect((res.messages ?? []).map(m => m.handle).join(',')).toBe('u0,a0')
})

test('a compaction that is not ours goes to the engine', async ($, on) => {
  on('session.compact', () => ({ messages: [{ role: 'user', text: 'engine summary', toolUses: [] }] }))
  const res = (await $.session.compact({ instructions: 'keep the plan' } as never)) as { messages?: { text: string }[] }
  expect(res.messages?.[0]?.text).toBe('engine summary')
})

test('a prompt gets matching archived snippets attached', async ($, on) => {
  on('env.get', () => ({ value: '/home/t' }))
  on('fs.exists', () => ({ value: true }))
  on('session.id', () => ({ value: 'sid1' }))
  on('process.run', () => ({
    value: {
      exitCode: 0,
      stderr: '',
      stdout: JSON.stringify([
        { session: 'sid1', exchange: 3, role: 'assistant', label: 'pick threshold', at: 0, archive: '/a.md', lc: 'we set the threshold to 200k tokens for retier', snip: 'we set the «threshold» to 200k' },
        { session: 'sid1', exchange: 4, role: 'assistant', label: 'noise', at: 0, archive: '/a.md', lc: 'unrelated threshold', snip: 'unrelated' },
      ]),
    },
  }) as never)
  on('prompt.submit', (_, e) => ({ text: e.text, context: e.context }))
  const res = (await $.prompt.submit({ text: 'what retier threshold did we choose for tokens?' } as never)) as { context?: string[] }
  const block = (res.context ?? []).join('\n')
  expect(block.includes('exchange #3')).toBe(true)
  // a hit sharing only one query word is filtered out
  expect(block.includes('exchange #4')).toBe(false)
})

test('no fork is paid for when every exchange fits the budget', async ($, on) => {
  let forks = 0
  on('model.fork', () => { forks++; return { value: { isAnswered: true, text: '[]' } } as never })
  on('session.compact', () => ({ messages: [] }))
  const small: Record<string, unknown>[] = []
  for (let i = 0; i < 6; i++) {
    small.push({ role: 'user', text: `q${i}`, toolUses: [], handle: `u${i}` })
    small.push({ role: 'assistant', text: `a${i} ${big(8_000)}`, toolUses: [], handle: `a${i}` })
  }
  await $.session.compact({ instructions: 'context-tiers:retier', messages: small, trigger: 'plugin' } as never)
  expect(forks).toBe(0)
})

test('/tiers target lowers the budget, so more is archived', { timeoutMs: 30_000 }, async ($, on) => {
  on('env.get', () => ({ value: '/home/t' }))
  on('session.id', () => ({ value: 'sid1' }))
  on('clock.now', () => ({ value: 1_700_000_000_000 }))
  on('fs.write', () => ({ value: undefined }))
  on('store.set', () => ({ value: undefined }))
  on('model.fork', () => ({ value: { isAnswered: true, text: '[]' } }) as never)
  on('session.compact', () => ({ messages: [] }))
  on('session.messages', () => ({ value: [] }) as never)
  on('ui.toast', () => ({ value: undefined }))
  on('process.run', () => ({ value: { exitCode: 0, stdout: '', stderr: '' } }) as never)
  const set = (await $.command.run({ command: 'tiers', args: 'target 40k' } as never)) as { text?: string }
  expect(set.text?.startsWith('target set to 40K')).toBe(true)
  const res = (await $.session.compact({ instructions: 'context-tiers:retier', messages: transcript(), trigger: 'plugin' } as never)) as { messages?: { handle?: string }[] }
  const kept = (res.messages ?? []).filter(m => m.handle?.startsWith('a')).length
  // 40K budget, ~10K per exchange: about 4 exchanges keep Claude's work verbatim
  expect(kept <= 4).toBe(true)
  expect(kept >= 3).toBe(true)
})

test('an idle MCP server goes behind ToolSearch at a re-tier; a used one stays', { timeoutMs: 30_000 }, async ($, on) => {
  on('env.get', () => ({ value: '/home/t' }))
  on('session.id', () => ({ value: 'sid1' }))
  on('clock.now', () => ({ value: 1_700_000_000_000 }))
  on('fs.write', () => ({ value: undefined }))
  on('fs.exists', () => ({ value: false }))
  on('store.set', () => ({ value: undefined }))
  on('model.fork', () => ({ value: { isAnswered: true, text: '[]' } }) as never)
  on('session.compact', () => ({ messages: [] }))
  on('ui.toast', () => ({ value: undefined }))
  on('ui.invalidate', () => ({ value: undefined }))
  on('process.run', () => ({ value: { exitCode: 0, stdout: '', stderr: '' } }) as never)
  on('prompt.submit', (_, e) => ({ text: e.text }))
  on('tool.call', () => ({ result: 'ok' }) as never)
  on('tool.describe', (_, e) => ({ description: e.description }))
  on('tool.list', () => ({ value: [
    { name: 'mcp__jira__search', description: '', mcp: true },
    { name: 'mcp__wiki__search', description: '', mcp: true },
    { name: 'mcp__context-tiers__search_archive', description: '', mcp: true },
    { name: 'Bash', description: '', mcp: false },
  ] }) as never)

  await $.command.run({ command: 'tiers', args: 'mcp on' } as never)
  for (let i = 0; i < 14; i++) {
    await $.prompt.submit({ text: `p${i}` } as never)
    if (i === 12) await $.tool.call({ tool: 'mcp__jira__search', tool_use_id: 't1' } as never)
  }
  await $.session.compact({ instructions: 'context-tiers:retier', messages: transcript(), trigger: 'plugin' } as never)

  const wiki = (await $.tool.describe({ tool: 'mcp__wiki__search', description: 'w' } as never)) as { isDeferred?: boolean }
  const jira = (await $.tool.describe({ tool: 'mcp__jira__search', description: 'j' } as never)) as { isDeferred?: boolean }
  const own = (await $.tool.describe({ tool: 'mcp__context-tiers__search_archive', description: 's' } as never)) as { isDeferred?: boolean }
  expect(wiki.isDeferred).toBe(true)
  expect(jira.isDeferred === true).toBe(false)
  expect(own.isDeferred === true).toBe(false)
})
