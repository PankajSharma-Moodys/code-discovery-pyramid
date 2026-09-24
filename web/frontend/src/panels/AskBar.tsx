import { useEffect, useMemo, useRef, useState } from "react";
import { useAskQuery, useSearch, useSourceFile } from "../api/hooks.ts";
import { formatAskCommand, QUERY_KINDS, useAskBarStore } from "../store/askBarStore.ts";
import { useAtlasStore } from "../store/atlasStore.ts";
import { useViewStore } from "../store/viewStore.ts";

interface Anchor {
  file: string;
  line: number;
}

const ANCHOR_RE = /^(.+):(\d+)$/;

function looksLikePath(s: string): boolean {
  return s.includes("/") || /\.\w+$/.test(s);
}

/** Walks any `/api/query` result -- shape varies by `kind`, deliberately
 * has no fixed model (`web/api/app.py:get_query`) -- pulling out every
 * `"file:line"` string it can find. This is what lets the ask-bar answer
 * every kind without fourteen bespoke renderers: whatever the shape, its
 * citations surface as clickable anchors (§10: no summary without a
 * `file:line` behind it). Capped so a huge `search`/`unknowns` result can't
 * hang the render. */
function extractAnchors(value: unknown, out: Anchor[] = [], seen = new Set<string>()): Anchor[] {
  if (out.length >= 40) return out;
  if (typeof value === "string") {
    const m = ANCHOR_RE.exec(value);
    if (m && looksLikePath(m[1]) && !seen.has(value)) {
      seen.add(value);
      out.push({ file: m[1], line: Number(m[2]) });
    }
  } else if (Array.isArray(value)) {
    for (const v of value) extractAnchors(v, out, seen);
  } else if (value && typeof value === "object") {
    for (const v of Object.values(value)) extractAnchors(v, out, seen);
  }
  return out;
}

function AnchorButton({ anchor, onOpen, isOpen }: { anchor: Anchor; onOpen: () => void; isOpen: boolean }) {
  return (
    <button
      onClick={onOpen}
      className="truncate rounded border px-1.5 py-0.5 text-left text-[11px]"
      style={{
        borderColor: "var(--atlas-border)",
        color: isOpen ? "var(--atlas-accent)" : "var(--atlas-text)",
      }}
    >
      {anchor.file}:{anchor.line}
    </button>
  );
}

function SourcePeek({ anchor }: { anchor: Anchor }) {
  const { data } = useSourceFile(anchor.file, anchor.line);
  return (
    <pre
      className="mt-2 max-h-40 overflow-auto rounded border p-2 font-mono text-xs"
      style={{ borderColor: "var(--atlas-border)", background: "var(--atlas-bg-0)" }}
    >
      {data?.lines.map((line, idx) => {
        const lineNo = (data.start_line ?? 1) + idx;
        const isTarget = lineNo === anchor.line;
        return (
          <div
            key={idx}
            style={{ background: isTarget ? "color-mix(in srgb, var(--atlas-accent) 20%, transparent)" : undefined }}
          >
            {lineNo} {line}
          </div>
        );
      }) ?? "loading…"}
    </pre>
  );
}

/** Persistent cmd-K ask-bar, shared by both rooms (`WEB_RESEARCH.md` §2, §4).
 * Accepts `cdp query` kinds directly (`trace OrderResource`, `symbol foo`,
 * `unknowns`, `table orders`) with typeahead over `xref.symbols`; a `module`
 * or `file` result with exactly one match selects and flies the Atlas to
 * it, a `trace` result hands off entirely to the existing path-trace panel
 * (`TracePanel`/`atlasStore.startTrace`) rather than a second trace UI. No
 * natural-language mode this pass -- see `askBarStore.ts`'s
 * `parseAskInput`. */
export function AskBar() {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [openAnchor, setOpenAnchor] = useState<Anchor | null>(null);

  const isOpen = useAskBarStore((s) => s.isOpen);
  const draft = useAskBarStore((s) => s.draft);
  const submitted = useAskBarStore((s) => s.submitted);
  const open = useAskBarStore((s) => s.open);
  const close = useAskBarStore((s) => s.close);
  const toggle = useAskBarStore((s) => s.toggle);
  const setDraft = useAskBarStore((s) => s.setDraft);
  const submit = useAskBarStore((s) => s.submit);
  const clear = useAskBarStore((s) => s.clear);

  const jumpTo = useAtlasStore((s) => s.jumpTo);
  const selectNode = useAtlasStore((s) => s.selectNode);
  const startTrace = useAtlasStore((s) => s.startTrace);
  const setView = useViewStore((s) => s.setView);

  const isTraceQuery = submitted === null && /^(trace|symbol)\s+\S/i.test(draft);
  const typeaheadPrefix = draft.match(/^(trace|symbol)\s+(.*)$/i)?.[2] ?? "";
  // `WEB_REDESIGN_RESEARCH.md` §4's server-side search-to-focus: ranked
  // symbol/file typeahead over the thin `/api/search` endpoint, not the old
  // full-L0-fetch-then-substring-filter (`useSymbolTypeahead`, 6.8MB on
  // `unified-store`). One query serves both the `trace|symbol <prefix>`
  // typeahead below and the free-text jump-to-result list further down.
  const { data: prefixResults } = useSearch(typeaheadPrefix, isOpen && isTraceQuery);
  const suggestions = useMemo(() => {
    if (!isTraceQuery || !prefixResults) return [];
    return prefixResults.filter((r) => r.kind === "symbol").map((r) => r.id).slice(0, 8);
  }, [isTraceQuery, prefixResults]);

  // Free-text jump-to-result: shown only when the draft has no recognized
  // `cdp query` kind prefix and nothing has been submitted yet -- a direct
  // "search-to-focus" shortcut so a bare repo-vocabulary term (a file path, a
  // class name) doesn't require running the full `search` query and hunting
  // its `anchors` first.
  const isFreeText = submitted === null && !isTraceQuery && !(QUERY_KINDS as readonly string[]).includes(
    draft.trim().split(/\s+/, 1)[0]?.toLowerCase() ?? "",
  );
  const { data: freeTextResults } = useSearch(draft.trim(), isOpen && isFreeText);
  const jumpSuggestions = useMemo(
    () => (isFreeText ? (freeTextResults ?? []).slice(0, 8) : []),
    [isFreeText, freeTextResults],
  );

  const queryForBackend = submitted && submitted.kind !== "trace" ? submitted : null;
  const { data: result, isLoading, error } = useAskQuery(queryForBackend);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        toggle();
      } else if (event.key === "Escape" && isOpen) {
        close();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [toggle, close, isOpen]);

  useEffect(() => {
    if (isOpen) inputRef.current?.focus();
  }, [isOpen]);

  // Route the answer onto the canvas (§4: "routes every answer back onto
  // the canvas -- a query result is never just a table"). `trace` hands off
  // to the existing TracePanel entirely; `module`/`file` select + jump when
  // the match is unambiguous.
  useEffect(() => {
    if (!submitted) return;
    if (submitted.kind === "trace" && submitted.term) {
      startTrace(submitted.term);
      setView("atlas");
      return;
    }
    if (!result) return;
    if (submitted.kind === "module") {
      const found = result.found as { name: string }[] | undefined;
      if (found?.length === 1) {
        jumpTo("L3");
        selectNode(found[0].name);
        setView("atlas");
      }
    } else if (submitted.kind === "file") {
      const found = result.found as { path: string }[] | undefined;
      if (found?.length === 1) {
        jumpTo("L1");
        selectNode(found[0].path);
        setView("atlas");
      }
    }
  }, [submitted, result, startTrace, jumpTo, selectNode, setView]);

  const anchors = useMemo(() => (result ? extractAnchors(result) : []), [result]);

  // A new query invalidates whichever anchor was pinned open from the
  // previous one -- otherwise `SourcePeek` keeps showing stale source for
  // an anchor that isn't even in the new result.
  useEffect(() => {
    setOpenAnchor(null);
  }, [submitted]);

  if (!isOpen) {
    return (
      <button
        onClick={open}
        className="atlas-ask-bar-trigger absolute bottom-3 right-1/2 z-30 translate-x-1/2 rounded-full px-4 py-1.5 text-xs shadow-lg"
        style={{ background: "var(--atlas-bg-2)", color: "var(--atlas-text-dim)", border: "1px solid var(--atlas-border)" }}
      >
        ask CDP · ⌘K
      </button>
    );
  }

  return (
    <div className="absolute inset-0 z-40 flex items-start justify-center pt-24" onClick={close}>
      <div
        className="atlas-card w-[36rem] max-w-[90vw] p-3"
        onClick={(e) => e.stopPropagation()}
      >
        <input
          ref={inputRef}
          value={draft}
          onChange={(e) => {
            setDraft(e.target.value);
            useAskBarStore.setState({ submitted: null });
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter") submit();
          }}
          placeholder="trace OrderResource · symbol foo · unknowns · table orders"
          className="w-full rounded border bg-transparent px-2 py-1.5 text-sm outline-none"
          style={{ borderColor: "var(--atlas-border)", color: "var(--atlas-text)" }}
        />

        {suggestions.length > 0 && (
          <ul className="mt-1 max-h-40 overflow-y-auto text-xs">
            {suggestions.map((fqn) => (
              <li key={fqn}>
                <button
                  className="w-full truncate rounded px-2 py-1 text-left"
                  style={{ color: "var(--atlas-text-dim)" }}
                  onClick={() => {
                    const kind = draft.match(/^(trace|symbol)/i)?.[1].toLowerCase() ?? "symbol";
                    setDraft(`${kind} ${fqn}`);
                    inputRef.current?.focus();
                  }}
                >
                  {fqn}
                </button>
              </li>
            ))}
          </ul>
        )}

        {jumpSuggestions.length > 0 && (
          <ul className="mt-1 max-h-40 overflow-y-auto text-xs">
            {jumpSuggestions.map((r) => (
              <li key={`${r.kind}:${r.id}`}>
                <button
                  className="flex w-full items-center justify-between gap-2 truncate rounded px-2 py-1 text-left"
                  style={{ color: "var(--atlas-text-dim)" }}
                  onClick={() => {
                    if (r.kind === "file") {
                      jumpTo("L1");
                      selectNode(r.id);
                      setView("atlas");
                      close();
                    } else {
                      setDraft(`symbol ${r.id}`);
                      inputRef.current?.focus();
                    }
                  }}
                >
                  <span className="truncate">{r.label}</span>
                  <span className="shrink-0 font-mono text-[10px] opacity-60">{r.kind}</span>
                </button>
              </li>
            ))}
          </ul>
        )}

        {submitted && (
          <div className="mt-3 border-t pt-2" style={{ borderColor: "var(--atlas-border)" }}>
            <div className="mb-2 flex items-center justify-between gap-2 font-mono text-[11px]" style={{ color: "var(--atlas-text-dim)" }}>
              <span>ran: {formatAskCommand(submitted)}</span>
              <button onClick={clear} style={{ color: "var(--atlas-text-dim)" }}>
                clear
              </button>
            </div>

            {submitted.kind === "trace" ? (
              <div className="text-xs" style={{ color: "var(--atlas-text-dim)" }}>
                sent to the path-trace panel — switching to the Atlas.
              </div>
            ) : (
              <>
                {isLoading && <div className="text-xs" style={{ color: "var(--atlas-text-dim)" }}>querying…</div>}
                {error && <div className="text-xs" style={{ color: "var(--atlas-unknown)" }}>{String(error)}</div>}
                {result && (
                  <>
                    {typeof result.count === "number" && (
                      <div className="mb-1 text-xs" style={{ color: "var(--atlas-text-dim)" }}>
                        {result.count} result{result.count === 1 ? "" : "s"}
                      </div>
                    )}
                    {anchors.length > 0 ? (
                      <div className="flex max-h-40 flex-col gap-1 overflow-y-auto">
                        {anchors.map((a, i) => (
                          <div key={i}>
                            <AnchorButton
                              anchor={a}
                              isOpen={openAnchor?.file === a.file && openAnchor?.line === a.line}
                              onOpen={() => setOpenAnchor((cur) => (cur?.file === a.file && cur?.line === a.line ? null : a))}
                            />
                          </div>
                        ))}
                      </div>
                    ) : (
                      <div className="text-xs" style={{ color: "var(--atlas-text-dim)" }}>
                        no citable anchors in this result.
                      </div>
                    )}
                    {openAnchor && <SourcePeek anchor={openAnchor} />}
                    <details className="mt-2">
                      <summary className="cursor-pointer text-[11px]" style={{ color: "var(--atlas-text-dim)" }}>
                        raw result
                      </summary>
                      <pre className="mt-1 max-h-48 overflow-auto rounded border p-2 font-mono text-[10px]" style={{ borderColor: "var(--atlas-border)" }}>
                        {JSON.stringify(result, null, 2)}
                      </pre>
                    </details>
                  </>
                )}
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
