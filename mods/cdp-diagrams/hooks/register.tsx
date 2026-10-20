// cdp-diagrams: draws ```mermaid flowchart / stateDiagram blocks of Claude's
// replies as diagrams. The ui.render hook on AssistantMessage changes the
// drawing and never the stored message. turn.start / tool.call / turn.complete
// observe (next(e)) to note whether a main-loop turn used CDP; after such a
// turn's answer, turn.complete opens $.ui.ask (the person's dialog) to offer a
// diagram (offer.ts). The one message the mod sends the model is the follow-up
// the person asked for there: one $.prompt.submit (followup.ts), during whose
// turn main-loop tool calls are denied. Nothing else reaches the model.
// Fences of CDP turns and of those follow-ups are checked with
// `cdp verify-diagram` (verify.ts) and their edges badged; that runs on the
// host and its result only changes the drawing. On the fullscreen terminal a
// follow-up's drawing moves above the answer it draws and its own row shows a
// pointer (placement.ts); elsewhere it stays in the follow-up's row.

import type { Elements, Register } from 'claude-code'

import { CdpTurnTracker } from './detect.ts'
import { hasMermaid, splitBlocks } from './mermaid.ts'
import { DiagramFollowUp, type DiagramLink } from './followup.ts'
import { type DiagramChoice, DiagramOffer, type OnChoice } from './offer.ts'
import { canPlaceAbove, DiagramPlacement, POINTER } from './placement.ts'
import { altText, kindName, legendTable, prepare, type Run as Styled, styledRows, summary, toSvg, verdictStyle } from './render.ts'
import { MARK, matchEdges, type Run, type Verdict, verdictLine, Verifier } from './verify.ts'
import type { Block } from './mermaid.ts'
import type { Outcome } from './layout.ts'

/** Columns the transcript leaves a reply after its bullet and margins. */
const INDENT = 4

const tracker = new CdpTurnTracker()

/** Whether the last main-loop turn that completed used CDP (MCP or the Bash CLI). */
export const lastTurnUsedCdp = (): boolean => tracker.lastTurnUsedCdp()

const offer = new DiagramOffer()

/** The diagram the person last chose to have drawn, or null. */
export const pendingChoice = (): DiagramChoice | null => offer.pending()

/** Sets the hook point told of each offer's result (null: no diagram) with the answer it was for. */
export const onDiagramChoice = (cb: OnChoice | null): void => {
  offer.onChoice = cb
}

/** Call before submitting the mod's own diagram follow-up, so its end is not offered. */
export const expectDiagramFollowUp = (): void => offer.expectFollowUp()

/** Resolves once the latest offer has settled. */
export const offerSettled = (): Promise<void> => offer.idle()

const followUp = new DiagramFollowUp()

/** Whether `turnId` is the mod's own diagram follow-up turn. */
export const isDiagramTurn = (turnId: string): boolean => followUp.isDiagramTurn(turnId)

/** For a follow-up turn: the answer's turnId and text it draws, and the kinds asked for; else null. */
export const diagramFor = (turnId: string): DiagramLink | null => followUp.diagramFor(turnId)

const verifier = new Verifier()

/** Resolves once every citation check started so far has ended. */
export const verifySettled = (): Promise<void> => verifier.idle()

const placement = new DiagramPlacement()

export const register: Register = on => {
  on('turn.start', ($, e, next) => {
    tracker.start(e)
    followUp.start(e)
    return next(e)
  }).catch(($, e, next) => next(e))

  on('tool.call', ($, e, next) => {
    tracker.call(e)
    // Only during the follow-up turn, main loop only; every other call passes unchanged.
    const deny = followUp.denies(e)
    if (deny !== null) return { deny }
    return next(e)
  }).catch(($, e, next) => next(e))

  on('turn.complete', async ($, e, next) => {
    const used = tracker.complete(e)
    followUp.complete(e)
    if (e.agentId === undefined) {
      try {
        let moved = placement.count(e.answer)
        const link = followUp.diagramFor(e.turnId)
        if (link && e.reason === 'answer' && hasMermaid(e.answer)) moved = placement.complete(link.answer, e.answer) || moved
        if (moved) $.ui.invalidate('ui.render')
      } catch {
        // placement is extra; the follow-up's row draws the diagram without it
      }
    }
    if (used !== undefined) $.ui.log(`cdp-diagrams: turn ${e.turnId} used CDP: ${used}`, { to: 'debug' })
    // A CDP turn's or a diagram follow-up's fences get their citations checked.
    if (e.agentId === undefined && (used === true || followUp.isDiagramTurn(e.turnId))) {
      try {
        if (verifier.allow(e.answer) > 0) {
          $.ui.invalidate('ui.render')
          // Started here, not from a row's ui.render: on the fullscreen terminal a
          // run asked through a render the engine drew again never replied (I4 live).
          const answer = e.answer
          void $.session
            .cwd()
            .then(cwd =>
              verifier.prefetch(answer, cwd, (argv, init) => $.process.run(argv, init), () => $.ui.invalidate('ui.render')),
            )
            .catch(() => {})
        }
      } catch {
        // badges are extra; the drawing stands without them
      }
    }
    const r = await next(e)
    // Unawaited: the turn ends now; the dialog follows its answer row.
    if (offer.maybeOffer(e, used === true, (q, o) => $.ui.ask(q, o))) {
      const { turnId, answer } = e
      void offer.idle().then(() => {
        const choice = offer.take()
        if (!choice) return
        return followUp.begin(
          choice,
          turnId,
          answer,
          text => $.prompt.submit({ text }),
          () => offer.expectFollowUp(),
          () => offer.cancelFollowUp(),
        )
      })
    }
    return r
  }).catch(($, e, next) => next(e))

  on('ui.render', { component: 'AssistantMessage' }, async ($, e, next) => {
    const text = e.props.text
    if (e.props.isSummary) return next(e)

    // Fullscreen terminal only: a follow-up's reply row becomes a pointer once
    // its answer row draws the diagram above itself (placement.ts).
    const above = canPlaceAbove(e.surface, e.viewport)
    const asReply = placement.replyRow(text, e.surface, above)
    const asAnswer = asReply ? null : placement.answerRow(text, e.surface, above)
    if (asReply?.changed || asAnswer?.changed) $.ui.invalidate('ui.render')
    if (!asAnswer && asReply?.row.kind !== 'pointer' && !hasMermaid(text)) return next(e)

    const t = $.ui.resolve(e)
    const { Box, Text, Markdown } = t
    // Every surface but the terminal draws Svg (Elements); the table itself
    // answers `in` for any name, so the surface decides.
    const Svg = e.surface === 'terminal' ? null : (t as Elements['desktop']).Svg
    const columns = Math.max(30, (e.viewport?.columns ?? 100) - INDENT)

    if (asReply?.row.kind === 'pointer') return <Text dimColor>{POINTER}</Text>

    const blocks = [...splitBlocks(text), ...(asAnswer ? splitBlocks(asAnswer.reply) : [])]
    let cwd: string | null = null
    let run: Run | null = null
    if (blocks.some(b => b.kind === 'mermaid' && verifier.isAllowed(b.source))) {
      try {
        cwd = await $.session.cwd()
        run = (argv, init) => $.process.run(argv, init)
      } catch {
        cwd = null
      }
    }
    const verdictFor = (source: string): Verdict | null | undefined => {
      if (cwd === null || run === null) return undefined
      try {
        return verifier.lookup(source, cwd, run, () => $.ui.invalidate('ui.render'))
      } catch {
        return undefined
      }
    }

    // One row of styled runs as a Text of Texts.
    const row = (runs: Styled[], wrap: 'truncate-end' | 'wrap' = 'wrap') => (
      <Text wrap={wrap}>
        {runs.map(r =>
          r.style ? (
            <Text color={r.style.color} dimColor={r.style.dimColor} bold={r.style.bold}>
              {r.text}
            </Text>
          ) : (
            r.text
          ),
        )}
      </Text>
    )

    const draw = (source: string, k: string) => {
      const blocks: Block[] = splitBlocks(source)
      // The model's one line about a diagram is its caption: it goes in the
      // diagram's title and leaves the text. Either the line that introduces
      // the fence ("Flowchart of the call flow:"), or else the line under it.
      const captions = new Map<number, string>()
      const plainLine = (l: string) => !!l && !/^(```|~~~|#|[-*>] |\d+\. |\|)/.test(l) && l.length <= 240
      blocks.forEach((b, j) => {
        if (b.kind !== 'mermaid') return
        const before = blocks[j - 1]
        if (before?.kind === 'text') {
          const m = /(?:^|\n)([^\n]+):[ \t]*\n\s*$/.exec(before.text)
          const line = m?.[1]?.trim() ?? ''
          if (m && plainLine(line)) {
            captions.set(j, line)
            before.text = before.text.slice(0, m.index)
            return
          }
        }
        const after = blocks[j + 1]
        if (after?.kind !== 'text') return
        const m = /^\s*\n?([^\n]+)/.exec(after.text)
        const line = m?.[1]?.trim() ?? ''
        // Not a line that introduces what follows (that one is the next fence's).
        if (!plainLine(line) || /:$/.test(line)) return
        captions.set(j, line)
        after.text = after.text.replace(m![0], '')
      })
      return blocks.map((block, j) => {
      const i = `${k}${j}`
      if (block.kind === 'text') {
        return block.text.trim() ? <Markdown key={`m${i}`} text={block.text} /> : null
      }
      const p = prepare(block.source, Svg ? null : columns)
      if (!p.ok) {
        return (
          <Box key={`d${i}`} flexDirection="column">
            <Text dimColor>mermaid diagram not drawn: {p.reason}; showing the source</Text>
            <Markdown text={block.raw} />
          </Box>
        )
      }
      const verdict = verdictFor(block.source)
      const matched = verdict ? matchEdges(p.graph, verdict) : null
      const checkedOf = (edge: number) => (matched ? matched[edge] : undefined)
      const dashed = (edge: number) => p.graph.edges[edge]?.dashed ?? false
      const legend = legendTable(p.layout.legend, p.unplaced, checkedOf, columns)
      const outcomes = p.layout.routes.reduce<(Outcome | null)[]>((a, r) => ((a[r.edge] = r.outcome), a), [])
      const notes = p.graph.notes.map(n => `note ${n}`)
      const caption = captions.get(j)
      const ok = verdict ? verdict.edges.every(e => e.status === 'correct' || e.status === 'inferred') : false
      return (
        <Box key={`d${i}`} flexDirection="column">
          {row([
            { text: `◆ ${kindName(p.graph)}`, style: { bold: true, color: 'claude' } },
            ...(caption ? [{ text: `  ${caption}`, style: null }] : []),
          ])}
          <Text dimColor>{'─'.repeat(Math.min(columns, Math.max(24, p.layout.width)))}</Text>
          {Svg ? (
            <Svg source={toSvg(p.layout)} alt={altText(p.graph)} />
          ) : (
            <Box flexDirection="column">
              {styledRows({ lines: p.lines ?? [], owners: p.owners, outcomes }, e => checkedOf(e)?.status, dashed).map(runs =>
                runs.length ? row(runs, 'truncate-end') : <Text> </Text>,
              )}
            </Box>
          )}
          {legend.length > 0 && <Box flexDirection="column">{legend.map(runs => row(runs))}</Box>}
          {verdict && row([{ text: `${ok ? MARK.correct : '!'} ${verdictLine(p.graph, verdict)}`, style: verdictStyle(verdict.edges) }])}
          <Text dimColor wrap="wrap">{summary(p.graph)}</Text>
          {notes.map(n => (
            <Text dimColor wrap="wrap">{n}</Text>
          ))}
        </Box>
      )
    })
    }

    const own = hasMermaid(text) ? <Box flexDirection="column">{draw(text, 'o')}</Box> : await next(e)
    if (!asAnswer) return own
    // Prepended: the answer below draws as it did.
    return (
      <Box flexDirection="column">
        <Box key="above" flexDirection="column">
          <Text dimColor>diagram of this answer (asked for below)</Text>
          {draw(asAnswer.reply, 'a')}
        </Box>
        {own}
      </Box>
    )
  }).catch(($, e, next) => next(e))
}
