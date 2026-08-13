export interface PlatformContract {
  product: "NoahAI Client";
  release_version: string;
  release_label: string;
  schema_version: string;
  ui_platform: "web_parallel";
  legacy_ui: "customtkinter_active";
  gateway_mode: "read_only";
  commands_enabled: false;
}

export interface RuntimeSnapshot {
  snapshot_version: number;
  status: "detached" | "ready" | "partial" | "stale" | "error";
  service: string | null;
  selected_source: string | null;
  enabled_sources: string[];
  running_sources: string[];
  paper_trading: boolean | null;
  live_trading: boolean | null;
  captured_at: string;
  reason: string;
}

export interface Feature {
  id: string;
  label: string;
  route?: string;
  migration: string;
}

export interface ServiceFeatureGroup {
  id: string;
  label: string;
  sources: string[];
  features: Feature[];
}

export interface FeatureInventory {
  schema_version: string;
  release_version: string;
  transition_mode: "read_only_parallel";
  commands_enabled: false;
  services: ServiceFeatureGroup[];
  platform_features: Feature[];
}

export interface Candle {
  source: string;
  market_type: "spot" | "futures" | "stock";
  symbol: string;
  interval: string;
  open_time: number;
  close_time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  closed: boolean;
  sequence: number;
}

export interface CandleSnapshot {
  schema_version: string;
  source: string;
  symbol: string;
  interval: string;
  candles: Candle[];
  captured_at: string;
}
