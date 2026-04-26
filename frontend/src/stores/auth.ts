import { defineStore } from "pinia";
import { computed, ref } from "vue";
import { clearToken, get, getToken, post, setToken } from "@/api/client";

export interface User {
  id: string;
  email: string;
  name: string;
  role: "admin" | "organiser";
  is_approved: boolean;
  created_at: string;
}

interface AuthResponse {
  token: string;
  user: User;
}

export const useAuthStore = defineStore("auth", () => {
  const user = ref<User | null>(null);
  const loaded = ref(false);

  const isAuthenticated = computed(() => user.value !== null);
  const isApproved = computed(() => user.value?.is_approved === true);
  const isAdmin = computed(() => user.value?.role === "admin");

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

  return { user, loaded, isAuthenticated, isApproved, isAdmin, fetchMe, login, register, logout };
});
