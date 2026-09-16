export interface PlatformContract {
  product: "NoahAI Client";
  release_version: string;
  release_label: string;
  schema_version: string;
  ui_platform: "web_electron";
  legacy_ui: "not_packaged";
  gateway_mode: "account_scoped";
  commands_enabled: true;
}

export interface SessionSnapshot {
  authenticated: boolean;
  account: string | null;
  user: { id?: string; email?: string; user_grade?: string; membership_policy?: Record<string, any> };
}

export interface RuntimeSnapshot {
  snapshot_version: number;
  status: "detached" | "ready" | "partial" | "stale" | "error";
  service: string | null;
  selected_source: string | null;
  selected_sources: Record<string, string>;
  enabled_sources: string[];
  running_sources: string[];
  enabled_sources_by_service: Record<string, string[]>;
  running_sources_by_service: Record<string, string[]>;
  credential_status: Record<string, boolean>;
  configured_sources_by_service: Record<string, string[]>;
  execution_modes: Record<string, "learning" | "paper" | "live">;
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
  transition_mode: "internal_full_migration";
  commands_enabled: true;
  services: ServiceFeatureGroup[];
  platform_features: Feature[];
}

export interface ManualSection {
  id: string;
  label: string;
  content: string;
  legacy_method: string;
}

export interface ManualSnapshot {
  schema_version: string;
  source: "docs/USER_MANUAL_SECTIONS.json";
  source_reference: "ui/widgets/user_manual_widget.py";
  source_sha256: string;
  release_version: string;
  sections: ManualSection[];
  content: string;
  captured_at: string;
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
  markers?: Array<{ time: number; position: "aboveBar" | "belowBar" | "inBar"; color: string; shape: "circle" | "square" | "arrowUp" | "arrowDown"; text: string; kind?: string }>;
  captured_at: string;
}

export interface SettingField {
  path: string;
  label: string;
  group: string;
  section: "general" | "exchange_selection" | "exchange_api" | "ai_engine" | "notifications" | "advanced" | "alpha" | "system" | "update";
  presentation: "primary" | "advanced";
  kind: "boolean" | "integer" | "number" | "percent_fraction" | "select" | "model_select" | "multiselect" | "text" | "json";
  help: string;
  minimum: number | null;
  maximum: number | null;
  options: string[];
  risk: "normal" | "high" | "critical";
  value: boolean | number | string | string[] | null | { configured: boolean; write_only: true };
  default_value?: boolean | number | string | string[] | Record<string, unknown> | null;
}

export interface SettingsSnapshot {
  schema_version: string;
  revision: string;
  account_scope: string;
  fields: SettingField[];
  credential_status: Record<string, boolean>;
  storage_status?: { ok?: boolean; encoding?: string; needs_normalization?: boolean; code?: string; error_type?: string };
  credential_field_status?: Record<string, Record<string, boolean>>;
  model_catalogs?: Record<string, { chat_text: string[]; chat_json: string[]; transcribe: string[] }>;
  model_catalog_details?: Record<string, Array<{
    model: string;
    status: string;
    status_label: string;
    capabilities: string[];
    replacement?: string;
    note?: string;
    use: string;
    strength: string;
    limitation: string;
    input_per_mtok_usd?: number | null;
    output_per_mtok_usd?: number | null;
  }>>;
  model_catalog_meta?: {
    model_as_of: string;
    price_as_of: string;
    pricing_urls: Record<string, string>;
    account_availability_requires_check: boolean;
    price_basis: string;
    billing_truth: string;
  };
  apply_plan?: Record<string, boolean>;
  runtime_refresh?: { ok: boolean; restart_required: boolean; error_code?: string };
  save_receipt?: { verified: boolean; requested_paths: string[]; revision: string };
  coverage?: { template_top_level: number; editable_top_level: number; editable_fields?: number; excluded: Record<string, string>; protected_paths?: Record<string, string>; managed_nested?: Record<string, string> };
}

export interface SettingsBackup {
  name: string;
  created_at: string;
  size: number;
}

export interface SettingsBackupsSnapshot {
  schema_version: string;
  backups: SettingsBackup[];
  captured_at: string;
}

export interface StrategyVersion {
  strategy_key: string;
  version_id: string;
  version: number;
  name: string;
  status: string;
  created_at?: string;
  updated_at?: string;
  missing_conditions: string[];
  xai: { summary?: string; risks?: string[]; guardrails?: string[] };
  rules: Record<string, any>;
  guidance: Record<string, any>;
  paper_validation?: Record<string, any> | null;
  paper_progress?: {
    trades: number;
    observation_days: number;
    required_trades: number;
    required_days: number;
    observing: boolean;
  };
  paper_evidence_by_venue?: Array<{
    exchange: string;
    quote_currency: string;
    recorded_trades: number;
    valid_trades: number;
    unverified_trades: number;
    wins: number;
    losses: number;
    breakeven: number;
    win_rate: number | null;
    net_pnl: number;
    fees: number;
    estimated_taxes: number;
    estimated_slippage: number;
    total_cost: number;
    estimated_cost_trades: number;
    recovered_cost_trades: number;
    cost_policy_issue_trades: number;
    unavailable_cost_trades: number;
    first_closed_at?: string | null;
    last_closed_at?: string | null;
  }>;
  venue_compatibility?: Array<{
    venue: string;
    market_type: string;
    status: "compatible" | "partial" | "blocked";
    requested_directions: string[];
    supported_directions: string[];
    reason: string;
  }>;
  execution_validation?: Record<string, any> | null;
  validation_lab?: Record<string, any> | null;
  ir_hash?: string;
  source_kind?: string;
  source_reference?: string;
  paper_observing?: boolean;
  paper_observation_started_at?: string;
  paper_observation_stopped_at?: string;
  paper_observation_windows?: Array<{ started_at: string; stopped_at?: string | null }>;
  paper_validation_history?: Array<Record<string, any>>;
  paper_validation_attempt_history?: Array<Record<string, any>>;
  paper_execution_readiness?: {
    ready: boolean;
    document_ready?: boolean;
    signal_mode: string;
    entry_signal: string;
    entry_directions?: string[];
    has_executable_entry: boolean;
    validation_subject?: "custom_entry_logic" | "noah_base_with_custom_risk_exit" | "source_preserved_not_executable";
    source_strategy_logic_executed?: boolean;
    historical_validation_applicable?: boolean;
    historical_validation_reason?: "custom_entry_rules_available" | "noah_base_entry_requires_forward_paper" | string;
    exit_policy_mode?: string;
    has_explicit_exit_rates?: boolean;
    reasons: string[];
  };
  execution_readiness?: StrategyVersion["paper_execution_readiness"];
  validation_subject?: string;
  version_diff?: { changes?: Array<{ path?: string; before?: unknown; after?: unknown }> };
  strategy_ir?: Record<string, any>;
  active: boolean;
}

export interface StrategyGroup {
  scope: "binance" | "unified";
  strategy_key: string;
  versions: StrategyVersion[];
}

export interface StrategyCatalog {
  schema_version: string;
  strategies: StrategyGroup[];
  paper_outcomes?: Array<Record<string, any>>;
  captured_at: string;
}

export interface LogSnapshot {
  schema_version: string;
  source: string;
  lines: Array<{ source: string; message: string; level?: string; exchange?: string; category?: "trade" | "analysis" | "learning" | "system" | string }>;
  captured_at: string;
}

export interface LifeFinanceSnapshot {
  schema_version: string;
  summary: Record<string, any>;
  transactions: Array<Record<string, any>>;
  goals: Array<Record<string, any>>;
  captured_at: string;
}

export interface WorkspaceSnapshot {
  schema_version: string;
  service: string;
  feature: string;
  source: string;
  captured_at: string;
  freshness: string;
  membership_access?: {
    exchange: string;
    status: string;
    label: string;
    allowed: boolean;
    reason?: string;
    referral_url?: string;
    uid_masked?: string;
  };
  paper_trades?: Array<Record<string, any>>;
  paper_positions?: Array<Record<string, any>>;
  paper_positions_status?: string;
  active_custom_strategies?: Array<{
    id?: string;
    name?: string;
    strategy_key?: string;
    version_id?: string;
    operation_mode?: string;
  }>;
  paper_position_policy?: {
    mode: "focus" | "multi";
    limit: number;
    scope: "per_exchange_adapter";
  };
  paper_statistics?: {
    closed_count: number;
    recorded_count?: number;
    unverified_count?: number;
    winning_count: number;
    win_rate: number | null;
    net_pnl: number;
    fees: number;
    pnl_by_currency?: Record<string, number>;
    fees_by_currency?: Record<string, number>;
    recent_window_limit: number;
    window_limited: boolean;
  };
  data_scope?: { mode: string; source: string; unscoped_records_included: boolean };
  trading?: {
    execution_mode?: "live" | "paper";
    open_position_count: number;
    closed_count: number;
    reconciled_closed_count?: number;
    unresolved_closed_count?: number;
    win_rate: number;
    pnl_by_currency: Record<string, number>;
    gross_pnl_by_currency?: Record<string, number>;
    recent_trades: Array<Record<string, any>>;
    schema_compatible: boolean;
    error: string;
    range?: StatisticsRange;
  };
  trading_statistics?: {
    asset_class: string;
    filter_source: string;
    closed_count: number;
    reconciled_closed_count?: number;
    unresolved_closed_count?: number;
    execution_count: number;
    display_trade_count: number;
    execution_history_available: boolean;
    execution_history_status: string;
    execution_history_reason: string;
    win_rate: number;
    pnl_by_currency: Record<string, number>;
    fees_by_currency: Record<string, number>;
    notional_by_currency: Record<string, number>;
    avg_hold_minutes: number | null;
    valid_hold_count: number;
    groups: Array<Record<string, any>>;
    execution_rows: Array<Record<string, any>>;
    schema_compatible: boolean;
    error: string;
    range?: StatisticsRange;
    execution_mode?: "live" | "paper";
    recorded_count?: number;
    unverified_count?: number;
    ledger_authority?: "trade_log" | "strategy_paper_outcomes.jsonl";
    execution_authority?: "exchange_execution_log" | "trade_log" | "paper_virtual_fill_ledger";
    legacy_execution_modes_mapped_to_live?: string[];
    legacy_unattributed_count?: number;
  };
  period_statistics?: WorkspaceSnapshot["trading_statistics"];
  statistics_view?: {
    period?: "today" | "7d" | "30d" | "all" | "custom";
    custom_start?: string | null;
    custom_end?: string | null;
    scope?: string;
    baseline_at?: string | null;
    active?: boolean;
    records_deleted?: false;
    learning_preserved?: true;
    paper_preserved?: true;
    risk_ledgers_preserved?: true;
    execution_mode?: "live" | "paper";
  };
  report_periods?: {
    asset_class: string;
    source: string;
    execution_history_available: boolean;
    execution_history_status: string;
    execution_history_reason: string;
    error?: string;
    periods: Record<string, {
      started_at: string;
      ended_at: string;
      closed_count: number;
      reconciled_closed_count?: number;
      unresolved_closed_count?: number;
      winning_count: number;
      losing_count: number;
      win_rate: number;
      pnl_by_currency: Record<string, number>;
      fees_by_currency: Record<string, number>;
      execution_count: number;
      execution_notional_by_currency: Record<string, number>;
      linked_closed_count: number;
      unlinked_closed_count: number;
      legacy_unknown_count: number;
      execution_history_available: boolean;
      execution_history_status: string;
      execution_history_reason: string;
      detail_rows?: Array<Record<string, any>>;
      detail_total_count?: number;
      detail_offset?: number;
      detail_limit?: number;
      detail_has_more?: boolean;
      detail_checksum?: {
        closed_count: number;
        pnl_by_currency: Record<string, number>;
        fees_by_currency: Record<string, number>;
      };
      ledger_reconciled?: boolean;
    }>;
  };
  stock_trading_statistics?: {
    asset_class: "stock";
    filter_source: string;
    data_source: "stock_trade_stats";
    period_days: number;
    cross_service_data_included: false;
    brokers: Array<{
      broker: string;
      total_trades: number;
      buy_count: number;
      sell_count: number;
      today_count: number;
      open_orders_count: number;
      realized_pnl: number;
      win_rate: number;
      avg_pnl: number;
      max_drawdown: number;
      details: Array<Record<string, any>>;
      execution_quality?: Record<string, number>;
    }>;
  };
  statistics?: Array<Record<string, any>>;
  execution?: Array<Record<string, any>>;
  execution_quality?: {
    status: string;
    source?: string;
    rows: Array<Record<string, any>>;
    message?: string;
    read_only: boolean;
  };
  learning?: Record<string, any>;
  ai_decisions?: Array<Record<string, any>>;
  ai_analysis?: Array<Record<string, any>>;
  analysis_log?: Array<Record<string, any>>;
  risk?: Array<Record<string, any>>;
  selected_coins?: Array<Record<string, any>>;
  portfolio?: Record<string, any>;
  scenario?: {
    available_currencies?: string[];
    policy_source: string;
    trade_source: string;
    read_only: boolean;
    policy: { buy_threshold: number; sell_threshold: number; interval_minutes: number; max_positions: number; risk_guard_enabled: boolean; threshold_scale?: number };
    scopes: Record<string, { live_history_evidence?: import("./components/LiveHistoryEvidence").LiveHistoryEvidenceData; asset_class: string; sample_count: number; currencies?: string[]; currency_mixed?: boolean; schema_compatible: boolean; error: string; scenarios: Array<Record<string, any>> }>;
  };
}

export interface StatisticsRange {
  period: "today" | "7d" | "30d" | "all" | "custom";
  started_at?: string | null;
  ended_at: string;
  baseline_at?: string | null;
  baseline_applied: boolean;
}
