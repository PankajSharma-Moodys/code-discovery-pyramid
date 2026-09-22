# UI/UX improvement plan — CDP web frontend

**Budget for this doc: ≤420 lines, ≤3,200 words. Design only — no
implementation in this pass; CSS below is illustrative reference material
for whoever builds this, not a spec to copy verbatim.**

## 0. How to use this document

This is direction, not a contract. Treat every color value, easing curve,
and pixel number below as a starting point to feel out and adjust once
it's on screen — if something in here looks good in theory but feels off,
dead, or fights the tool's actual usage patterns once built, change it.
The goal stated by the person who asked for this is a UI **people want to
poke at** — hover things to see what happens, click around because it's
satisfying, not just functional. That goal beats literal adherence to any
single number in this doc. Optimize for "does this feel good to use,"
and treat the CSS snippets as a running start, not a checklist.

## 1. Verification note (read before trusting the reference)

I could not load `openai.com/index/gpt-6-astra/` or its sibling page
directly — both returned HTTP 403, and the Wayback Machine is unreachable
from this tool. I have **not** seen that page's actual pixels and won't
claim specific colors/layout from it as fact. What I *can* verify:
third-party design reviews (UX Planet, MindStudio, others, via web search
2026-09-22) describe GPT-6 Astra-generated marketing sites as trending
toward large expressive type, image-heavy hero sections with scroll/
cursor-reactive motion, and — a failure mode reviewers explicitly warn
against — generic "AI slop" gradients when done lazily. The recommendations
below draw on that generically-documented style plus established
glassmorphism/depth practice, not on an unverified reading of one URL. If
you can share a screenshot of the actual page, I'll revise this against it
directly.

## 2. Current state (verified by reading the code)

- **Palette is 3 shades of near-black + one accent**, all flat solid
  fills, no gradients anywhere (`tokens.css:6-13`).
- **Every panel is the same shape**: `rounded-[10px] border p-4`, one
  `1px solid` stroke, no shadow, no elevation differentiation
  (`RepoHealthStrip.tsx:35-42`, repeated in every panel/rail).
- **Control Room is a stack of identical boxes** (`ControlRoom.tsx:14-31`)
  — the literal "tiles here and there" complaint: six panels, same gray
  rectangle, nothing telling you which one matters right now.
- **One typographic voice**: `system-ui`, 15px base, weight-only scale
  (`index.css:11`) — nothing reads as a headline.
- **Motion is narrow**: one fade-in keyframe (`tokens.css:36-45`) + hover
  recolor. Nothing moves on load, scroll, or idle outside the Atlas canvas.
- **Zero imagery, texture, or depth** — flat fills everywhere, hence
  "pitch black background."

This is a tool that optimized entirely for "cite every claim with
file:line" and correctly so — but left zero budget for the surface to
feel alive or invite play.

## 3. Design principles

1. **Depth without noise.** Stay dark (it's a dev tool, not a marketing
   page) but layer the dark — ambient gradient mesh behind content, glow
   on focus/hover, not flat fills everywhere.
2. **One hero moment per screen.** Not every panel is equal; size, glow,
   and motion should encode importance the way color already encodes
   confidence.
3. **Motion as feedback and invitation.** Every interaction — hover,
   click, state change — gets a response. This is what makes a UI feel
   "alive" enough to want to poke at: cursors that pull a subtle glow,
   cards that lift slightly, numbers that count up instead of snapping in.
4. **Type hierarchy communicates priority.** One display-size number/
   status per screen; keep the rest at the current dense scale.
5. **Never let decorative color drift into semantic territory.** The
   verified/inferred/unknown/contested triad (`tokens.css:16-21`) stays
   reserved for that meaning; new gradients use new tokens.

## 4. Tokens (illustrative)

```css
:root {
  /* ambient depth, applied once on the app shell, not per-panel */
  --atlas-mesh-bg:
    radial-gradient(60% 50% at 10% 0%,  color-mix(in srgb, #6a5cff 18%, transparent), transparent 70%),
    radial-gradient(50% 40% at 90% 100%, color-mix(in srgb, var(--atlas-accent) 12%, transparent), transparent 70%);

  --atlas-elev-1: 0 1px 0 rgba(255,255,255,0.04) inset, 0 8px 24px -12px rgba(0,0,0,0.6);
  --atlas-elev-2: 0 1px 0 rgba(255,255,255,0.06) inset, 0 16px 48px -16px rgba(0,0,0,0.7);
  --atlas-glow-ring: 0 0 0 1px color-mix(in srgb, var(--atlas-accent) 40%, transparent),
                     0 0 24px color-mix(in srgb, var(--atlas-accent) 25%, transparent);

  --atlas-display-size: clamp(1.75rem, 2vw + 1rem, 2.75rem);
  --atlas-motion-spring: cubic-bezier(0.34, 1.56, 0.64, 1);
  --atlas-motion-hover: 140ms;
}

@media (prefers-reduced-motion: reduce) {
  :root { --atlas-motion-hover: 0ms; }
}
```

## 5. Concrete component CSS (reference sketches)

These are meant to be adapted in place, not copy-pasted verbatim onto
existing classNames — treat class names as placeholders for wherever the
equivalent element lives.

**App shell — ambient mesh background (once, in `App.tsx`'s outer div):**

```css
.app-shell {
  background:
    var(--atlas-mesh-bg),
    var(--atlas-bg-0);
  background-attachment: fixed;
}
```

**Panel → elevated card with hover lift (replaces the flat
`border + p-4` pattern used in every panel today):**

```css
.card {
  border-radius: var(--atlas-radius);
  border: 1px solid var(--atlas-border);
  background: color-mix(in srgb, var(--atlas-bg-1) 90%, transparent);
  box-shadow: var(--atlas-elev-1);
  backdrop-filter: blur(12px);
  transition:
    transform var(--atlas-motion-hover) var(--atlas-ease),
    box-shadow var(--atlas-motion-hover) var(--atlas-ease),
    border-color var(--atlas-motion-hover) var(--atlas-ease);
}

.card:hover {
  transform: translateY(-2px);
  border-color: color-mix(in srgb, var(--atlas-accent) 35%, var(--atlas-border));
  box-shadow: var(--atlas-elev-2);
}

.card--hero {
  box-shadow: var(--atlas-elev-2);
  grid-column: span 2;
}
```

**Primary button — glow on hover/focus instead of a flat opacity swap:**

```css
.btn-primary {
  background: var(--atlas-accent);
  color: #07090c;
  border-radius: 6px;
  padding: 0.5rem 1rem;
  transition: box-shadow var(--atlas-motion-hover) var(--atlas-ease),
              transform var(--atlas-motion-hover) var(--atlas-ease);
}

.btn-primary:hover,
.btn-primary:focus-visible {
  box-shadow: var(--atlas-glow-ring);
  transform: translateY(-1px);
}

.btn-primary:active {
  transform: translateY(0) scale(0.98);
}
```

**Ask Bar trigger pill — idle pulse so it reads as inviting, not inert:**

```css
@keyframes ask-bar-idle-pulse {
  0%, 100% { box-shadow: 0 0 0 0 color-mix(in srgb, var(--atlas-accent) 30%, transparent); }
  50%      { box-shadow: 0 0 0 6px color-mix(in srgb, var(--atlas-accent) 0%, transparent); }
}

.ask-bar-trigger {
  animation: ask-bar-idle-pulse 2.6s ease-in-out infinite;
}

.ask-bar-trigger:hover {
  animation-play-state: paused;
  box-shadow: var(--atlas-glow-ring);
}
```

**Stat number — count-up on mount instead of snapping to its final value**
(behavior sketch, pair with a small `useEffect` easing loop rather than a
library):

```css
.stat-display {
  font-size: var(--atlas-display-size);
  font-variant-numeric: tabular-nums;
  font-weight: 600;
  letter-spacing: -0.02em;
}
```

**Progress/coverage bar — shimmer only while pending (keep the bar itself
flat; don't gradient something read for exact proportion):**

```css
.bar-fill--pending::after {
  content: "";
  position: absolute; inset: 0;
  background: linear-gradient(90deg, transparent, rgba(255,255,255,0.15), transparent);
  animation: shimmer 1.4s linear infinite;
}
@keyframes shimmer {
  from { transform: translateX(-100%); }
  to   { transform: translateX(100%); }
}
```

## 6. Component-pattern changes

| Surface | Now | Proposed |
|---|---|---|
| Control Room panels | Identical bordered boxes, uniform stack | Bento grid (already collapses to 1-col narrow per `ControlRoom.tsx:12-13`), one hero cell (`.card--hero`, repo health) at 2× size/elevation |
| Ask Bar | Flat blur box, snaps open/closed | Spring-in via `--atlas-motion-spring`; idle trigger gets the pulse above so it invites a click |
| Refresh / primary actions | Solid fill, opacity-only hover | `.btn-primary` glow + lift; progress-ring or shimmer while pending instead of plain text |
| Freshness/coverage bars | Flat segmented bar | Keep flat fills for readability; add shimmer only while `isPending` |
| Atlas canvas | Already has motion tokens, underused elsewhere | Reference implementation — extend its patterns outward rather than inventing new ones |

## 7. Phased delivery (wow/effort)

| Phase | Contents | Score | Done = |
|---|---|---|---|
| **A. Foundation** | Mesh background, elevation/glow tokens, `.card` base | ★★★ / XS | Contrast still passes at every text/background pairing; semantic colors untouched |
| **B. Hierarchy** | Hero panel promotion, display-size stat | ★★★★ / S | A first-time viewer names "the one thing that matters" on Control Room within 2 seconds |
| **C. Motion + invitation** | View cross-fade, button glow, Ask Bar pulse, shimmer, stat count-up | ★★★★★ / S | Every hover/click/state-change has a response; `prefers-reduced-motion` disables all of it |
| **D. Polish** | Stagger on first paint, refresh-success pulse on the hero panel | ★★★ / XS | Nice-to-have, cut first under time pressure |

**Cut line:** A + C are cheap, repo-wide, and are what make it feel alive —
protect those. B and D touch layout/timing and can slip without the tool
feeling broken.

## 8. Stress test of this plan

- **Risk: gradient mesh reduces text contrast.** Mesh sits behind panels
  at low opacity (12–18% color-mix); panels keep solid `bg-1/2` fills
  underneath. Check contrast once built, on the actual rendered colors —
  don't trust the numbers above blind.
- **Risk: motion/glow overdone reads as gimmicky rather than inviting.**
  If it starts to feel like it's trying too hard, dial back amplitude
  (translateY, glow spread) before adding more effects — the tool this is
  built for is dense/technical, not a consumer product; "delightful" here
  means "responsive and warm," not "flashy."
- **Risk: hardcoding new durations outside `--atlas-motion-*` breaks
  reduced-motion support.** Every new animation must route through a
  token gated by the existing `prefers-reduced-motion` block
  (`tokens.css:29-34`).
- **Explicitly not proposing:** a light/glossy marketing aesthetic,
  illustration/photography, or a new animation library — CSS transitions
  and keyframes cover everything above.
