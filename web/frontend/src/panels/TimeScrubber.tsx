import { useEffect, useState } from "react";
import { useDiff, useSnapshots } from "../api/hooks.ts";
import { useAtlasStore } from "../store/atlasStore.ts";

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

  const hasPrior = index !== null && index > 0;
  const oldSha = hasPrior ? snapshots[index - 1].commit_sha : null;
  const newSha = hasPrior ? snapshots[index!].commit_sha : null;
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
      <div
        className="absolute bottom-0 right-0 z-20 w-[22rem] p-3 text-xs"
        style={{ color: "var(--atlas-text-dim)" }}
      >
        time scrubber needs at least 2 scanned commits ({snapshots.length} available -- run `cdp scan` again after
        another commit)
      </div>
    );
  }

  return (
    <div
      className="absolute bottom-0 right-0 z-20 w-[26rem] border-l border-t p-3 text-sm backdrop-blur-md"
      style={{
        background: "color-mix(in srgb, var(--atlas-bg-1) 92%, transparent)",
        borderColor: "var(--atlas-border)",
        color: "var(--atlas-text)",
        boxShadow: "var(--atlas-elev-2)",
      }}
    >
      <div className="mb-2 font-medium">Time scrubber</div>
      <input
        type="range"
        min={0}
        max={snapshots.length - 1}
        value={index ?? snapshots.length - 1}
        onChange={(e) => setIndex(Number(e.target.value))}
        className="w-full"
      />
      <div className="mt-1 flex justify-between text-xs" style={{ color: "var(--atlas-text-dim)" }}>
        <span>{shortSha(snapshots[0].commit_sha)}</span>
        <span>{shortSha(snapshots[snapshots.length - 1].commit_sha)}</span>
      </div>
      {index !== null && (
        <div className="mt-2 text-xs" style={{ color: "var(--atlas-text-dim)" }}>
          {hasPrior
            ? `${shortSha(snapshots[index - 1].commit_sha)} → ${shortSha(snapshots[index].commit_sha)}`
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
    </div>
  );
}
