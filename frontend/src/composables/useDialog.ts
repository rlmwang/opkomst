/**
 * Triple-state dialog helper: open + target + submitting.
 *
 * Every page mounted three refs per dialog:
 *
 *   const fooOpen = ref(false);
 *   const fooTarget = ref<T | null>(null);
 *   const fooSubmitting = ref(false);
 *
 * Plus an ``openWith(t)`` / ``submit(fn)`` / ``close()`` flow
 * that all looked the same. ``useDialog<T>()`` packages it into
 * one composable.
 *
 * Typical use:
 *
 *   const editDialog = useDialog<Event>();
 *
 *   function openEdit(e: Event) { editDialog.openWith(e); }
 *
 *   async function submitEdit() {
 *     await editDialog.submit(async () => {
 *       await mutation.mutateAsync(...);
 *       toasts.success("Saved");
 *     });
 *   }
 */

import { ref, type Ref } from "vue";

export interface DialogState<T> {
  open: Ref<boolean>;
  target: Ref<T | null>;
  submitting: Ref<boolean>;
  /** Set the target and open the dialog. */
  openWith(t: T): void;
  /** Close the dialog and clear the target. */
  close(): void;
  /** Run ``fn`` while ``submitting`` is true; close on success.
   * On failure the dialog stays open so the user can retry —
   * ``submitting`` resets either way. */
  submit(fn: () => Promise<void>): Promise<void>;
}

export function useDialog<T = void>(): DialogState<T> {
  const open = ref(false);
  const target = ref<T | null>(null) as Ref<T | null>;
  const submitting = ref(false);

  function openWith(t: T): void {
    target.value = t;
    open.value = true;
  }

  function close(): void {
    open.value = false;
    target.value = null;
  }

  async function submit(fn: () => Promise<void>): Promise<void> {
    submitting.value = true;
    try {
      await fn();
      close();
    } finally {
      submitting.value = false;
    }
  }

  return { open, target, submitting, openWith, close, submit };
}
