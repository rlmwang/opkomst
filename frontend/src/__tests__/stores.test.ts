/**
 * Smoke tests for the Pinia stores.
 *
 * Each store is instantiated with a fresh Pinia and asserted to expose
 * its documented initial state. Goal: catch a typo in a store rename
 * or a state-shape regression at type-check time, before a component
 * tries to render against it.
 *
 * No HTTP calls are made — the API client module is mocked so an
 * accidental network call inside a store's setup function would fail
 * loudly.
 */

import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";

// All five stores import from "@/api/client". Mock once so no test
// can accidentally hit the network.
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

beforeEach(() => {
  setActivePinia(createPinia());
});

describe("auth store", () => {
  it("starts logged-out and unloaded", async () => {
    const { useAuthStore } = await import("@/stores/auth");
    const store = useAuthStore();
    expect(store.user).toBeNull();
    expect(store.loaded).toBe(false);
    expect(store.isAuthenticated).toBe(false);
    expect(store.isVerified).toBe(false);
    expect(store.isApproved).toBe(false);
    expect(store.isAdmin).toBe(false);
  });
});

describe("admin store", () => {
  it("starts with an empty users list", async () => {
    const { useAdminStore } = await import("@/stores/admin");
    const store = useAdminStore();
    expect(store.users).toEqual([]);
  });
});

describe("chapters store", () => {
  it("starts with an empty list", async () => {
    const { useChaptersStore } = await import("@/stores/chapters");
    const store = useChaptersStore();
    expect(store.all).toEqual([]);
  });
});

describe("events store", () => {
  it("starts with empty active and archived lists", async () => {
    const { useEventsStore } = await import("@/stores/events");
    const store = useEventsStore();
    expect(store.all).toEqual([]);
    expect(store.archived).toEqual([]);
  });
});

describe("feedback store", () => {
  it("starts with an empty questions list", async () => {
    const { useFeedbackStore } = await import("@/stores/feedback");
    const store = useFeedbackStore();
    expect(store.questions).toEqual([]);
  });
});
