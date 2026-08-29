<script lang="ts">
import LoginForm from "@/components/LoginForm.svelte";
import { t } from "@/i18n.svelte";

/**
 * The way in for people who have already made something.
 *
 * It sits under the tiles on both signed-out front pages, past a rule
 * and a good deal of air: signing in is the alternative to what the
 * page is offering, not a step inside it, and the distance is what says
 * so. Not a link to a sign-in wall either, but the form itself.
 */
</script>

<section class="organiser-door">
  <p class="divider muted">{t("tenantIndex.signIn")}</p>
  <div class="door-form">
    <LoginForm />
  </div>
</section>

<style>
/* Equal air above and below the rule, so it reads as a divider rather
 * than a lid on the form. */
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
/* Narrower than the grid above it, so nothing about it looks like one
 * more tile. */
.door-form {
  max-width: 26rem;
  margin: 0 auto;
}
</style>
