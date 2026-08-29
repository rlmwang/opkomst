<script lang="ts">
import type { Snippet } from "svelte";

import AppButton from "@/components/AppButton.svelte";
import AppCard from "@/components/AppCard.svelte";
import AppHeader from "@/components/AppHeader.svelte";
import SupportButtons from "@/public_shared/SupportButtons.svelte";
import { t } from "@/i18n.svelte";

/**
 * Shared shell for "managed resource" edit pages — EventFormPage
 * today (handling both ``/event/new`` and ``/event/:id/edit``);
 * FormEditPage when the Forms feature lands. Owns:
 *
 * * AppHeader.
 * * The bare ``.container`` (no ``.stack`` — the form's own
 *   ``form-section`` gap drives vertical spacing instead, matching
 *   the existing event form).
 * * The ``<AppCard tag="form">`` wrapper with ``novalidate`` and
 *   the ``@submit.prevent``; the parent listens on the ``submit``
 *   event for the actual save.
 * * The page title.
 * * The Cancel + Save footer — Cancel emits a ``cancel`` event
 *   the parent routes from (back to the list, or back to details),
 *   Save is a real submit button so the form submit handler fires.
 *
 * Per-page concerns stay outside: state refs, draft persistence
 * (``useFormDraft``), input validation toasts, the actual mutation
 * call. The shell is chrome only.
 */
const {
  title,
  submitLabel,
  submitting,
  cancelLabel,
  children,
  onsubmit,
  oncancel,
}: {
  title: string;
  submitLabel: string;
  submitting: boolean;
  cancelLabel?: string;
  children: Snippet;
  onsubmit: () => void;
  oncancel: () => void;
} = $props();
</script>

<AppHeader />
<div class="container-wide">
  <AppCard
    tag="form"
    novalidate
    onsubmit={(e: SubmitEvent) => {
      e.preventDefault();
      onsubmit();
    }}
  >
    <h1>{title}</h1>
    {@render children()}
    <div class="form-footer">
      <!-- An aside, opposite the primary action: it asks, it does not
           compete. Renders nothing unless a support URL is set. -->
      <div class="form-footer-support"><SupportButtons /></div>
      <AppButton
        label={cancelLabel ?? t("common.cancel")}
        severity="secondary"
        text
        type="button"
        onclick={oncancel}
      />
      <AppButton type="submit" label={submitLabel} loading={submitting} />
    </div>
  </AppCard>
</div>

<style>
/* Cancel + submit pinned to the right with breathing room above so
 * the footer doesn't feel glued to the last section. */
.form-footer {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 0.5rem;
  margin-top: 1.5rem;
}
/* Pushes everything after it to the right, so the row is support on the
 * left and the actions on the right however many buttons there are. */
.form-footer-support {
  margin-right: auto;
}
</style>
