import { expect, test } from "@playwright/test";

/**
 * The sign-in tour, signed out: start it from the door, type the seeded
 * organiser's address at step 2, and see step 3 light the sent state.
 * The dev mail backend takes the send; nothing reads the inbox.
 */
test("a visitor takes the sign-in tour from the door", async ({ page }) => {
  await page.goto("/rsp/");
  await page.getByRole("button", { name: "Hoe werkt inloggen?" }).click();

  const callout = page.getByRole("dialog").filter({ hasText: "van 4" });
  await expect(callout).toContainText("1 van 4");
  await page.getByRole("button", { name: "Volgende" }).click();

  await expect(callout).toContainText("2 van 4");
  await page.getByPlaceholder("E-mailadres").fill("organiser@local.dev");
  await page.getByRole("button", { name: "Stuur link" }).click();

  await expect(callout).toContainText("3 van 4", { timeout: 15_000 });
  await expect(page.locator("p.muted", { hasText: "organiser@local.dev" })).toBeVisible();
  await page.getByRole("button", { name: "Volgende" }).click();

  await expect(callout).toContainText("4 van 4");
  await page.getByRole("button", { name: "Klaar" }).click();
  await expect(page.locator(".tour-callout")).toHaveCount(0);
});
