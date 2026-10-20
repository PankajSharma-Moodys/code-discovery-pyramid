// cdp-diagrams: draws ```mermaid flowchart / stateDiagram blocks of Claude's
// replies as diagrams. The ui.render hook on AssistantMessage changes the
// drawing and never the stored message. turn.start / tool.call / turn.complete
// observe (next(e)) to note whether a main-loop turn used CDP; after such a
// turn's answer, turn.complete opens $.ui.ask (the person's dialog) to offer a
// diagram (offer.ts). The one message the mod sends the model is the follow-up
// the person asked for there: one $.prompt.submit (followup.ts), during whose
// turn main-loop tool calls are denied. Nothing else reaches the model.

import type { Elements, Register } from 'claude-code'

import { CdpTurnTracker } from './detect.ts'
import { hasMermaid, splitBlocks } from './mermaid.ts'
import { DiagramFollowUp, type DiagramLink } from './followup.ts'
import { type DiagramChoice, DiagramOffer, type OnChoice } from './offer.ts'
import { altText, legendText, prepare, summary, toSvg } from './render.ts'

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
    if (used !== undefined) $.ui.log(`cdp-diagrams: turn ${e.turnId} used CDP: ${used}`, { to: 'debug' })
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
    if (e.props.isSummary || !hasMermaid(text)) return next(e)

    const t = $.ui.resolve(e)
    const { Box, Text, Markdown } = t
    // Every surface but the terminal draws Svg (Elements); the table itself
    // answers `in` for any name, so the surface decides.
    const Svg = e.surface === 'terminal' ? null : (t as Elements['desktop']).Svg
    const columns = Math.max(30, (e.viewport?.columns ?? 100) - INDENT)

    const parts = splitBlocks(text).map((block, i) => {
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
      const pad = Math.max(2, ...p.layout.legend.map(r => r.tag.length))
      const legend = p.layout.legend.map(r => legendText(r, p.unplaced, pad))
      const notes = p.graph.notes.map(n => `note ${n}`)
      return (
        <Box key={`d${i}`} flexDirection="column">
          <Text dimColor>{summary(p.graph)}</Text>
          {Svg ? (
            <Svg source={toSvg(p.layout)} alt={altText(p.graph)} />
          ) : (
            <Box flexDirection="column">
              {(p.lines ?? []).map(line => (
                <Text wrap="truncate-end">{line || ' '}</Text>
              ))}
            </Box>
          )}
          {legend.length > 0 && (
            <Box flexDirection="column">
              {legend.map(row => (
                <Text>{row}</Text>
              ))}
            </Box>
          )}
          {notes.map(n => (
            <Text dimColor>{n}</Text>
          ))}
        </Box>
      )
    })

    return <Box flexDirection="column">{parts}</Box>
  }).catch(($, e, next) => next(e))
}
