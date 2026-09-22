import type { Lens } from "../store/atlasStore.ts";
import { useAtlasStore } from "../store/atlasStore.ts";

const LENSES: { id: Lens; label: string }[] = [
  { id: "structure", label: "Structure" },
  { id: "divergence", label: "Divergence" },
  { id: "confidence", label: "Confidence" },
];

/** Segmented control, styled like `AtlasCanvas`'s altitude buttons.
 * Switching lens only ever recolors the canvas (`AtlasCanvas`'s lens
 * effect) -- it never touches `graph` identity, so layout never re-runs
 * (`WEB_RESEARCH.md` §3: "Lens changes animate color only, never layout"). */
export function LensSwitcher() {
  const lens = useAtlasStore((s) => s.lens);
  const setLens = useAtlasStore((s) => s.setLens);

  return (
    <div className="absolute left-3 top-12 z-10 flex gap-2 text-sm">
      {LENSES.map(({ id, label }) => (
        <button
          key={id}
          onClick={() => setLens(id)}
          className="rounded px-2 py-1"
          style={{
            background: id === lens ? "var(--atlas-accent)" : "var(--atlas-bg-2)",
            color: id === lens ? "#07090c" : "var(--atlas-text-dim)",
            border: "1px solid var(--atlas-border)",
          }}
        >
          {label}
        </button>
      ))}
    </div>
  );
}
