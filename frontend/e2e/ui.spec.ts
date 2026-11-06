import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

const VIEWS = ["Workspace", "Security Inspector", "Approvals", "Attack Evidence"] as const;

async function guard(page: Page) {
  const external: string[] = [];
  const dialogs: string[] = [];
  page.on("request", (r) => { if (!r.url().startsWith("http://127.0.0.1:5174")) external.push(r.url()); });
  page.on("dialog", (d) => { dialogs.push(d.message()); void d.dismiss(); });
  return { external, dialogs };
}

async function choose(page: Page, userId: string) {
  await page.getByLabel("Development user").selectOption(userId);
}

async function open(page: Page, view: (typeof VIEWS)[number]) {
  await page.getByRole("navigation", { name: "Primary" }).getByRole("button", { name: new RegExp(view) }).click();
}

test("legitimate interaction: chat as a support agent, traced in the inspector", async ({ page }) => {
  const { external, dialogs } = await guard(page);
  await page.goto("/");
  await choose(page, "ns-agent-01");
  await page.getByRole("button", { name: /phone number do we have on file/ }).click();
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page.getByText("The agent runtime is not connected.")).toBeVisible();
  const cid = (await page.getByTestId("latest-cid").textContent())!.trim();
  expect(cid).toMatch(/^[0-9a-f-]{36}$/);

  await page.getByRole("button", { name: "Open in Security Inspector" }).click();
  await expect(page.getByText(cid).first()).toBeVisible();
  await expect(page.getByText("POST /chat")).toBeVisible();
  await page.screenshot({ path: "e2e/screenshots/legit-inspector.png", fullPage: true });

  expect(await page.content()).not.toContain("sk-ant");
  expect(external).toEqual([]);
  expect(dialogs).toEqual([]);
});

test("denied operation: agent cannot approve; a different supervisor can, then executes once", async ({ page }) => {
  const { dialogs } = await guard(page);
  await page.goto("/");
  await choose(page, "ns-agent-01");
  await open(page, "Approvals");
  await expect(page.getByText("onerror", { exact: false })).toBeVisible();       // payload shown as text
  await page.getByRole("button", { name: "Approve…" }).click();
  await page.getByRole("button", { name: "Send approval to backend" }).click();
  await expect(page.getByText("Your fixture role is not permitted to do this.")).toBeVisible();
  await expect(page.locator("[data-tone='denied']").first()).toBeVisible();
  await page.screenshot({ path: "e2e/screenshots/denied-approval.png", fullPage: true });

  await choose(page, "ns-super-01");
  await page.getByRole("button", { name: "Approve…" }).click();
  await page.getByRole("button", { name: "Send approval to backend" }).click();
  await expect(page.getByText("Approved by the backend.")).toBeVisible();
  await page.getByRole("button", { name: "Execute" }).click();
  await expect(page.getByText("Executed (simulated ledger entry).")).toBeVisible();

  await open(page, "Security Inspector");
  await expect(page.getByText("Human approval").first()).toBeVisible();
  await expect(page.getByText("Execution").first()).toBeVisible();

  expect(await page.evaluate(() => (window as unknown as { __pwned?: number }).__pwned)).toBeUndefined();
  expect(await page.locator("img").count()).toBe(0);
  expect(dialogs).toEqual([]);
});

test("attack evidence page lists A01–A08 as prepared and makes no chat calls", async ({ page }) => {
  const calls: string[] = [];
  page.on("request", (r) => calls.push(new URL(r.url()).pathname));
  await page.goto("/");
  await open(page, "Attack Evidence");
  await expect(page.getByText("Prepared — not executed")).toHaveCount(9);   // 8 list items + selected detail
  await page.getByRole("button", { name: "README.md" }).first().click();
  expect(calls.filter((p) => p.startsWith("/api/chat"))).toEqual([]);
});

for (const view of VIEWS) {
  test(`accessibility (axe) — ${view}`, async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/");
    await choose(page, "ns-super-01");
    await open(page, view);
    await page.waitForLoadState("networkidle");
    const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
    const serious = results.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
    expect(serious.map((v) => `${v.id}: ${v.nodes.length} node(s)`)).toEqual([]);
    await page.screenshot({ path: `e2e/screenshots/desktop-${view.replace(/ /g, "-").toLowerCase()}.png`, fullPage: true });
  });

  test(`responsive (390px, no horizontal page scroll) — ${view}`, async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/");
    await choose(page, "ns-super-01");
    await open(page, view);
    await page.waitForLoadState("networkidle");
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow).toBeLessThanOrEqual(0);
    await page.screenshot({ path: `e2e/screenshots/mobile-${view.replace(/ /g, "-").toLowerCase()}.png`, fullPage: true });
  });
}
