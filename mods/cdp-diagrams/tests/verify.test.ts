import { describe, expect, test } from 'claude-code/testing'

import { parseMermaid } from '../hooks/mermaid.ts'
import { commandsFor, fenceHash, MARK, matchEdges, parseVerdict, type Run, type Verdict, verdictLine, Verifier } from '../hooks/verify.ts'
import { FLOW_SRC, FLOW_STDOUT, STATE_MD, STATE_STDOUT } from './fixtures/verify-samples.ts'

const STATE_SRC = STATE_MD.slice(STATE_MD.indexOf('stateDiagram'), STATE_MD.lastIndexOf('```'))
const fence = (src: string) => '```mermaid\n' + src + '```\n'

/** checker JSON for one diagram whose edges have the given statuses. */
function out(edges: { from: string; to: string; label?: string; status: string; cite?: string; hint?: string }[]): string {
  return JSON.stringify({
    ok: edges.every(e => e.status === 'correct' || e.status === 'inferred'),
    diagrams: [
      {
        kind: 'flowchart',
        errors: [],
        edges: edges.map((e, i) => ({
          id: `E${i + 1}`,
          from: e.from,
          to: e.to,
          label: e.label ?? '',
          status: e.status,
          cites: e.cite ? [{ text: e.cite, status: e.status, file: 'a/x.java', ...(e.hint ? { hint: e.hint } : {}) }] : [],
        })),
      },
    ],
  })
}

const SIMPLE = 'flowchart TD\n  A -->|call x.java:12| B\n  B -->|save y.java:3| C\n'

/**
 * A stubbed process.run: git answers the root, `test -f` answers whether the
 * vendored copy is there, the checker answers `checker` (a function of the argv and env).
 */
function stub(
  checker: (argv: readonly string[], stdin: string, env?: Record<string, string>) => Promise<{ exitCode: number; stdout: string }>,
  vendored = false,
) {
  const calls: { argv: readonly string[]; cwd?: string; stdin?: string; env?: Record<string, string> }[] = []
  const run: Run = async (argv, init) => {
    calls.push({ argv, cwd: init.cwd, stdin: init.stdin, ...(init.env ? { env: init.env } : {}) })
    if (argv[0] === 'git') return { exitCode: 0, stdout: '/repo\n' }
    if (argv[0] === 'test') return { exitCode: vendored ? 0 : 1, stdout: '' }
    return checker(argv, init.stdin ?? '', init.env)
  }
  return { run, calls, checks: () => calls.filter(c => c.argv[0] !== 'git' && c.argv[0] !== 'test') }
}

async function verdictOf(v: Verifier, src: string, run: Run): Promise<{ v: Verdict | null | undefined; invalidated: number }> {
  let invalidated = 0
  const first = v.lookup(src, '/repo/sub', run, () => invalidated++)
  expect(first).toBeUndefined()
  await v.idle()
  return { v: v.lookup(src, '/repo/sub', run, () => invalidated++), invalidated }
}

describe('parseVerdict on real checker output', () => {
  test('the flowchart sample: every status the checker gave, cites and hint kept', () => {
    const v = parseVerdict(FLOW_STDOUT, 3)!
    expect(v.edges.map(e => `${e.from}>${e.to}:${e.status}`)).toEqual([
      'CLI>G:correct',
      'CLI>X:correct',
      'CLI>S:wrong_citation',
      'G>P:uncited',
      'G>R:ambiguous',
      'G>Q:inferred',
    ])
    expect(v.edges[2]!.cites[0]).toMatchObject({ text: 'verify_diagram.py:12', hint: 'cdp/commands/core/verify_diagram.py:44' })
  })

  test('the state sample: [*] edges the checker skips, unsupported transitions', () => {
    const v = parseVerdict(STATE_STDOUT, 3)!
    expect(v.edges.map(e => `${e.from}>${e.to}:${e.status}`)).toEqual(['Idle>Graded:unsupported', 'Graded>Done:unsupported'])
  })

  test('exit 1, other exits, a parse-error diagram and junk are no verdict', () => {
    expect(parseVerdict('{"error": "not a Mermaid flowchart/stateDiagram", "ok": false}', 1)).toBeNull()
    expect(parseVerdict(FLOW_STDOUT, 1)).toBeNull()
    expect(parseVerdict(FLOW_STDOUT, 2)).toBeNull()
    expect(parseVerdict('Traceback ...', 3)).toBeNull()
    expect(parseVerdict(JSON.stringify({ diagrams: [{ edges: [], errors: ['line 3: bad note'] }] }), 3)).toBeNull()
    expect(parseVerdict(JSON.stringify({ diagrams: [{ edges: [{ from: 'A', to: 'B', status: 'weird' }], errors: [] }] }), 3)).toBeNull()
  })
})

describe('matchEdges and the summary line', () => {
  test('real sample: each drawn edge gets its own status', () => {
    const g = parseMermaid(FLOW_SRC)
    const m = matchEdges(g, parseVerdict(FLOW_STDOUT, 3)!)
    expect(m.map(e => (e ? MARK[e.status] : '-'))).toEqual(['✓', '✓', '✗', '?', '?', '~'])
    expect(verdictLine(g, parseVerdict(FLOW_STDOUT, 3)!)).toBe(
      'verified 2/5 edges; 1 wrong: cmd_verify_diagram→summarize @ verify_diagram.py:12 (try verify_diagram.py:44); ' +
        '1 ambiguous: grade→resolve @ __init__.py:1; 1 uncited: grade→parse; 1 inferred',
    )
  })

  test('state sample: [*] start/end edges have no checked edge and get no badge', () => {
    const g = parseMermaid(STATE_SRC)
    const m = matchEdges(g, parseVerdict(STATE_STDOUT, 3)!)
    const byEdge = g.edges.map((e, i) => `${e.from}>${e.to}:${m[i]?.status ?? '-'}`)
    expect(byEdge).toEqual(['[*]start>Idle:-', 'Idle>Graded:unsupported', 'Graded>Done:unsupported', 'Done>[*]end:-'])
  })

  test('same endpoints twice: the label decides, not the order', () => {
    const g = parseMermaid('flowchart TD\n  A -->|save x.java:5| B\n  A -->|load x.java:9| B\n')
    const v = parseVerdict(
      out([
        { from: 'A', to: 'B', label: 'load x.java:9', status: 'wrong_citation', cite: 'x.java:9' },
        { from: 'A', to: 'B', label: 'save x.java:5', status: 'correct', cite: 'x.java:5' },
      ]),
      3,
    )!
    expect(matchEdges(g, v).map(e => e?.status)).toEqual(['correct', 'wrong_citation'])
  })

  test('a checked edge whose endpoints are not drawn matches nothing; an undrawn-by-checker edge gets no badge', () => {
    const g = parseMermaid('flowchart TD\n  A & B -->|go x.java:1| C\n')
    const v = parseVerdict(out([{ from: 'B', to: 'C', label: 'go x.java:1', status: 'correct', cite: 'x.java:1' }, { from: 'Z', to: 'C', status: 'uncited' }]), 0)!
    const m = matchEdges(g, v)
    expect(g.edges.map((e, i) => `${e.from}>${e.to}:${m[i]?.status ?? '-'}`)).toEqual(['A>C:-', 'B>C:correct'])
  })

  test('all correct reads as such', () => {
    const g = parseMermaid(SIMPLE)
    const v = parseVerdict(out([{ from: 'A', to: 'B', label: 'call x.java:12', status: 'correct', cite: 'x.java:12' }, { from: 'B', to: 'C', label: 'save y.java:3', status: 'correct', cite: 'y.java:3' }]), 0)!
    expect(verdictLine(g, v)).toBe('verified 2/2 edges')
  })
})

describe('Verifier with a stubbed process.run', () => {
  const allCorrect = out([
    { from: 'A', to: 'B', label: 'call x.java:12', status: 'correct', cite: 'x.java:12' },
    { from: 'B', to: 'C', label: 'save y.java:3', status: 'correct', cite: 'y.java:3' },
  ])

  test('only fences of an allowed answer are checked', async () => {
    const v = new Verifier()
    const s = stub(async () => ({ exitCode: 0, stdout: allCorrect }))
    expect(v.lookup(SIMPLE, '/repo', s.run, () => {})).toBeUndefined()
    await v.idle()
    expect(s.calls).toEqual([])
    expect(v.allow('Here:\n\n' + fence(SIMPLE) + '\nand text')).toBe(1)
    expect(v.allow(fence(SIMPLE))).toBe(0)
    expect(v.isAllowed(SIMPLE)).toBe(true)
  })

  test('all correct: one git root, then cdp on the fence from the repo root, then invalidate', async () => {
    const v = new Verifier()
    v.allow(fence(SIMPLE))
    const s = stub(async () => ({ exitCode: 0, stdout: allCorrect }))
    const r = await verdictOf(v, SIMPLE, s.run)
    expect(r.invalidated).toBe(1)
    expect(r.v!.edges.map(e => e.status)).toEqual(['correct', 'correct'])
    expect(s.calls[0]).toEqual({ argv: ['git', 'rev-parse', '--show-toplevel'], cwd: '/repo/sub', stdin: undefined })
    expect(s.checks()).toEqual([{ argv: ['cdp', 'verify-diagram', '-', '--repo', '/repo', '--json'], cwd: '/repo', stdin: SIMPLE }])
  })

  test('mixed (exit 3): the verdict carries each status', async () => {
    const v = new Verifier()
    v.allow(fence(SIMPLE))
    const mixed = out([
      { from: 'A', to: 'B', label: 'call x.java:12', status: 'correct', cite: 'x.java:12' },
      { from: 'B', to: 'C', label: 'save y.java:3', status: 'wrong_citation', cite: 'y.java:3', hint: 'a/y.java:9' },
    ])
    const r = await verdictOf(v, SIMPLE, stub(async () => ({ exitCode: 3, stdout: mixed })).run)
    const g = parseMermaid(SIMPLE)
    expect(matchEdges(g, r.v!).map(e => e && MARK[e.status])).toEqual(['✓', '✗'])
    expect(verdictLine(g, r.v!)).toBe('verified 1/2 edges; 1 wrong: B→C @ y.java:3 (try y.java:9)')
  })

  test('exit 1 (parse error): null, no badges, not retried', async () => {
    const v = new Verifier()
    v.allow(fence(SIMPLE))
    const s = stub(async () => ({ exitCode: 1, stdout: '{"error": "not a Mermaid flowchart", "ok": false}' }))
    expect((await verdictOf(v, SIMPLE, s.run)).v).toBeNull()
    expect(s.checks().length).toBe(1)
  })

  test('cdp cannot start: falls back to python3 -m cdp.cli, then remembers it', async () => {
    const v = new Verifier()
    v.allow(fence(SIMPLE))
    const other = 'flowchart TD\n  A -->|call x.java:12| B\n'
    v.allow(fence(other))
    const s = stub(async argv => {
      if (argv[0] === 'cdp') throw new Error('ENOENT')
      return { exitCode: 0, stdout: allCorrect }
    })
    expect((await verdictOf(v, SIMPLE, s.run)).v).not.toBeNull()
    await verdictOf(v, other, s.run)
    expect(s.checks().map(c => c.argv.slice(0, 3).join(' '))).toEqual(['cdp verify-diagram -', 'python3 -m cdp.cli', 'python3 -m cdp.cli'])
    expect(s.checks().every(c => c.env === undefined)).toBe(true)
  })

  test('vendored copy present: python3 -m cdp.cli with PYTHONPATH at it, first, then remembered', async () => {
    const v = new Verifier()
    v.allow(fence(SIMPLE))
    const other = 'flowchart TD\n  A -->|call x.java:12| B\n'
    v.allow(fence(other))
    const s = stub(async () => ({ exitCode: 0, stdout: allCorrect }), true)
    expect((await verdictOf(v, SIMPLE, s.run)).v!.edges.length).toBe(2)
    await verdictOf(v, other, s.run)
    expect(s.calls.filter(c => c.argv[0] === 'test')).toEqual([
      { argv: ['test', '-f', '/repo/.claude/skills/cdp/cdp/cli.py'], cwd: '/repo', stdin: undefined },
    ])
    const want = {
      argv: ['python3', '-m', 'cdp.cli', 'verify-diagram', '-', '--repo', '/repo', '--json'],
      cwd: '/repo',
      env: { PYTHONPATH: '/repo/.claude/skills/cdp' },
    }
    expect(s.checks()).toEqual([
      { ...want, stdin: SIMPLE },
      { ...want, stdin: other },
    ])
  })

  test('vendored copy present but broken: falls through to cdp, then python3', async () => {
    const v = new Verifier()
    v.allow(fence(SIMPLE))
    const s = stub(async (argv, _stdin, env) => {
      if (env) return { exitCode: 1, stdout: 'ModuleNotFoundError' }
      if (argv[0] === 'cdp') throw new Error('ENOENT')
      return { exitCode: 0, stdout: allCorrect }
    }, true)
    expect((await verdictOf(v, SIMPLE, s.run)).v).not.toBeNull()
    expect(s.checks().map(c => `${c.argv.slice(0, 3).join(' ')}${c.env ? ' +PYTHONPATH' : ''}`)).toEqual([
      'python3 -m cdp.cli +PYTHONPATH',
      'cdp verify-diagram -',
      'python3 -m cdp.cli',
    ])
  })

  test('vendored absent: cdp then python3, no PYTHONPATH; commandsFor gives the order', async () => {
    const v = new Verifier()
    v.allow(fence(SIMPLE))
    const s = stub(async () => {
      throw new Error('ENOENT')
    })
    expect((await verdictOf(v, SIMPLE, s.run)).v).toBeNull()
    expect(s.checks().map(c => [c.argv[0], c.env])).toEqual([
      ['cdp', undefined],
      ['python3', undefined],
    ])
    expect(commandsFor('/r', false)).toEqual([{ argv: ['cdp'] }, { argv: ['python3', '-m', 'cdp.cli'] }])
    expect(commandsFor('/r', true)[0]).toEqual({ argv: ['python3', '-m', 'cdp.cli'], env: { PYTHONPATH: '/r/.claude/skills/cdp' } })
  })

  test('the vendored check itself failing to start counts as absent', async () => {
    const v = new Verifier()
    v.allow(fence(SIMPLE))
    const seen: string[] = []
    const run: Run = async (argv, init) => {
      seen.push(argv[0]! + (init.env ? '+env' : ''))
      if (argv[0] === 'git') return { exitCode: 0, stdout: '/repo\n' }
      if (argv[0] === 'test') throw new Error('ENOENT')
      return { exitCode: 0, stdout: allCorrect }
    }
    expect((await verdictOf(v, SIMPLE, run)).v).not.toBeNull()
    expect(seen).toEqual(['git', 'test', 'cdp'])
  })

  test('every command throws, or python3 has no cdp module: null', async () => {
    for (const checker of [
      async () => {
        throw new Error('ENOENT')
      },
      async (argv: readonly string[]) => {
        if (argv[0] === 'cdp') throw new Error('ENOENT')
        return { exitCode: 1, stdout: '' }
      },
    ]) {
      const v = new Verifier()
      v.allow(fence(SIMPLE))
      expect((await verdictOf(v, SIMPLE, stub(checker).run)).v).toBeNull()
    }
  })

  test('process.run itself missing (desktop) or not a git repo: null, the checker never runs', async () => {
    const v = new Verifier()
    v.allow(fence(SIMPLE))
    const broken: Run = () => {
      throw new TypeError('process is undefined')
    }
    expect((await verdictOf(v, SIMPLE, broken)).v).toBeNull()

    const w = new Verifier()
    w.allow(fence(SIMPLE))
    const calls: string[] = []
    const noGit: Run = async argv => {
      calls.push(argv[0]!)
      return argv[0] === 'git' ? { exitCode: 128, stdout: '' } : { exitCode: 0, stdout: allCorrect }
    }
    expect((await verdictOf(w, SIMPLE, noGit)).v).toBeNull()
    expect(calls).toEqual(['git'])
  })

  test('a timeout: null, no fallback run after it', async () => {
    const v = new Verifier(30)
    v.allow(fence(SIMPLE))
    const s = stub(
      () =>
        new Promise((_, reject) => {
          setTimeout(() => reject(new Error('timed out')), 40)
        }),
    )
    expect((await verdictOf(v, SIMPLE, s.run)).v).toBeNull()
    expect(s.checks().length).toBe(1)
  })

  test('cache hit: many renders while running and after, one run per fence and directory', async () => {
    const v = new Verifier()
    v.allow(fence(SIMPLE))
    const s = stub(async () => ({ exitCode: 0, stdout: allCorrect }))
    let inv = 0
    for (let i = 0; i < 5; i++) expect(v.lookup(SIMPLE, '/repo', s.run, () => inv++)).toBeUndefined()
    await v.idle()
    for (let i = 0; i < 5; i++) expect(v.lookup(SIMPLE + '\n', '/repo', s.run, () => inv++)).not.toBeUndefined()
    expect(s.checks().length).toBe(1)
    expect(inv).toBe(1)
    expect(fenceHash(SIMPLE)).toBe(fenceHash(SIMPLE + '  \n'))
    expect(fenceHash(SIMPLE)).not.toBe(fenceHash(SIMPLE.replace('12', '13')))
  })
})
