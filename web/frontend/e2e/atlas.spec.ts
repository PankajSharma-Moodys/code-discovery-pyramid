import { test, expect, type Page } from "@playwright/test";

/**
 * Locks in the manual Playwright checks recorded in TODO.md's "Closing the
 * live-verification gap for real" entry, so they run on every CI pass
 * instead of being re-derived as throwaway scripts each session. Runs
 * against this repo's own real `.cdp/index.db` (the default repo
 * selection) via `playwright.config.ts`'s `webServer`.
 */

interface AtlasSigmaHandle {
  getGraph(): {
    order: number;
    size: number;
    nodes(): string[];
    hasNode(id: string): boolean;
  };
  getNodeDisplayData(id: string): { x: number; y: number } | undefined;
  framedGraphToViewport(pos: { x: number; y: number }): { x: number; y: number };
  getCamera(): { x: number; y: number; ratio: number };
}

function atlasSigma(page: Page) {
  return page.evaluate(() => {
    const s = (window as unknown as { __atlasSigma?: AtlasSigmaHandle }).__atlasSigma;
    if (!s) throw new Error("__atlasSigma not attached -- only set in import.meta.env.DEV");
    return {
      order: s.getGraph().order,
      size: s.getGraph().size,
      nodes: s.getGraph().nodes(),
    };
  });
}

/** Screen-space (viewport) pixel coords for a node, via the same
 * `framedGraphToViewport(getNodeDisplayData(...))` pattern the file's own
 * dev-console probe comment documents -- there is no DOM element per node,
 * Sigma renders to a single `<canvas>`. */
async function nodeScreenPosition(page: Page, nodeId: string) {
  const canvasBox = await page.locator("canvas").first().boundingBox();
  if (!canvasBox) throw new Error("sigma canvas not found");
  const rel = await page.evaluate((id) => {
    const s = (window as unknown as { __atlasSigma?: AtlasSigmaHandle }).__atlasSigma;
    if (!s) throw new Error("__atlasSigma not attached");
    const display = s.getNodeDisplayData(id);
    if (!display) throw new Error(`node ${id} has no display data`);
    return s.framedGraphToViewport(display);
  }, nodeId);
  return { x: canvasBox.x + rel.x, y: canvasBox.y + rel.y };
}

async function waitForGraph(page: Page) {
  await expect
    .poll(async () => {
      try {
        return (await atlasSigma(page)).order;
      } catch {
        return 0;
      }
    }, { timeout: 15_000 })
    .toBeGreaterThan(0);
  // Fit-to-viewport / layout settle happens shortly after nodes first appear
  // in the graphology object -- give the camera a moment to stop moving
  // before trusting `framedGraphToViewport` for a pixel-accurate click.
  await page.waitForTimeout(600);
}

/** Clicks a node by re-resolving its live screen position immediately before
 * each attempt (the camera can still be settling) and retrying against a
 * couple of candidate nodes, since a hub node's hit-radius is much larger
 * and easier to land a real mouse click on than an arbitrary array index. */
async function clickNodeReliably(page: Page, candidates: string[], click: "click" | "dblclick" = "click") {
  for (const id of candidates) {
    const pos = await nodeScreenPosition(page, id);
    if (click === "click") await page.mouse.click(pos.x, pos.y);
    else await page.mouse.dblclick(pos.x, pos.y);
    const selected = await page
      .locator('[aria-pressed]')
      .filter({ hasText: /focus neighbourhood/i })
      .count()
      .catch(() => 0);
    if (selected > 0) return id;
  }
  return candidates[0];
}

test("top rung (Packages) renders real container nodes, not the 823-singleton wall", async ({ page }) => {
  await page.goto("/");
  await waitForGraph(page);
  const { order } = await atlasSigma(page);
  // This repo's own real index has a handful of top-level directories/type
  // buckets, never hundreds of id-string singletons (the doc's original bug).
  expect(order).toBeGreaterThan(0);
  expect(order).toBeLessThan(100);
});

test("selecting a node reveals Focus/Pin toggles and they are actually clickable", async ({ page }) => {
  await page.goto("/");
  await waitForGraph(page);
  const before = await atlasSigma(page);
  await clickNodeReliably(page, before.nodes.slice(0, 8));

  const focusToggle = page.getByRole("button", { name: /focus neighbourhood/i });
  const pinToggle = page.getByRole("button", { name: /pin position/i });
  await expect(focusToggle).toBeVisible();
  await expect(pinToggle).toBeVisible();

  // Regression guard for the InspectorRail-overlaps-legend bug: a real click
  // must land on the button, not be intercepted by another element.
  await focusToggle.click({ timeout: 5_000 });
  await expect(focusToggle).toHaveAttribute("aria-pressed", "true");

  // Restricting to the neighbourhood must actually shrink the rendered graph.
  await expect
    .poll(async () => (await atlasSigma(page)).order)
    .toBeLessThan(before.order);

  await focusToggle.click();
  await expect(focusToggle).toHaveAttribute("aria-pressed", "false");
  await expect
    .poll(async () => (await atlasSigma(page)).order)
    .toBe(before.order);
});

test("pin toggle survives an altitude round-trip", async ({ page }) => {
  await page.goto("/");
  await waitForGraph(page);
  const { nodes } = await atlasSigma(page);
  const target = await clickNodeReliably(page, nodes.slice(0, 8));
  const pos = await nodeScreenPosition(page, target);

  const pinToggle = page.getByRole("button", { name: /pin position/i });
  await pinToggle.click();
  await expect(pinToggle).toHaveAttribute("aria-pressed", "true");

  const before = await page.evaluate((id) => {
    const s = (window as unknown as { __atlasSigma?: AtlasSigmaHandle }).__atlasSigma;
    return s?.getNodeDisplayData(id);
  }, target);

  // Descend then ascend back to the same rung -- the pinned node's real
  // position must survive the round-trip, not get re-seeded from scratch.
  await page.mouse.dblclick(pos.x, pos.y);
  await page.waitForTimeout(500);
  await page.keyboard.press("Escape");
  await waitForGraph(page);

  const after = await page.evaluate((id) => {
    const s = (window as unknown as { __atlasSigma?: AtlasSigmaHandle }).__atlasSigma;
    return s?.getNodeDisplayData(id);
  }, target);

  expect(after).toBeTruthy();
  if (before && after) {
    expect(Math.hypot(after.x - before.x, after.y - before.y)).toBeLessThan(0.05);
  }
});

test("double-click expands a container in place (node count grows, parent stays on canvas)", async ({ page }) => {
  await page.goto("/");
  await waitForGraph(page);
  const before = await atlasSigma(page);

  // Pick the node with the most members via the same `/api/graph` response
  // the page itself fetched -- a container with only 1-2 members won't
  // visibly grow the node count even if expand-in-place works correctly.
  const graphData: {
    nodes: Array<{ id: string; members?: string[] }>;
  } = await page.evaluate(async () => {
    const res = await fetch("/api/graph?level=L3");
    return res.json();
  });
  const byMembers = [...graphData.nodes].sort(
    (a, b) => (b.members?.length ?? 0) - (a.members?.length ?? 0),
  );
  const target = byMembers.find((n) => before.nodes.includes(n.id))?.id ?? before.nodes[0];
  const pos = await nodeScreenPosition(page, target);

  await page.mouse.dblclick(pos.x, pos.y);
  await page.waitForTimeout(500);

  const after = await atlasSigma(page);
  expect(after.order).toBeGreaterThan(before.order);
  expect(after.nodes).toContain(target); // shrunk to an anchor, not removed

  // Collapse back via a second double-click on the same (now-shrunk) anchor.
  // Re-resolve its screen position rather than reusing `pos`: Sigma's
  // `framedGraphToViewport` mapping normalizes against the *whole graph's*
  // bounding box, which just grew when expand injected far-flung children --
  // so the target's own pixel position shifts even though its world x/y
  // never moved (measured live: same node's viewport x moved ~13px after
  // expanding, on this repo's own real index). Reusing the stale `pos` here
  // missed the shrunk anchor entirely and silently double-clicked empty
  // canvas, which is why this test was failing against the grown (not
  // collapsed) node count instead of ever actually collapsing.
  const posAfterExpand = await nodeScreenPosition(page, target);
  await page.mouse.dblclick(posAfterExpand.x, posAfterExpand.y);
  await page.waitForTimeout(300);
  const collapsed = await atlasSigma(page);
  expect(collapsed.order).toBe(before.order);
});

test("expanding a second sibling container keeps the first one's children on canvas", async ({ page }) => {
  await page.goto("/");
  await waitForGraph(page);
  const before = await atlasSigma(page);

  const graphData: {
    nodes: Array<{ id: string; members?: string[] }>;
  } = await page.evaluate(async () => {
    const res = await fetch("/api/graph?level=L3");
    return res.json();
  });
  const byMembers = [...graphData.nodes]
    .filter((n) => before.nodes.includes(n.id) && (n.members?.length ?? 0) >= 1)
    .sort((a, b) => (b.members?.length ?? 0) - (a.members?.length ?? 0));
  if (byMembers.length < 2) test.skip(true, "this repo's L3 doesn't have two expandable containers");
  const [first, second] = byMembers;

  const firstPos = await nodeScreenPosition(page, first.id);
  await page.mouse.dblclick(firstPos.x, firstPos.y);
  await page.waitForTimeout(500);
  const afterFirst = await atlasSigma(page);
  expect(afterFirst.order).toBeGreaterThan(before.order);

  const secondPos = await nodeScreenPosition(page, second.id);
  await page.mouse.dblclick(secondPos.x, secondPos.y);
  await page.waitForTimeout(500);
  const afterBoth = await atlasSigma(page);

  // Both expansions' children coexist -- the second container's children
  // don't push the first container's children off the graph, and both
  // parent anchors are still present.
  expect(afterBoth.order).toBeGreaterThan(afterFirst.order);
  expect(afterBoth.nodes).toContain(first.id);
  expect(afterBoth.nodes).toContain(second.id);

  // Collapsing the first leaves the second's children untouched. Re-resolve
  // its screen position first -- same reason as the previous test: the
  // graph's bounding box grew twice more since `firstPos` was captured (the
  // first expansion, then the second), so `first.id`'s pixel position has
  // moved even though its world x/y haven't.
  const firstPosNow = await nodeScreenPosition(page, first.id);
  await page.mouse.dblclick(firstPosNow.x, firstPosNow.y);
  await page.waitForTimeout(300);
  const afterFirstCollapsed = await atlasSigma(page);
  expect(afterFirstCollapsed.order).toBe(afterBoth.order - (afterFirst.order - before.order));
  expect(afterFirstCollapsed.nodes).toContain(second.id);
});

test("collapsing an outer container tears down its nested expansion too (no orphaned nodes)", async ({ page }) => {
  await page.goto("/");
  await waitForGraph(page);
  const before = await atlasSigma(page);

  // This repo's own real ladder is only `["L3", "L2"]` (checked live: a
  // container's members are already leaf `L2` nodes, one rung below `L3` --
  // there is no intermediate grouped rung to nest a second expansion
  // inside). A container-within-a-container needs a `>=3`-rung ladder to
  // exist for real, so this live check is data-shape-gated; the actual
  // nested-expansion algorithm (radius shrink, `rung` stamping, cascade
  // collapse ordering) is covered unconditionally by the synthetic
  // `graphLayout.test.ts` cases regardless of what this repo's own index
  // happens to look like.
  const graphData: {
    rungs: Array<{ level: string }>;
    nodes: Array<{ id: string; members?: string[] }>;
  } = await page.evaluate(async () => {
    const res = await fetch("/api/graph?level=L3");
    return res.json();
  });
  if (graphData.rungs.length < 3) {
    test.skip(true, "this repo's ladder has no intermediate grouped rung to nest an expansion inside");
  }

  const byMembers = [...graphData.nodes]
    .filter((n) => before.nodes.includes(n.id) && (n.members?.length ?? 0) >= 2)
    .sort((a, b) => (b.members?.length ?? 0) - (a.members?.length ?? 0));
  if (byMembers.length === 0) test.skip(true, "this repo's L3 has no container with 2+ members");
  const outer = byMembers[0];
  const outerPos = await nodeScreenPosition(page, outer.id);

  await page.mouse.dblclick(outerPos.x, outerPos.y);
  await page.waitForTimeout(500);
  const afterOuter = await atlasSigma(page);
  expect(afterOuter.order).toBeGreaterThan(before.order);

  // Ask the server which injected child (if any) is itself a container at
  // the next rung down, the same data the app itself would use to decide --
  // rather than trial double-clicking every child, which would trigger a
  // real (slow) altitude change for any child that turns out to be a leaf.
  const childrenData: { nodes: Array<{ id: string; members?: string[] }> } = await page.evaluate(
    async (scope) => {
      const res = await fetch(`/api/graph?level=L2&scope=${encodeURIComponent(scope)}`);
      return res.json();
    },
    outer.id,
  );
  const nestedCandidate = childrenData.nodes.find((n) => (n.members?.length ?? 0) >= 1);
  if (!nestedCandidate) test.skip(true, "no injected child of this container is itself a container");

  const childPos = await nodeScreenPosition(page, nestedCandidate!.id);
  await page.mouse.dblclick(childPos.x, childPos.y);
  await page.waitForTimeout(500);
  const afterNested = await atlasSigma(page);
  expect(afterNested.order).toBeGreaterThan(afterOuter.order);

  // Collapsing the outer container must remove its own children *and* the
  // nested expansion's children in one step -- not leave the nested
  // children orphaned on the canvas with a dead parent.
  await page.mouse.dblclick(outerPos.x, outerPos.y);
  await page.waitForTimeout(300);
  const afterCollapse = await atlasSigma(page);
  expect(afterCollapse.order).toBe(before.order);
  expect(afterCollapse.order).toBeLessThan(afterNested.order);
});

test("minimap click pans the main camera", async ({ page }) => {
  await page.goto("/");
  await waitForGraph(page);

  const minimap = page.getByLabel("Minimap: click to pan");
  await expect(minimap).toBeVisible({ timeout: 10_000 });

  const before = await page.evaluate(() => {
    const s = (window as unknown as { __atlasSigma?: AtlasSigmaHandle }).__atlasSigma;
    return s?.getCamera();
  });

  const box = await minimap.boundingBox();
  if (!box) throw new Error("minimap not found");
  await page.mouse.click(box.x + box.width * 0.15, box.y + box.height * 0.15);
  await page.waitForTimeout(300);

  const after = await page.evaluate(() => {
    const s = (window as unknown as { __atlasSigma?: AtlasSigmaHandle }).__atlasSigma;
    return s?.getCamera();
  });

  expect(after).toBeTruthy();
  if (before && after) {
    expect(Math.hypot(after.x - before.x, after.y - before.y)).toBeGreaterThan(0);
  }
});
