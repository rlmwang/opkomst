<script setup lang="ts">
import { computed } from "vue";
import { useI18n } from "vue-i18n";
import AppHeader from "@/components/AppHeader.vue";
import { brand } from "@/lib/branding";
import { useAuthStore } from "@/stores/auth";

/**
 * The organisation's landing page — where the wordmark takes you, and
 * where a fresh sign-in lands. One tile per kind of thing the tool
 * makes (events, forms, datepolls, chore rosters), with the
 * organisation-management pages on a full-width tile below them.
 *
 * It exists because "which of the four workspaces did I want?" is the
 * first question every session starts with, and answering it from a
 * dropdown on the events list made events the accidental home.
 */

const { t } = useI18n();
const auth = useAuthStore();
const b = brand();

interface Tile {
  key: string;
  to: string;
  label: string;
  hint: string;
}

// Events is the one workspace an unapproved organiser can open; the
// rest wait for an admin to approve the account, so they aren't shown
// as doors that lead to a redirect.
const tiles = computed<Tile[]>(() => {
  const all: Tile[] = [
    { key: "events", to: "/events", label: t("header.events"), hint: t("home.eventsHint") },
    { key: "forms", to: "/forms", label: t("header.forms"), hint: t("home.formsHint") },
    { key: "datepolls", to: "/datepolls", label: t("header.datepolls"), hint: t("home.datepollsHint") },
    { key: "chores", to: "/chores", label: t("header.chores"), hint: t("home.choresHint") },
  ];
  return auth.isApproved ? all : all.slice(0, 1);
});
</script>

<template>
  <AppHeader />
  <main class="container stack">
    <h1 class="home-title">{{ b.wordmark }}</h1>
    <p class="muted home-lede">{{ t("home.lede") }}</p>

    <div class="tile-grid">
      <router-link v-for="tile in tiles" :key="tile.key" :to="tile.to" class="tile">
        <span class="tile-label">{{ tile.label }}</span>
        <span class="tile-hint muted">{{ tile.hint }}</span>
      </router-link>

      <router-link v-if="auth.isApproved" to="/users" class="tile tile-wide">
        <span class="tile-label">{{ t("header.admin") }}</span>
        <span class="tile-hint muted">{{ t("home.adminHint") }}</span>
      </router-link>
    </div>
  </main>
</template>

<style scoped>
.home-title {
  margin-top: 0.5rem;
}
.home-lede {
  margin: 0;
}

/* Two columns at every width. The tiles are the whole page, so on a
 * phone they should still be side by side — a single column would push
 * the admin tile below the fold for no gain. */
.tile-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 0.75rem;
  margin-top: 0.5rem;
}
.tile-wide {
  grid-column: 1 / -1;
}

.tile {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  min-height: 6.5rem;
  padding: 1rem;
  border: 1px solid var(--brand-border);
  border-radius: 10px;
  background: var(--brand-surface);
  color: var(--brand-text);
  text-decoration: none;
  transition: border-color 120ms, background 120ms, transform 120ms;
}
.tile:hover {
  border-color: var(--brand-red);
  background: var(--brand-red-soft);
}
.tile:active {
  transform: translateY(1px);
}
.tile-label {
  font-size: 1.125rem;
  font-weight: 600;
  color: var(--brand-red);
}
.tile-hint {
  font-size: 0.875rem;
  line-height: 1.35;
}

/* The full-width admin tile sits apart from the four workspaces: it
 * acts on the organisation rather than on its programme. */
.tile-wide {
  flex-direction: row;
  align-items: baseline;
  gap: 0.625rem;
  min-height: 0;
  flex-wrap: wrap;
}

/* On the narrowest phones the hint is the first thing to go — two
 * words per line reads worse than no line at all — and the tiles
 * shrink to fit the label they're left with. */
@media (max-width: 380px) {
  .tile {
    min-height: 3.5rem;
    padding: 0.75rem;
    justify-content: center;
  }
  .tile-wide {
    min-height: 0;
  }
  .tile-label {
    font-size: 1rem;
  }
  .tile-hint {
    display: none;
  }
}
</style>
