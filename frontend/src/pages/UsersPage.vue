<script setup lang="ts">
import Button from "primevue/button";
import InputText from "primevue/inputtext";
import MultiSelect from "primevue/multiselect";
import ToggleSwitch from "primevue/toggleswitch";
import { computed, ref } from "vue";
import { useI18n } from "vue-i18n";
import AppCard from "@/components/AppCard.vue";
import AppDialog from "@/components/AppDialog.vue";
import AppHeader from "@/components/AppHeader.vue";
import AppSkeleton from "@/components/AppSkeleton.vue";
import SearchInput from "@/components/SearchInput.vue";
import {
  useApproveUser,
  useDemoteUser,
  usePromoteUser,
  useRemoveUser,
  useRenameUser,
  useSetUserChapters,
  userList,
  useUsers,
} from "@/composables/useAdmin";
import { type Chapter, chapterList, useChapters } from "@/composables/useChapters";
import { useGuardedMutation } from "@/composables/useGuardedMutation";
import { can as permCan } from "@/lib/permissions";
import { useToasts } from "@/lib/toasts";
import { type User, useAuthStore } from "@/stores/auth";

const { t } = useI18n();
const auth = useAuthStore();
const toasts = useToasts();

// Permission helpers — every UI affordance gates through these
// so the visible buttons match the matrix on the backend. The
// row-level helpers take the target ``User`` so self-service
// vs admin actions render correctly.
function canApprove(_target: User): boolean {
  return permCan(auth.user, "approve_user");
}
function canEdit(target: User): boolean {
  // Edit dialog covers rename + set-chapters; show the pencil
  // when the actor can do at least one of those.
  return (
    permCan(auth.user, "rename_user", target) ||
    permCan(auth.user, "set_user_chapters", target)
  );
}
function canDelete(target: User): boolean {
  return permCan(auth.user, "delete_user", target) && target.id !== auth.user?.id;
}
function canTogglePromotion(target: User): boolean {
  // The dialog's admin toggle is only useful when the actor can
  // both promote and demote (otherwise it's a one-way switch
  // they can't reverse). In practice that means: admin actor,
  // not editing self.
  return (
    permCan(auth.user, "promote_user", target) &&
    permCan(auth.user, "demote_user", target)
  );
}

const usersQuery = useUsers();
const users = userList(usersQuery);
const approveMutation = useApproveUser();
const setChaptersMutation = useSetUserChapters();
const promoteMutation = usePromoteUser();
const demoteMutation = useDemoteUser();
const removeMutation = useRemoveUser();
const renameMutation = useRenameUser();

const askDeleteUser = useGuardedMutation(removeMutation, (u: User) => ({
  vars: u.id,
  ok: t("admin.deleteUserOk", { name: u.name }),
  fail: t("admin.deleteUserFail"),
  confirm: {
    header: t("admin.deleteUserConfirmTitle"),
    message: t("admin.deleteUserConfirmBody", { name: u.name }),
    icon: "pi pi-exclamation-triangle",
    rejectLabel: t("common.cancel"),
    acceptLabel: t("admin.deleteUser"),
  },
}));

// Chapters list — only the option pool for the user-edit dialog's
// MultiSelect. Chapter CRUD lives on /chapters.
const chaptersQuery = useChapters({ includeArchived: false });
const chapters = chapterList(chaptersQuery);

// --- User-edit dialog -------------------------------------------------
//
// One dialog covers every user-mutating flow on this page: approve a
// pending user, change an approved user's chapter, change a user's
// display name, promote/demote admin. The mode flag distinguishes
// "approve" (chapter required, fires /approve + sends the approval
// email) from "edit" (independent rename / assign-chapter /
// promote-or-demote calls fire only for fields that actually
// changed).
//
// The admin toggle is *deferred*: flipping it inside the dialog only
// stages the change. Nothing hits the backend until "Save".
type EditMode = "approve" | "edit";
const userEditOpen = ref(false);
const userEditMode = ref<EditMode>("approve");
const userEditTarget = ref<User | null>(null);
const userEditName = ref("");
const userEditChapters = ref<Chapter[]>([]);
const userEditIsAdmin = ref(false);
const userEditSubmitting = ref(false);

function chaptersForUser(u: User): Chapter[] {
  // Resolve via the chapters store so an upstream chapter rename
  // flows in reactively. Falls back to the cached projection for
  // chapters that have since been soft-deleted (which the live
  // ``chapters.value`` doesn't include).
  const live = new Map(chapters.value.map((c) => [c.id, c]));
  return u.chapters
    .map((ref) => live.get(ref.id) ?? (ref as unknown as Chapter))
    .sort((a, b) => a.name.localeCompare(b.name));
}

// --- User search -----------------------------------------------------
const userQuery = ref("");

// Sort tiers, top to bottom:
//   0  the actor's own row — most-likely target of any action
//   1  pending approval — admin's first task is clearing these
//   2  approved admins   — quick reach for promote / contact
//   3  approved organisers — the long tail
// Within each tier we fall through to newest-first by created_at,
// which keeps row order stable across renders for the same data.
function _tier(u: User, selfId: string | null): number {
  if (u.id === selfId) return 0;
  if (!u.is_approved) return 1;
  if (u.role === "admin") return 2;
  return 3;
}

const sortedUsers = computed(() => {
  const selfId = auth.user?.id ?? null;
  return [...users.value].sort((a, b) => {
    const tierDiff = _tier(a, selfId) - _tier(b, selfId);
    if (tierDiff !== 0) return tierDiff;
    return b.created_at.localeCompare(a.created_at);
  });
});

const filteredUsers = computed(() => {
  const q = userQuery.value.trim().toLowerCase();
  if (!q) return sortedUsers.value;
  return sortedUsers.value.filter((u) => {
    const chapterMatch = u.chapters.some((c) => c.name.toLowerCase().includes(q));
    return (
      u.name.toLowerCase().includes(q) ||
      u.email.toLowerCase().includes(q) ||
      chapterMatch
    );
  });
});

const loaded = computed(() => !usersQuery.isLoading.value);

function openApprove(u: User) {
  userEditMode.value = "approve";
  userEditTarget.value = u;
  userEditName.value = u.name;
  userEditChapters.value = [];
  // Approve always lands as a non-admin organiser; admin promotion
  // is a separate, post-approval action.
  userEditIsAdmin.value = false;
  userEditOpen.value = true;
}

function openEdit(u: User) {
  userEditMode.value = "edit";
  userEditTarget.value = u;
  userEditName.value = u.name;
  // Resolve to live ``Chapter`` rows from the chapters store so
  // the MultiSelect's selected-chip names update reactively when
  // an upstream chapter rename lands.
  const liveByRef = new Map(chapters.value.map((c) => [c.id, c]));
  userEditChapters.value = u.chapters
    .map((ref) => liveByRef.get(ref.id))
    .filter((c): c is Chapter => c !== undefined);
  userEditIsAdmin.value = u.role === "admin";
  userEditOpen.value = true;
}

function _setEquals(a: string[], b: string[]): boolean {
  if (a.length !== b.length) return false;
  const sb = new Set(b);
  return a.every((x) => sb.has(x));
}

async function submitUserEdit() {
  const target = userEditTarget.value;
  if (!target) return;

  const trimmedName = userEditName.value.trim();
  if (!trimmedName) {
    toasts.warn(t("admin.userEditFillName"));
    return;
  }

  // Chapters are required for *edit* mode (an approved user
  // shouldn't be able to clear themselves out of every
  // chapter), but optional in *approve* mode — the user can
  // self-pick via the dashboard's onboarding banner once they're
  // logged in.
  if (userEditMode.value === "edit" && userEditChapters.value.length === 0) {
    toasts.warn(t("admin.userEditPickChapter"));
    return;
  }

  const desiredChapterIds = userEditChapters.value.map((c) => c.id);
  const currentChapterIds = target.chapters.map((c) => c.id);

  userEditSubmitting.value = true;
  try {
    if (userEditMode.value === "approve") {
      // Rename first so the approval email carries the corrected
      // name. /approve doesn't accept a name field — keeping the
      // endpoints orthogonal means each one stays small + auditable.
      if (trimmedName !== target.name) {
        await renameMutation.mutateAsync({ userId: target.id, name: trimmedName });
      }
      await approveMutation.mutateAsync({
        userId: target.id,
        chapterIds: desiredChapterIds,
      });
      toasts.success(t("admin.approveOk"));
    } else {
      // Edit mode — fire only the endpoints whose field actually
      // changed. Three no-op clicks (open + Save with nothing
      // edited) close the dialog without a single round-trip.
      const renamed = trimmedName !== target.name;
      const chaptersChanged = !_setEquals(desiredChapterIds, currentChapterIds);
      const wasAdmin = target.role === "admin";
      const roleChanged = userEditIsAdmin.value !== wasAdmin;

      if (renamed) {
        await renameMutation.mutateAsync({ userId: target.id, name: trimmedName });
      }
      if (chaptersChanged) {
        await setChaptersMutation.mutateAsync({
          userId: target.id,
          chapterIds: desiredChapterIds,
        });
      }
      // Promote/demote last so a partial failure earlier doesn't
      // leave a user with elevated privileges they wouldn't have
      // had otherwise.
      if (roleChanged) {
        if (userEditIsAdmin.value) {
          await promoteMutation.mutateAsync(target.id);
        } else {
          await demoteMutation.mutateAsync(target.id);
        }
      }
      if (renamed || chaptersChanged || roleChanged) {
        toasts.success(t("admin.userEditOk"));
      }
    }
    userEditOpen.value = false;
  } catch {
    toasts.error(
      userEditMode.value === "approve"
        ? t("admin.approveFail")
        : t("admin.userEditFail"),
    );
  } finally {
    userEditSubmitting.value = false;
  }
}
</script>

<template>
  <AppHeader />
  <div class="container stack">
    <h1>{{ t("admin.usersTitle") }}</h1>
    <p class="muted">{{ t("admin.usersIntro") }}</p>

    <AppCard>
      <AppSkeleton v-if="!loaded" :rows="4" />
      <template v-else>
        <SearchInput
          v-model="userQuery"
          :placeholder="t('admin.searchPlaceholder')"
        />
        <div v-if="users.length === 0">
          <p class="muted">{{ t("admin.empty") }}</p>
        </div>
        <p v-else-if="filteredUsers.length === 0" class="muted">
          {{ t("admin.noMatches") }}
        </p>
        <div v-for="u in filteredUsers" :key="u.id" class="account-row">
        <div class="account-main">
          <div class="account-identity">
            <strong>{{ u.name }}</strong>
            <span class="muted"> · {{ u.email }}</span>
            <span v-if="u.is_approved && u.role === 'admin'" class="admin-chip">{{ t("admin.adminToggle") }}</span>
          </div>
          <div class="account-actions">
            <Button
              v-if="!u.is_approved"
              :label="t('admin.approve')"
              size="small"
              :disabled="!canApprove(u)"
              @click="openApprove(u)"
            />
            <Button
              v-if="u.is_approved"
              icon="pi pi-pencil"
              size="small"
              severity="secondary"
              text
              :disabled="!canEdit(u)"
              :aria-label="t('admin.userEditDialogTitle', { name: u.name })"
              @click="openEdit(u)"
            />
            <Button
              icon="pi pi-trash"
              size="small"
              severity="secondary"
              text
              :disabled="!canDelete(u)"
              :aria-label="t('admin.deleteUser')"
              @click="askDeleteUser(u)"
            />
          </div>
        </div>
        <!-- Chapter chips on their own row beneath the
             identity. Wrapping is intentionally disabled and
             overflow is hidden; many-chapter members get the
             first few chips fully rendered with the row clipped
             at the right edge. The pencil-icon dialog is where
             you go to see the full set + edit. -->
        <div v-if="chaptersForUser(u).length > 0" class="account-chapters">
          <span
            v-for="c in chaptersForUser(u)"
            :key="c.id"
            class="chapter-chip"
          >{{ c.name }}</span>
        </div>
      </div>
      </template>
    </AppCard>

    <AppDialog
      v-model:visible="userEditOpen"
      :header="userEditMode === 'approve'
        ? t('admin.approveDialogTitle')
        : t('admin.userEditDialogTitle', { name: userEditTarget?.name ?? '' })"
    >
      <p class="muted dialog-text">
        {{
          userEditMode === "approve"
            ? t("admin.approveDialogBody", { name: userEditTarget?.name ?? "" })
            : t("admin.userEditDialogBody")
        }}
      </p>
      <label class="reassign-label">
        {{ t("auth.name") }}
        <InputText
          v-model="userEditName"
          autocomplete="off"
          fluid
          @keydown.enter="submitUserEdit"
        />
      </label>
      <label class="reassign-label">
        {{ t("admin.chaptersLabel") }}
        <MultiSelect
          v-model="userEditChapters"
          :options="chapters"
          option-label="name"
          :placeholder="t('admin.userEditPickChapter')"
          display="chip"
          filter
          fluid
        />
      </label>
      <!-- Admin toggle is deferred: flipping it stages a change
           that only commits when "Save" is clicked. Hidden in
           approve mode (a freshly approved user is never an admin
           on the same click; promotion is a separate, explicit
           step). Disabled when editing your own row — the server
           rejects self-demotion, and we want the UI to surface
           that constraint up front rather than 409 on submit. -->
      <label
        v-if="userEditMode === 'edit'"
        class="admin-toggle"
        :class="{ disabled: !userEditTarget || !canTogglePromotion(userEditTarget) }"
      >
        <ToggleSwitch
          v-model="userEditIsAdmin"
          :disabled="!userEditTarget || !canTogglePromotion(userEditTarget)"
        />
        <span>{{ t("admin.adminToggle") }}</span>
      </label>
      <template #footer>
        <Button :label="t('common.cancel')" severity="secondary" text @click="userEditOpen = false" />
        <Button
          :label="userEditMode === 'approve' ? t('admin.approve') : t('common.save')"
          :disabled="
            !userEditName.trim() ||
            (userEditMode === 'edit' && userEditChapters.length === 0)
          "
          :loading="userEditSubmitting"
          @click="submitUserEdit"
        />
      </template>
    </AppDialog>
  </div>
</template>

<style scoped>
/* Mobile: the account-main row stays as identity-then-actions
 * (with chips below); the actions cluster aligns to the end of
 * the available width and the identity truncates if needed. */
@media (max-width: 540px) {
  .account-actions {
    margin-left: auto;
  }
}
/* Two-row account card: identity + admin chip + actions on the
 * top row, chapter chips clipped on a second row beneath. */
.account-row {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  padding: 0.5rem 0.5rem;
  border-radius: 6px;
  transition: background 120ms ease;
}
.account-row:hover {
  background: var(--brand-surface-subtle, rgba(0, 0, 0, 0.03));
}
.account-main {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  min-width: 0;
}
.account-identity {
  display: flex;
  align-items: baseline;
  gap: 0.5rem;
  min-width: 0;
  flex: 1;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}
.account-identity > strong {
  flex-shrink: 0;
}
.account-actions {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-shrink: 0;
}
.account-chapters {
  display: flex;
  flex-wrap: nowrap;
  gap: 0.375rem;
  overflow: hidden;
  white-space: nowrap;
  mask-image: linear-gradient(to right, black 85%, transparent 100%);
  -webkit-mask-image: linear-gradient(to right, black 85%, transparent 100%);
}
.account-chapters .chapter-chip {
  flex-shrink: 0;
}
.chapter-chip {
  display: inline-flex;
  align-items: center;
  padding: 0.25rem 0.625rem;
  border-radius: 999px;
  background: var(--brand-surface-subtle, rgba(0, 0, 0, 0.05));
  color: var(--brand-text-muted);
  font-size: 0.875rem;
  white-space: nowrap;
}
.admin-chip {
  display: inline-flex;
  align-items: center;
  padding: 0.25rem 0.625rem;
  border-radius: 999px;
  background: var(--brand-accent-subtle, rgba(159, 0, 11, 0.1));
  color: var(--brand-accent, #9f000b);
  font-size: 0.875rem;
  font-weight: 600;
  white-space: nowrap;
}
.admin-toggle {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  font-size: 0.875rem;
  color: var(--brand-text-muted);
  cursor: pointer;
}
.admin-toggle.disabled {
  cursor: default;
  opacity: 0.65;
}
/* PrimeVue's disabled ToggleSwitch defaults to ``not-allowed``; force
 * the default arrow so hovering the user's own self-toggle doesn't
 * flash a "blocked" cursor. */
.admin-toggle.disabled :deep(.p-toggleswitch) {
  cursor: default;
}
.dialog-text {
  margin: 0;
}
.reassign-label {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
  font-size: 0.875rem;
  color: var(--brand-text);
}
</style>
