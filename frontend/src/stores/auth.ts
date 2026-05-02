import { defineStore } from "pinia";
import { computed, ref } from "vue";
import type { AuthResponse, User } from "@/api/types";
import { clearToken, get, getToken, post, setToken } from "@/api/client";

export type { User };

export const useAuthStore = defineStore("auth", () => {
  const user = ref<User | null>(null);
  const loaded = ref(false);

  const isAuthenticated = computed(() => user.value !== null);
  const isApproved = computed(() => user.value?.is_approved === true);
  // Admin must also be approved — keep this in lock-step with the
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

  function logout(): void {
    clearToken();
    user.value = null;
  }

  return {
    user,
    loaded,
    isAuthenticated,
    isApproved,
    isAdmin,
    fetchMe,
    requestLoginLink,
    redeem,
    completeRegistration,
    logout,
  };
});
