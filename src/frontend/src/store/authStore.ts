import { create } from "zustand";
import { persist } from "zustand/middleware";
import { authApi, type User } from "@/lib/api";

interface AuthState {
  token: string | null;
  user: User | null;
  isLoading: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
  fetchMe: () => Promise<void>;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      user: null,
      isLoading: false,

      login: async (username, password) => {
        set({ isLoading: true });
        try {
          const data = await authApi.login(username, password);
          localStorage.setItem("access_token", data.access_token);
          set({ token: data.access_token, isLoading: false });
          const user = await authApi.me();
          set({ user });
        } catch (err) {
          set({ isLoading: false });
          throw err;
        }
      },

      logout: () => {
        localStorage.removeItem("access_token");
        set({ token: null, user: null });
      },

      fetchMe: async () => {
        set({ isLoading: true });
        try {
          const user = await authApi.me();
          set({ user, isLoading: false });
        } catch {
          set({ isLoading: false });
        }
      },
    }),
    {
      name: "auth-storage",
      partialize: (state) => ({ token: state.token }),
    },
  ),
);
