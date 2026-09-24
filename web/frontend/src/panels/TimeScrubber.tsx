import { useEffect, useState } from "react";
import { useDiff, useSnapshots } from "../api/hooks.ts";
import { useAtlasStore } from "../store/atlasStore.ts";
import { CollapsiblePanel } from "./CollapsiblePanel.tsx";

/** How long an `AtlasCanvas` pulse/fade stays lit before clearing, so
 * scrubbing to a new position always re-triggers a fresh, visible pulse
 * rather than silently extending the previous one. */
const HIGHLIGHT_MS = 2200;

function shortSha(sha: string): string {
  return sha.slice(0, 8);
}

/** Real-commit replay: scrubs across this repo's actual scanned commits
 * (`snapshot_meta`, via `/api/snapshots`) and, on each move, diffs the two
 * adjacent real snapshots (`/api/diff`) and pushes the touched L3 module
 * ids onto `atlasStore`'s `diffHighlight` for `AtlasCanvas` to pulse/fade --
 * no synthetic commits or fabricated deltas, only what was actually scanned. */
export function TimeScrubber() {
  const { data: snapshotsData, isLoading } = useSnapshots();
  const setDiffHighlight = useAtlasStore((s) => s.setDiffHighlight);
  const jumpTo = useAtlasStore((s) => s.jumpTo);
  const [index, setIndex] = useState<number | null>(null);

  const snapshots = snapshotsData?.snapshots ?? [];

  useEffect(() => {
    if (snapshots.length > 0 && index === null) setIndex(snapshots.length - 1);
  }, [snapshots.length, index]);

  // Switching repos refetches `snapshots` under the same `index` state --
  // a repo with fewer scanned commits than the previous one's scrubber
  // position left `index` pointing past the new array's end, and
  // `snapshots[index - 1]` read `undefined` below with nothing to catch it
  // (no error boundary in this app), blanking the whole page until reload.
  // Clamping here, rather than resetting `index` on repo change, also
  // covers any other case where `snapshots` shrinks under an existing index.
  const safeIndex = index === null || snapshots.length === 0 ? null : Math.min(index, snapshots.length - 1);

  const hasPrior = safeIndex !== null && safeIndex > 0;
  const oldSha = hasPrior ? snapshots[safeIndex - 1].commit_sha : null;
  const newSha = hasPrior ? snapshots[safeIndex!].commit_sha : null;
  const { data: diffResult } = useDiff(oldSha, newSha);

  useEffect(() => {
    if (!diffResult) return;
    jumpTo("L3");
    setDiffHighlight({
      added: diffResult.diff.modules.added,
      removed: diffResult.diff.modules.removed,
    });
    const timer = setTimeout(() => setDiffHighlight(null), HIGHLIGHT_MS);
    return () => clearTimeout(timer);
  }, [diffResult, jumpTo, setDiffHighlight]);

  if (isLoading) return null;

  if (snapshots.length < 2) {
    return (
      <CollapsiblePanel title="What changed between commits?" side="right" width="26rem">
        <div className="text-xs" style={{ color: "var(--atlas-text-dim)" }}>
          Only {snapshots.length} scanned commit{snapshots.length === 1 ? "" : "s"} so far, and
          comparing needs two. Scan again after your next commit and this becomes a timeline.
        </div>
      </CollapsiblePanel>
    );
  }

  return (
    <CollapsiblePanel
      title="What changed between commits?"
      side="right"
      width="26rem"
      badge={`${snapshots.length} scans`}
    >
      <div className="mb-1 text-xs" style={{ color: "var(--atlas-text-dim)" }}>
        Drag to compare two scanned commits. Modules that appeared pulse on the map.
      </div>
      <input
        type="range"
        min={0}
        max={snapshots.length - 1}
        value={safeIndex ?? snapshots.length - 1}
        onChange={(e) => setIndex(Number(e.target.value))}
        className="w-full"
      />
      <div className="mt-1 flex justify-between text-xs" style={{ color: "var(--atlas-text-dim)" }}>
        <span>{shortSha(snapshots[0].commit_sha)}</span>
        <span>{shortSha(snapshots[snapshots.length - 1].commit_sha)}</span>
      </div>
      {safeIndex !== null && (
        <div className="mt-2 text-xs" style={{ color: "var(--atlas-text-dim)" }}>
          {hasPrior
            ? `${shortSha(snapshots[safeIndex - 1].commit_sha)} → ${shortSha(snapshots[safeIndex].commit_sha)}`
            : `${shortSha(snapshots[0].commit_sha)} (earliest scanned commit, nothing before it)`}
        </div>
      )}
      {diffResult && (
        <div className="mt-2 max-h-32 overflow-y-auto text-xs">
          <div>modules added: {diffResult.diff.modules.added.length ? diffResult.diff.modules.added.join(", ") : "none"}</div>
          <div>
            modules removed:{" "}
            {diffResult.diff.modules.removed.length ? diffResult.diff.modules.removed.join(", ") : "none"}
          </div>
          {diffResult.diff.findings.length > 0 && (
            <ul className="mt-1 list-disc pl-4">
              {diffResult.diff.findings.map((f, i) => (
                <li key={i}>{f}</li>
              ))}
            </ul>
          )}
        </div>
      )}
    </CollapsiblePanel>
  );
}
