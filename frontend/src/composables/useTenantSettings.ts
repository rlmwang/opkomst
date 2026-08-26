/**
 * The organisation's own settings — today the public agenda's
 * rolling window, read by every approved member and written by
 * its admins.
 *
 * One key, one object, replaced whole. The save is optimistic
 * with a snapshot rollback like every other mutation in the app:
 * the two numbers the form already holds are exactly what the
 * server returns, so there is nothing to wait for.
 */

import { useMutation, useQueryClient } from "@tanstack/vue-query";

import { put } from "@/api/client";
import { useApiQuery } from "@/api/queries";
import type { TenantSettings } from "@/api/types";

export type { TenantSettings };

const SETTINGS_KEY = ["settings"] as const;

export function useTenantSettings() {
  return useApiQuery<TenantSettings>(SETTINGS_KEY, "/api/v1/settings");
}

export function useSaveTenantSettings() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: TenantSettings) => put<TenantSettings>("/api/v1/settings", vars),
    onMutate: async (vars) => {
      await qc.cancelQueries({ queryKey: SETTINGS_KEY });
      const snap = qc.getQueryData<TenantSettings>(SETTINGS_KEY);
      qc.setQueryData<TenantSettings>(SETTINGS_KEY, vars);
      return { snap };
    },
    onError: (_err, _vars, ctx) => {
      qc.setQueryData(SETTINGS_KEY, ctx?.snap);
    },
    onSettled: () => qc.invalidateQueries({ queryKey: SETTINGS_KEY }),
  });
}
