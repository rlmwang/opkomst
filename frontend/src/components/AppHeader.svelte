<script lang="ts">
import AppPopover from "@/components/AppPopover.svelte";
import AppIcon from "@/components/AppIcon.svelte";
import BrandMark from "@/public_shared/BrandMark.svelte";
import LanguageSwitcher from "@/components/LanguageSwitcher.svelte";
import RouterLink from "@/router/RouterLink.svelte";
import { t } from "@/i18n.svelte";
import { APP_NAME } from "@/lib/branding";
import { pendingCountQuery } from "@/composables/useAdmin.svelte";
import { auth, logout } from "@/stores/auth.svelte";
import { go, route } from "@/router/navigation.svelte";

// Pending-approval indicator — fired only when the actor is an
// admin (organisers don't get the badge and shouldn't pay the
// network round-trip). The query auto-refetches on the
// staleTime cadence so a new sign-up shows up within ~30s on
// any open admin tab.
const pendingQuery = pendingCountQuery(() => auth.isAdmin && !auth.isPersonal);
const pendingCount = $derived(pendingQuery.data?.count ?? 0);
const showPendingBadge = $derived(auth.isAdmin && pendingCount > 0);

// Every top-level destination lives in one dropdown. Each item
// knows how to recognise its own subtree (so e.g. ``/event/new``
// still reads as Evenementen), which is what lets the trigger
// double as a "you are here" label.
interface MenuItem {
  key: string;
  to: string;
  label: string;
  isActive: (path: string) => boolean;
  badge?: number;
}

// Group one: the content workspaces. All five are approval-gated, so an
// account still waiting on an admin is offered none of them; its menu is
// the sign-out and nothing else.
//
// Same order as the tiles on the landing page (``PersonalIndexPage``):
// somebody meets these in the order they organise something, and a menu
// that disagrees with the front page about the order is a menu you have
// to read rather than know.
const workspaceItems = $derived.by<MenuItem[]>(() => {
  if (!auth.isApproved) return [];
  return [
    {
      key: "events",
      to: "/event",
      label: t("header.events"),
      isActive: (p) => p === "/event" || p.startsWith("/event/"),
    },
    {
      key: "datepolls",
      to: "/datepoll",
      label: t("header.datepolls"),
      isActive: (p) => p === "/datepoll" || p.startsWith("/datepoll/"),
    },
    {
      key: "chores",
      to: "/chore",
      label: t("header.chores"),
      isActive: (p) => p === "/chore" || p.startsWith("/chore/"),
    },
    {
      key: "forms",
      to: "/form",
      label: t("header.forms"),
      isActive: (p) => p === "/form" || p.startsWith("/form/"),
    },
    {
      key: "quizzes",
      to: "/quiz",
      label: t("header.quizzes"),
      isActive: (p) => p === "/quiz" || p.startsWith("/quiz/"),
    },
    {
      key: "compasses",
      to: "/compass",
      label: t("header.compasses"),
      isActive: (p) => p === "/compass" || p.startsWith("/compass/"),
    },
  ];
});

// Group two: the organisation-management destinations. Separated
// from the workspaces by a rule in the menu — they act on the
// tool itself rather than on a chapter's programme.
// A personal account has no second group: nobody to approve, no
// chapters to sort them into, and no WhatsApp blast. The menu then
// holds the workspaces and the sign-out, which is all of it.
const adminItems = $derived.by<MenuItem[]>(() => {
  const items: MenuItem[] = [];
  if (auth.isPersonal) return items;
  if (auth.isApproved) {
    items.push({
      key: "admin",
      to: "/users",
      label: t("header.admin"),
      isActive: (p) => p === "/users" || p === "/chapters" || p === "/settings",
      badge: showPendingBadge ? pendingCount : undefined,
    });
  }
  if (auth.isAdmin && auth.whatsappAvailable) {
    items.push({
      key: "whatsapp",
      to: "/admin/whatsapp",
      label: t("header.whatsapp"),
      isActive: (p) => p === "/admin/whatsapp",
    });
  }
  return items;
});

// Whichever destination the current route belongs to. Drives the
// trigger label, so the collapsed nav still answers "where am I".
const activeItem = $derived(
  [...workspaceItems, ...adminItems].find((i) => i.isActive(route.path)) ?? null,
);
const triggerLabel = $derived(activeItem?.label ?? t("header.menu"));

let navMenu = $state<AppPopover>();
let navMenuOpen = $state(false);
function toggleNavMenu(event: Event) {
  navMenu?.toggle(event);
}
function navigate(to: string) {
  navMenu?.hide();
  void go(to);
}
async function signOut() {
  navMenu?.hide();
  await logout();
  void go("/");
}

// Subtabs derived from the current route. Empty array on routes
// that don't sit under one of the parents with subtabs (Lid-
// feedback, WhatsApp, /event/new, /event/:id/edit, /form/new,
// etc.) — the subtab pair distinguishes only the two list views,
// so hiding it on detail/edit routes keeps the navigation honest.
interface Subtab {
  to: string;
  label: string;
  badge?: number;
}
const subtabs = $derived.by<Subtab[]>(() => {
  const p = route.path;
  if (p === "/event" || p === "/event/archived") {
    return [
      { to: "/event", label: t("header.active") },
      { to: "/event/archived", label: t("header.archive") },
    ];
  }
  if (p === "/form" || p === "/form/archived") {
    return [
      { to: "/form", label: t("header.active") },
      { to: "/form/archived", label: t("header.archive") },
    ];
  }
  if (p === "/datepoll" || p === "/datepoll/archived") {
    return [
      { to: "/datepoll", label: t("header.active") },
      { to: "/datepoll/archived", label: t("header.archive") },
    ];
  }
  if (p === "/chore" || p === "/chore/archived") {
    return [
      { to: "/chore", label: t("header.active") },
      { to: "/chore/archived", label: t("header.archive") },
    ];
  }
  if (p === "/users" || p === "/chapters" || p === "/settings") {
    return [
      {
        to: "/users",
        label: t("header.users"),
        badge: showPendingBadge ? pendingCount : undefined,
      },
      { to: "/chapters", label: t("header.chapters") },
      { to: "/settings", label: t("header.settings") },
    ];
  }
  return [];
});
const hasSubtabs = $derived(subtabs.length > 0);
</script>

<header class="app-bar">
  <div class="app-header" class:has-subtabs={hasSubtabs}>
    <BrandMark class="brand">
      {#snippet wordmark()}
        <RouterLink to="/" class="wordmark">{APP_NAME}</RouterLink>
      {/snippet}
    </BrandMark>

    <!-- Second-level, route-contextual navigation. Its own grid area,
         so on phones it drops to a full-width row of its own instead of
         competing with the brand and the menu. -->
    {#if hasSubtabs}
      <nav class="subtabs" aria-label={t("header.subnavLabel")}>
        {#each subtabs as s (s.to)}
          <RouterLink to={s.to} class="subtab">
            {s.label}
            {#if s.badge}
              <span class="pending-badge" aria-label={t("header.pendingBadgeLabel", { n: s.badge })}>
                {s.badge}
              </span>
            {/if}
          </RouterLink>
        {/each}
        <span class="group-divider" aria-hidden="true"></span>
      </nav>
    {/if}

    <!-- Exactly two controls, at every width: the nav menu, then
         language at the far right. Language is the last thing in the row
         on every surface, public pages included, so it sits in the same
         place whichever part of the app someone is in. Fixed and compact
         enough that this cluster never wraps. -->
    <div class="actions">
      {#if auth.isAuthenticated}
        <button
          type="button"
          class="menu-trigger"
          class:open={navMenuOpen}
          aria-haspopup="true"
          aria-expanded={navMenuOpen}
          aria-label={t("header.menuAria", { section: triggerLabel })}
          onclick={toggleNavMenu}
        >
          <AppIcon name="bars" class="trigger-icon" />
          <span class="trigger-label">{triggerLabel}</span>
          <AppIcon name="chevron-down" class="trigger-chevron" />
          {#if showPendingBadge}
            <span
              class="trigger-dot"
              aria-label={t("header.pendingBadgeLabel", { n: pendingCount })}
            ></span>
          {/if}
        </button>
        <AppPopover
          bind:this={navMenu}
          onshow={() => (navMenuOpen = true)}
          onhide={() => (navMenuOpen = false)}
        >
          <div class="nav-menu">
            {#each workspaceItems as item (item.key)}
              <button
                type="button"
                class="menu-item"
                class:active={item.isActive(route.path)}
                onclick={() => navigate(item.to)}
              >{item.label}</button>
            {/each}
            {#if adminItems.length}
              <span class="menu-rule" aria-hidden="true"></span>
            {/if}
            {#each adminItems as item (item.key)}
              <button
                type="button"
                class="menu-item"
                class:active={item.isActive(route.path)}
                onclick={() => navigate(item.to)}
              >
                {item.label}
                {#if item.badge}
                  <span
                    class="pending-badge"
                    aria-label={t("header.pendingBadgeLabel", { n: item.badge })}
                  >{item.badge}</span>
                {/if}
              </button>
            {/each}
            <span class="menu-rule" aria-hidden="true"></span>
            <button type="button" class="menu-item menu-item-logout" onclick={signOut}>
              <AppIcon name="sign-out" />
              {t("header.logout")}
            </button>
          </div>
        </AppPopover>
      {/if}
      <LanguageSwitcher />
    </div>
  </div>
</header>

<style>
/* Grid, not ``flex-wrap``. Wrapping used to be the no-overflow
 * guarantee, but it let the browser pick the break point: on a
 * phone the subtabs, the section tabs and the logout button
 * landed on whichever row they happened to fit. Three named
 * areas make the break an explicit decision instead —
 *
 *   ≥721px   brand · · · · · subtabs | [lang] [menu]
 *   ≤720px   brand · · · · · · · · · · [lang] [menu]
 *            subtabs
 *
 * The brand column is ``auto`` and the middle is ``1fr``, so the
 * actions cluster is pinned to the right edge whether or not
 * subtabs exist. */
/* The bar spans the window; its contents do not. Every organiser page
 * below is a centred 720px ``.container``, so a full-bleed header put
 * the logo and the menu at the far edges of the screen, which is where
 * the ad rails are. Matching the column keeps the eye inside the
 * content and never sends it out to the margins. Horizontal padding
 * and width match ``.container-wide``'s so the logo lines up with the
 * cards below — the app's pages are all one column now. */
.app-bar {
  border-bottom: 1px solid var(--brand-border);
  background: var(--brand-surface);
}
.app-header {
  display: grid;
  grid-template-areas: "brand subtabs actions";
  grid-template-columns: auto 1fr auto;
  align-items: center;
  column-gap: 1rem;
  max-width: 1120px;
  margin: 0 auto;
  padding: 0.75rem 1rem;
}
:global(.brand) {
  grid-area: brand;
  min-width: 0;
}
.subtabs {
  grid-area: subtabs;
  justify-self: end;
  display: flex;
  align-items: center;
  gap: 1rem;
}
.actions {
  grid-area: actions;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

:global(.subtab) {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  color: var(--brand-text);
  text-decoration: none;
  white-space: nowrap;
}
/* Subtabs use router-link's built-in active class — each has
 * exactly one matching path. */
:global(.subtab.router-link-active) {
  color: var(--brand-red);
  font-weight: 600;
}
/* Vertical separator between the contextual subtabs and the
 * actions cluster. Only meaningful while the two share a row. */
.group-divider {
  width: 1px;
  height: 1.5rem;
  background: var(--brand-border);
}

/* The single nav control. Deliberately styled as a pill matching
 * the language switcher next to it, so the actions cluster reads
 * as one pair of controls rather than a run of loose links. The
 * label is the section the user is currently in, which is what
 * pays for collapsing the tabs. */
.menu-trigger {
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  min-height: 2.25rem;
  padding: 0 0.75rem;
  border: 1px solid var(--brand-border);
  border-radius: 999px;
  background: var(--brand-surface);
  color: var(--brand-text);
  font: inherit;
  font-size: 0.9375rem;
  font-weight: 600;
  line-height: 1;
  white-space: nowrap;
  cursor: pointer;
  transition: border-color 120ms ease, background 120ms ease;
}
.menu-trigger:hover,
.menu-trigger.open {
  border-color: var(--brand-red);
  background: var(--brand-bg);
}
/* The hamburger only appears once the label is dropped (≤480px). */
:global(.trigger-icon) {
  display: none;
}
:global(.trigger-chevron) {
  font-size: 0.75rem;
  color: var(--brand-text-muted);
  transition: transform 150ms ease;
}
.menu-trigger[aria-expanded="true"] :global(.trigger-chevron) {
  transform: rotate(180deg);
}
/* Pending approvals are two clicks away now that Admin lives in
 * the menu, so the trigger carries a dot to surface them from
 * any page. The exact count is on the Admin menu item. */
.trigger-dot {
  position: absolute;
  top: -2px;
  right: -2px;
  width: 0.5rem;
  height: 0.5rem;
  border-radius: 999px;
  background: var(--brand-red);
  box-shadow: 0 0 0 2px var(--brand-surface);
}

.nav-menu {
  display: flex;
  flex-direction: column;
  min-width: 12rem;
}
.menu-item {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  text-align: left;
  background: none;
  border: none;
  padding: 0.5rem 0.75rem;
  border-radius: 0.375rem;
  font: inherit;
  cursor: pointer;
  color: var(--brand-text);
}
.menu-item:hover {
  background: var(--brand-bg);
}
.menu-item.active {
  color: var(--brand-red);
  font-weight: 600;
}
.menu-item-logout {
  color: var(--brand-text-muted);
}
/* Horizontal rule between the menu's three groups — workspaces,
 * organisation admin, session. Grouping is what keeps a
 * six-entry dropdown scannable. */
.menu-rule {
  height: 1px;
  margin: 0.375rem 0.25rem;
  background: var(--brand-border);
}

/* Brand-red pill carrying the pending-approval count. Sized to
 * fit a 1- or 2-digit number; for ≥10 the pill expands rather
 * than the digits getting clipped. ``min-width`` matches the
 * height so a single-digit count renders as a circle. */
.pending-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 1.25rem;
  height: 1.25rem;
  padding: 0 0.375rem;
  border-radius: 999px;
  background: var(--brand-red);
  color: #ffffff;
  font-size: 0.75rem;
  font-weight: 700;
  line-height: 1;
}
.menu-item .pending-badge {
  margin-left: auto;
}

/* ≤720px — the row can no longer hold brand + subtabs + actions.
 * The subtabs get their own full-width row under the bar, which
 * also fixes a hierarchy inversion: the contextual tabs used to
 * sit to the LEFT of the parent nav they belong to. The header
 * only grows a second row on routes that actually have subtabs,
 * hence ``.has-subtabs`` rather than an always-present empty
 * grid track (an empty track still pays the row gap). */
@media (max-width: 720px) {
  .app-header {
    grid-template-areas: "brand actions";
    grid-template-columns: 1fr auto;
    row-gap: 0.5rem;
    padding: 0.625rem 0.75rem;
  }
  .app-header.has-subtabs {
    grid-template-areas:
      "brand actions"
      "subtabs subtabs";
  }
  .subtabs {
    justify-self: start;
    /* Two entries never need to scroll; the rule is here so a
     * future third one degrades to a swipe instead of a wrap. */
    overflow-x: auto;
    max-width: 100%;
    scrollbar-width: none;
  }
  .subtabs::-webkit-scrollbar {
    display: none;
  }
  /* Shares its row with the actions cluster now, not the
   * subtabs. */
  .group-divider {
    display: none;
  }
  /* 60px of logo is desktop sizing; on a phone that width is
   * needed by the nav. Three selectors deep to outrank
   * BrandMark's own scoped rule regardless of bundle order. */
  .app-header :global(.brand .party-logo) {
    height: 40px;
    width: 40px;
  }
  .app-header :global(.brand .wordmark) {
    font-size: 1rem;
  }
}

/* ≤480px — the section label no longer fits beside the brand and
 * the language switcher, so the trigger collapses to a hamburger.
 * The "where am I" cue isn't lost: the page's own <h1> sits
 * directly below and names the section. */
@media (max-width: 480px) {
  :global(.trigger-icon) {
    display: inline;
    font-size: 1.05rem;
  }
  .trigger-label,
  :global(.trigger-chevron) {
    display: none;
  }
  .menu-trigger {
    gap: 0;
    padding: 0;
    width: 2.25rem;
    justify-content: center;
  }
}
</style>
