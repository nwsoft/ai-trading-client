import { getLocale } from './i18n';
import type {
  CandleSnapshot,
  FeatureInventory,
  LifeFinanceSnapshot,
  LogSnapshot,
  ManualSnapshot,
  PlatformContract,
  RuntimeSnapshot,
  SettingsSnapshot,
  SettingsBackupsSnapshot,
  StrategyCatalog,
  WorkspaceSnapshot,
  SessionSnapshot,
} from "./types";

export interface GatewayClient {
  recordRecovery: (source: string, start?: boolean) => Promise<Record<string, any>>;
  storageMaintenance: (action?: 'optimize' | 'debug', hours?: number) => Promise<Record<string, any>>;
  displayPreferences: () => Promise<{locale: string; saved: boolean}>;
  saveDisplayPreferences: (locale: string) => Promise<{locale: string; saved: boolean}>;
  remoteStatus: () => Promise<Record<string, any>>;
  configureRemote: (enabled: boolean, name: string, allowPause?: boolean, allowControl?: boolean, shareDetails?: boolean) => Promise<Record<string, any>>;
  resumeEntries: (source: string) => Promise<Record<string, any>>;
  platform: () => Promise<PlatformContract>;
  session: () => Promise<SessionSnapshot>;
  login: (username: string, password: string) => Promise<SessionSnapshot>;
  features: () => Promise<FeatureInventory>;
  manual: () => Promise<ManualSnapshot>;
  runtime: () => Promise<RuntimeSnapshot>;
  refreshAccounts: (sources: string[], forceRefresh?: boolean) => Promise<Record<string, any>>;
  workspace: (service: string, feature: string, source?: string, paging?: { offset?: number; limit?: number; reportPeriod?: "today" | "week" | "month" | "realtime"; reportOffset?: number; reportLimit?: number; statisticsPeriod?: "today" | "7d" | "30d" | "all" | "custom"; statisticsStart?: string; statisticsEnd?: string; statisticsMode?: "live" | "paper"; statisticsCurrency?: string }) => Promise<WorkspaceSnapshot>;
  updateStatisticsBaseline: (service: "blockchain" | "stock", source: string, action: "set" | "clear") => Promise<Record<string, any>>;
  candles: (symbol: string, interval: string, limit?: number, source?: string, marketType?: string) => Promise<CandleSnapshot>;
  marketSentiment: (symbol?: string) => Promise<Record<string, any>>;
  stockOverview: (symbols?: string[]) => Promise<Record<string, any>>;
  settings: () => Promise<SettingsSnapshot>;
  settingsDiagnostics: () => Promise<Record<string, any>>;
  checkAIProvider: (provider: string, model?: string, capability?: "chat_text" | "chat_json" | "vision" | "transcribe") => Promise<Record<string, any>>;
  settingsBackups: () => Promise<SettingsBackupsSnapshot>;
  restoreSettings: (expectedRevision: string, backupName: string) => Promise<SettingsSnapshot>;
  updateSettings: (expectedRevision: string, changes: Record<string, unknown>) => Promise<SettingsSnapshot>;
  updateCredentials: (expectedRevision: string, provider: string, values: Record<string, string>) => Promise<SettingsSnapshot>;
  notificationStatus: () => Promise<Record<string, any>>;
  testNotification: (channel: "discord" | "telegram") => Promise<Record<string, any>>;
  discoverTelegramChats: () => Promise<Record<string, any>>;
  sendReportNotification: (title: string, message: string, source?: string) => Promise<Record<string, any>>;
  notifyUpdateAvailable: (version: string, currentVersion?: string) => Promise<Record<string, any>>;
  stockSearchProfile: () => Promise<Record<string, any>>;
  stockSuggestions: (source: string, query?: string, assetMode?: "all" | "stock" | "etf") => Promise<Record<string, any>>;
  updateStockSearchProfile: (action: "recent_add" | "favorite_toggle" | "watchlist_add", symbol: string) => Promise<Record<string, any>>;
  strategies: () => Promise<StrategyCatalog>;
  deleteStrategy: (scope: string, strategyKey: string, versionId?: string) => Promise<Record<string, unknown>>;
  submitStrategy: (payload: Record<string, unknown>) => Promise<Record<string, unknown>>;
  strategyAction: (payload: Record<string, unknown>) => Promise<Record<string, unknown>>;
  runHistoricalValidation: (payload: Record<string, unknown>) => Promise<Record<string, unknown>>;
  analyzeStrategySource: (payload: Record<string, unknown>) => Promise<Record<string, any>>;
  validateStrategyDraft: (payload: Record<string, unknown>) => Promise<Record<string, any>>;
  strategyMentor: (profile: Record<string, unknown>) => Promise<Record<string, any>>;
  exportStrategyPackage: (scope: string, strategyKey: string, versionId: string) => Promise<Record<string, any>>;
  exportStrategyExecutionEvidence: (scope: string, strategyKey: string, versionId: string) => Promise<Record<string, any>>;
  importStrategyPackage: (scope: string, fileName: string, strategyPackage: Record<string, unknown>) => Promise<Record<string, unknown>>;
  lifeFinance: () => Promise<LifeFinanceSnapshot>;
  addLifeTransaction: (payload: Record<string, unknown>) => Promise<Record<string, unknown>>;
  deleteLifeTransaction: (id: string) => Promise<Record<string, unknown>>;
  addLifeGoal: (payload: Record<string, unknown>) => Promise<Record<string, unknown>>;
  addLifeGoalSavings: (id: string, amount: number) => Promise<Record<string, unknown>>;
  deleteLifeGoal: (id: string) => Promise<Record<string, unknown>>;
  logs: (service?: "blockchain" | "stock", source?: string, lines?: number) => Promise<LogSnapshot>;
  runtimeCommand: (command: "trading.start" | "trading.stop" | "coins.select" | "coins.analyze" | "stocks.analyze" | "trades.import", source: string, closeAll?: boolean, symbol?: string, liveConfirmation?: boolean) => Promise<Record<string, unknown>>;
  askAssistant: (question: string, service: string, explanationLevel: "beginner" | "standard" | "advanced", mode?: "guide" | "deep_analysis", recentMessages?: Array<{ role: "user" | "assistant"; content: string }>, settingsSection?: string, dataScope?: "private" | "public_general", consultation?: { conversation_kind: "strategy"; strategy_service: "blockchain" | "stock"; strategy_preferences: Record<string, string> }) => Promise<Record<string, any>>;
  assistantStatus: () => Promise<Record<string, any>>;
  analyzeChart: (fileName: string, imageDataUrl: string, service: "blockchain" | "stock" | "portfolio" | "ai_analyst") => Promise<Record<string, any>>;
  auditExport: () => Promise<Record<string, any>>;
  financialIntelligence: (service: "blockchain" | "stock" | "ai_analyst") => Promise<Record<string, any>>;
  refreshFinancialMarket: (service: "blockchain" | "stock" | "ai_analyst", useNetwork?: boolean, universe?: Array<Record<string, unknown>>) => Promise<Record<string, any>>;
  runFinancialIntelligence: (service: "blockchain" | "stock" | "ai_analyst", action: string, payload?: Record<string, unknown>) => Promise<Record<string, any>>;
  portfolioAnalysis: (mode?: "live" | "paper") => Promise<Record<string, any>>;
  savePortfolioSnapshot: () => Promise<Record<string, any>>;
  alphaArena: () => Promise<Record<string, any>>;
  alphaArenaCommand: (action: "start" | "stop", liveConfirmation?: boolean) => Promise<Record<string, any>>;
  lifeFinanceAnalysis: () => Promise<Record<string, any>>;
  financeProducts: () => Promise<Record<string, any>>;
  compareFinanceProduct: (payload: Record<string, unknown>) => Promise<Record<string, any>>;
  calculateLifeTax: (payload: Record<string, unknown>) => Promise<Record<string, any>>;
}

function bootstrap(): NoahAIBootstrap {
  if (window.noahAI) {
    return window.noahAI.bootstrap();
  }
  return {
    gatewayUrl: import.meta.env.VITE_GATEWAY_URL || window.location.origin,
    gatewayToken: import.meta.env.VITE_GATEWAY_TOKEN || "",
    desktop: false,
  };
}

const GATEWAY_ERROR_MESSAGES: Record<string, string> = {
  gateway_authentication_required: "로그인 세션을 다시 확인하세요.",
  login_service_unavailable: "로그인 서비스를 사용할 수 없습니다. 잠시 후 다시 시도하세요.",
  invalid_login_response: "로그인 응답을 확인하지 못했습니다. 잠시 후 다시 시도하세요.",
  invalid_credentials: "아이디 또는 패스워드를 확인하세요.",
  settings_revision_conflict: "다른 화면에서 설정이 변경되었습니다. 설정을 다시 불러온 뒤 저장하세요.",
  interactive_ai_budget_exceeded: "오늘 또는 이번 달의 외부 AI 호출 한도에 도달했습니다. 이는 Provider 호출 전 NoahAI 비용 보호이며 회원·거래 제한이나 Provider 자체 429가 아닙니다. 일반 안내와 앱 내부 전략 규칙 분석은 계속 사용할 수 있습니다. 설정 → AI 엔진/API → AI 비용 관리에서 사용량·한도를 확인하세요. 일일 한도는 UTC 00:00(한국시간 09:00)에 갱신됩니다.",
};

export function userFacingGatewayError(detail: unknown, status: number): string {
  if (typeof detail !== "string" || !detail.trim()) {
    return `요청을 처리하지 못했습니다. 다시 시도하세요. (상태 ${status})`;
  }
  const normalized = detail.trim();
  const brokerReasons: Record<string, string> = {
    non_main_thread_init: "키움 연결 모듈이 잘못된 실행 스레드에서 시작됐습니다. 최신 엔진으로 재시작하고 지원 로그를 확인하세요.",
    kiwoom_rpc_timeout: "키움 로그인/조회 응답 시간이 초과되어 연결 프로세스를 종료했습니다. 주문 중이었다면 주문내역을 먼저 대조한 뒤 다시 연결하세요.",
    kis_credentials_missing: "KIS 앱키·앱시크릿이 없습니다. 설정 → 한국투자증권 API에 입력하세요.",
    kis_account_format_invalid: "KIS 계좌번호의 계좌 8자리와 상품코드 2자리를 확인하세요.",
    kis_token_unavailable: "KIS 인증 토큰을 받지 못했습니다. 실전/모의 서버 선택과 API 키를 확인하고, 토큰 발급 제한이면 1분 뒤 다시 시도하세요.",
  };
  for (const [reason, message] of Object.entries(brokerReasons)) {
    if (normalized.includes(reason)) return message;
  }
  if (GATEWAY_ERROR_MESSAGES[normalized]) return GATEWAY_ERROR_MESSAGES[normalized];
  const [code, source = ""] = normalized.split(":", 2);
  if (code === "settings_save_failed") {
    const saveMessages: Record<string, string> = {
      permission_denied: "설정 파일 쓰기 권한이 없습니다. Windows 문서 폴더 보호 또는 보안 프로그램의 NoahAI 허용 여부를 확인하세요. (지원 코드: permission_denied)",
      file_locked: "설정 파일이 다른 프로그램이나 동기화 도구에 사용 중입니다. 모든 NoahAI 창을 종료한 뒤 한 번만 실행하고 다시 저장하세요. (지원 코드: file_locked)",
      concurrent_writer_timeout: "다른 NoahAI 엔진이 설정 파일을 사용 중입니다. 모든 NoahAI 창을 종료한 뒤 한 번만 실행하세요. (지원 코드: concurrent_writer_timeout)",
      disk_full: "저장 공간이 부족해 설정을 저장하지 못했습니다. 여유 공간을 확보한 뒤 다시 시도하세요. (지원 코드: disk_full)",
      path_unavailable: "사용자 설정 폴더를 찾거나 열지 못했습니다. Documents/NoahAI 계정 폴더와 동기화 상태를 확인하세요. (지원 코드: path_unavailable)",
      path_too_long: "Windows 사용자 설정 경로가 너무 깁니다. Documents/NoahAI 기본 경로를 사용하세요. (지원 코드: path_too_long)",
      read_only: "설정 파일 또는 폴더가 읽기 전용입니다. 쓰기 권한을 복구한 뒤 다시 저장하세요. (지원 코드: read_only)",
      settings_file_unreadable: "기존 settings.json의 문자 인코딩 또는 JSON 형식을 읽을 수 없어 원본 보호를 위해 저장을 중단했습니다. 설정 백업에서 복구하거나 지원 로그를 전달해 주세요. API 키가 들어 있을 수 있으므로 파일을 삭제하지 마세요. (지원 코드: settings_file_unreadable)",
      invalid_settings_data: "저장할 설정 데이터 형식이 올바르지 않습니다. 지원 로그의 settings.write_failed 항목을 전달해 주세요. (지원 코드: invalid_settings_data)",
      verification_failed: "설정 파일을 쓴 뒤 재확인한 값이 일치하지 않습니다. 화면의 변경 내용은 유지됩니다. 실행 중인 구버전 NoahAI를 모두 종료한 뒤 다시 저장하세요. (지원 코드: verification_failed)",
      write_failed: "설정 파일을 저장하지 못했습니다. 지원 로그의 settings.write_failed 항목을 전달해 주세요. (지원 코드: write_failed)",
    };
    return saveMessages[source] ?? saveMessages.write_failed;
  }
  const chartMessages: Record<string, string> = {
    chart_analysis_service_invalid: "이 서비스에서는 차트 스크린샷 분석을 사용할 수 없습니다.",
    chart_image_format_invalid: "PNG, JPG 또는 WEBP 차트 이미지를 선택하세요.",
    chart_image_decode_failed: "차트 이미지 파일을 읽지 못했습니다. 다른 파일로 다시 시도하세요.",
    chart_image_size_invalid: "차트 이미지는 8MB 이하만 분석할 수 있습니다.",
    chart_image_signature_invalid: "확장자와 실제 이미지 형식이 일치하지 않습니다.",
    chart_ai_credential_required: `${source.toUpperCase() || "Analyst"} 비전 AI API 키를 설정하고 연결을 점검하세요.`,
    chart_vision_not_supported: `${source.toUpperCase() || "선택한 Provider"} 모델은 이미지 분석을 지원하지 않습니다. OpenAI·Kimi·Gemini의 비전 지원 모델을 선택하세요.`,
    chart_analysis_provider_failed: "비전 AI가 차트 분석 결과를 반환하지 못했습니다. 모델과 API 연결 상태를 확인하세요.",
  };
  if (chartMessages[code]) return chartMessages[code];
  const sourceLabel = source ? source.toUpperCase() : "선택한 연결";
  const runtimeMessages: Record<string, string> = {
    membership_exchange_approval_required: `${sourceLabel}은 현재 계정에 승인되지 않은 해외 거래소입니다. daltrading에서 레퍼럴 UID 승인 상태를 확인하거나 관리자에게 거래소 권한 승인을 요청하세요. API 키 인증 완료와 거래 권한은 별개입니다.`,
    membership_exchange_not_approved: `${sourceLabel} 거래 권한이 현재 계정에 없습니다. daltrading의 거래소 승인 상태를 확인하거나 관리자에게 승인을 요청하세요. API 키 인증 완료와 거래 권한은 별개입니다.`,
    membership_exchange_approval_pending: `${sourceLabel} 레퍼럴 UID 승인을 확인 중입니다. 승인 완료 전에는 거래 엔진을 시작할 수 없습니다. daltrading 승인 상태를 확인하거나 관리자에게 문의하세요.`,
    membership_exchange_approval_rejected: `${sourceLabel} 레퍼럴 귀속 승인이 거절되었습니다. daltrading에 등록한 UID와 가입 경로를 확인한 뒤 관리자에게 재검토를 요청하세요.`,
    membership_exchange_approval_expired: `${sourceLabel} 레퍼럴 승인이 만료되었습니다. daltrading에서 재승인을 요청하거나 관리자에게 문의하세요.`,
    membership_exchange_activation_pending: `${sourceLabel} UID 승인은 확인됐지만 거래소 운영 권한이 아직 활성화되지 않았습니다. 관리자에게 거래소 활성화를 요청하세요.`,
    membership_crypto_plan_required: `${sourceLabel} 코인 거래는 현재 회원등급의 이용 범위가 아닙니다. 코인 이용 권한이 있는 계정으로 로그인하거나 회원등급을 확인하세요.`,
    membership_stock_plan_required: `${sourceLabel} 주식·ETF 거래는 현재 회원등급의 이용 범위가 아닙니다. 주식 이용 권한이 있는 계정으로 로그인하거나 회원등급을 확인하세요.`,
    membership_session_inactive: "회원 세션 또는 라이선스가 비활성 상태입니다. 다시 로그인한 뒤 계속되면 관리자에게 계정 상태 확인을 요청하세요.",
    membership_source_unsupported: `${sourceLabel}은 현재 지원되는 거래 기관이 아닙니다.`,
    credential_required: `${sourceLabel} API 인증 정보를 설정한 뒤 연결을 확인하세요.`,
    live_start_confirmation_required: "LIVE 실제 주문 시작 확인이 필요합니다. 현재 모드와 주문 대상 범위를 다시 확인한 뒤 시작 버튼을 사용하세요.",
    runtime_source_not_enabled: `${sourceLabel}는 분석·학습·주문 대상 범위에 없습니다. 설정에서 사용할 대상을 먼저 활성화하세요.`,
    stock_source_not_enabled: `${sourceLabel} 증권사가 사용 설정되어 있지 않습니다. 설정 → 거래소 선택에서 증권사를 활성화하세요.`,
    stock_adapter_unavailable: `${sourceLabel} 증권 연결 모듈을 사용할 수 없습니다. 설치 및 API 유형을 확인하세요.`,
    stock_connection_failed: `${sourceLabel} 증권사 연결에 실패했습니다. 계정 정보와 연결 상태를 확인하세요.`,
    stock_candles_unsupported: `${sourceLabel} 연결은 현재 일봉 조회를 지원하지 않습니다.`,
    stock_candles_unavailable: `${sourceLabel}에서 해당 종목의 일봉을 받지 못했습니다. 종목코드와 장 운영 상태를 확인하세요.`,
    local_runtime_encoding_error: "거래소 요청 전에 Windows 로컬 엔진의 문자 인코딩 처리에 실패했습니다. API 키나 거래소 권한 오류가 아닙니다. NoahAI를 UTF-8 런타임 패치 버전으로 업데이트하세요.",
    exchange_client_unavailable: `${sourceLabel} 거래소 연결을 사용할 수 없습니다. API 설정을 확인하세요.`,
    trade_history_unavailable: `${sourceLabel} 연결은 거래내역 가져오기를 지원하지 않습니다.`,
    discord_webhook_invalid: "Discord 웹훅 주소 형식이 올바르지 않습니다. Discord 채널 설정에서 새 웹훅 URL을 복사하세요.",
    telegram_token_invalid: "Telegram 봇 토큰 형식이 올바르지 않습니다. BotFather가 발급한 토큰을 다시 복사하세요.",
    telegram_chat_id_invalid: "Telegram 대화방 ID 형식이 올바르지 않습니다. 대화방 자동 찾기를 사용하세요.",
    telegram_chat_id_missing: "Telegram에서 봇에 Start 또는 /start를 보낸 뒤 대화방 자동 찾기를 실행하세요.",
    notification_credential_rejected: "알림 서비스가 연결 정보를 거부했습니다. 새 웹훅 또는 봇 토큰을 발급해 다시 저장하세요.",
    notification_rate_limited: "알림 서비스의 호출 제한에 도달했습니다. 잠시 뒤 다시 테스트하세요.",
    notification_network_error: "알림 서비스에 연결하지 못했습니다. 인터넷 연결과 방화벽을 확인하세요.",
    notification_remote_error: "알림 서비스가 요청을 처리하지 못했습니다. 잠시 뒤 다시 테스트하세요.",
    notification_response_invalid: "알림 서비스의 응답 형식을 확인하지 못했습니다.",
    notification_channel_not_enabled: "설정에서 외부 알림과 하나 이상의 채널을 ON으로 저장한 뒤 다시 시도하세요.",
  };
  if (runtimeMessages[code]) return runtimeMessages[code];
  if (/[가-힣]/.test(normalized) || /\s/.test(normalized)) return normalized;
  return `요청을 처리하지 못했습니다. 다시 시도하세요. (상태 ${status})`;
}

export function createGatewayClient(): GatewayClient {
  const configuration = bootstrap();
  const baseUrl = configuration.gatewayUrl.replace(/\/$/, "");

  async function request(input: string, init: RequestInit, timeoutMs: number): Promise<Response> {
    const controller = new AbortController();
    let timedOut = false;
    const timer = window.setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, Math.max(1_000, timeoutMs));
    try {
      return await fetch(input, { ...init, signal: controller.signal });
    } catch (reason) {
      if (timedOut || (reason instanceof DOMException && reason.name === "AbortError")) {
        throw new Error("요청 응답 시간이 초과되었습니다. 마지막 정상 상태를 유지하고 다음 갱신에서 다시 시도합니다.");
      }
      throw new Error("NoahAI 내부 서비스에 연결하지 못했습니다. 앱을 다시 시작한 뒤 다시 시도하세요.");
    } finally {
      window.clearTimeout(timer);
    }
  }

  async function get<T>(path: string, timeoutMs = 12_000): Promise<T> {
    if (!configuration.gatewayToken) {
      throw new Error("Gateway token이 없습니다. Electron 셸 또는 개발 환경 변수를 확인하세요.");
    }
    const response = await request(`${baseUrl}${path}`, {
      method: "GET",
      headers: { Authorization: `Bearer ${configuration.gatewayToken}`, 'X-NoahAI-Locale': getLocale() },
      cache: "no-store",
    }, timeoutMs);
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(userFacingGatewayError(payload.detail, response.status));
    }
    return (await response.json()) as T;
  }

  async function mutate<T>(method: "POST" | "DELETE", path: string, body: unknown, timeoutMs = 120_000): Promise<T> {
    if (!configuration.gatewayToken) {
      throw new Error("Gateway token이 없습니다. Electron 셸 또는 개발 환경 변수를 확인하세요.");
    }
    const response = await request(`${baseUrl}${path}`, {
      method,
      headers: {
        Authorization: `Bearer ${configuration.gatewayToken}`,
        "Content-Type": "application/json",
        "X-NoahAI-Intent": "confirmed",
        "X-NoahAI-Locale": getLocale(),
      },
      cache: "no-store",
      body: JSON.stringify(body),
    }, timeoutMs);
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(userFacingGatewayError(payload.detail, response.status));
    }
    return payload as T;
  }

  return {
    displayPreferences: () => get('/api/v1/display-preferences'),
    saveDisplayPreferences: (locale) => mutate('POST', '/api/v1/display-preferences', {locale}),
    platform: () => get<PlatformContract>("/api/v1/platform"),
    session: () => get<SessionSnapshot>("/api/v1/session"),
    login: (username, password) => mutate<SessionSnapshot>("POST", "/api/v1/session/login", { username, password }),
    features: () => get<FeatureInventory>("/api/v1/features"),
    manual: () => get<ManualSnapshot>("/api/v1/manual"),
    runtime: () => get<RuntimeSnapshot>("/api/v1/runtime/snapshot"),
    refreshAccounts: (sources, forceRefresh = false) => mutate<Record<string, any>>(
      "POST", "/api/v1/runtime/account-snapshot", { sources, force_refresh: forceRefresh }, 15_000,
    ),
    workspace: (service, feature, source = "", paging = {}) => get<WorkspaceSnapshot>(
      `/api/v1/workspaces/${encodeURIComponent(service)}/${encodeURIComponent(feature)}?source=${encodeURIComponent(source)}&learning_offset=${paging.offset ?? 0}&learning_limit=${paging.limit ?? 50}&report_period=${paging.reportPeriod ?? "today"}&report_offset=${paging.reportOffset ?? 0}&report_limit=${paging.reportLimit ?? 100}&statistics_period=${paging.statisticsPeriod ?? "today"}&statistics_start=${encodeURIComponent(paging.statisticsStart ?? "")}&statistics_end=${encodeURIComponent(paging.statisticsEnd ?? "")}&statistics_mode=${encodeURIComponent(paging.statisticsMode ?? "live")}&statistics_currency=${encodeURIComponent(paging.statisticsCurrency ?? "")}`,
    ),
    updateStatisticsBaseline: (service, source, action) => mutate<Record<string, any>>(
      "POST", "/api/v1/statistics/view-baseline", { service, source, action },
    ),
    candles: (symbol, interval, limit = 300, source = "binance", marketType = "spot") =>
      get<CandleSnapshot>(
        `/api/v1/market/candles?source=${encodeURIComponent(source)}&market_type=${encodeURIComponent(marketType)}&symbol=${encodeURIComponent(symbol)}&interval=${encodeURIComponent(interval)}&limit=${limit}`,
      ),
    stockOverview: (symbols = []) => get<Record<string, any>>(`/api/v1/market/stock-overview?symbols=${encodeURIComponent(symbols.join(","))}`),
    marketSentiment: (symbol = "BTCUSDT") =>
      get<Record<string, any>>(`/api/v1/market/sentiment?symbol=${encodeURIComponent(symbol)}`),
    settings: () => get<SettingsSnapshot>("/api/v1/settings"),
    settingsDiagnostics: () => get<Record<string, any>>("/api/v1/settings/diagnostics"),
    checkAIProvider: (provider, model = "", capability = "chat_text") =>
      mutate<Record<string, any>>("POST", "/api/v1/settings/ai-provider-check", { provider, model, capability }),
    settingsBackups: () => get<SettingsBackupsSnapshot>("/api/v1/settings/backups"),
    restoreSettings: (expectedRevision, backupName) =>
      mutate<SettingsSnapshot>("POST", "/api/v1/settings/restore", { expected_revision: expectedRevision, backup_name: backupName }),
    updateSettings: (expectedRevision, changes) =>
      mutate<SettingsSnapshot>("POST", "/api/v1/settings", { expected_revision: expectedRevision, changes }),
    updateCredentials: (expectedRevision, provider, values) =>
      mutate<SettingsSnapshot>("POST", "/api/v1/settings/credentials", { expected_revision: expectedRevision, provider, values }),
    remoteStatus: () => get<Record<string, any>>("/api/v1/remote/status"),
    configureRemote: (enabled, name, allowPause = false, allowControl = false, shareDetails = false) => mutate<Record<string, any>>("POST", "/api/v1/remote/configure", { enabled, name, allow_pause: allowPause, allow_control: allowControl, share_details: shareDetails }),
    resumeEntries: (source) => mutate<Record<string, any>>("POST", "/api/v1/remote/resume-entries", { source }),
    notificationStatus: () => get<Record<string, any>>("/api/v1/notifications/status"),
    testNotification: (channel) => mutate<Record<string, any>>("POST", "/api/v1/notifications/test", { channel }, 20_000),
    discoverTelegramChats: () => mutate<Record<string, any>>("POST", "/api/v1/notifications/telegram/discover", {}, 20_000),
    sendReportNotification: (title, message, source = "") => mutate<Record<string, any>>(
      "POST", "/api/v1/notifications/report", { title, message, source }, 15_000,
    ),
    notifyUpdateAvailable: (version, currentVersion = "") => mutate<Record<string, any>>(
      "POST", "/api/v1/notifications/update-available", { version, current_version: currentVersion }, 15_000,
    ),
    stockSearchProfile: () => get<Record<string, any>>("/api/v1/stocks/search-profile"),
    stockSuggestions: (source, query = "", assetMode = "all") => get<Record<string, any>>(`/api/v1/stocks/suggestions?source=${encodeURIComponent(source)}&query=${encodeURIComponent(query)}&asset_mode=${encodeURIComponent(assetMode)}`),
    updateStockSearchProfile: (action, symbol) =>
      mutate<Record<string, any>>("POST", "/api/v1/stocks/search-profile", { action, symbol }),
    strategies: () => get<StrategyCatalog>("/api/v1/strategies"),
    deleteStrategy: (scope, strategyKey, versionId) =>
      mutate<Record<string, unknown>>("DELETE", "/api/v1/strategies", {
        scope,
        strategy_key: strategyKey,
        version_id: versionId || null,
      }),
    submitStrategy: (payload) => mutate<Record<string, unknown>>("POST", "/api/v1/strategies", payload),
    strategyAction: (payload) => mutate<Record<string, unknown>>("POST", "/api/v1/strategies/actions", payload),
    runHistoricalValidation: (payload) => mutate<Record<string, unknown>>("POST", "/api/v1/strategies/historical-validation", payload),
    analyzeStrategySource: (payload) => mutate<Record<string, any>>("POST", "/api/v1/strategies/source-analysis", payload),
    validateStrategyDraft: (payload) => mutate<Record<string, any>>("POST", "/api/v1/strategies/draft-validation", payload),
    strategyMentor: (profile) => mutate<Record<string, any>>("POST", "/api/v1/strategies/mentor", { profile }),
    exportStrategyPackage: (scope, strategyKey, versionId) => get<Record<string, any>>(
      `/api/v1/strategies/${encodeURIComponent(scope)}/${encodeURIComponent(strategyKey)}/${encodeURIComponent(versionId)}/package`,
    ),
    exportStrategyExecutionEvidence: (scope, strategyKey, versionId) => get<Record<string, any>>(
      `/api/v1/strategies/${encodeURIComponent(scope)}/${encodeURIComponent(strategyKey)}/${encodeURIComponent(versionId)}/execution-evidence`,
    ),
    importStrategyPackage: (scope, fileName, strategyPackage) => mutate<Record<string, unknown>>(
      "POST", "/api/v1/strategies/package", { scope, file_name: fileName, package: strategyPackage },
    ),
    lifeFinance: () => get<LifeFinanceSnapshot>("/api/v1/life-finance"),
    addLifeTransaction: (payload) => mutate<Record<string, unknown>>("POST", "/api/v1/life-finance/transactions", payload),
    deleteLifeTransaction: (id) => mutate<Record<string, unknown>>("DELETE", `/api/v1/life-finance/transactions/${encodeURIComponent(id)}`, {}),
    addLifeGoal: (payload) => mutate<Record<string, unknown>>("POST", "/api/v1/life-finance/goals", payload),
    addLifeGoalSavings: (id, amount) => mutate<Record<string, unknown>>(
      "POST", `/api/v1/life-finance/goals/${encodeURIComponent(id)}/savings`, { amount },
    ),
    deleteLifeGoal: (id) => mutate<Record<string, unknown>>("DELETE", `/api/v1/life-finance/goals/${encodeURIComponent(id)}`, {}),
    logs: (service = "blockchain", source = "all", lines = 300) =>
      get<LogSnapshot>(`/api/v1/logs?service=${encodeURIComponent(service)}&source=${encodeURIComponent(source)}&lines=${lines}`),
    runtimeCommand: (command, source, closeAll = false, symbol = "", liveConfirmation = false) =>
      mutate<Record<string, unknown>>("POST", "/api/v1/runtime/commands", {
        command_id: crypto.randomUUID().replaceAll("-", ""),
        command,
        source,
        close_all: closeAll,
        symbol,
        live_confirmation: liveConfirmation,
      }),
    askAssistant: (question, service, explanationLevel, mode = "guide", recentMessages = [], settingsSection, dataScope = "private", consultation) =>
      mutate<Record<string, any>>("POST", "/api/v1/assistant/ask", {
        question,
        service,
        explanation_level: explanationLevel,
        mode,
        recent_messages: recentMessages,
        settings_section: service === "settings" ? settingsSection || null : null,
        data_scope: dataScope,
        ...consultation,
      }),
    assistantStatus: () => get<Record<string, any>>("/api/v1/assistant/status"),
    analyzeChart: (fileName, imageDataUrl, service) =>
      mutate<Record<string, any>>("POST", "/api/v1/assistant/chart-analysis", {
        file_name: fileName,
        image_data_url: imageDataUrl,
        service,
      }),
    auditExport: () => get<Record<string, any>>("/api/v1/audit/export"),
    financialIntelligence: (service) => get<Record<string, any>>(`/api/v1/financial-intelligence/${encodeURIComponent(service)}`),
    refreshFinancialMarket: (service, useNetwork = true, universe = []) => mutate<Record<string, any>>(
      "POST", "/api/v1/financial-intelligence/market", { service, use_network: useNetwork, universe },
    ),
    runFinancialIntelligence: (service, action, payload = {}) => mutate<Record<string, any>>(
      "POST", "/api/v1/financial-intelligence/action", { service, action, payload },
    ),
    recordRecovery: (source, start = false) => start
      ? mutate<Record<string, any>>("POST", "/api/v1/maintenance/trade-records", { source })
      : get<Record<string, any>>(`/api/v1/maintenance/trade-records?source=${encodeURIComponent(source)}`),
    storageMaintenance: (action, hours) => action
      ? mutate<Record<string, any>>('POST', '/api/v1/maintenance/storage', action === 'debug' ? { action, hours } : { action })
      : get<Record<string, any>>('/api/v1/maintenance/storage'),
    portfolioAnalysis: (mode = "live") => get<Record<string, any>>(`/api/v1/portfolio/analysis?statistics_mode=${mode}`),
    savePortfolioSnapshot: () => mutate<Record<string, any>>("POST", "/api/v1/portfolio/snapshot", {}),
    alphaArena: () => get<Record<string, any>>("/api/v1/alpha-arena"),
    alphaArenaCommand: (action, liveConfirmation = false) => mutate<Record<string, any>>(
      "POST", "/api/v1/alpha-arena/commands", {
        command_id: crypto.randomUUID().replaceAll("-", ""), action, live_confirmation: liveConfirmation,
      },
    ),
    lifeFinanceAnalysis: () => get<Record<string, any>>("/api/v1/life-finance/analysis"),
    financeProducts: () => get<Record<string, any>>("/api/v1/life-finance/products"),
    compareFinanceProduct: (payload) => mutate<Record<string, any>>("POST", "/api/v1/life-finance/products/compare", payload),
    calculateLifeTax: (payload) => mutate<Record<string, any>>("POST", "/api/v1/life-finance/tax", payload),
  };
}
