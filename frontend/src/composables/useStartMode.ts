/**
 * Making something at the root, with no account.
 *
 * The four create pages are reached two ways. An organiser opens one
 * from inside their app and it saves through the organiser endpoint.
 * A visitor opens the same page from the root's landing tiles, having
 * never signed in — that is *start mode*: one extra field for their
 * address, no chapter picker, and ``POST /api/v1/start/{kind}`` as the
 * target. The form itself is the same form; nothing about it is a
 * lesser version.
 *
 * The composable is what keeps the four pages from each growing their
 * own version of that: they ask it whether they are in start mode,
 * whether to show a chapter picker at all, and hand it the create body
 * they already assembled.
 */

import { computed, ref, type Ref } from "vue";
import { useI18n } from "vue-i18n";
import { useRouter } from "vue-router";
import { ApiError, post } from "@/api/client";
import { isPersonalApp } from "@/lib/branding";
import { useToasts } from "@/lib/toasts";
import { isValidEmail } from "@/lib/validate";
import { useAuthStore } from "@/stores/auth";
import type { Started } from "@/api/types";

/** The wire name of the create body, which is also the key the start
 * endpoint expects it under. */
export type StartKind = "event" | "form" | "datepoll" | "roster" | "quiz";

// The endpoint path per kind. Rosters are "chores" everywhere in the
// URL space, so the two names differ here and nowhere else.
const PATHS: Record<StartKind, string> = {
  event: "events",
  quiz: "quizzes",
  form: "forms",
  datepoll: "datepolls",
  roster: "chores",
};

export interface StartMode {
  /** Signed-out visitor at the root: the form saves through the start
   * endpoint and asks for an address. */
  active: Ref<boolean>;
  /** Whether this app has chapters at all: false at the root, both for
   * a visitor with no account and for a signed-in personal one. That is
   * what hides the picker and the agenda toggle. An organisation's
   * member always has at least one, so this stays true for them even
   * before their memberships have loaded. */
  hasChapters: Ref<boolean>;
  /** The visitor's address — the account the entity lands in. */
  email: Ref<string>;
  /** Set once the write succeeded; the page shows what it made instead
   * of the form. */
  started: Ref<Started | null>;
  /** Warn and refuse on a missing or malformed address. Called from the
   * page's own validation run, so the address is checked in the same
   * pass as everything else. */
  validate: () => boolean;
  /** POST the create body to the start endpoint. Returns false when the
   * server refused, having already said why: the refusals here are
   * ones the visitor can act on (wait, or archive something), so they
   * must not collapse into a generic "saving failed". */
  submit: (body: object) => Promise<boolean>;
  /** The ``chapter_id`` to put on the wire. An account with no chapters
   * sends none; the API refuses one from it rather than dropping it
   * quietly, so this is not a formality. */
  chapterFor: (value: string | null) => string | null;
  /** Handle a cancel for a visitor with no account, who came from the
   * landing tiles and has no list of their own to go back to. Returns
   * true when it navigated, so the caller's own routing is skipped. */
  cancel: () => boolean;
}

export function useStartMode(kind: StartKind): StartMode {
  const { t } = useI18n();
  const auth = useAuthStore();
  const toasts = useToasts();
  const router = useRouter();

  const active = computed(() => isPersonalApp() && !auth.isAuthenticated);
  const hasChapters = computed(() => !isPersonalApp() && !auth.isPersonal);
  const email = ref("");
  const started = ref<Started | null>(null);

  function validate(): boolean {
    const value = email.value.trim();
    if (!value) {
      toasts.warn(t("start.fillEmail"));
      return false;
    }
    if (!isValidEmail(value)) {
      toasts.warn(t("common.invalidEmail"));
      return false;
    }
    return true;
  }

  async function submit(body: object): Promise<boolean> {
    try {
      started.value = await post<Started>(`/api/v1/start/${PATHS[kind]}`, {
        email: email.value.trim(),
        [kind]: body,
      });
      return true;
    } catch (err) {
      toasts.error(describe(err));
      return false;
    }
  }

  /** What went wrong, in the visitor's language. The endpoint's own
   * detail strings are English and written for an organiser, so the
   * status is what is translated, not the body. */
  function describe(err: unknown): string {
    if (err instanceof ApiError) {
      // One caller, five an hour: somebody filling in a form twice is
      // nowhere near it, so this is worth naming rather than hiding.
      if (err.status === 429) return t("start.tooMany");
      // The only 409 these endpoints raise is the ceiling on how many
      // live things one account may hold.
      if (err.status === 409) return t("start.accountFull");
    }
    return t("start.failed");
  }

  function chapterFor(value: string | null): string | null {
    return hasChapters.value ? value : null;
  }

  function cancel(): boolean {
    if (!active.value) return false;
    void router.push("/");
    return true;
  }

  return { active, hasChapters, email, started, validate, submit, chapterFor, cancel };
}
