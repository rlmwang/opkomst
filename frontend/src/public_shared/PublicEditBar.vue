<script setup lang="ts">
/**
 * The edit-mode action bar shared by every public edit page. Withdraw sits
 * bottom-left, separated from Save + Revert bottom-right. Purely
 * presentational: the page owns save/revert/withdraw and (for withdraw)
 * its own confirm text. Labels come from the shared chrome strings so all
 * four entities read identically.
 *
 * Save is disabled with nothing pending or during the transient "saved"
 * flash; Revert is disabled with nothing pending.
 */
import { computed } from "vue";
import { type Locale, chromeStrings } from "./strings";

const props = withDefaults(
  defineProps<{
    dirty: boolean;
    saving: boolean;
    justSaved: boolean;
    locale: Locale;
    /** Whether the withdraw button shows (default true). */
    canWithdraw?: boolean;
  }>(),
  { canWithdraw: true },
);

const emit = defineEmits<{
  save: [];
  revert: [];
  withdraw: [];
}>();

const c = computed(() => chromeStrings(props.locale));
</script>

<template>
  <div class="edit-bar">
    <button
      v-if="canWithdraw"
      type="button"
      class="bar-btn danger"
      :disabled="saving"
      @click="emit('withdraw')"
    >
      {{ c.withdraw }}
    </button>
    <span v-else />
    <div class="bar-right">
      <button type="button" class="bar-btn" :disabled="saving || !dirty" @click="emit('revert')">
        {{ c.revert }}
      </button>
      <button type="button" class="btn-primary" :disabled="saving || justSaved || !dirty" @click="emit('save')">
        {{ justSaved ? c.saved : c.save }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.edit-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 0.75rem;
  flex-wrap: wrap;
}
.bar-right {
  display: flex;
  gap: 0.5rem;
  margin-left: auto;
}
/* Save is the shared ``.btn-primary`` (forms.css); Revert + Withdraw are
 * low-emphasis outline buttons defined here so the bar is self-contained. */
.bar-btn {
  font: inherit;
  cursor: pointer;
  padding: 0.5rem 0.875rem;
  border: 1px solid var(--brand-border);
  border-radius: 6px;
  background: var(--brand-surface);
  color: var(--brand-text);
}
.bar-btn:disabled {
  opacity: 0.5;
  cursor: default;
}
.bar-btn.danger {
  border-color: transparent;
  background: none;
  color: var(--brand-red);
}
.bar-btn.danger:hover:not(:disabled) {
  background: color-mix(in srgb, var(--brand-red) 8%, transparent);
}
</style>
