import axios, { isAxiosError } from "axios";

import { api, SENTINEL_TOKEN_KEY } from "@/lib/api";
import { create } from "zustand";

export type AuthUser = {
  id: number;
  username: string;
  email: string;
  role: string;
  is_active: boolean;
};

type AuthState = {
  token: string | null;
  user: AuthUser | null;
  isHydrated: boolean;
  loadingMe: boolean;
  validateToken: () => Promise<boolean>;
  setToken: (token: string) => void;
  clearToken: () => void;
};

export const useAuthStore = create<AuthState>((set, get) => ({
  token: typeof window !== "undefined" ? localStorage.getItem(SENTINEL_TOKEN_KEY) : null,
  user: null,
  isHydrated: typeof window !== "undefined",
  loadingMe: false,

  validateToken: async () => {
    const token = get().token;
    if (!token) {
      set({ user: null });
      return false;
    }
    set({ loadingMe: true });
    try {
      const res = await api.get<AuthUser>("/auth/me");
      set({ user: res.data, loadingMe: false });
      return true;
    } catch (err) {
      // Only clear token on auth failures; keep it for transient/network issues.
      if (isAxiosError(err)) {
        const status = err.response?.status;
        if (status === 401 || status === 403) {
          get().clearToken();
        }
      } else {
        // Non-Axios errors: don't clear token automatically.
      }
      set({ user: null, loadingMe: false });
      return false;
    }
  },

  setToken: (token) => {
    localStorage.setItem(SENTINEL_TOKEN_KEY, token);
    set({ token });
  },

  clearToken: () => {
    localStorage.removeItem(SENTINEL_TOKEN_KEY);
    set({ token: null, user: null });
  },
}));

