import type {
  CandleSnapshot,
  FeatureInventory,
  PlatformContract,
  RuntimeSnapshot,
} from "./types";

export interface GatewayClient {
  platform: () => Promise<PlatformContract>;
  features: () => Promise<FeatureInventory>;
  runtime: () => Promise<RuntimeSnapshot>;
  candles: (symbol: string, interval: string, limit?: number) => Promise<CandleSnapshot>;
}

function bootstrap(): NoahAIBootstrap {
  if (window.noahAI) {
    return window.noahAI.bootstrap();
  }
  return {
    gatewayUrl: import.meta.env.VITE_GATEWAY_URL || "http://127.0.0.1:3910",
    gatewayToken: import.meta.env.VITE_GATEWAY_TOKEN || "",
    desktop: false,
  };
}

export function createGatewayClient(): GatewayClient {
  const configuration = bootstrap();
  const baseUrl = configuration.gatewayUrl.replace(/\/$/, "");

  async function get<T>(path: string): Promise<T> {
    if (!configuration.gatewayToken) {
      throw new Error("Gateway token이 없습니다. Electron 셸 또는 개발 환경 변수를 확인하세요.");
    }
    const response = await fetch(`${baseUrl}${path}`, {
      method: "GET",
      headers: { Authorization: `Bearer ${configuration.gatewayToken}` },
      cache: "no-store",
    });
    if (!response.ok) {
      throw new Error(`Gateway 요청 실패 (${response.status})`);
    }
    return (await response.json()) as T;
  }

  return {
    platform: () => get<PlatformContract>("/api/v1/platform"),
    features: () => get<FeatureInventory>("/api/v1/features"),
    runtime: () => get<RuntimeSnapshot>("/api/v1/runtime/snapshot"),
    candles: (symbol, interval, limit = 300) =>
      get<CandleSnapshot>(
        `/api/v1/market/candles?source=binance&symbol=${encodeURIComponent(symbol)}&interval=${encodeURIComponent(interval)}&limit=${limit}`,
      ),
  };
}
