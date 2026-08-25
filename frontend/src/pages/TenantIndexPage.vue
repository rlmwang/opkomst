<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useI18n } from "vue-i18n";
import LanguageSwitcher from "@/components/LanguageSwitcher.vue";
import LoginForm from "@/components/LoginForm.vue";
import PublicIdentity from "@/public_shared/PublicIdentity.vue";
import { brand } from "@/lib/branding";

/**
 * The organisation's public front page, at ``/{tenant}``.
 *
 * Its chapters, each linking to that chapter's agenda — which is where
 * "which Utrecht?" gets answered, and what makes the agenda URLs
 * findable instead of passed around by hand. Shown to visitors who
 * aren't signed in; an organiser sees their landing page at the same
 * path (``HomePage``).
 */

interface ChapterEntry {
  name: string;
  slug: string;
  city: string | null;
}

const { t } = useI18n();
const b = brand();
const chapters = ref<ChapterEntry[] | null>(null);
const failed = ref(false);

onMounted(async () => {
  try {
    const response = await fetch(`/api/v1/tenants/${encodeURIComponent(b.slug)}/chapters`);
    if (!response.ok) throw new Error(String(response.status));
    chapters.value = await response.json();
  } catch {
    failed.value = true;
  }
});
</script>

<template>
  <!-- Same column as a chapter's agenda (``container-wide``, ~1120px):
       the two public pages of an organisation are one surface, and a
       narrower front page reads as a different site. The header sits
       inside it, so the logo and the language toggle line up with the
       tiles under them. -->
  <main class="container-wide stack">
    <header class="public-header">
      <PublicIdentity :title="b.wordmark" />
      <LanguageSwitcher />
    </header>
    <p class="muted">{{ t("tenantIndex.lede") }}</p>

    <p v-if="failed" class="muted">{{ t("tenantIndex.failed") }}</p>
    <p v-else-if="chapters !== null && chapters.length === 0" class="muted">
      {{ t("tenantIndex.none") }}
    </p>

    <div v-if="chapters && chapters.length > 0" class="chapter-grid">
      <a v-for="c in chapters" :key="c.slug" :href="`/${b.slug}/${c.slug}`" class="chapter-tile">
        <span class="chapter-name">{{ c.name }}</span>
        <span v-if="c.city" class="muted chapter-city">{{ c.city }}</span>
      </a>
    </div>

    <!-- Same grammar as the tenant-less root (see
         docs/design-personal-tenants.md): tiles first, because
         browsing is what most visitors came for, and the door under
         them for the few who came to organise. Not a link to a
         sign-in wall — the form itself. -->
    <section class="organiser-door">
      <p class="divider muted">{{ t("tenantIndex.signIn") }}</p>
      <div class="door-form">
        <LoginForm />
      </div>
    </section>
  </main>
</template>

<style scoped>
/* The same grid the agenda lays its event cards out on: up to three
 * across the wide column, dropping to two and then one as the viewport
 * narrows. One chapter per tile. */
.chapter-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(min(320px, 100%), 1fr));
  gap: 1rem;
  margin-top: 0.5rem;
}
.chapter-tile {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  min-height: 4.5rem;
  padding: 1rem;
  border: 1px solid var(--brand-border);
  border-radius: 10px;
  background: var(--brand-surface);
  text-decoration: none;
  transition: border-color 120ms, background 120ms;
}
.chapter-tile:hover {
  border-color: var(--brand-red);
  background: var(--brand-red-soft);
}
.chapter-name {
  font-size: 1.125rem;
  font-weight: 600;
  color: var(--brand-red);
}
.chapter-city {
  font-size: 0.875rem;
}
/* Set apart from the chapters by space and a rule, not by a different
 * look: it is the same page, addressed to a different visitor. The rule
 * spans the column and carries its own label. */
/* Equal air above and below the rule, so it reads as a divider rather
 * than a lid on the form. */
.organiser-door {
  margin-top: 2rem;
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
/* The form is a short line of controls; centred under the rule it reads
 * as one block with it, rather than drifting to the left edge of a
 * 720px column. */
.door-form {
  max-width: 26rem;
  margin: 0 auto;
}

@media (max-width: 380px) {
  .chapter-tile {
    min-height: 3.5rem;
    padding: 0.75rem;
    justify-content: center;
  }
  .chapter-name {
    font-size: 1rem;
  }
  .chapter-city {
    display: none;
  }
}
</style>
