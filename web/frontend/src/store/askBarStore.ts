import { create } from "zustand";

/** `cdp query`'s kinds (`cdp/query.py`'s `QUERIES` dict, mirrored here since
 * the wrapper endpoint (`/api/query`) deliberately has no fixed
 * `response_model` to type this from -- `web/api/app.py:get_query`). Keep in
 * sync with that dict by hand; there is no generated contract for it. */
export const QUERY_KINDS = [
  "symbol", "file", "module", "routes", "table", "config",
  "paths", "trace", "search", "claims", "unknowns", "conflicts",
  "stats", "coverage",
] as const;
export type QueryKind = (typeof QUERY_KINDS)[number];

export interface AskQuery {
  kind: QueryKind;
  term?: string;
  frm?: string;
  to?: string;
}

/** Parses the ask-bar's free-text input into a `cdp query` kind + args, per
 * `WEB_RESEARCH.md` §4: "the ask-bar accepts CDP query kinds directly
 * (`trace OrderResource`, `symbol foo`, `unknowns`, `table orders`)". No
 * natural-language mode this pass -- that is explicitly optional in the
 * doc, and shipping it would mean guessing at intent instead of citing a
 * command, which is the one thing this UI must never do. */
export function parseAskInput(raw: string): AskQuery | null {
  const trimmed = raw.trim();
  if (!trimmed) return null;
  const [head, ...rest] = trimmed.split(/\s+/);
  const kind = head.toLowerCase();
  const remainder = rest.join(" ").trim() || undefined;

  if ((QUERY_KINDS as readonly string[]).includes(kind)) {
    if (kind === "paths" && remainder) {
      const [frm, to] = remainder.split("->").map((s) => s.trim() || undefined);
      return { kind: "paths", frm, to };
    }
    return { kind: kind as QueryKind, term: remainder };
  }
  // No recognized kind prefix: fall back to `search`, the one kind that
  // takes free text and searches claims/symbols/unknowns/files at once.
  return { kind: "search", term: trimmed };
}

/** Renders the literal command the ask-bar ran, so a result is always
 * traceable to the exact query it answers (§4: "must render as 'I ran
 * `cdp query X` for you' ... visible and editable"). */
export function formatAskCommand(q: AskQuery): string {
  if (q.kind === "paths") {
    const parts = ["cdp", "query", "paths"];
    if (q.frm) parts.push("--from", q.frm);
    if (q.to) parts.push("--to", q.to);
    return parts.join(" ");
  }
  return ["cdp", "query", q.kind, q.term].filter(Boolean).join(" ");
}

interface AskBarState {
  isOpen: boolean;
  draft: string;
  submitted: AskQuery | null;
  open: () => void;
  close: () => void;
  toggle: () => void;
  setDraft: (draft: string) => void;
  submit: () => void;
  clear: () => void;
}

export const useAskBarStore = create<AskBarState>((set, get) => ({
  isOpen: false,
  draft: "",
  submitted: null,

  open: () => set({ isOpen: true }),
  close: () => set({ isOpen: false }),
  toggle: () => set((s) => ({ isOpen: !s.isOpen })),
  setDraft: (draft) => set({ draft }),
  submit: () => set({ submitted: parseAskInput(get().draft) }),
  clear: () => set({ draft: "", submitted: null }),
}));
