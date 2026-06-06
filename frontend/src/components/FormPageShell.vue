<script setup lang="ts">
import Button from "primevue/button";
import { useI18n } from "vue-i18n";
import AppCard from "@/components/AppCard.vue";
import AppHeader from "@/components/AppHeader.vue";

/**
 * Shared shell for "managed resource" edit pages — EventFormPage
 * today (handling both ``/events/new`` and ``/events/:id/edit``);
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

defineProps<{
  title: string;
  submitLabel: string;
  submitting: boolean;
  cancelLabel?: string;
}>();

const emit = defineEmits<{
  submit: [];
  cancel: [];
}>();

const { t } = useI18n();
</script>

<template>
  <AppHeader />
  <div class="container">
    <AppCard tag="form" novalidate @submit.prevent="emit('submit')">
      <h1>{{ title }}</h1>
      <slot />
      <div class="form-footer">
        <Button
          :label="cancelLabel ?? t('common.cancel')"
          severity="secondary"
          text
          type="button"
          @click="emit('cancel')"
        />
        <Button type="submit" :label="submitLabel" :loading="submitting" />
      </div>
    </AppCard>
  </div>
</template>

<style scoped>
/* Cancel + submit pinned to the right with breathing room above so
 * the footer doesn't feel glued to the last section. */
.form-footer {
  display: flex;
  justify-content: flex-end;
  gap: 0.5rem;
  margin-top: 1.5rem;
}
</style>
