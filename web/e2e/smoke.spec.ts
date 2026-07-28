import { expect, test } from "@playwright/test";

// Runs against a seeded stack (`make seed && make dev`).

test("overview shows the leaderboard and charts", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1, name: "Overview" })).toBeVisible();
  await expect(page.getByRole("link", { name: "hybrid-rerank", exact: true })).toBeVisible();
  await expect(page.getByText("Quality against latency")).toBeVisible();
});

test("run detail drills down into a question", async ({ page }) => {
  await page.goto("/runs");
  await page.getByRole("link", { name: /^hybrid-rerank@/ }).first().click();
  await expect(page.getByRole("heading", { name: "Latency by stage" }).first()).toBeVisible();
  await page.locator("table").last().getByRole("link").first().click();
  await expect(page.getByText("Where the evidence lives")).toBeVisible();
});

test("playground answers with citations", async ({ page }) => {
  await page.goto("/playground");
  await page.getByLabel("Question").fill("Who presides when the President is tried for impeachment?");
  await page.getByRole("button", { name: /^Ask/ }).click();
  await expect(page.getByRole("button", { name: /^Source \d+$/ }).first()).toBeVisible({ timeout: 30_000 });
});

test("playground abstains on out-of-scope questions", async ({ page }) => {
  await page.goto("/playground");
  await page.getByLabel("Question").fill("Who won the 1998 FIFA World Cup?");
  await page.getByRole("button", { name: /^Ask/ }).click();
  await expect(page.getByText(/Not enough evidence|don't contain the answer|Nothing matched/)).toBeVisible({ timeout: 30_000 });
});

test("golden review queue, judge calibration, compare and pipelines render", async ({ page }) => {
  await page.goto("/golden");
  await expect(page.getByRole("list", { name: "Questions" })).toBeVisible();

  await page.goto("/judge");
  await expect(page.getByText("Cohen's kappa")).toBeVisible();

  await page.goto("/compare");
  await expect(page.getByText(/would (pass|fail) the gate/)).toBeVisible({ timeout: 15_000 });

  await page.goto("/configs");
  await expect(page.getByText("Quality over time")).toBeVisible();
});

test("a new pipeline version starts from the selected config", async ({ page }) => {
  await page.goto("/configs");
  await page.getByRole("navigation", { name: "Configs" }).getByRole("button", { name: /^bm25/ }).click();
  await page.getByRole("button", { name: "New version" }).click();
  const dialog = page.getByRole("dialog", { name: "New version of bm25" });
  await expect(dialog.getByLabel("Spec")).toHaveValue(/"kind": "bm25"/);
});
