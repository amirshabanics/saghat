import { create } from "zustand";
import { paymentsApi, type Config } from "@/lib/api";

interface ConfigState {
  config: Config | null;
  isLoading: boolean;
  fetchConfig: () => Promise<void>;
}

export const useConfigStore = create<ConfigState>()((set) => ({
  config: null,
  isLoading: false,

  fetchConfig: async () => {
    set({ isLoading: true });
    try {
      const config = await paymentsApi.config();
      set({ config, isLoading: false });
    } catch {
      set({ isLoading: false });
    }
  },
}));
