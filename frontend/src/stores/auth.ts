import { defineStore } from "pinia";
import { computed, ref } from "vue";
import type { AuthResponse, User } from "@/api/types";
import { clearToken, get, getToken, post, setToken } from "@/api/client";

export type { User };

export const useAuthStore = defineStore("auth", () => {
  const user = ref<User | null>(null);
  const loaded = ref(false);

  const isAuthenticated = computed(() => user.value !== null);
  const isVerified = computed(() => user.value?.email_verified_at != null);
  const isApproved = computed(
    () => user.value?.is_approved === true && user.value?.email_verified_at != null,
  );
  // Admin must clear the same two gates the backend's require_admin
  // dependency enforces (verified + approved). Keeping the frontend
  // computed in lock-step avoids a nav link that would 403 when clicked.
  const isAdmin = computed(
    () =>
      user.value?.role === "admin" &&
      user.value?.is_approved === true &&
      user.value?.email_verified_at != null,
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

  async function login(email: string, password: string): Promise<void> {
    const resp = await post<AuthResponse>("/api/v1/auth/login", { email, password });
    setToken(resp.token);
    user.value = resp.user;
  }

  async function register(email: string, password: string, name: string): Promise<void> {
    const resp = await post<AuthResponse>("/api/v1/auth/register", { email, password, name });
    setToken(resp.token);
    user.value = resp.user;
  }

  function logout(): void {
    clearToken();
    user.value = null;
  }

  async function verifyEmail(token: string): Promise<void> {
    user.value = await post<User>("/api/v1/auth/verify-email", { token });
  }

  async function resendVerification(): Promise<void> {
    await post("/api/v1/auth/resend-verification");
  }

  return {
    user,
    loaded,
    isAuthenticated,
    isVerified,
    isApproved,
    isAdmin,
    fetchMe,
    login,
    register,
    logout,
    verifyEmail,
    resendVerification,
  };
});
