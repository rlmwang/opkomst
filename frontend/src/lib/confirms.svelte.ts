import type { IconName } from "@/components/app-icons";

/**
 * The app's confirmation dialog. Was a wrapper over PrimeVue's
 * ``useConfirm``; the queue underneath is the app's own now, and
 * ``AppConfirmDialog`` in ``App.svelte`` renders it over ``AppDialog``.
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

let request = $state<ConfirmRequest | null>(null);

/** What is being asked, for the one component that renders it. */
export function currentConfirm(): ConfirmRequest | null {
  return request;
}

export function ask(opts: ConfirmRequest): void {
  request = opts;
}

export async function acceptConfirm(): Promise<void> {
  const pending = request;
  request = null;
  await pending?.accept();
}

export function rejectConfirm(): void {
  request = null;
}
