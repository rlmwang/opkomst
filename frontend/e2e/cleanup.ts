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
    const res = await request.get(listPath, { headers });
    if (!res.ok()) continue;
    const items = (await res.json()) as { id: string; name?: string }[];
    for (const item of items) {
      if (!isThrowaway(item.name) || seen.has(item.id)) continue;
      seen.add(item.id);
      await request.post(`${path}/${item.id}/archive`, { headers }); // no-op if already archived
      await request.delete(`${path}/${item.id}`, { headers });
    }
  }
}

test("clean up throwaway e2e entities", async ({ request }) => {
  const login = await request.post("/api/v1/auth/dev-issue-token", {
    data: { email: "organiser@local.dev", tenant: "rsp" },
  });
  const { token } = await login.json();
  const headers = { Authorization: `Bearer ${token}` };
  for (const path of ["/api/v1/events", "/api/v1/forms", "/api/v1/datepolls", "/api/v1/chores"]) {
    await purge(request, path, headers);
  }
});
