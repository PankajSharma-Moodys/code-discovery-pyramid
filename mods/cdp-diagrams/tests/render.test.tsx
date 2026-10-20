import { expect, mock, test } from 'claude-code/testing'

import { FIXTURES } from './fixtures.ts'

const REPLY = [
  'The flow, with citations:',
  '',
  '```mermaid',
  FIXTURES.create_db_decls,
  '```',
  '',
  'And the states:',
  '',
  '```mermaid',
  FIXTURES.store_states_short,
  '```',
].join('\n')

const viewport = { columns: 120, rows: 40 }
const props = (text: string) => ({ text, isFirstOfReply: true })

test('a reply with mermaid blocks draws diagrams with their citations, on terminal and desktop', async $ => {
  for (const surface of ['terminal', 'desktop'] as const) {
    const ui = await $.ui.mount({ plugin: 'cdp-diagrams', surface, component: 'AssistantMessage', props: props(REPLY), viewport })
    // the line introducing each fence is its title's caption, not text of its own
    expect(await ui.find({ type: 'Text', text: /^◆ Flowchart {2}The flow, with citations$/ })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: /^◆ State machine {2}And the states$/ })).toBeDefined()
    expect(await ui.find({ type: 'Markdown', text: /The flow, with citations|And the states/ })).toBeUndefined()
    expect(await ui.find({ type: 'Text', text: /flowchart TD · 6 nodes · 6 edges/ })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: /state diagram · / })).toBeDefined()
    // the legend table: marker │ action │ cite │ check (a dashed edge reads inferred)
    expect(await ui.find({ type: 'Text', text: /^[①-⑳] │ on exception +│ Handler\.cs:317 +│ ╌ inferred$/ })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: /DeleteStoreHandler\.cs:133/ })).toBeDefined()
    if (surface === 'desktop') expect(await ui.find({ type: 'Svg' })).toBeDefined()
    else expect(await ui.find({ type: 'Text', text: /┌/ })).toBeDefined()
    await ui.unmount()
  }
})

test('a block that does not parse shows why and its source', async $ => {
  const text = 'See:\n\n```mermaid\nsequenceDiagram\nA->>B: hi\n```\n'
  for (const surface of ['terminal', 'desktop'] as const) {
    const ui = await $.ui.mount({ plugin: 'cdp-diagrams', surface, component: 'AssistantMessage', props: props(text), viewport })
    expect(await ui.find({ type: 'Text', text: /not drawn: could not parse it: unsupported diagram type/ })).toBeDefined()
    expect(await ui.find({ type: 'Markdown', text: /sequenceDiagram/ })).toBeDefined()
    await ui.unmount()
  }
})

test('a diagram too wide for the terminal shows why and its source', async $ => {
  const text = '```mermaid\n' + FIXTURES.event_fanout + '\n```'
  const ui = await $.ui.mount({
    plugin: 'cdp-diagrams',
    surface: 'terminal',
    component: 'AssistantMessage',
    props: props(text),
    viewport: { columns: 40, rows: 40 },
  })
  expect(await ui.find({ type: 'Text', text: /too wide: needs \d+ columns, 36 available/ })).toBeDefined()
  expect(await ui.find({ type: 'Markdown', text: /JobSubscriber\.scala:39-45/ })).toBeDefined()
})

test('a reply without mermaid is left to the engine', async ($, on) => {
  on('ui.render', { component: 'AssistantMessage' }, ($, e) => {
    const { Text } = $.ui.resolve(e)
    return <Text>engine drew this</Text>
  })
  const ui = await $.ui.mount({
    plugin: 'cdp-diagrams',
    surface: 'terminal',
    component: 'AssistantMessage',
    props: props('Plain answer, ```python\nprint(1)\n```'),
    viewport,
  })
  expect(await ui.find({ type: 'Text', text: /engine drew this/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /nodes ·/ })).toBeUndefined()
})

test('drawing adds nothing to the conversation the model reads', async ($, on) => {
  const session = mock.session(on)
  for (const surface of ['terminal', 'desktop'] as const) {
    const ui = await $.ui.mount({ plugin: 'cdp-diagrams', surface, component: 'AssistantMessage', props: props(REPLY), viewport })
    await ui.unmount()
  }
  expect(session.appended()).toEqual([])
})

test('a reply from no CDP or diagram turn runs no checker and draws no badges', async ($, on) => {
  const runs: unknown[] = []
  on('process.run', ($, e) => {
    runs.push(e.argv)
    return { exitCode: 0, stdout: '', stderr: '' }
  })
  for (const surface of ['terminal', 'desktop'] as const) {
    const ui = await $.ui.mount({ plugin: 'cdp-diagrams', surface, component: 'AssistantMessage', props: props(REPLY), viewport })
    expect(await ui.find({ type: 'Text', text: /DeleteStoreHandler\.cs:133/ })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: /verified \d+\/\d+ edges/ })).toBeUndefined()
    expect(await ui.find({ type: 'Text', text: /^[✓✗?~] / })).toBeUndefined()
    await ui.unmount()
  }
  expect(runs).toEqual([])
})

test('a caption under a fence goes in its title; an intro line of the next fence stays the next one\'s', async $ => {
  const text = [
    '```mermaid',
    'flowchart TD',
    '  A -->|"charge(order) · orders.py:23"| B',
    '```',
    'place_order flow: build, charge, ship or cancel.',
    '',
    'Then the states:',
    '',
    '```mermaid',
    'stateDiagram-v2',
    '  [*] --> NEW: Order() · orders.py:18',
    '```',
  ].join('\n')
  const ui = await $.ui.mount({ plugin: 'cdp-diagrams', surface: 'terminal', component: 'AssistantMessage', props: props(text), viewport })
  expect(await ui.find({ type: 'Text', text: /^◆ Flowchart {2}place_order flow: build, charge, ship or cancel\.$/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^◆ State machine {2}Then the states$/ })).toBeDefined()
  expect(await ui.find({ type: 'Markdown', text: /place_order flow|Then the states/ })).toBeUndefined()
})
