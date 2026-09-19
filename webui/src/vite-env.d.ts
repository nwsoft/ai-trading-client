/// <reference types="vite/client" />

interface NoahAIBootstrap {
  gatewayUrl: string;
  gatewayToken: string;
  desktop: boolean;
  systemLanguage?: string;
}

interface Window {
  noahAI?: {
    bootstrap: () => NoahAIBootstrap;
    window?: {
      setMode: (mode: "login" | "dashboard") => Promise<unknown>;
      applyDisplayPreferences: (preferences: { displayPreset?: string; alwaysOnTop?: boolean }) => Promise<unknown>;
      openLoginHelp: () => Promise<unknown>;
      requestClose: () => Promise<unknown>;
    };
    credentials?: {
      load: () => Promise<{ saved: boolean; username?: string; password?: string }>;
      save: (username: string, password: string) => Promise<{ saved: boolean }>;
      clear: () => Promise<{ saved: boolean }>;
    };
    updater: {
      configure: (options: { enabled: boolean; intervalHours: number; autoDownload: boolean; autoInstallOnAppQuit: boolean }) => Promise<unknown>;
      getStatus: () => Promise<Record<string, unknown>>;
      check: () => Promise<unknown>;
      download: () => Promise<unknown>;
      install: () => Promise<unknown>;
      onStatus: (listener: (status: Record<string, unknown>) => void) => () => void;
    };
  };
}
