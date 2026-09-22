/**
 * Single source of truth for the confidence→color/stroke mapping used by
 * both `InspectorRail` (per-claim) and the Confidence lens (per-node
 * rollup). The enum is the schema's, not a UI invention:
 * `schema/patch-1.0.0.json`'s `confidence` def -- `high|medium|low|contested`
 * -- confirmed against this repo's own `.cdp/index.db` `state` artifact
 * while planning this (129 `high` / 28 `medium` claims, zero `low`/
 * `contested`). There is no `verified`/`inferred` value in real data.
 */
export type ConfidenceBucket = "high" | "medium" | "low" | "contested" | "unreviewed";

export function confidenceColor(bucket: ConfidenceBucket): string {
  switch (bucket) {
    case "high":
      return "var(--atlas-verified)";
    case "medium":
      return "var(--atlas-inferred)";
    case "low":
      return "var(--atlas-unknown)";
    case "contested":
      return "var(--atlas-contested)";
    default:
      return "var(--atlas-text-dim)";
  }
}

export function confidenceStroke(bucket: ConfidenceBucket): "solid" | "dashed" | "dotted" {
  switch (bucket) {
    case "high":
      return "solid";
    case "medium":
      return "dashed";
    default:
      return "dotted";
  }
}

const RANK: Record<Exclude<ConfidenceBucket, "unreviewed">, number> = {
  contested: 0,
  low: 1,
  medium: 2,
  high: 3,
};

/** Most-conservative-wins: a node with any low/contested claim is not
 * "high confidence" just because it also has a high-confidence claim --
 * the weakest claim is the honest summary of how sure we are. */
export function dominantConfidence(confidences: string[]): ConfidenceBucket {
  if (confidences.length === 0) return "unreviewed";
  let worst: ConfidenceBucket = "high";
  for (const raw of confidences) {
    if (raw !== "high" && raw !== "medium" && raw !== "low" && raw !== "contested") continue;
    if (RANK[raw] < RANK[worst as Exclude<ConfidenceBucket, "unreviewed">]) worst = raw;
  }
  return worst;
}
