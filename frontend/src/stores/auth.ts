import { defineStore } from "pinia";
import { computed, ref } from "vue";
import type { AuthResponse, User } from "@/api/types";
import { clearToken, get, getToken, post, setToken } from "@/api/client";

export type { User };

export const useAuthStore = defineStore("auth", () => {
  const user = ref<User | null>(null);
  const loaded = ref(false);
  // Admin-only feature flag. True when EVOLUTION_URL,
  // EVOLUTION_API_KEY, and EVOLUTION_INSTANCE are all set on the
  // server. Drives the WhatsApp nav tab visibility and the
  // route guard. Hydrated on fetchMe for admins only.
  const whatsappAvailable = ref(false);

  const isAuthenticated = computed(() => user.value !== null);
  const isApproved = computed(() => user.value?.is_approved === true);
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
      if (user.value?.role === "admin" && user.value?.is_approved) {
        try {
          const s = await get<{ state: string }>("/api/v1/whatsapp/status");
          whatsappAvailable.value = s.state !== "not_configured";
        } catch {
          whatsappAvailable.value = false;
        }
      } else {
        whatsappAvailable.value = false;
      }
    } catch {
      user.value = null;
      whatsappAvailable.value = false;
    } finally {
      loaded.value = true;
    }
  }

  async function requestLoginLink(email: string): Promise<void> {
    await post("/api/v1/auth/login-link", { email });
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
    whatsappAvailable.value = false;
    // Drop any draft / recipient list the WhatsApp blast tool
    // had stashed in sessionStorage. Same privacy posture as
    // the rest of the project: nothing of the previous session
    // leaks into the next one.
    try {
      sessionStorage.removeItem("opkomst.whatsapp.draft");
    } catch {
      // ignore
    }
  }

  return {
    user,
    loaded,
    isAuthenticated,
    isApproved,
    isAdmin,
    whatsappAvailable,
    fetchMe,
    requestLoginLink,
    redeem,
    completeRegistration,
    logout,
  };
});
