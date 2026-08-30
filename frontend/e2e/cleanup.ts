import { type APIRequestContext, test } from "@playwright/test";

/**
 * Teardown "test": deletes the throwaway entities the specs create so they
 * don't pile up in the shared local dev DB run after run. Every spec names
 * its data with an ``E2E`` / ``EL`` prefix; this hard-deletes anything
 * matching across all four entity types, as the seeded organiser. Runs as
 * the ``teardown`` of the main project — i.e. after the specs, while the
 * dev servers are still up (a plain ``globalTeardown`` runs too late, once
 * the API is already gone).
 *
 * Hard delete refuses a live entity ("archive it first", 409), so each is
 * archived then deleted; both the active and archived lists are swept.
 */
const PREFIXES = ["E2E ", "EL "];

function isThrowaway(name: unknown): name is string {
  return typeof name === "string" && PREFIXES.some((p) => name.startsWith(p));
}

async function purge(request: APIRequestContext, path: string, headers: Record<string, string>): Promise<void> {
  const seen = new Set<string>();
  for (const listPath of [path, `${path}/archived`]) {
    // The lists are paged, so the sweep walks the pages: a run that
    // left more than a page of throwaways would otherwise leave the
    // rest behind.
    for (let page = 1; ; page++) {
      const res = await request.get(`${listPath}?page=${page}&per_page=200`, { headers });
      if (!res.ok()) break;
      const body = (await res.json()) as { items: { id: string; name?: string }[]; total: number };
      for (const item of body.items) {
        if (!isThrowaway(item.name) || seen.has(item.id)) continue;
        seen.add(item.id);
        await request.post(`${path}/${item.id}/archive`, { headers }); // no-op if already archived
        await request.delete(`${path}/${item.id}`, { headers });
      }
      if (page * 200 >= body.total || body.items.length === 0) break;
    }
  }
}

test("clean up throwaway e2e entities", async ({ request }) => {
  const login = await request.post("/api/v1/auth/dev-issue-token", {
    data: { email: "organiser@local.dev", tenant: "rsp" },
  });
  const { token } = await login.json();
  const headers = { Authorization: `Bearer ${token}` };
  for (const path of ["/api/v1/event", "/api/v1/form", "/api/v1/datepoll", "/api/v1/chore"]) {
    await purge(request, path, headers);
  }
});
