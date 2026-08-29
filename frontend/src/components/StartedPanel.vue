<script setup lang="ts">
import AppButton from "@/components/AppButton.vue";
import { useI18n } from "vue-i18n";
import AppCard from "@/components/AppCard.vue";
import AppHeader from "@/components/AppHeader.vue";
import { useToasts } from "@/lib/toasts";
import type { Started } from "@/api/types";

/**
 * What a visitor sees the moment they have made something without an
 * account: the public link, working already, and the note that a
 * sign-in link is on its way to the address they gave.
 *
 * The link comes first because it is the thing they came for and they
 * can hand it around before the mail arrives. The mail is the other
 * half, how they get back to what they made, so it is stated plainly
 * rather than left to be discovered in an inbox.
 *
 * Both actions keep the visitor here. Copying is the common one, and
 * opening the page goes to a new tab: this card is the only place that
 * holds the link and the note together, and navigating away from it
 * would leave nothing behind.
 */

const props = defineProps<{ started: Started; email: string }>();

const { t } = useI18n();
const toasts = useToasts();

function open() {
  window.open(props.started.public_url, "_blank", "noopener");
}

async function copy() {
  try {
    await navigator.clipboard.writeText(props.started.public_url);
    toasts.success(t("start.linkCopied"));
  } catch {
    /* clipboard unavailable; the URL is on screen to copy by hand */
  }
}
</script>

<template>
  <AppHeader />
  <div class="container-wide">
    <AppCard>
      <h1>{{ t("start.doneTitle") }}</h1>
      <p class="muted">{{ t("start.doneBody", { email }) }}</p>
      <p class="public-url">
        <a :href="started.public_url" target="_blank" rel="noopener">{{ started.public_url }}</a>
      </p>
      <div class="actions">
        <AppButton
          :label="t('start.openIt')"
          severity="secondary"
          text
          @click="open"
        />
        <AppButton :label="t('start.copyLink')" icon="link" @click="copy" />
      </div>
    </AppCard>
  </div>
</template>

<style scoped>
/* The link is the answer to "what did I just make", so it gets a line
 * of its own and breaks rather than overflowing on a phone. */
.public-url {
  margin: 1rem 0 0;
  font-size: 1.0625rem;
  word-break: break-all;
}
.actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.5rem;
  margin-top: 1.5rem;
}
</style>
