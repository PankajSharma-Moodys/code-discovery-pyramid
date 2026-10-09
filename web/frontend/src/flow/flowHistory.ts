export interface FlowViewState {
  expanded: string[]; // sorted, so equality is order-independent
  selectedId: string | null;
}

export const INITIAL_VIEW: FlowViewState = { expanded: [], selectedId: null };
const MAX_HISTORY = 50;

export function sameView(a: FlowViewState, b: FlowViewState): boolean {
  return a.selectedId === b.selectedId && a.expanded.length === b.expanded.length && a.expanded.every((id, i) => id === b.expanded[i]);
}

export function pushState(history: FlowViewState[], current: FlowViewState): FlowViewState[] {
  const last = history[history.length - 1];
  if (last && sameView(last, current)) return history;
  return [...history, current].slice(-MAX_HISTORY);
}

export function popState(history: FlowViewState[]): { history: FlowViewState[]; state: FlowViewState | null } {
  if (history.length === 0) return { history, state: null };
  return { history: history.slice(0, -1), state: history[history.length - 1] };
}
