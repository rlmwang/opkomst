<script lang="ts">
import AppButton from "@/components/AppButton.svelte";
import AppCard from "@/components/AppCard.svelte";
import AppDialog from "@/components/AppDialog.svelte";
import AppHeader from "@/components/AppHeader.svelte";
import AppInput from "@/components/AppInput.svelte";
import AppSkeleton from "@/components/AppSkeleton.svelte";
import AppToggle from "@/components/AppToggle.svelte";
import MultiSelectField from "@/components/MultiSelectField.svelte";
import SearchInput from "@/components/SearchInput.svelte";
import {
  approveUser,
  demoteUser,
  promoteUser,
  removeUser,
  renameUser,
  setUserChapters,
  usersQuery,
} from "@/composables/useAdmin.svelte";
import { type Chapter, chaptersQuery, sortedChapters } from "@/composables/useChapters.svelte";
import { guarded } from "@/composables/useGuardedMutation.svelte";
import { t } from "@/i18n.svelte";
import { can } from "@/lib/permissions";
import { useToasts } from "@/lib/toasts";
import { auth } from "@/stores/auth.svelte";
import type { User } from "@/api/types";

/**
 * The accounts of an organisation: approve them, rename them, put them
 * in chapters, make them admins, remove them.
 *
 * Every button asks ``can`` first, so what is on screen matches what
 * the server would allow.
 */
const toasts = useToasts();

const canEdit = (target: User) =>
  can(auth.user, "rename_user", target) || can(auth.user, "set_user_chapters", target);
const canDelete = (target: User) =>
  can(auth.user, "delete_user", target) && target.id !== auth.user?.id;
/** The dialog's admin switch is only worth showing when the actor can
 *  move it both ways, which means an admin editing somebody else. */
const canTogglePromotion = (target: User) =>
  can(auth.user, "promote_user", target) && can(auth.user, "demote_user", target);

const query = usersQuery();
const users = $derived(query.data ?? []);
const approve = approveUser();
const setChapters = setUserChapters();
const promote = promoteUser();
const demote = demoteUser();
const remove = removeUser();
const rename = renameUser();

const askDelete = guarded(remove.run, (u: User) => ({
  vars: u.id,
  ok: t("admin.deleteUserOk", { name: u.name }),
  fail: t("admin.deleteUserFail"),
  confirm: {
    header: t("admin.deleteUserConfirmTitle"),
    message: t("admin.deleteUserConfirmBody", { name: u.name }),
    icon: "exclamation-triangle" as const,
    rejectLabel: t("common.cancel"),
    acceptLabel: t("admin.deleteUser"),
  },
}));

// Only the option pool for the dialog's picker. Chapters themselves are
// managed on their own page.
const chapters = chaptersQuery({ includeArchived: false });
const liveChapters = $derived(sortedChapters(chapters.data));

/** A user's chapters, resolved against the live rows so an upstream
 *  rename shows here too. A membership pointing at a soft-deleted
 *  chapter falls back to the name the user row carries. */
function chaptersForUser(u: User): Chapter[] {
  const live = new Map(liveChapters.map((c) => [c.id, c]));
  return u.chapters
    .map((ref) => live.get(ref.id) ?? (ref as unknown as Chapter))
    .sort((a, b) => a.name.localeCompare(b.name));
}

let search = $state("");

/* Top to bottom: the actor's own row, because it is the likeliest
 * target of anything they do here; the accounts waiting on approval,
 * because clearing those is the job; the other admins; then everyone
 * else. Newest first inside each tier, which keeps the order stable
 * across renders of the same data. */
function tier(u: User, selfId: string | null): number {
  if (u.id === selfId) return 0;
  if (!u.is_approved) return 1;
  if (u.role === "admin") return 2;
  return 3;
}

const sorted = $derived.by(() => {
  const selfId = auth.user?.id ?? null;
  return [...users].sort((a, b) => {
    const byTier = tier(a, selfId) - tier(b, selfId);
    return byTier !== 0 ? byTier : b.created_at.localeCompare(a.created_at);
  });
});

const filtered = $derived.by(() => {
  const q = search.trim().toLowerCase();
  if (!q) return sorted;
  return sorted.filter(
    (u) =>
      u.name.toLowerCase().includes(q) ||
      u.email.toLowerCase().includes(q) ||
      u.chapters.some((c) => c.name.toLowerCase().includes(q)),
  );
});

// --- The one dialog --------------------------------------------------
//
// It covers every write on this page: approving somebody, changing a
// name, changing which chapters they are in, making them an admin or
// not. The mode says which of two it is. Approve needs a chapter and
// sends the approval email; edit fires only the endpoints whose field
// actually changed.
//
// The admin switch is staged: flipping it inside the dialog changes
// nothing until Save.
type EditMode = "approve" | "edit";
let open = $state(false);
let mode = $state<EditMode>("approve");
let target = $state<User | null>(null);
let name = $state("");
// Chapter ids, not chapter rows. Held as rows, the picker matched them
// against its options by object identity, so any refetch of the chapter
// list (a window focus, a chapter renamed elsewhere) replaced those
// objects and silently emptied the field.
let picked = $state<string[]>([]);
let isAdmin = $state(false);
let submitting = $state(false);

function openApprove(u: User): void {
  mode = "approve";
  target = u;
  name = u.name;
  picked = [];
  // Approval always lands as an organiser. Making somebody an admin is
  // a separate, deliberate step.
  isAdmin = false;
  open = true;
}

function openEdit(u: User): void {
  mode = "edit";
  target = u;
  name = u.name;
  picked = u.chapters.map((c) => c.id);
  isAdmin = u.role === "admin";
  open = true;
}

function sameSet(a: string[], b: string[]): boolean {
  if (a.length !== b.length) return false;
  const sb = new Set(b);
  return a.every((x) => sb.has(x));
}

async function submit(): Promise<void> {
  if (!target) return;
  const user = target;

  const trimmed = name.trim();
  if (!trimmed) {
    toasts.warn(t("admin.userEditFillName"));
    return;
  }

  // A chapter is required when editing, because an approved organiser
  // with none is an account that can see nothing. It is optional when
  // approving: they can pick their own from the dashboard's banner.
  if (mode === "edit" && picked.length === 0) {
    toasts.warn(t("admin.userEditPickChapter"));
    return;
  }

  const wanted = picked;
  const current = user.chapters.map((c) => c.id);

  submitting = true;
  try {
    if (mode === "approve") {
      // The rename goes first so the approval email carries the
      // corrected name. Approve takes no name of its own, which keeps
      // both endpoints small and each one auditable.
      if (trimmed !== user.name) await rename.run({ userId: user.id, name: trimmed });
      await approve.run({ userId: user.id, chapterIds: wanted });
      toasts.success(t("admin.approveOk"));
    } else {
      const renamed = trimmed !== user.name;
      const chaptersChanged = !sameSet(wanted, current);
      const roleChanged = isAdmin !== (user.role === "admin");

      if (renamed) await rename.run({ userId: user.id, name: trimmed });
      if (chaptersChanged) await setChapters.run({ userId: user.id, chapterIds: wanted });
      // The role goes last, so a failure earlier cannot leave somebody
      // holding rights the rest of the save never granted them.
      if (roleChanged) {
        if (isAdmin) await promote.run(user.id);
        else await demote.run(user.id);
      }
      if (renamed || chaptersChanged || roleChanged) toasts.success(t("admin.userEditOk"));
    }
    open = false;
  } catch {
    toasts.error(mode === "approve" ? t("admin.approveFail") : t("admin.userEditFail"));
  } finally {
    submitting = false;
  }
}
</script>

<AppHeader />
<div class="container-wide stack">
  <h1>{t("admin.usersTitle")}</h1>
  <p class="muted">{t("admin.usersIntro")}</p>

  <AppCard>
    {#if query.isPending}
      <AppSkeleton rows={4} />
    {:else}
      <SearchInput bind:value={search} placeholder={t("admin.searchPlaceholder")} />
      {#if users.length === 0}
        <p class="muted">{t("admin.empty")}</p>
      {:else if filtered.length === 0}
        <p class="muted">{t("admin.noMatches")}</p>
      {/if}
      {#each filtered as u (u.id)}
        <div class="account-row">
          <div class="account-main">
            <div class="account-identity">
              <strong>{u.name}</strong>
              <span class="muted"> · {u.email}</span>
              {#if u.is_approved && u.role === "admin"}
                <span class="admin-chip">{t("admin.adminToggle")}</span>
              {/if}
            </div>
            <div class="account-actions">
              {#if !u.is_approved}
                <AppButton
                  label={t("admin.approve")}
                  size="small"
                  disabled={!can(auth.user, "approve_user")}
                  onclick={() => openApprove(u)}
                />
              {:else}
                <AppButton
                  icon="pencil"
                  size="small"
                  severity="secondary"
                  text
                  disabled={!canEdit(u)}
                  ariaLabel={t("admin.userEditDialogTitle", { name: u.name })}
                  onclick={() => openEdit(u)}
                />
              {/if}
              <AppButton
                icon="trash"
                size="small"
                severity="secondary"
                text
                disabled={!canDelete(u)}
                ariaLabel={t("admin.deleteUser")}
                onclick={() => askDelete(u)}
              />
            </div>
          </div>
          <!-- The chapter chips get their own row under the name. They
               do not wrap and the row is clipped: somebody in eight
               chapters shows the first few, and the pencil is where the
               whole set is read and changed. -->
          {#if chaptersForUser(u).length > 0}
            <div class="account-chapters">
              {#each chaptersForUser(u) as c (c.id)}
                <span class="chapter-chip">{c.name}</span>
              {/each}
            </div>
          {/if}
        </div>
      {/each}
    {/if}
  </AppCard>

  <AppDialog
    bind:visible={open}
    header={mode === "approve"
      ? t("admin.approveDialogTitle")
      : t("admin.userEditDialogTitle", { name: target?.name ?? "" })}
  >
    <p class="muted dialog-text">
      {mode === "approve"
        ? t("admin.approveDialogBody", { name: target?.name ?? "" })
        : t("admin.userEditDialogBody")}
    </p>
    <label class="reassign-label">
      {t("auth.name")}
      <AppInput
        bind:value={name}
        autocomplete="off"
        fluid
        onkeydown={(e: KeyboardEvent) => e.key === "Enter" && submit()}
      />
    </label>
    <label class="reassign-label">
      {t("admin.chaptersLabel")}
      <MultiSelectField
        bind:value={picked}
        options={liveChapters}
        optionLabel="name"
        optionValue="id"
        placeholder={t("admin.userEditPickChapter")}
        display="chip"
        filter
        fluid
      />
    </label>
    <!-- Staged: flipping this changes nothing until Save. Hidden while
         approving, because a freshly approved account is never an admin
         on the same click. Disabled on your own row, because the server
         refuses self-demotion and the switch should say so before the
         click rather than after it. -->
    {#if mode === "edit"}
      <label class="admin-toggle" class:disabled={!target || !canTogglePromotion(target)}>
        <AppToggle bind:checked={isAdmin} disabled={!target || !canTogglePromotion(target)} />
        <span>{t("admin.adminToggle")}</span>
      </label>
    {/if}
    {#snippet footer()}
      <AppButton
        label={t("common.cancel")}
        severity="secondary"
        text
        onclick={() => (open = false)}
      />
      <AppButton
        label={mode === "approve" ? t("admin.approve") : t("common.save")}
        disabled={!name.trim() || (mode === "edit" && picked.length === 0)}
        loading={submitting}
        onclick={submit}
      />
    {/snippet}
  </AppDialog>
</div>

<style>
/* On a phone the identity truncates and the actions stay pinned to the
 * right of the row. */
@media (max-width: 540px) {
  .account-actions {
    margin-left: auto;
  }
}
.account-row {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  padding: 0.5rem;
  border-radius: 6px;
  transition: background 120ms ease;
}
.account-row:hover {
  background: var(--brand-surface-100);
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
/* The row is one line that truncates, which is what the rules above
 * ask for and never got: ``.muted`` is ``white-space: pre-line``
 * globally, so the address wrapped to a second line, ran under the
 * buttons and pushed the chapter chips down. The ellipsis belongs on
 * the element that overflows, not on the flex container holding it. */
.account-identity > .muted {
  min-width: 0;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
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
.admin-chip {
  display: inline-flex;
  /* Never squeezed: a chip narrower than its word is a smear of colour
   * that says nothing. The address gives way instead. */
  flex-shrink: 0;
  align-items: center;
  padding: 0.25rem 0.625rem;
  border-radius: 999px;
  background: color-mix(in srgb, var(--brand-red), transparent 90%);
  color: var(--brand-red);
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
/* The switch dims itself; dimming the label too would stack and wash the
 * state out. */
.admin-toggle.disabled {
  cursor: default;
}
/* The default arrow, so hovering your own switch does not flash a
 * "blocked" cursor. */
.admin-toggle.disabled :global(.app-toggle) {
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
