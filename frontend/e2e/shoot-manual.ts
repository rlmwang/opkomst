import { type APIRequestContext, type Browser, type Page, test } from "@playwright/test";
import { mkdirSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

/**
 * Every picture in the manual is a screenshot of a tour step
 * (``docs/design-manual.md`` chapter 6). This drives each tour through
 * the store one step at a time and writes one picture per step, named
 * by tour, product and declared step, into that language's folder, plus
 * the few "after" states a chapter's checkpoint shows.
 *
 * Not a test: it runs from ``make shoot-manual`` under its own config
 * and writes into the repository. The pictures are committed, because
 * a Docker build has no browser and no database.
 *
 * Chapters 1 to 11 are shot in the house brand in a personal account,
 * so no chapter chip appears in them; the organisation's chapters are
 * shot under the seeded organisation.
 */

type Lang = "nl" | "en";
type Product = "event" | "datepoll" | "chore" | "form" | "quiz" | "compass";

const OUT = fileURLToPath(new URL("../../backend/manual", import.meta.url));
const PERSONAL = "handleiding-plaatjes@local.dev";
const PENDING = "nieuwe-organisator@local.dev";
const VIEWPORT = { width: 1024, height: 768 };

const PRODUCTS: Product[] = ["event", "datepoll", "chore", "form", "quiz", "compass"];

interface TourWindow extends Window {
  __opkomstTour: {
    start: (id: string, path: string, product: string | null) => boolean;
    next: () => void;
    stop: () => void;
    tour: { active: boolean; index: number; step: { n: number; anchor: string; advance: { kind: string } } | null };
  };
}

/** What the start door makes for the personal account, per kind. */
function startPayload(kind: Product, lang: Lang): Record<string, unknown> {
  const soon = new Date(Date.now() + 14 * 24 * 60 * 60 * 1000);
  const iso = soon.toISOString().slice(0, 10);
  const base = {
    name_nl: null as string | null,
    name_en: null as string | null,
    description_nl: null,
    description_en: null,
    image_artist_instagram: null,
    locale: lang,
  };
  const names: Record<Product, [string, string]> = {
    event: ["Ledenvergadering", "Members' meeting"],
    datepoll: ["Wanneer kan de volgende borrel?", "When is the next drinks night?"],
    chore: ["Bar en opruimen", "Bar and clean-up"],
    form: ["Hoe was de avond?", "How was the evening?"],
    quiz: ["Pubquiz mei", "Pub quiz May"],
    compass: ["Waar staan we?", "Where do we stand?"],
  };
  base.name_nl = names[kind][0];
  base.name_en = names[kind][1];
  switch (kind) {
    case "event":
      return {
        event: {
          ...base,
          location: "De Kroon, Utrecht",
          latitude: null,
          longitude: null,
          starts_on: iso,
          start_time: "20:00:00",
          end_time: "22:00:00",
          source_options: [{ label: "Via een vriend" }, { label: "Poster" }],
          source_enabled: true,
          help_options: [],
          feedback_enabled: false,
          reminder_enabled: false,
        },
      };
    case "datepoll":
      return {
        datepoll: {
          ...base,
          location: null,
          latitude: null,
          longitude: null,
          slots: [1, 3, 8].map((d) => ({
            on_date: new Date(Date.now() + d * 24 * 60 * 60 * 1000).toISOString().slice(0, 10),
          })),
        },
      };
    case "chore":
      return {
        roster: {
          ...base,
          location: null,
          latitude: null,
          longitude: null,
          period_weeks: 1,
          starts_on: new Date().toISOString().slice(0, 10),
          ends_on: null,
          reminder_enabled: false,
          reminder_days_before: 1,
          commit_horizon_days: 28,
          chores: [
            { id: null, name: "Bar", description: null, cycle_slots: [4], people_per_shift: 2, emoji: null },
            { id: null, name: "Opruimen", description: null, cycle_slots: [4], people_per_shift: 1, emoji: null },
          ],
        },
      };
    case "form":
    case "quiz":
    case "compass": {
      const question: Record<string, unknown> = {
        id: null,
        kind: "multiple_choice",
        prompt: lang === "nl" ? "Hoe was de sfeer?" : "How was the atmosphere?",
        required: false,
        options: [
          { id: null, label: lang === "nl" ? "Goed" : "Good", is_correct: true, pole: kind === "compass" ? "x_high" : null },
          { id: null, label: lang === "nl" ? "Ging wel" : "So-so", is_correct: false, pole: kind === "compass" ? "x_low" : null },
        ],
        low_label: null,
        high_label: null,
      };
      const body: Record<string, unknown> = { ...base, questions: [question] };
      if (kind === "compass") {
        // Every axis needs a question that moves somebody on it.
        (body.questions as unknown[]).push({
          ...question,
          prompt: lang === "nl" ? "Hoe vaak kom je?" : "How often do you come?",
          options: [
            { id: null, label: lang === "nl" ? "Elke week" : "Every week", is_correct: false, pole: "y_high" },
            { id: null, label: lang === "nl" ? "Af en toe" : "Now and then", is_correct: false, pole: "y_low" },
          ],
        });
        body.axes = [
          { axis: "x", name: "Economie", description: null, low_name: "Links", high_name: "Rechts" },
          { axis: "y", name: "Cultuur", description: null, low_name: "Conservatief", high_name: "Progressief" },
        ];
      }
      return { [kind]: body };
    }
  }
}

async function json<T>(res: { ok(): boolean; json(): Promise<T>; text(): Promise<string> }, what: string): Promise<T> {
  if (!res.ok()) throw new Error(`${what}: ${await res.text()}`);
  return res.json();
}

/** Where the step being shown is, or nothing when the tour ended. */
async function stepOf(page: Page): Promise<{ n: number; anchor: string; kind: string } | null> {
  return page.evaluate(() => {
    const t = (window as unknown as TourWindow).__opkomstTour.tour;
    if (!t.active || !t.step) return null;
    return { n: t.step.n, anchor: t.step.anchor, kind: t.step.advance.kind };
  });
}

async function startTour(page: Page, id: string, product: string | null): Promise<void> {
  await page.waitForLoadState("networkidle");
  await page.waitForTimeout(400);
  const started = await page.evaluate(
    ([tourId, prod]) => {
      const w = window as unknown as TourWindow;
      // The path as the router sees it: without the organisation's base.
      const base = (window as unknown as { __OPKOMST_BRAND__: { app_base: string } }).__OPKOMST_BRAND__.app_base;
      const path = location.pathname.slice(base.length - 1) || "/";
      return w.__opkomstTour.start(tourId as string, path, prod as string | null);
    },
    [id, product],
  );
  if (!started) throw new Error(`${id} did not start on ${page.url()}`);
  await page.locator(".tour-callout").waitFor({ state: "visible", timeout: 15_000 });
}

async function shoot(page: Page, lang: Lang, name: string): Promise<void> {
  await page.waitForTimeout(250);
  await page.screenshot({ path: path.join(OUT, lang, "pictures", `${name}.png`) });
}

/** Run a per-page tour to its end, one picture per step that shows. A
 *  click step is pressed; the rest are advanced through the store. */
async function shootTour(page: Page, lang: Lang, id: string, product: string | null, only?: (n: number) => boolean) {
  await startTour(page, id, product);
  for (;;) {
    const step = await stepOf(page);
    if (!step) break;
    const name = product ? `${id}.${product}.${step.n}` : `${id}.${step.n}`;
    if (!only || only(step.n)) await shoot(page, lang, name);
    if (step.kind === "click") {
      await page.locator(".tour-mask").waitFor();
      // The control is the one thing the mask lets through; press it.
      const box = await page.evaluate(() => {
        const ring = document.querySelector(".tour-ring") as SVGRectElement | null;
        if (!ring) return null;
        const r = ring.getBoundingClientRect();
        return { x: r.left + r.width / 2, y: r.top + 24 };
      });
      if (!box) break;
      await page.mouse.click(box.x, box.y);
    } else {
      await page.evaluate(() => (window as unknown as TourWindow).__opkomstTour.next());
    }
    await page.waitForTimeout(500);
    await page.waitForLoadState("networkidle");
  }
}

async function signedIn(browser: Browser, lang: Lang, token: string, key: string): Promise<Page> {
  const context = await browser.newContext({ viewport: VIEWPORT, deviceScaleFactor: 2 });
  await context.addInitScript(
    ([t, k, l]) => {
      window.localStorage.setItem(k as string, t as string);
      window.localStorage.setItem("locale", l as string);
    },
    [token, key, lang],
  );
  return context.newPage();
}

for (const lang of ["nl", "en"] as Lang[]) {
  test(`shoot the manual's pictures in ${lang}`, async ({ browser, request }) => {
    mkdirSync(path.join(OUT, lang, "pictures"), { recursive: true });

    // --- the personal account: made at the start door once, then one of
    // everything through the organiser API, which the start door's own
    // limit of a few a day is not meant for ---
    let personal = await request.post("/api/v1/auth/dev-issue-token", { data: { email: PERSONAL, tenant: null } });
    if (!personal.ok()) {
      await json(
        await request.post("/api/v1/start/event", { data: { email: PERSONAL, ...startPayload("event", lang) } }),
        "start event",
      );
      personal = await request.post("/api/v1/auth/dev-issue-token", { data: { email: PERSONAL, tenant: null } });
    }
    const { token } = await json<{ token: string }>(personal, "personal token");
    const auth = { Authorization: `Bearer ${token}` };
    const ids: Partial<Record<Product, string>> = {};
    for (const kind of PRODUCTS) {
      const payload = startPayload(kind, lang);
      const body = payload[kind === "chore" ? "roster" : kind] as Record<string, unknown>;
      const made = await json<{ id: string }>(
        await request.post(`/api/v1/${kind}`, { headers: auth, data: { ...body, chapter_id: null } }),
        `make ${kind}`,
      );
      ids[kind] = made.id;
    }

    // --- signed out: the door ---
    {
      const context = await browser.newContext({ viewport: VIEWPORT, deviceScaleFactor: 2 });
      await context.addInitScript((l) => window.localStorage.setItem("locale", l as string), lang);
      const page = await context.newPage();
      await page.goto("/");
      await startTour(page, "inloggen", null);
      await shoot(page, lang, "inloggen.1");
      await page.evaluate(() => (window as unknown as TourWindow).__opkomstTour.next());
      await page.getByPlaceholder(lang === "nl" ? "E-mailadres" : "Email address").fill(PERSONAL);
      await shoot(page, lang, "inloggen.2");
      await page.getByRole("button", { name: lang === "nl" ? "Stuur link" : "Send link" }).click();
      await page.locator(".tour-callout").filter({ hasText: "3" }).waitFor({ timeout: 15_000 });
      await shoot(page, lang, "inloggen.3");
      await page.evaluate(() => (window as unknown as TourWindow).__opkomstTour.next());
      await shoot(page, lang, "inloggen.4");
      await context.close();
    }

    // --- the welcome tour, through the store rather than the card ---
    {
      const page = await signedIn(browser, lang, token, "token:personal");
      await page.goto("/");
      await startTour(page, "welkom", "event");
      await shoot(page, lang, "welkom.1");
      await page.getByRole("link", { name: lang === "nl" ? /^Evenement/ : /^Event/ }).first().click();
      await page.locator(".tour-callout").filter({ hasText: "2" }).waitFor({ timeout: 15_000 });
      await shoot(page, lang, "welkom.2");
      await page.getByRole("button", { name: lang === "nl" ? "Nieuw evenement" : "New event" }).click();
      await page.locator(".tour-callout").filter({ hasText: "3" }).waitFor({ timeout: 15_000 });
      await page.getByPlaceholder(lang === "nl" ? "Titel" : "Title").fill(lang === "nl" ? "Filmavond" : "Film night");
      const date = new Date(Date.now() + 21 * 24 * 60 * 60 * 1000);
      const dd = String(date.getDate()).padStart(2, "0");
      const mm = String(date.getMonth() + 1).padStart(2, "0");
      const dateField = page.getByPlaceholder(lang === "nl" ? "Datum" : "Date");
      await dateField.fill(`${dd}-${mm}-${date.getFullYear()}`);
      // Leave the field by clicking the form's own heading: Tab would
      // land in the time field and open its picker over the picture.
      await page.locator("h1").click();
      await page.evaluate(() => window.scrollTo(0, 0));
      await shoot(page, lang, "welkom.3");
      await page.getByRole("button", { name: lang === "nl" ? "Evenement aanmaken" : "Create event" }).click();
      await page.locator(".tour-callout").filter({ hasText: "4" }).waitFor({ timeout: 20_000 });
      await shoot(page, lang, "welkom.4");
      await page.evaluate(() => (window as unknown as TourWindow).__opkomstTour.next());
      await page.waitForTimeout(300);
      await shoot(page, lang, "welkom.5");
      await page.evaluate(() => (window as unknown as TourWindow).__opkomstTour.stop());

      // --- the three per-page tours, per product ---
      for (const product of PRODUCTS) {
        await page.goto(`/${product}`);
        await shootTour(page, lang, "lijst", product);
        await page.goto(`/${product}/${ids[product]}/details`);
        await shootTour(page, lang, "details", product);
        await page.goto(`/${product}/${ids[product]}/edit`);
        await shootTour(page, lang, "formulier", product);
      }

      // --- after: the archive, with the film night in it ---
      const events = await json<{ items: { id: string; name_nl: string | null; name_en: string | null }[] }>(
        await request.get("/api/v1/event?per_page=50", { headers: auth }),
        "events",
      );
      const film = events.items.find((e) => e.name_nl === "Filmavond" || e.name_en === "Film night");
      if (film) await request.post(`/api/v1/event/${film.id}/archive`, { headers: auth });
      await page.goto("/event/archived");
      await page.waitForLoadState("networkidle");
      await shoot(page, lang, "after.archief");
      await page.context().close();
    }

    // --- the organisation: users, chapters, settings, mail ---
    {
      const pending = await json<{ user: { id: string } }>(
        await request.post("/api/v1/auth/dev-pending-user", { data: { email: PENDING, tenant: "rsp" } }),
        "pending user",
      );
      const admin = await json<{ token: string }>(
        await request.post("/api/v1/auth/dev-issue-token", { data: { email: "admin@local.dev", tenant: "rsp" } }),
        "admin token",
      );
      const adminAuth = { Authorization: `Bearer ${admin.token}` };
      const organiser = await json<{ token: string; user: { chapters: { id: string; name: string }[] } }>(
        await request.post("/api/v1/auth/dev-issue-token", { data: { email: "organiser@local.dev", tenant: "rsp" } }),
        "organiser token",
      );
      const orgAuth = { Authorization: `Bearer ${organiser.token}` };
      const soon = new Date(Date.now() + 14 * 24 * 60 * 60 * 1000).toISOString().slice(0, 10);
      const mailed = await json<{ id: string }>(
        await request.post("/api/v1/event", {
          headers: orgAuth,
          data: {
            name_nl: "Ledenvergadering Amsterdam",
            name_en: "Members' meeting Amsterdam",
            description_nl: null,
            description_en: null,
            image_artist_instagram: null,
            chapter_id: organiser.user.chapters[0].id,
            location: "De Rode Hoed",
            latitude: null,
            longitude: null,
            starts_on: soon,
            start_time: "20:00:00",
            end_time: "22:00:00",
            source_options: [{ label: "Via een vriend" }],
            source_enabled: true,
            help_options: [],
            feedback_enabled: true,
            reminder_enabled: true,
            locale: lang,
          },
        }),
        "organisation event",
      );

      const page = await signedIn(browser, lang, admin.token, "token:rsp");
      await page.goto("/rsp/users");
      await shootTour(page, lang, "beheer", null);
      await page.goto("/rsp/users");
      await page.waitForLoadState("networkidle");
      await shoot(page, lang, "after.gebruikers");
      await page.goto("/rsp/chapters");
      await shootTour(page, lang, "beheer", null);
      await page.goto("/rsp/settings");
      await shootTour(page, lang, "beheer", null);

      // The feedback summary is the details tour's fifth step; the other
      // four are the personal account's pictures and stay.
      await page.goto(`/rsp/event/${mailed.id}/details`);
      await shootTour(page, lang, "details", "event", (n) => n === 5);

      // The mail switches sit in the fold; open it and look at them.
      await page.goto(`/rsp/event/${mailed.id}/edit`);
      await page.waitForLoadState("networkidle");
      await page.locator("details.advanced > summary").click();
      const reminder = page.getByText(lang === "nl" ? "Herinnering vooraf versturen" : "Send a reminder before the event");
      await reminder.scrollIntoViewIfNeeded();
      await page.evaluate(() => window.scrollBy(0, -160));
      await shoot(page, lang, "after.mail");

      // The public chapter agenda.
      const chapters = await json<{ slug: string }[]>(
        await request.get("/api/v1/chapters", { headers: adminAuth }),
        "chapters",
      );
      await page.goto(`/rsp/${chapters[0].slug}`);
      await page.waitForLoadState("networkidle");
      await shoot(page, lang, "after.afdelingen");
      await page.context().close();

      // Leave the organisation as it was.
      await request.delete(`/api/v1/admin/users/${pending.user.id}`, { headers: adminAuth });
      await request.post(`/api/v1/event/${mailed.id}/archive`, { headers: orgAuth });
      await request.delete(`/api/v1/event/${mailed.id}`, { headers: orgAuth });
    }

    // --- leave the personal account as it was ---
    for (const kind of PRODUCTS) {
      for (const listPath of [`/api/v1/${kind}`, `/api/v1/${kind}/archived`]) {
        const res = await request.get(`${listPath}?per_page=200`, { headers: auth });
        if (!res.ok()) continue;
        const body = (await res.json()) as { items: { id: string }[] };
        for (const item of body.items) {
          await request.post(`/api/v1/${kind}/${item.id}/archive`, { headers: auth });
          await request.delete(`/api/v1/${kind}/${item.id}`, { headers: auth });
        }
      }
    }
  });
}
