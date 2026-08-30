<script lang="ts">
import AppButton from "@/components/AppButton.svelte";
import AppCard from "@/components/AppCard.svelte";
import AppTextarea from "@/components/AppTextarea.svelte";
import PublicHeader from "@/components/PublicHeader.svelte";
import RatingScale from "@/components/RatingScale.svelte";
import {
  type FeedbackQuestion,
  feedbackFormQuery,
  feedbackPreviewQuery,
  submitFeedback,
} from "@/composables/useFeedback.svelte";
import { setLocale, t } from "@/i18n.svelte";
import { ApiError } from "@/api/client";
import { route } from "@/router/navigation.svelte";
import { useToasts } from "@/lib/toasts";

/**
 * The day-after form, opened from the one email the app sends a
 * participant.
 *
 * The token in the URL is the whole of the visitor's identity here, and
 * spending it deletes it. ``preview`` is the organiser looking at their
 * own form: the same page, read-only, so what they check is what will
 * be sent.
 */
const { slug }: { slug: string } = $props();

const toasts = useToasts();
const token = (route.query.get("t") ?? "") as string;
const isPreview = token === "preview";

const formQuery = feedbackFormQuery(
  () => token,
  () => !isPreview && Boolean(token),
);
const previewQuery = feedbackPreviewQuery(
  () => slug,
  () => isPreview,
);
const submit = submitFeedback();

const form = $derived((isPreview ? previewQuery.data : formQuery.data) ?? null);

let ratings = $state<Record<string, number | null>>({});
let texts = $state<Record<string, string>>({});
let submitted = $state(false);

const error = $derived.by(() => {
  if (!token) return t("feedback.expired");
  const err = isPreview ? previewQuery.error : formQuery.error;
  if (!err) return null;
  return err instanceof ApiError && (err.status === 410 || err.status === 404)
    ? t("feedback.expired")
    : t("feedback.loadFailed");
});

// The form arrives in the event's language, and the page follows it: a
// participant reads the words the organiser wrote, not the words this
// browser prefers.
let seeded: unknown = undefined;
$effect(() => {
  const f = form;
  if (!f || f === seeded) return;
  seeded = f;
  setLocale(f.event_locale);
  for (const q of f.questions) {
    if (q.kind === "rating") ratings[q.key] = null;
    if (q.kind === "text") texts[q.key] = "";
  }
});

function prompt(q: FeedbackQuestion): string {
  return t(`feedback.questions.${q.key}.prompt`);
}

function ratingLabel(q: FeedbackQuestion, end: "Low" | "High"): string {
  return t(`feedback.questions.${q.key}.label${end}`);
}

async function send(event: Event): Promise<void> {
  event.preventDefault();
  if (!form || isPreview) return;
  // The same required check the server makes, so an unanswered
  // question is named here rather than coming back as a 422.
  for (const q of form.questions) {
    if (!q.required) continue;
    if (q.kind === "rating" && ratings[q.key] == null) {
      toasts.warn(prompt(q));
      return;
    }
    if (q.kind === "text" && !texts[q.key].trim()) {
      toasts.warn(prompt(q));
      return;
    }
  }

  const answers = form.questions.map((q) =>
    q.kind === "rating"
      ? { question_key: q.key, answer_int: ratings[q.key] }
      : { question_key: q.key, answer_text: texts[q.key] || null },
  );

  try {
    await submit.run({ token, answers });
    submitted = true;
  } catch (e) {
    toasts.error(
      e instanceof ApiError && (e.status === 410 || e.status === 404)
        ? t("feedback.expired")
        : t("feedback.submitFail"),
    );
  }
}
</script>

<div class="container stack">
  <PublicHeader />

  <!-- ``submitted`` beats ``error``: once a submit lands, nothing
       downstream may flip the visitor back to "this link is no longer
       valid". -->
  {#if submitted}
    <AppCard>
      <h2>{t("feedback.thanks")}</h2>
      <p class="muted">{t("feedback.thanksBody")}</p>
    </AppCard>
  {:else if error}
    <AppCard stack={false}>
      <p>{error}</p>
    </AppCard>
  {:else if !form}
    <AppCard stack={false}>
      <p class="muted">{t("common.loading")}</p>
    </AppCard>
  {:else}
    {#if isPreview}
      <AppCard stack={false} class="preview-banner">
        <p>{t("feedback.previewBanner")}</p>
      </AppCard>
    {/if}

    <AppCard>
      <h1>{t("feedback.title", { name: form.event_name })}</h1>
      <p class="muted intro">{t("feedback.intro")}</p>
    </AppCard>

    <form class="stack" novalidate onsubmit={send}>
      {#each form.questions as q (q.key)}
        <AppCard>
          <span class="prompt">{prompt(q)}</span>
          {#if q.kind === "rating"}
            <RatingScale
              bind:value={ratings[q.key]}
              labelLow={ratingLabel(q, "Low")}
              labelHigh={ratingLabel(q, "High")}
            />
          {:else}
            <AppTextarea
              bind:value={texts[q.key]}
              placeholder={t(`feedback.questions.${q.key}.placeholder`)}
              maxlength={500}
              rows={3}
              autoResize
              fluid
            />
          {/if}
        </AppCard>
      {/each}
      <div class="submit-row">
        <AppButton
          type="submit"
          label={t("feedback.submit")}
          loading={submit.pending}
          disabled={isPreview}
        />
      </div>
    </form>
  {/if}
</div>

<style>
.intro {
  font-size: 0.875rem;
}
.prompt {
  font-weight: 600;
  font-size: 1.125rem;
  line-height: 1.4;
}
div :global(.preview-banner) {
  border: 1px dashed var(--brand-red);
  background: color-mix(in srgb, var(--brand-red) 6%, transparent);
}
div :global(.preview-banner p) {
  margin: 0;
  font-size: 0.875rem;
  color: var(--brand-red);
}
/* Submit aligned right, matching the public sign-up form. */
.submit-row {
  display: flex;
  justify-content: flex-end;
}
</style>
