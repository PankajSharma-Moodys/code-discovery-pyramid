/** Pure helpers for the Control Room's Claude-runner confirm step and spend line. */
export function remainingScopes(waves: { done: number; total: number }[]): number {
  return waves.reduce((sum, w) => sum + Math.max(0, w.total - w.done), 0);
}

export function formatSpend(spent: number, budget: number): string {
  return `$${spent.toFixed(2)} of $${budget.toFixed(2)} (estimate)`;
}
