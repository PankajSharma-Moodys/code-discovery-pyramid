import type { Lens } from "../store/atlasStore.ts";
import { useAtlasStore } from "../store/atlasStore.ts";

/**
 * `ATLAS_REDESIGN.md` §5, second row: the three buttons read `Structure` /
 * `Divergence` / `Confidence` with nothing saying they *recolour the canvas*.
 * Each now carries a one-line caption of what it makes the colour mean, and
 * the group is labelled with the question it answers.
 *
 * `Divergence` became `Flow` — see `store/atlasStore.ts`'s `Lens` for why
 * (the declared/observed tags it coloured only existed on the edge set P0
 * removed). The divergence counts still surface in the legend at L3.
 *
 * Switching lens only ever re-runs `AtlasCanvas`'s reducers — it never
 * touches graph identity, so layout cannot re-run (`WEB_RESEARCH.md` §3:
 * "Lens changes animate color only, never layout").
 */
const LENSES: { id: Lens; label: string; caption: string }[] = [
  {
    id: "structure",
    label: "Structure",
    caption: "colour = what kind of thing it is",
  },
  {
    id: "flow",
    label: "Flow",
    caption: "colour = how the connection was found",
  },
  {
    id: "confidence",
    label: "Confidence",
    caption: "colour = how sure CDP is",
  },
];

export function LensSwitcher() {
  const lens = useAtlasStore((s) => s.lens);
  const setLens = useAtlasStore((s) => s.setLens);
  const active = LENSES.find((l) => l.id === lens) ?? LENSES[0];

  return (
    <div className="absolute left-3 top-24 z-10 flex flex-col gap-1.5">
      <span className="text-xs" style={{ color: "var(--atlas-text-dim)" }}>
        Lens — what colour means right now
      </span>
      <div className="flex gap-2 text-sm">
        {LENSES.map(({ id, label, caption }) => (
          <button
            key={id}
            onClick={() => setLens(id)}
            title={caption}
            className="atlas-btn-primary rounded px-2.5 py-1"
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
      <span className="text-xs" style={{ color: "var(--atlas-text-dim)" }}>
        {active.caption}
      </span>
    </div>
  );
}
