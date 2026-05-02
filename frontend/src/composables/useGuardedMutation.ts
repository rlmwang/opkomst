/**
 * "Confirm → mutate → toast" idiom in one composable.
 *
 * Pages repeated the same pattern in every destructive action:
 *
 *   confirms.ask({
 *     header, message, accept: async () => {
 *       try { await mutation.mutateAsync(x); toasts.success(ok) }
 *       catch { toasts.error(fail) }
 *     }
 *   })
 *
 * ``useGuardedMutation`` wraps that into a setup-time hook. It
 * MUST run during component setup — it calls ``useToasts()`` and
 * ``useConfirms()``, which call PrimeVue's ``inject()``. Calling
 * the hook from an event handler trips Vue's "inject() outside
 * setup" warning and may resolve the wrong (or no) provider.
 *
 * Each click-time arg becomes the input to a per-call ``spec``
 * function that returns the mutation vars plus the toast / confirm
 * copy for that specific invocation. This shape:
 *
 *   const askDelete = useGuardedMutation(removeMutation, (u: User) => ({
 *     vars: u.id,
 *     ok: t("admin.deleteOk", { name: u.name }),
 *     fail: t("admin.deleteFail"),
 *     confirm: { header: ..., message: t("...", { name: u.name }), ... },
 *   }));
 *   // click: askDelete(u);
 *
 * keeps the per-call data (here ``u.name``) in scope without
 * recreating the wrapper on every click.
 */

import type { UseMutationReturnType } from "@tanstack/vue-query";

import { useConfirms } from "@/lib/confirms";
import { useToasts } from "@/lib/toasts";

interface ConfirmOpts {
  header: string;
  message: string;
  acceptLabel: string;
  rejectLabel: string;
  /** Optional PrimeIcon class for the dialog header icon. */
  icon?: string;
}

interface ToastSpec {
  summary: string;
  detail?: string;
}

export interface GuardedSpec<TVar, TData = unknown, TError = unknown> {
  /** The input the underlying mutation will receive. */
  vars: TVar;
  /** Toast on success. String shorthand for ``{ summary }``; function
   * receives the mutation result for count-aware messages. */
  ok: string | ((data: TData) => string | ToastSpec);
  /** Toast on failure. String shorthand for ``{ summary }``; function
   * receives the caught error so error-class branching can render
   * a different message. */
  fail: string | ((err: TError) => string);
  /** Optional confirmation dialog before running the mutation. */
  confirm?: ConfirmOpts;
}

/** Setup-time hook. Returns a function that takes the click-time
 * arg, resolves the per-call ``spec``, optionally confirms, then
 * runs the mutation with toast feedback. */
export function useGuardedMutation<TArg, TVar, TData = unknown, TError = unknown>(
  mutation: UseMutationReturnType<TData, TError, TVar, unknown>,
  spec: (arg: TArg) => GuardedSpec<TVar, TData, TError>,
): (arg: TArg) => Promise<void> {
  const toasts = useToasts();
  const confirms = useConfirms();

  const resolveOk = (
    ok: GuardedSpec<TVar, TData, TError>["ok"],
    data: TData,
  ): ToastSpec => {
    const v = typeof ok === "function" ? ok(data) : ok;
    return typeof v === "string" ? { summary: v } : v;
  };
  const resolveFail = (
    fail: GuardedSpec<TVar, TData, TError>["fail"],
    err: TError,
  ): string => (typeof fail === "function" ? fail(err) : fail);

  const run = async (s: GuardedSpec<TVar, TData, TError>): Promise<void> => {
    try {
      const data = await mutation.mutateAsync(s.vars);
      const out = resolveOk(s.ok, data);
      toasts.success(out.summary, { detail: out.detail });
    } catch (err) {
      toasts.error(resolveFail(s.fail, err as TError));
    }
  };

  return async (arg: TArg): Promise<void> => {
    const s = spec(arg);
    if (!s.confirm) {
      await run(s);
      return;
    }
    confirms.ask({
      ...s.confirm,
      accept: () => run(s),
    });
  };
}
