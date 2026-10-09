import { test, expect, type Locator } from "@playwright/test";

/**
 * Smoke test for the default Flow tab, against this repo's own real
 * `.cdp/index.db` (see `playwright.config.ts`): the Flow view renders group
 * boxes, a `+N` group expands to its members, the container header's Collapse
 * button folds it back, and clicking a member leaf opens the inspector rail.
 */

const BADGE = /\+(\d+)\s*$/;

/** The data-id of the group box with the smallest `+N` badge (keeps clear of
 * the >150-item `window.confirm` guard, which Playwright would auto-dismiss). */
async function smallestGroupId(boxes: Locator): Promise<string> {
  const all = await boxes.all();
  let best: { id: string; n: number } | null = null;
  for (const box of all) {
    const m = BADGE.exec((await box.innerText()).trim());
    const id = await box.getAttribute("data-id");
    if (!m || !id) continue;
    const n = Number(m[1]);
    if (!best || n < best.n) best = { id, n };
  }
  if (!best) throw new Error("no group box with a +N badge");
  return best.id;
}

test("Flow tab is the default and groups expand, collapse and open the inspector", async ({ page }) => {
  await page.goto("/");

  // Flow is the default view: its React Flow canvas renders with group boxes.
  await expect(page.getByRole("button", { name: "Flow", exact: true })).toBeVisible();
  const flowNodes = page.locator(".react-flow__node-flowBox");
  await expect(flowNodes.first()).toBeVisible();

  const groupBoxes = flowNodes.filter({ hasText: BADGE });
  const groupId = await smallestGroupId(groupBoxes);
  const group = page.locator(`.react-flow__node[data-id="${groupId}"]`);
  const before = await page.locator(".react-flow__node").count();

  // Expand: the box becomes a container frame with a Collapse header button
  // and its members appear.
  await group.click();
  const collapse = page.getByRole("button", { name: /^Collapse / });
  await expect(collapse).toHaveCount(1);
  await expect.poll(() => page.locator(".react-flow__node").count()).toBeGreaterThan(before);

  // Collapse via the header button: members disappear again.
  await collapse.click();
  await expect(collapse).toHaveCount(0);
  await expect.poll(() => page.locator(".react-flow__node").count()).toBe(before);

  // Expand again and click a member leaf (a flow box lying inside the frame).
  await page.locator(`.react-flow__node[data-id="${groupId}"]`).click();
  const frame = page.locator(`.react-flow__node-flowGroup[data-id="${groupId}"]`);
  await expect(frame).toBeVisible();
  const frameBox = await frame.boundingBox();
  if (!frameBox) throw new Error("expanded frame has no bounding box");

  let memberIndex = -1;
  const leaves = await page.locator(".react-flow__node-flowBox").all();
  for (let i = 0; i < leaves.length; i++) {
    const text = (await leaves[i].innerText()).trim();
    const b = await leaves[i].boundingBox();
    if (BADGE.test(text) || !b) continue;
    if (b.x >= frameBox.x && b.y >= frameBox.y && b.x + b.width <= frameBox.x + frameBox.width && b.y + b.height <= frameBox.y + frameBox.height) {
      memberIndex = i;
      break;
    }
  }
  expect(memberIndex, "expected a member leaf inside the expanded frame").toBeGreaterThanOrEqual(0);
  await leaves[memberIndex].click();

  await expect(page.getByRole("button", { name: "close", exact: true })).toBeVisible();
});
