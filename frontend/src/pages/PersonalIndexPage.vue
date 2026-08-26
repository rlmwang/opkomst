<script setup lang="ts">
import { computed } from "vue";
import { useI18n } from "vue-i18n";
import LanguageSwitcher from "@/components/LanguageSwitcher.vue";
import LoginForm from "@/components/LoginForm.vue";
import PublicIdentity from "@/public_shared/PublicIdentity.vue";
import { brand, tagline } from "@/lib/branding";

/**
 * The root's signed-out face: a door with four handles.
 *
 * An organisation's front page lists its chapters, because a visitor
 * there is looking for one of them. Nobody arrives at the bare root
 * looking for an organisation — they arrive wanting to make one thing,
 * so the four things this tool makes *are* the page, and each tile
 * opens that thing's create form rather than a description of it.
 *
 * Signing in sits below the tiles, past a rule: it is the way in for
 * the people who have already made something, not a step inside
 * making something. The distance is what says so.
 */

const { t, locale } = useI18n();
const b = brand();

interface Tile {
  key: string;
  to: string;
  label: string;
  hint: string;
}

const tiles = computed<Tile[]>(() => [
  { key: "events", to: "/events/new", label: t("header.events"), hint: t("home.eventsHint") },
  { key: "forms", to: "/forms/new", label: t("header.forms"), hint: t("home.formsHint") },
  { key: "datepolls", to: "/datepolls/new", label: t("header.datepolls"), hint: t("home.datepollsHint") },
  { key: "chores", to: "/chores/new", label: t("header.chores"), hint: t("home.choresHint") },
]);
</script>

<template>
  <!-- Same column and same header as an organisation's front page:
       the root is not a different site, it is the same app without an
       organisation in front of it. -->
  <main class="container-wide stack">
    <header class="public-header">
      <PublicIdentity :title="b.wordmark" :subtitle="tagline(locale)" />
      <LanguageSwitcher />
    </header>
    <div class="tile-grid">
      <router-link v-for="tile in tiles" :key="tile.key" :to="tile.to" class="tile">
        <span class="tile-label">{{ tile.label }}</span>
        <span class="tile-hint muted">{{ tile.hint }}</span>
      </router-link>
    </div>

    <section class="organiser-door">
      <p class="divider muted">{{ t("tenantIndex.signIn") }}</p>
      <div class="door-form">
        <LoginForm />
      </div>
    </section>
  </main>
</template>

<style scoped>
/* Two columns at every width — four tiles are the page, and a single
 * column would push half of them below the fold on a phone. */
.tile-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 1rem;
  margin-top: 0.5rem;
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

/* Roughly triple the grid's own gap. A form pressed up against four
 * buttons reads as a step in them ("pick one, then identify
 * yourself"); this is the alternative to them, and the gap is what
 * says which. Equal air on both sides of the rule so it divides
 * rather than lids. */
.organiser-door {
  margin-top: 3rem;
}
.divider {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin: 0 0 2rem;
  font-size: 0.875rem;
}
.divider::before,
.divider::after {
  content: "";
  flex: 1 1 auto;
  height: 1px;
  background: var(--brand-border);
}
/* Narrower than the grid, so nothing about it looks like a fifth
 * tile. */
.door-form {
  max-width: 26rem;
  margin: 0 auto;
}

@media (max-width: 380px) {
  .tile {
    min-height: 3.5rem;
    padding: 0.75rem;
    justify-content: center;
  }
  .tile-label {
    font-size: 1rem;
  }
  .tile-hint {
    display: none;
  }
}
</style>
