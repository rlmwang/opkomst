import { reactive, readonly } from "vue";

import type { IconName } from "@/components/AppIcon.vue";

/**
 * The app's confirmation dialog. Was a wrapper over PrimeVue's
 * ``useConfirm``; the queue underneath is the app's own now, and
 * ``<AppConfirmDialog>`` in ``App.vue`` renders it over ``AppDialog``.
 *
 * One request at a time, which is what a modal means. ``ask`` from six
 * call sites, and none of them changed for this: reject is a secondary
 * text button, accept is the brand-red primary, so dialog buttons never
 * drift.
 */
export interface ConfirmRequest {
  header: string;
  message: string;
  acceptLabel: string;
  rejectLabel: string;
  /** Optional ``AppIcon`` name shown beside the message. */
  icon?: IconName;
  accept: () => void | Promise<void>;
}

const state = reactive<{ request: ConfirmRequest | null }>({ request: null });

export function useConfirms() {
  return {
    ask(opts: ConfirmRequest) {
      state.request = opts;
    },
  };
}

/** For the one component that renders the dialog. */
export function useConfirmRequest() {
  return {
    state: readonly(state),
    async accept() {
      const request = state.request;
      state.request = null;
      await request?.accept();
    },
    reject() {
      state.request = null;
    },
  };
}
