/**
 * A dialog's three pieces of state: whether it is open, what it is
 * about, and whether its submit is in flight.
 *
 * Every page that had a dialog declared those three separately along
 * with the same open, close and submit around them.
 *
 * On a failed submit the dialog stays open so the person can try again;
 * ``submitting`` is cleared either way.
 */
export interface DialogState<T> {
  open: boolean;
  readonly target: T | null;
  readonly submitting: boolean;
  openWith(target: T): void;
  close(): void;
  submit(fn: () => Promise<void>): Promise<void>;
}

export function dialog<T = void>(): DialogState<T> {
  let open = $state(false);
  let target = $state<T | null>(null);
  let submitting = $state(false);

  return {
    get open() {
      return open;
    },
    set open(next: boolean) {
      open = next;
      if (!next) target = null;
    },
    get target() {
      return target;
    },
    get submitting() {
      return submitting;
    },
    openWith(next: T) {
      target = next;
      open = true;
    },
    close() {
      open = false;
      target = null;
    },
    async submit(fn: () => Promise<void>) {
      submitting = true;
      try {
        await fn();
        open = false;
        target = null;
      } finally {
        submitting = false;
      }
    },
  };
}
