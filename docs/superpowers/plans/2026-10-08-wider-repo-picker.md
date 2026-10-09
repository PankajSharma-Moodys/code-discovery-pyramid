# Plan: wider repo picker label

Budget: ≤30 lines. Spec: user request 2026-10-08 — "make the tab on which the
github/name of repo is given a lot wider so it's visible properly and fully".

## Global Constraints

- Only `web/frontend/src/panels/RepoPicker.tsx` changes. No new dependencies.
- Tailwind classes only (Tailwind v4 via `@tailwindcss/vite`; arbitrary values allowed).
- Verify: in `web/frontend`, `npm run build`, `npm run lint`, `npm test` all pass.

## Task 1: Widen the picker button and dropdown

- Button (line ~33): replace `max-w-64` with `max-w-[min(48rem,70vw)]`.
  Keep `truncate` so it still clips only beyond that limit on narrow windows.
- Dropdown panel (line ~47): replace `w-80` with `w-[min(48rem,90vw)]`.
- Dropdown row id (line ~87): replace `truncate` with `break-all` so a long
  repo id wraps and is shown in full instead of being cut off.
- The button's `title` tooltip: show the full id and the state dir,
  `title={`${currentLabel}\n${current?.state_dir ?? ""}`}`, so the full name is
  always available on hover even if clipped.
- Commit on `feat/folder-opener`, ending with
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
