import { useConfirm } from "primevue/useconfirm";

interface ConfirmOpts {
  header: string;
  message: string;
  acceptLabel: string;
  rejectLabel: string;
  /** Optional PrimeIcon class for the dialog header icon. */
  icon?: string;
  accept: () => void | Promise<void>;
}

/** Brand-consistent confirmation dialog. Reject = secondary text
 * button (matches ``AppDialog`` cancel); Accept = brand-red primary
 * button. Every ``confirm.require`` call site goes through this so
 * dialog buttons never drift. */
export function useConfirms() {
  const confirm = useConfirm();
  return {
    ask(opts: ConfirmOpts) {
      confirm.require({
        header: opts.header,
        message: opts.message,
        icon: opts.icon,
        rejectLabel: opts.rejectLabel,
        rejectProps: { severity: "secondary", text: true },
        acceptLabel: opts.acceptLabel,
        accept: opts.accept,
      });
    },
  };
}
