import { put } from "@/api/client";
import { apiQuery } from "@/api/queries.svelte";
import { mutation } from "@/composables/mutation.svelte";
import { queryClient } from "@/lib/query-client";
import type { TenantSettings } from "@/api/types";

/**
 * The organisation's own settings: today the public agenda's rolling
 * window, read by every approved member and written by its admins.
 *
 * One key, one object, replaced whole. The save patches the cache
 * first, because the two numbers the form holds are exactly what the
 * server will return.
 */
export type { TenantSettings };

const SETTINGS_KEY = ["settings"];

export function tenantSettingsQuery() {
  return apiQuery<TenantSettings>(
    () => SETTINGS_KEY,
    () => "/api/v1/settings",
  );
}

export const saveTenantSettings = () =>
  mutation((vars: TenantSettings) => put<TenantSettings>("/api/v1/settings", vars), {
    invalidate: [SETTINGS_KEY],
    optimistic: (vars) => {
      const snap = queryClient.getQueryData<TenantSettings>(SETTINGS_KEY);
      queryClient.setQueryData<TenantSettings>(SETTINGS_KEY, vars);
      return () => queryClient.setQueryData(SETTINGS_KEY, snap);
    },
  });
