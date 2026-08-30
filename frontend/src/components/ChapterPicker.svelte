<script lang="ts" module>
import type { Chapter } from "@/api/types";
export type { Chapter };
</script>

<script lang="ts">
import AutoCompleteField, {
  type AutoCompleteCompleteEvent,
  type AutoCompleteOptionSelectEvent,
} from "@/components/AutoCompleteField.svelte";
import AppIcon, { type IconName } from "@/components/AppIcon.svelte";
import { t } from "@/i18n.svelte";
import { chaptersQuery } from "@/composables/useChapters.svelte";

const {
  archivedOnly,
  placeholder,
  disabled,
  leadingIcon,
  onpick,
  oncreate,
}: {
  /** When true, the picker ONLY surfaces archived suggestions: active
   *  chapters are filtered out. The add-bar on the admin page uses this
   *  so typing an existing active name doesn't pop a "no-op"
   *  suggestion; it falls through to create, and the backend's dupe
   *  check rejects with 409. */
  archivedOnly?: boolean;
  placeholder?: string;
  /** Render the input non-interactive. Used on the Chapters page for
   *  non-admin actors: they see the picker for affordance consistency
   *  but can't trigger the create or restore branches. */
  disabled?: boolean;
  /** An ``AppIcon`` name. When set, the input carries that icon on its
   *  left, the way ``SearchInput`` does. */
  leadingIcon?: IconName;
  /** Picked an existing chapter, active or archived. The caller
   *  decides: usually a no-op for an active pick, a restore for an
   *  archived one. */
  onpick: (value: Chapter) => void;
  /** Typed text that matches no existing chapter, then Enter. The
   *  caller should create one with this name. */
  oncreate: (name: string) => void;
} = $props();

let suggestions = $state<Chapter[]>([]);
// The field sets its bound value to the option object on select and to
// the typed string until then. That distinction is the whole mechanism:
// a string at Enter time means no match was picked, so treat it as a
// create.
let local = $state<Chapter | string | null>(null);

// The chapters to match against, archived ones included so a typed name
// can resolve to a pick-to-restore. Shared with the page through the
// normal query cache: the picker used to fetch the whole list on every
// keystroke, which asked the server nine times to type "Amsterdam" and
// threw away eight of the answers. The matching was always local
// anyway. Creating, renaming, archiving and restoring all invalidate
// ``["chapters"]``, so the suggestions follow the page.
const chapters = chaptersQuery({ includeArchived: true });

function onComplete(e: AutoCompleteCompleteEvent) {
  const list = chapters.data ?? [];
  const q = e.query.trim().toLowerCase();
  const matched = q ? list.filter((a) => a.name.toLowerCase().includes(q)) : list;
  suggestions = archivedOnly ? matched.filter((a) => a.archived) : matched;
}

function onSelect(e: AutoCompleteOptionSelectEvent) {
  onpick(e.value as Chapter);
  local = null;
}

function onKeyup(event: KeyboardEvent) {
  if (event.key !== "Enter") return;
  if (typeof local === "string" && local.trim()) {
    oncreate(local.trim());
    local = null;
  }
}
</script>

{#snippet field()}
  <AutoCompleteField
    bind:value={local}
    {suggestions}
    optionLabel="name"
    placeholder={placeholder ?? t("chapters.pickerPlaceholder")}
    delay={200}
    {disabled}
    fluid
    oncomplete={onComplete}
    onoptionSelect={onSelect}
    onkeyup={onKeyup}
  >
    {#snippet optionSnippet({ option })}
      <div class="option" class:archived={(option as Chapter).archived}>
        <span>{(option as Chapter).name}</span>
        {#if (option as Chapter).archived}
          <span class="tag">{t("chapters.archivedTag")}</span>
        {/if}
      </div>
    {/snippet}
  </AutoCompleteField>
{/snippet}

{#if leadingIcon}
  <div class="icon-field">
    <AppIcon name={leadingIcon} class="field-icon" />
    {@render field()}
  </div>
{:else}
  {@render field()}
{/if}

<style>
/* The leading icon inside the field. PrimeVue's IconField was a
 * wrapper, an absolutely-positioned icon and padding on the input;
 * written here rather than imported. */
.icon-field {
  position: relative;
  display: block;
}
.icon-field :global(.app-icon) {
  position: absolute;
  top: 50%;
  inset-inline-start: 0.75rem;
  margin-top: -0.5rem;
  color: var(--brand-text-muted);
  z-index: 1;
}
/* Twice the field's own inline padding, plus the icon. */
.icon-field :global(.ac-input) {
  padding-inline-start: 2.5rem;
}
:global(.option) {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
  gap: 0.75rem;
}
:global(.option.archived span:first-child) {
  color: var(--brand-text-muted);
  font-style: italic;
}
:global(.tag) {
  font-size: 0.75rem;
  color: var(--brand-red);
  background: var(--brand-red-soft);
  padding: 0.125rem 0.5rem;
  border-radius: 999px;
}
</style>
