import { ApiError, post } from "@/api/client";
import { t } from "@/i18n.svelte";
import { isPersonalApp } from "@/lib/branding";
import { useToasts } from "@/lib/toasts";
import { isValidEmail } from "@/lib/validate";
import { go } from "@/router/navigation.svelte";
import { auth } from "@/stores/auth.svelte";
import type { Started } from "@/api/types";

/**
 * Making something at the root, with no account.
 *
 * A create page is reached two ways. An organiser opens one from inside
 * their app and it saves through the organiser endpoint. A visitor
 * opens the same page from the root's tiles, having never signed in:
 * that is start mode, which adds one field for their address, drops the
 * chapter picker, and posts to ``/api/v1/start/{kind}``. The form is
 * the same form; nothing about it is a lesser version.
 *
 * This is what keeps the create pages from each growing their own
 * version of that. They ask whether they are in start mode, whether to
 * show a chapter picker at all, and hand over the body they already
 * assembled.
 */
export type StartKind = "event" | "form" | "datepoll" | "roster" | "quiz" | "compass";

/** Rosters are "chore" everywhere in the URL space, so the two names
 *  differ here and nowhere else. */
const PATHS: Record<StartKind, string> = {
  event: "event",
  quiz: "quiz",
  compass: "compass",
  form: "form",
  datepoll: "datepoll",
  roster: "chore",
};

export function startMode(kind: StartKind) {
  const toasts = useToasts();
  let email = $state("");
  let started = $state<Started | null>(null);

  /** What went wrong, in the visitor's language. The endpoint's own
   *  detail strings are English and written for an organiser, so it is
   *  the status that gets translated, not the body. */
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

  return {
    /** A signed-out visitor at the root. */
    get active(): boolean {
      return isPersonalApp() && !auth.isAuthenticated;
    },
    /** Whether this app has chapters at all: false at the root, both
     *  for a visitor with no account and for a signed-in personal one.
     *  That is what hides the picker and the agenda switch. An
     *  organisation's member always has at least one, so this stays
     *  true for them even before their memberships have loaded. */
    get hasChapters(): boolean {
      return !isPersonalApp() && !auth.isPersonal;
    },
    /** The visitor's address: the account the thing lands in. */
    get email(): string {
      return email;
    },
    set email(next: string) {
      email = next;
    },
    /** Set once the write succeeded, so the page can show what it made
     *  instead of the form. */
    get started(): Started | null {
      return started;
    },

    /** Warn and refuse on a missing or malformed address. Called from
     *  the page's own validation, so the address is checked in the same
     *  pass as everything else. */
    validate(): boolean {
      const value = email.trim();
      if (!value) {
        toasts.warn(t("start.fillEmail"));
        return false;
      }
      if (!isValidEmail(value)) {
        toasts.warn(t("common.invalidEmail"));
        return false;
      }
      return true;
    },

    /** Post the body to the start endpoint. False means the server
     *  refused, having already said why: these refusals are ones the
     *  visitor can act on, so they must not collapse into a generic
     *  "saving failed". */
    async submit(body: object): Promise<boolean> {
      try {
        started = await post<Started>(`/api/v1/start/${PATHS[kind]}`, {
          email: email.trim(),
          [kind]: body,
        });
        return true;
      } catch (err) {
        toasts.error(describe(err));
        return false;
      }
    },

    /** The ``chapter_id`` to put on the wire. An account with no
     *  chapters sends none, and the API refuses one from it rather than
     *  dropping it quietly, so this is not a formality. */
    chapterFor(value: string | null): string | null {
      return this.hasChapters ? value : null;
    },

    /** Cancel, for a visitor with no account who came from the tiles
     *  and has no list of their own to go back to. True means it
     *  navigated and the caller's own routing is skipped. */
    cancel(): boolean {
      if (!this.active) return false;
      void go("/");
      return true;
    },
  };
}

export type StartMode = ReturnType<typeof startMode>;
