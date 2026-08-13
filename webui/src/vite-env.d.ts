/// <reference types="vite/client" />

interface NoahAIBootstrap {
  gatewayUrl: string;
  gatewayToken: string;
  desktop: boolean;
}

interface Window {
  noahAI?: {
    bootstrap: () => NoahAIBootstrap;
  };
}
