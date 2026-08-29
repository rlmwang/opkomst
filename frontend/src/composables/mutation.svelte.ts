import { queryClient } from "@/lib/query-client";

/**
 * One write, and whether it is in flight.
 *
 * Was ``useMutation`` from Vue Query, which the app used for two things:
 * running the call and telling a button to show a spinner. Everything
 * else it offers, optimistic state and retries and error objects, the
 * pages did themselves. This is those two things.
 *
 * ``invalidate`` names the cache keys the write disturbs; they are
 * invalidated when it settles, whichever way it went.
 */
export function mutation<TVars, TResult>(
  run: (vars: TVars) => Promise<TResult>,
  opts: { invalidate?: unknown[][]; onSuccess?: (result: TResult, vars: TVars) => void } = {},
) {
  let pending = $state(false);

  return {
    get pending() {
      return pending;
    },
    async run(vars: TVars): Promise<TResult> {
      pending = true;
      try {
        const result = await run(vars);
        opts.onSuccess?.(result, vars);
        return result;
      } finally {
        pending = false;
        for (const key of opts.invalidate ?? []) {
          void queryClient.invalidateQueries({ queryKey: key });
        }
      }
    },
  };
}
