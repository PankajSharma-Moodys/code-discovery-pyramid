// cdp-diagrams: draws ```mermaid flowchart / stateDiagram blocks of Claude's
// replies as diagrams. Display only: one ui.render hook on AssistantMessage,
// which changes the drawing and never the stored message (no tools, no MCP,
// no session.append, no prompt hooks), so nothing reaches the model.

import type { Elements, Register } from 'claude-code'

import { hasMermaid, splitBlocks } from './mermaid.ts'
import { altText, legendText, prepare, summary, toSvg } from './render.ts'

/** Columns the transcript leaves a reply after its bullet and margins. */
const INDENT = 4

export const register: Register = on => {
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
