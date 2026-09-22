import { useState, type ReactNode } from "react";

interface CollapsiblePanelProps {
  /** The question this panel answers, shown on the trigger chip and as the
   * heading when open (`ATLAS_REDESIGN.md` §5). */
  title: string;
  side: "left" | "right";
  width: string;
  /** Shown on the collapsed chip when there is something worth surfacing --
   * a count, a commit, a "2 available". Keeps the chip informative rather
   * than a bare toggle. */
  badge?: ReactNode;
  defaultOpen?: boolean;
  children: ReactNode;
}

/**
 * Bottom-corner panel that collapses to a chip.
 *
 * `ATLAS_REDESIGN.md`'s premise is that 75% of the screen is canvas, and the
 * measured result of the first pass was that two permanently-mounted 26rem
 * panels sat on the bottom-left and bottom-right corners of it. A probe of
 * the running app found no node *clipped* by the camera (§4's fix works) but
 * several sitting underneath these panels, which reads identically to the
 * user. Both are secondary tools, so they now open on demand.
 */
export function CollapsiblePanel({
  title,
  side,
  width,
  badge,
  defaultOpen = false,
  children,
}: CollapsiblePanelProps) {
  const [open, setOpen] = useState(defaultOpen);
  const corner = side === "left" ? "left-0" : "right-0";

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className={`atlas-btn-primary absolute bottom-3 ${side === "left" ? "left-3" : "right-3"} z-20 flex items-center gap-2 rounded-full px-3 py-1.5 text-xs`}
        style={{
          background: "color-mix(in srgb, var(--atlas-bg-1) 92%, transparent)",
          border: "1px solid var(--atlas-border)",
          color: "var(--atlas-text)",
          boxShadow: "var(--atlas-elev-1)",
          backdropFilter: "blur(12px)",
        }}
      >
        <span>{title}</span>
        {badge && <span style={{ color: "var(--atlas-text-dim)" }}>{badge}</span>}
      </button>
    );
  }

  return (
    <div
      className={`absolute bottom-0 ${corner} z-20 max-h-[55%] overflow-y-auto ${side === "left" ? "border-r" : "border-l"} border-t p-3 text-sm backdrop-blur-md`}
      style={{
        width,
        background: "color-mix(in srgb, var(--atlas-bg-1) 92%, transparent)",
        borderColor: "var(--atlas-border)",
        color: "var(--atlas-text)",
        boxShadow: "var(--atlas-elev-2)",
      }}
    >
      <div className="mb-2 flex items-start justify-between gap-2">
        <span className="font-medium">{title}</span>
        <button
          onClick={() => setOpen(false)}
          className="shrink-0 text-xs"
          style={{ color: "var(--atlas-text-dim)" }}
        >
          hide
        </button>
      </div>
      {children}
    </div>
  );
}
