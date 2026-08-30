import { queryClient } from "@/lib/query-client";

/**
 * One write, and whether it is in flight.
 *
 * Was ``useMutation`` from Vue Query, which the app used for three
 * things: running the call, telling a button to show a spinner, and
 * patching the cache before the server answers. Everything else it
 * offers, retries and error objects and status enums, the pages did
 * themselves. This is those three.
 *
 * ``invalidate`` names the cache keys the write disturbs; they are
 * invalidated when it settles, whichever way it went.
 *
 * ``optimistic`` patches the cache and hands back the undo. That shape
 * is deliberate: the snapshot and the rollback are written next to each
 * other, so a patch cannot be added without its undo, which is how the
 * Vue version's ``onMutate``/``onError`` pair drifted apart in the
 * first place.
 */
export function mutation<TVars, TResult>(
  run: (vars: TVars) => Promise<TResult>,
  opts: {
    invalidate?: unknown[][];
    optimistic?: (vars: TVars) => () => void;
    onSuccess?: (result: TResult, vars: TVars) => void;
  } = {},
) {
  let pending = $state(false);

  return {
    get pending() {
      return pending;
    },
    async run(vars: TVars): Promise<TResult> {
      pending = true;
      const rollback = opts.optimistic?.(vars);
      try {
        const result = await run(vars);
        opts.onSuccess?.(result, vars);
        return result;
      } catch (err) {
        rollback?.();
        throw err;
      } finally {
        pending = false;
        for (const key of opts.invalidate ?? []) {
          void queryClient.invalidateQueries({ queryKey: key });
        }
      }
    },
  };
}
