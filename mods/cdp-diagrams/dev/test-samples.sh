#!/bin/sh
# Runs the layout invariants over a folder of real .mmd diagrams without
# committing them: writes a temporary test that embeds them, runs
# `claude plugin test`, and deletes it again.
#   dev/test-samples.sh ~/.cdp-phase1/diagrams/mmd
set -eu
dir=${1:?usage: dev/test-samples.sh <folder of .mmd files>}
mod=$(cd "$(dirname "$0")/.." && pwd)
out="$mod/tests/samples.local.test.ts"
trap 'rm -f "$out"' EXIT INT TERM
node -e '
const fs = require("fs"), path = require("path")
const dir = process.argv[1]
const files = fs.readdirSync(dir).filter(f => f.endsWith(".mmd")).sort()
if (!files.length) { console.error("no .mmd files in " + dir); process.exit(1) }
const samples = Object.fromEntries(files.map(f => [f, fs.readFileSync(path.join(dir, f), "utf8")]))
process.stdout.write(`import { describe, expect, test } from "claude-code/testing"
import { parseMermaid } from "../hooks/mermaid.ts"
import { problems } from "./check.ts"
const SAMPLES: Record<string, string> = ${JSON.stringify(samples)}
describe("local samples", () => {
  for (const [name, source] of Object.entries(SAMPLES)) {
    test(name + ": parses; lays out at 200, 120, 100 columns and as SVG", () => {
      const g = parseMermaid(source)
      expect(g.nodes.length).toBeGreaterThan(0)
      expect(g.edges.length).toBeGreaterThan(0)
      for (const cols of [200, 120, 100, null]) expect(problems(source, cols)).toEqual([])
    })
    test(name + ": drawn through the engine on terminal and desktop", async $ => {
      const text = "Answer:\\n\\n\\x60\\x60\\x60mermaid\\n" + source + "\\n\\x60\\x60\\x60\\n"
      for (const surface of ["terminal", "desktop"] as const) {
        const ui = await $.ui.mount({ plugin: "cdp-diagrams", surface, component: "AssistantMessage",
          props: { text, isFirstOfReply: true }, viewport: { columns: 124, rows: 50 } })
        expect(await ui.find({ type: "Text", text: / nodes · / })).toBeDefined()
        expect(await ui.find({ type: "Text", text: /not drawn/ })).toBeUndefined()
        await ui.unmount()
      }
    })
  }
})
`)
' "$dir" > "$out"
claude plugin test "$mod"
