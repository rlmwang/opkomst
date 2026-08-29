/**
 * The query and mutation layer, by URL and verb.
 *
 * Nothing is rendered: each call is checked to hit the right URL with
 * the right verb, and the optimistic writes are checked to put the
 * cache back when the server refuses. The HTTP client is mocked. The
 * point is to catch a renamed route or a flipped verb here rather than
 * two refactors later.
 *
 * A query subscribes in an effect, and an effect needs an owner, so
 * each one runs inside an effect root (``effect-root``).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as apiClient from "@/api/client";
import { inEffect } from "@/__tests__/effect-root.svelte";
import { queryClient } from "@/lib/query-client";

vi.mock("@/api/client", () => ({
  get: vi.fn(),
  post: vi.fn(),
  put: vi.fn(),
  patch: vi.fn(),
  del: vi.fn(),
  getToken: vi.fn(() => null),
  setToken: vi.fn(),
  clearToken: vi.fn(),
  ApiError: class ApiError extends Error {},
}));

const mockGet = vi.mocked(apiClient.get);
const mockPost = vi.mocked(apiClient.post);
const mockPut = vi.mocked(apiClient.put);
const mockPatch = vi.mocked(apiClient.patch);
const mockDel = vi.mocked(apiClient.del);

beforeEach(() => {
  vi.clearAllMocks();
});

afterEach(() => {
  queryClient.clear();
});

describe("the admin writes", () => {
  it("usersQuery issues GET /api/v1/admin/users", async () => {
    const { usersQuery } = await import("@/composables/useAdmin.svelte");
    mockGet.mockResolvedValueOnce([]);

    await inEffect(() => usersQuery().refetch());

    expect(mockGet).toHaveBeenCalledWith("/api/v1/admin/users");
  });

  it("approveUser POSTs to /approve with the chapter_ids payload", async () => {
    const { approveUser } = await import("@/composables/useAdmin.svelte");
    mockPost.mockResolvedValueOnce({} as never);

    await inEffect(() => approveUser().run({ userId: "u1", chapterIds: ["ch1", "ch2"] }));

    expect(mockPost).toHaveBeenCalledWith("/api/v1/admin/users/u1/approve", {
      chapter_ids: ["ch1", "ch2"],
    });
  });

  it("setUserChapters POSTs the full chapter set", async () => {
    const { setUserChapters } = await import("@/composables/useAdmin.svelte");
    mockPost.mockResolvedValueOnce({} as never);

    await inEffect(() => setUserChapters().run({ userId: "u1", chapterIds: ["ch1", "ch2"] }));

    expect(mockPost).toHaveBeenCalledWith(
      "/api/v1/admin/users/u1/set-chapters",
      { chapter_ids: ["ch1", "ch2"] },
    );
  });

  it("removeUser DELETEs /api/v1/admin/users/{id}", async () => {
    const { removeUser } = await import("@/composables/useAdmin.svelte");
    mockDel.mockResolvedValueOnce(undefined as never);

    await inEffect(() => removeUser().run("u1"));

    expect(mockDel).toHaveBeenCalledWith("/api/v1/admin/users/u1");
  });

  it("removeUser skips the non-array pending-count cache entry", async () => {
    // Regression: the pending-count query lives at
    // ``["admin", "users", "pending-count"]`` so it matches the
    // ``["admin", "users"]`` prefix that the optimistic
    // ``setQueriesData`` call uses. Its data is ``{count: N}``,
    // not ``User[]``. An unguarded ``old?.filter`` throws there,
    // the mutation rejects in onMutate, and the DELETE never
    // leaves the browser — that's the prod bug "Verwijderen
    // mislukt with no DELETE in the access log".
    const { removeUser } = await import("@/composables/useAdmin.svelte");
    queryClient.setQueryData(
      ["admin", "users", { pending: false }],
      [{ id: "u1", name: "A" }, { id: "u2", name: "B" }],
    );
    queryClient.setQueryData(["admin", "users", "pending-count"], { count: 2 });
    mockDel.mockResolvedValueOnce(undefined as never);

    await inEffect(() => removeUser().run("u1"));

    // The DELETE actually fires.
    expect(mockDel).toHaveBeenCalledWith("/api/v1/admin/users/u1");
    // The list-shaped cache reflects the optimistic removal.
    const list = queryClient.getQueryData<{ id: string }[]>([
      "admin",
      "users",
      { pending: false },
    ]);
    expect(list?.map((u) => u.id)).toEqual(["u2"]);
    // The non-list cache is untouched.
    expect(queryClient.getQueryData(["admin", "users", "pending-count"]))
      .toEqual({ count: 2 });
  });

  it("removeUser rolls every cached users-list back on failure", async () => {
    const { removeUser } = await import("@/composables/useAdmin.svelte");

    // Two cached lists under the same prefix — verify both get
    // rolled back, not just one.
    queryClient.setQueryData(
      ["admin", "users", { pending: false }],
      [{ id: "u1", name: "A" }, { id: "u2", name: "B" }],
    );
    queryClient.setQueryData(
      ["admin", "users", { pending: true }],
      [{ id: "u1", name: "A" }],
    );
    mockDel.mockRejectedValueOnce(new Error("boom"));

    await expect(inEffect(() => removeUser().run("u1"))).rejects.toThrow();

    const all = queryClient.getQueryData<{ id: string }[]>([
      "admin",
      "users",
      { pending: false },
    ]);
    const pending = queryClient.getQueryData<{ id: string }[]>([
      "admin",
      "users",
      { pending: true },
    ]);
    expect(all?.map((u) => u.id)).toEqual(["u1", "u2"]);
    expect(pending?.map((u) => u.id)).toEqual(["u1"]);
  });
});

describe("the event writes", () => {
  it("archiveEvent rolls the cache back to the snapshot on failure", async () => {
    const { archiveEvent } = await import("@/composables/useEvents.svelte");

    queryClient.setQueryData(
      ["event", "active"],
      [{ id: "e1", name: "A" }, { id: "e2", name: "B" }],
    );
    mockPost.mockRejectedValueOnce(new Error("boom"));

    await expect(inEffect(() => archiveEvent().run("e1"))).rejects.toThrow();

    // Snapshot restored — both events back in the cache, in order.
    const after = queryClient.getQueryData<{ id: string }[]>(["event", "active"]);
    expect(after?.map((e) => e.id)).toEqual(["e1", "e2"]);
  });

  it("sendEmailsNow POSTs the channel-keyed URL", async () => {
    const { sendEmailsNow } = await import("@/composables/useEvents.svelte");
    mockPost.mockResolvedValueOnce({ processed: 3 });

    const r = await inEffect(() => sendEmailsNow().run({ eventId: "ev1", channel: "reminder" }));

    expect(mockPost).toHaveBeenCalledWith(
      "/api/v1/event/ev1/send-emails/reminder",
    );
    expect(r.processed).toBe(3);
  });

  it("events.create POSTs /api/v1/event with the payload", async () => {
    const { events } = await import("@/composables/useEvents.svelte");
    const payload = {
      name: "Demo",
      chapter_id: "ch1",
      topic: null,
      location: "X",
      latitude: null,
      longitude: null,
      starts_on: "2026-05-01",
      start_time: "18:00:00",
      end_time: "20:00:00",
      period_weeks: 1,
      cycle_slots: [4],
      span_weeks: 6,
      horizon_days: 90,
      source_options: [{ id: null, label: "F" }],
      source_enabled: true,
      help_options: [],
      help_enabled: false,
      feedback_enabled: true,
      reminder_enabled: false,
      listed: true,
      name_required: false,
      answers_editable: true,
      locale: "nl" as const,
    };
    mockPost.mockResolvedValueOnce({ id: "ev1" });

    await inEffect(() => events.create().run(payload));

    expect(mockPost).toHaveBeenCalledWith("/api/v1/event", payload);
  });

  it("updateEvent PUTs the event-id-keyed URL", async () => {
    const { updateEvent } = await import("@/composables/useEvents.svelte");
    mockPut.mockResolvedValueOnce({ id: "ev1" } as never);

    const payload = { name: "X" } as never;
    await inEffect(() => updateEvent().run({ eventId: "ev1", payload }));

    expect(mockPut).toHaveBeenCalledWith("/api/v1/event/ev1", payload);
  });

  it("events.restore POSTs /api/v1/event/{id}/restore", async () => {
    const { events } = await import("@/composables/useEvents.svelte");
    mockPost.mockResolvedValueOnce({} as never);

    await inEffect(() => events.restore().run("ev1"));

    expect(mockPost).toHaveBeenCalledWith("/api/v1/event/ev1/restore");
  });

  it("occurrencesQuery GETs the occurrence panel URL", async () => {
    const { occurrencesQuery } = await import("@/composables/useEvents.svelte");
    mockGet.mockResolvedValueOnce({ total_sessions: 6, occurrences: [], projected: [] });

    await inEffect(() => occurrencesQuery(() => "ev1").refetch());

    expect(mockGet).toHaveBeenCalledWith("/api/v1/event/ev1/occurrences");
  });

  it("deleteSignup DELETEs the line-item URL", async () => {
    const { deleteSignup } = await import("@/composables/useEvents.svelte");
    mockDel.mockResolvedValueOnce(undefined as never);

    await inEffect(() => deleteSignup().run({ eventId: "ev1", occurrenceId: "oc1", signupId: "su1" }));

    expect(mockDel).toHaveBeenCalledWith("/api/v1/event/ev1/signups/su1");
  });

  // ``usePublicSignup`` removed: the public sign-up form moved to
  // its own mini-app (``frontend/src/public/``) which uses raw
  // ``fetch`` instead of a query. Coverage for that POST shape
  // lives in the backend's ``test_events_router_extras.py`` /
  // ``test_public_archived.py`` end-to-end tests.
});

describe("the chapter writes", () => {
  it("archiveChapter rolls every cached chapters-list back on failure", async () => {
    const { archiveChapter } = await import("@/composables/useChapters.svelte");

    queryClient.setQueryData(
      ["chapters"],
      [{ id: "c1", name: "A" }, { id: "c2", name: "B" }],
    );
    mockDel.mockRejectedValueOnce(new Error("boom"));

    await expect(inEffect(() => archiveChapter().run({ id: "c1" }))).rejects.toThrow();

    const after = queryClient.getQueryData<{ id: string }[]>(["chapters"]);
    expect(after?.map((c) => c.id)).toEqual(["c1", "c2"]);
  });

  it("createChapter POSTs /api/v1/chapters with the name body", async () => {
    const { createChapter } = await import("@/composables/useChapters.svelte");
    mockPost.mockResolvedValueOnce({} as never);

    await inEffect(() => createChapter().run("New chapter"));

    expect(mockPost).toHaveBeenCalledWith("/api/v1/chapters", {
      name: "New chapter",
    });
  });

  it("updateChapter PATCHes /api/v1/chapters/{id} with the payload", async () => {
    const { updateChapter } = await import("@/composables/useChapters.svelte");
    mockPatch.mockResolvedValueOnce({} as never);

    await inEffect(() => updateChapter().run({ id: "c1", payload: { name: "Renamed" } }));

    expect(mockPatch).toHaveBeenCalledWith("/api/v1/chapters/c1", {
      name: "Renamed",
    });
  });
});

describe("the feedback write", () => {
  it("submitFeedback POSTs the URL-encoded token path with answers", async () => {
    const { submitFeedback } = await import("@/composables/useFeedback.svelte");
    mockPost.mockResolvedValueOnce({} as never);

    await inEffect(() => submitFeedback().run({
      token: "abc 123/x",
      answers: [{ question_key: "q1", answer_int: 5 }],
    }));

    expect(mockPost).toHaveBeenCalledWith("/api/v1/feedback/abc%20123%2Fx/submit", {
      answers: [{ question_key: "q1", answer_int: 5 }],
    });
  });
});
