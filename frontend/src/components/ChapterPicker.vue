<script setup lang="ts">
import AutoCompleteField, {
  type AutoCompleteCompleteEvent,
  type AutoCompleteOptionSelectEvent,
} from "@/components/AutoCompleteField.vue";
import { ref } from "vue";
import { useI18n } from "vue-i18n";
import type { Chapter } from "@/api/types";
import { get } from "@/api/client";
import AppIcon, { type IconName } from "@/components/AppIcon.vue";

export type { Chapter };

const props = defineProps<{
  /** When true, archived chapters surface in suggestions tagged
   * "restore?" so the caller can decide what to do with a pick. */
  showArchived?: boolean;
  /** When true, the picker ONLY surfaces archived suggestions —
   * active chapters are filtered out. The add-bar on the admin page
   * uses this so typing an existing active name doesn't pop a "no-op"
   * suggestion; it falls through to create (the backend's dupe check
   * rejects with 409). */
  archivedOnly?: boolean;
  placeholder?: string;
  /** Render the input non-interactive. Used on the Chapters
   * page for non-admin actors — they see the picker for
   * affordance consistency but can't actually trigger the
   * create / restore branches. */
  disabled?: boolean;
  /** An ``AppIcon`` name. When set, the input carries that icon on
   * its left, the way ``SearchInput`` does. */
  leadingIcon?: IconName;
}>();

const emit = defineEmits<{
  /** User picked an existing chapter (active or archived). The
   * caller decides what to do — for active picks usually a no-op,
   * for archived a restore. */
  pick: [value: Chapter];
  /** User typed text that doesn't match an existing chapter and
   * pressed Enter — caller should create a new one with this name. */
  create: [name: string];
}>();

const { t } = useI18n();

const suggestions = ref<Chapter[]>([]);
// AutoComplete sets the bound value to the option object on select
// and to the typed string until then. We exploit that distinction:
// string at Enter-time means "no match was picked, treat as create".
const local = ref<Chapter | string | null>(null);

async function onComplete(e: AutoCompleteCompleteEvent) {
  // Direct fetch: the picker is its own little island and shouldn't
  // share cache with the page-level chapter list (the picker always
  // wants archived results so the user can pick-to-restore; the
  // page list usually doesn't).
  const list = await get<Chapter[]>("/api/v1/chapters?include_archived=true");
  const q = e.query.trim().toLowerCase();
  const matched = q ? list.filter((a) => a.name.toLowerCase().includes(q)) : list;
  suggestions.value = props.archivedOnly ? matched.filter((a) => a.archived) : matched;
}

function onSelect(e: AutoCompleteOptionSelectEvent) {
  emit("pick", e.value as Chapter);
  local.value = null;
}

function onEnter() {
  if (typeof local.value === "string" && local.value.trim()) {
    emit("create", local.value.trim());
    local.value = null;
  }
}
</script>

<template>
  <div v-if="leadingIcon" class="icon-field">
    <AppIcon :name="leadingIcon" class="field-icon" />
    <AutoCompleteField
      v-model="local"
      :suggestions="suggestions"
      option-label="name"
      :placeholder="placeholder ?? t('chapters.pickerPlaceholder')"
      :delay="200"
      :disabled="props.disabled"
      fluid
      @complete="onComplete"
      @option-select="onSelect"
      @keyup.enter="onEnter"
    >
      <template #option="{ option }">
        <div class="option" :class="{ archived: (option as Chapter).archived }">
          <span>{{ (option as Chapter).name }}</span>
          <span v-if="(option as Chapter).archived" class="tag">{{ t("chapters.archivedTag") }}</span>
        </div>
      </template>
    </AutoCompleteField>
  </div>
  <AutoCompleteField
    v-else
    v-model="local"
    :suggestions="suggestions"
    option-label="name"
    :placeholder="placeholder ?? t('chapters.pickerPlaceholder')"
    :delay="200"
    :disabled="props.disabled"
    fluid
    @complete="onComplete"
    @option-select="onSelect"
    @keyup.enter="onEnter"
  >
    <template #option="{ option }">
      <div class="option" :class="{ archived: (option as Chapter).archived }">
        <span>{{ (option as Chapter).name }}</span>
        <span v-if="(option as Chapter).archived" class="tag">{{ t("chapters.archivedTag") }}</span>
      </div>
    </template>
  </AutoCompleteField>
</template>

<style scoped>
/* The leading icon inside the field. PrimeVue's IconField was a
 * wrapper, an absolutely-positioned icon and padding on the input;
 * written here rather than imported. */
.icon-field {
  position: relative;
  display: block;
}
.field-icon {
  position: absolute;
  top: 50%;
  inset-inline-start: 0.75rem;
  margin-top: -0.5rem;
  color: var(--brand-text-muted);
  z-index: 1;
}
/* Twice the field's own inline padding, plus the icon. */
.icon-field :deep(.ac-input) {
  padding-inline-start: 2.5rem;
}
.option {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
  gap: 0.75rem;
}
.option.archived span:first-child {
  color: var(--brand-text-muted);
  font-style: italic;
}
.tag {
  font-size: 0.75rem;
  color: var(--brand-red);
  background: var(--brand-red-soft);
  padding: 0.125rem 0.5rem;
  border-radius: 999px;
}
</style>
