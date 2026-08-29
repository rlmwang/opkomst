import { defineStore } from "pinia";
import { computed, ref } from "vue";
import type { AuthResponse, User } from "@/api/types";
import { clearToken, get, getToken, post, setToken } from "@/api/client";
import { brand, isPersonalApp } from "@/lib/branding";
import { clearAllDrafts } from "@/composables/useFormDraft";

export type { User };

export const useAuthStore = defineStore("auth", () => {
  const user = ref<User | null>(null);
  const loaded = ref(false);
  // Whether the WhatsApp blast tool is open to this account: an
  // approved admin of an organisation, on a deployment with the
  // EVOLUTION_* variables set. Drives the nav tab and the route guard.
  // It arrives on the user row, so there is no second request in front
  // of the first page.
  const whatsappAvailable = computed(() => user.value?.whatsapp_available === true);

  const isAuthenticated = computed(() => user.value !== null);
  // A personal account is one person and no chapters, so the pages
  // that manage people and chapters aren't offered. Read off the user
  // rather than off the brand, because it is a fact about the account:
  // the server refuses those routes for it either way.
  const isPersonal = computed(() => user.value?.tenant_kind === "personal");
  // An approved member of an organisation who is in none of its
  // chapters sees nothing until they pick one, so every list page
  // shows them the picker instead of an empty list. A personal account
  // is never in this state: it has no chapters by construction, and
  // its rows are scoped by tenant alone.
  const needsChapters = computed(
    () => isApproved.value && !isPersonal.value && (user.value?.chapters?.length ?? 0) === 0,
  );
  const isApproved = computed(() => user.value?.is_approved === true);
  // Whether this account may make the app mail the people it collects.
  // The reminder and feedback controls exist on the forms only when it
  // does (docs/design-paywall.md). Signed out is a visitor at the start
  // door, whose account will be a free one, so it is false there too.
  const participantMail = computed(() => user.value?.participant_mail === true);
  // Admin must also be approved, keep this in lock-step with the
  // backend's require_admin so a nav link can't 403 when clicked.
  const isAdmin = computed(
    () => user.value?.role === "admin" && user.value?.is_approved === true,
  );

  async function fetchMe(): Promise<void> {
    if (!getToken()) {
      loaded.value = true;
      return;
    }
    try {
      user.value = await get<User>("/api/v1/auth/me");
    } catch {
      user.value = null;
    } finally {
      loaded.value = true;
    }
  }

  async function requestLoginLink(email: string): Promise<void> {
    // The door is per organisation: the same address can organise for
    // two of them as two accounts, so the sign-in page names the
    // tenant it is served under. At the root there is no organisation
    // to name — ``tenant: null`` is the personal door, where the
    // address resolves to its own account, or becomes one.
    const tenant = isPersonalApp() ? null : brand().slug;
    await post("/api/v1/auth/login-link", { email, tenant });
  }

  async function redeem(token: string): Promise<void> {
    const resp = await post<AuthResponse>("/api/v1/auth/login", { token });
    setToken(resp.token);
    user.value = resp.user;
  }

  async function completeRegistration(token: string, name: string): Promise<void> {
    // Same shape as redeem: completing the sign-up is also the
    // first sign-in, so the response carries a JWT + user row.
    const resp = await post<AuthResponse>("/api/v1/auth/complete-registration", {
      token,
      name,
    });
    setToken(resp.token);
    user.value = resp.user;
  }

  async function logout(): Promise<void> {
    // Best-effort server hook. Wipes any linked WhatsApp blast
    // session before we drop the JWT. Failures here must not
    // block sign-out (the user clicked Logout, the local state
    // gets cleared regardless).
    try {
      await post("/api/v1/auth/logout", {});
    } catch {
      // ignore
    }
    clearToken();
    user.value = null;
    // Drop any draft / recipient list the WhatsApp blast tool
    // had stashed in sessionStorage. Same privacy posture as
    // the rest of the project: nothing of the previous session
    // leaks into the next one.
    try {
      sessionStorage.removeItem("opkomst.whatsapp.draft");
    } catch {
      // ignore
    }
    // Same rule for the half-typed create forms. At the root the next
    // visitor is not necessarily the same person.
    clearAllDrafts();
  }

  return {
    user,
    loaded,
    isAuthenticated,
    isApproved,
    isAdmin,
    isPersonal,
    participantMail,
    needsChapters,
    whatsappAvailable,
    fetchMe,
    requestLoginLink,
    redeem,
    completeRegistration,
    logout,
  };
});
