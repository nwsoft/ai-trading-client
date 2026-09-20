import { t, localized } from '../i18n';
import { useEffect, useMemo, useRef, useState } from "react";

import type { GatewayClient } from "../api";
import { CRYPTO_SOURCES, STOCK_SOURCES } from "../venueSources";
import { accountConnectionFailure } from "../accountConnection";
import type { PlatformContract, SettingField, SettingsBackup, SettingsSnapshot } from "../types";
import { UpdateCenter } from "./UpdateCenter";
import { RecordRecoveryPanel } from './RecordRecoveryPanel';
import { RemoteMonitorSettings } from "./RemoteMonitorSettings";
import { LanguagePicker } from './LanguagePicker';
import { STRATEGY_DIFFICULTY_PATH, strategyDifficultyLabel } from '../strategyDifficulty';

interface Props {
  client: GatewayClient;
  open: boolean;
  initialField?: string;
  onClose: () => void;
  onAskAssistant: (question: string, settingsSection?: string) => void;
  onOpenManual?: () => void;
  onSettingsSaved?: () => void | Promise<void>;
}

const SETTINGS_SECTIONS = [
  { id: "general", label: "일반", description: "PAPER/LIVE 운용 모드와 화면·로그 기본 동작을 확인합니다." },
  { id: "exchange_selection", label: "거래소 선택", description: "수집·분석·학습 범위와 실제 주문 실행 범위를 분리해 선택합니다." },
  { id: "exchange_api", label: "거래소 API", description: "거래소·증권사 연결 정보를 write-only 방식으로 저장합니다." },
  { id: "ai_engine", label: "AI 엔진/API", description: "AI Provider, 설명 수준, 전략 스튜디오 런타임과 비용·호출 관련 설정입니다." },
  { id: "notifications", label: "알림·리포트", description: "Discord·Telegram 연결과 가드레일·시장국면·리포트 알림을 설정합니다." },
  { id: "advanced", label: "고급 매매 계층", description: "전략 엔진·위험·주문 가드레일을 근거가 있을 때만 조정합니다." },
  { id: "alpha", label: "AlphaArena", description: "여러 전략을 같은 조건에서 비교하는 연구·PAPER 기능을 설정합니다." },
  { id: "system", label: "AI 시스템 상태", description: "AI·로그·화면 시스템 상태와 진단용 설정을 확인합니다." },
  { id: "update", label: "업데이트", description: "자동 업데이트 정책과 배포 채널 관련 설정을 확인합니다." },
] as const;

type SettingsSectionId = (typeof SETTINGS_SECTIONS)[number]["id"];
type SettingsGuideProfile = "beginner" | "balanced" | "advanced";
type QuickStartAsset = "crypto" | "stock";

const QUICK_START_SOURCES: Record<QuickStartAsset, Array<{ id: string; label: string; detail: string }>> = {
  crypto: [
    { id: "binance", label: "바이낸스", detail: "USDT 선물" },
    { id: "upbit", label: "업비트", detail: "KRW 현물" },
    { id: "bithumb", label: "빗썸", detail: "KRW 현물" },
    { id: "coinone", label: "코인원", detail: "KRW 현물 · 실계좌 검증 전" },
    { id: "bybit", label: "바이비트", detail: "USDT 선물" },
    { id: "bitget", label: "비트겟", detail: "USDT 선물" },
    { id: "okx", label: "OKX", detail: "USDT 선물" },
  ],
  stock: [
    { id: "kiwoom", label: "키움증권", detail: "주식·ETF" },
    { id: "shinhan", label: "신한증권", detail: "주식·ETF" },
    { id: "miraeAsset", label: "미래에셋", detail: "주식·ETF" },
    { id: "koreaInvestment", label: "한국투자증권", detail: "주식·ETF" },
  ],
};

const SETTINGS_GUIDE_PROFILE_LABELS: Record<SettingsGuideProfile, string> = {
  beginner: "처음 사용 · 안전 우선",
  balanced: "일반 사용 · 균형",
  advanced: "숙련 사용자 · 상세 설명",
};

const MODEL_PROVIDER_PATHS: Record<string, string> = {
  "ai_provider_profiles.analyst.model": "ai_provider_profiles.analyst.provider",
  "ai_provider_profiles.assistant.model": "ai_provider_profiles.assistant.provider",
  "ai_data_routing.public_openai_model": "__openai_fixed__",
  "ai_model_roles.frequent_cheap.model": "ai_model_roles.frequent_cheap.provider",
  "ai_model_roles.standard.model": "ai_model_roles.standard.provider",
  "ai_model_roles.premium.model": "ai_model_roles.premium.provider",
};

const MODEL_CAPABILITIES: Record<string, "chat_text" | "chat_json" | "transcribe"> = {
  "ai_provider_profiles.analyst.model": "chat_json",
  "ai_provider_profiles.assistant.model": "chat_text",
  "ai_model_roles.frequent_cheap.model": "chat_json",
  "ai_model_roles.standard.model": "chat_json",
  "ai_model_roles.premium.model": "chat_json",
  "ai_custom_transcription.model": "transcribe",
};

function credentialProvidersForSection(section: SettingsSectionId): string[] {
  if (section === "ai_engine") return ["openai", "openai_shared", "deepseek", "kimi", "anthropic", "gemini"];
  if (section === "alpha") return ["alpha:deepseek"];
  if (section === "notifications") return ["notification:discord", "notification:telegram"];
  return ["binance", "upbit", "bithumb", "coinone", "bybit", "okx", "bitget", "stock:kiwoom", "stock:shinhan", "stock:miraeasset", "stock:kis"];
}

function normalizeValue(field: SettingField, value: unknown): unknown {
  if (field.kind === "boolean") return Boolean(value);
  if (field.kind === "integer") return Number.parseInt(String(value), 10);
  if (field.kind === "number" || field.kind === "percent_fraction") return Number(value);
  if (field.kind === "json") return typeof value === "string" ? JSON.parse(value) : value;
  if (field.kind === "multiselect") return Array.isArray(value) ? value.map(String) : [];
  return String(value);
}

const SETTING_OPTION_LABELS: Record<string, string> = {
  binance: "바이낸스 (Binance) · 선물",
  upbit: "업비트 (Upbit) · 현물",
  bithumb: "빗썸 (Bithumb) · 현물",
  coinone: "코인원 (Coinone) · KRW 현물 · 실계좌 검증 전",
  bybit: "바이비트 (Bybit) · 선물",
  okx: "OKX · 선물",
  bitget: "비트겟 (Bitget) · 선물",
  kiwoom: "키움증권 (Kiwoom) · 주식/ETF",
  shinhan: "신한증권 (Shinhan) · 주식/ETF",
  miraeAsset: "미래에셋 (MiraeAsset) · 주식/ETF",
  koreaInvestment: "한국투자증권 (KIS) · 주식/ETF",
  parallel: "선택한 거래소에서 각각 실행 (권장)",
  split: "총위험을 거래소별로 분할",
  best: "우선순위 한 곳만 실행",
  all: "통합",
  stock: "주식만",
  etf: "ETF만",
  keep_with_tp_sl: "기존 TP/SL 보호 유지",
  close_all: "NoahAI 소유 포지션만 청산",
  beginner: "초보자",
  standard: "일반 (권장)",
  advanced: "고급",
  laboratory: "실험실",
  lab: "실험실",
  saver: "절약형",
  premium: "정밀형",
  focus: "집중 운용",
  multi: "다중 포지션",
  ISOLATED: "격리 마진",
  CROSSED: "교차 마진",
  display_standard: "기본 · 1500×980 / 글자 100%",
  display_large: "크게 · 1680×1050 / 글자 112%",
  display_extra_large: "매우 크게 · 1920×1080 / 글자 125%",
  auto: "자동 (권장)",
  manual: "수동 고정 (전문가)",
  account_risk: "NoahAI 자동 위험관리 (권장)",
  manual_notional: "수동 목표 거래 금액",
  legacy_venue: "기존 거래소별 호환 (업데이트 보호)",
  LOW: "저변동장",
  NORMAL: "보통 시장",
  HIGH: "고변동장",
  defer: "업데이트 연기 (권장)",
  evaluate: "평가 계속 (권장)",
  block: "항상 차단",
  "10000": "만불 ($10,000)",
  "1000": "천불 ($1,000)",
  "100": "백불 ($100)",
  "deepseek-v4-flash": "DeepSeek V4 Flash · 자동 최신",
  "deepseek-v4-pro": "DeepSeek V4 Pro · 정밀형",
  "deepseek-v4-flash-vision-exp": "DeepSeek V4 Flash Vision · 실험형",
  "gpt-6-astra": "GPT-6 Astra · 최상위 정밀형",
  "gpt-5.6-luna": "GPT-5.6 Luna · 절약형",
  "gpt-5.6-terra": "GPT-5.6 Terra · 균형형",
  "gpt-5.6-sol": "GPT-5.6 Sol · 정밀형",
  "claude-haiku-4-5": "Claude Haiku 4.5 · 절약형",
  "claude-sonnet-5": "Claude Sonnet 5 · 균형형",
  "claude-opus-5": "Claude Opus 5 · 정밀형",
  "claude-fable-5-1": "Claude Fable 5.1 · 최상위 정밀형",
  "gemini-3.5-flash-lite": "Gemini 3.5 Flash-Lite · 절약형",
  "gemini-3.8-flash": "Gemini 3.8 Flash · 최신 균형형",
  "gemini-3.7-flash": "Gemini 3.7 Flash · 균형형",
  "gemini-3.6-flash": "Gemini 3.6 Flash · 호환형",
  "gemini-3.5-flash": "Gemini 3.5 Flash · 호환형",
};

const OFFICIAL_API_PORTALS: Record<string, { label: string; url: string }> = {
  openai: { label: "OpenAI API Projects", url: "https://platform.openai.com/settings/organization/projects" },
  openai_shared: { label: "OpenAI 공개 질문용 Project", url: "https://platform.openai.com/settings/organization/projects" },
  binance: { label: "Binance 개발자 문서", url: "https://developers.binance.com/en/docs/introduction" },
  upbit: { label: "Upbit Open API", url: "https://docs.upbit.com/kr" },
  bithumb: { label: "Bithumb API 문서", url: "https://apidocs.bithumb.com/" },
  coinone: { label: "Coinone API 문서", url: "https://docs.coinone.co.kr/" },
  bybit: { label: "Bybit API 문서", url: "https://bybit-exchange.github.io/docs/" },
  okx: { label: "OKX API 문서", url: "https://www.okx.com/docs-v5/en/" },
  bitget: { label: "Bitget API 문서", url: "https://www.bitget.com/api-doc/common/intro" },
  "stock:kiwoom": { label: "키움 REST API", url: "https://openapi.kiwoom.com/intro/serviceInfo" },
  "stock:kis": { label: "한국투자 Open API", url: "https://apiportal.koreainvestment.com/intro" },
  "stock:shinhan": { label: "신한투자증권", url: "https://www.shinhansec.com/" },
  "stock:miraeasset": { label: "미래에셋증권", url: "https://securities.miraeasset.com/" },
  "alpha:deepseek": { label: "DeepSeek API", url: "https://platform.deepseek.com/" },
};

function credentialFieldsForProvider(provider: string): string[] {
  if (provider === "notification:discord") return ["webhook_url"];
  if (provider === "notification:telegram") return ["bot_token", "chat_id"];
  if (provider === "alpha:deepseek") return ["api_key"];
  if (provider === "okx") return ["api_key", "secret_key", "passphrase"];
  if (provider === "bitget") return ["api_key", "secret_key", "password"];
  if (provider === "stock:kiwoom") return ["account_no", "password", "cert_password", "user_id"];
  if (provider.startsWith("stock:")) return ["app_key", "app_secret", "account_no", "password", "cert_password", "user_id"];
  if (["openai", "openai_shared", "deepseek", "kimi", "anthropic", "gemini"].includes(provider)) return ["api_key", "base_url"];
  return ["api_key", "secret_key"];
}

const CREDENTIAL_FIELD_LABELS: Record<string, string> = {
  api_key: "API 키",
  secret_key: "Secret 키",
  passphrase: "패스프레이즈",
  password: "비밀번호",
  cert_password: "인증서 비밀번호",
  account_no: "계좌번호",
  user_id: "사용자 ID",
  app_key: "App 키",
  app_secret: "App Secret",
  base_url: "API 주소(선택)",
  webhook_url: "Discord 웹훅 URL",
  bot_token: "Telegram 봇 토큰",
  chat_id: "Telegram 대화방 ID",
};

function credentialStatusKey(provider: string): string {
  return ["openai", "openai_shared", "deepseek", "kimi", "anthropic", "gemini"].includes(provider)
    ? `ai:${provider}`
    : provider;
}

function credentialProviderLabel(provider: string): string {
  if (provider === "openai") return "OpenAI · 기본 보호 Project";
  if (provider === "openai_shared") return "OpenAI · 공개 일반 질문용 Project";
  if (provider === "notification:discord") return "Discord 웹훅";
  if (provider === "notification:telegram") return "Telegram 봇";
  if (provider.startsWith("stock:")) return `증권 · ${provider.split(":")[1].toUpperCase()}`;
  if (provider === "alpha:deepseek") return "AlphaArena · DEEPSEEK";
  return provider.toUpperCase();
}

function downloadText(name: string, content: string) {
  const blob = new Blob([content], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = name;
  anchor.click();
  URL.revokeObjectURL(url);
}

export function SettingsCenter({ client, open, initialField, onClose, onAskAssistant, onOpenManual, onSettingsSaved }: Props) {
  const focusedTarget = useRef(false);
  const [snapshot, setSnapshot] = useState<SettingsSnapshot | null>(null);
  const [draft, setDraft] = useState<Record<string, unknown>>({});
  const [activeSection, setActiveSection] = useState<SettingsSectionId>("general");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [credentialProvider, setCredentialProvider] = useState("binance");
  const [credentialDrafts, setCredentialDrafts] = useState<Record<string, Record<string, string>>>({});
  const [showCredentialDraft, setShowCredentialDraft] = useState(false);
  const [showTechnicalFields, setShowTechnicalFields] = useState(false);
  const [backupOpen, setBackupOpen] = useState(false);
  const [backups, setBackups] = useState<SettingsBackup[]>([]);
  const [diagnostics, setDiagnostics] = useState<Record<string, any> | null>(null);
  const diagnosticEpoch = useRef(0);
  const [providerCheck, setProviderCheck] = useState<Record<string, any> | null>(null);
  const [accountModelCatalogs, setAccountModelCatalogs] = useState<Record<string, string[]>>({});
  const [supportSummary, setSupportSummary] = useState("");
  const [readinessOpen, setReadinessOpen] = useState(false);
  const [platform, setPlatform] = useState<PlatformContract | null>(null);
  const [closePromptOpen, setClosePromptOpen] = useState(false);
  const [guideOpen, setGuideOpen] = useState(false);
  const [guideProfile, setGuideProfile] = useState<SettingsGuideProfile>("beginner");
  const [guideQuestion, setGuideQuestion] = useState("");
  const [guideAnswer, setGuideAnswer] = useState("");
  const [guideBusy, setGuideBusy] = useState(false);
  const [guideProposal, setGuideProposal] = useState<Record<string, unknown>>({});
  const guideRequestRef = useRef(0);
  const [notificationResult, setNotificationResult] = useState<Record<string, any> | null>(null);
  const [telegramChats, setTelegramChats] = useState<Array<{ chat_id: string; label: string; type: string }>>([]);
  const [assistantStatus, setAssistantStatus] = useState<Record<string, any> | null>(null);
  const [quickStartOpen, setQuickStartOpen] = useState(false);
  const [quickStartStep, setQuickStartStep] = useState(1);
  const [quickStartAsset, setQuickStartAsset] = useState<QuickStartAsset | null>(null);
  const [quickStartSource, setQuickStartSource] = useState("");

  useEffect(() => {
    if (!open) return;
    setBusy(true);
    client.settings()
      .then((next) => {
        setSnapshot(next);
        setDraft(Object.fromEntries(next.fields.map((field) => [field.path, field.value])));
        setActiveSection(initialField === STRATEGY_DIFFICULTY_PATH ? "ai_engine" : "general");
        setShowTechnicalFields(false);
        setReadinessOpen(false);
        setBackupOpen(false);
        setClosePromptOpen(false);
        setGuideOpen(false);
        setGuideQuestion("");
        setGuideAnswer("");
        setGuideProposal({});
        setCredentialDrafts({});
        setAccountModelCatalogs({});
        setProviderCheck(null);
        setSupportSummary("");
        diagnosticEpoch.current += 1;
        setShowCredentialDraft(false);
        setMessage("");
        setNotificationResult(null);
        setTelegramChats([]);
        setQuickStartOpen(false);
        setQuickStartStep(1);
        setQuickStartAsset(null);
        setQuickStartSource("");
      })
      .catch((error: unknown) => setMessage(error instanceof Error ? error.message : "설정을 불러오지 못했습니다."))
      .finally(() => setBusy(false));
    client.settingsDiagnostics().then(setDiagnostics).catch(() => setDiagnostics(null));
    client.platform().then(setPlatform).catch(() => setPlatform(null));
    client.assistantStatus().then((next) => setAssistantStatus(next?.budget ?? next)).catch(() => setAssistantStatus(null));
    focusedTarget.current = false;
  }, [client, open, initialField]);

  useEffect(() => {
    if (!open || busy || !snapshot || focusedTarget.current || initialField !== STRATEGY_DIFFICULTY_PATH || activeSection !== 'ai_engine') return;
    const frame = window.requestAnimationFrame(() => {
      const target = document.querySelector<HTMLElement>('[data-setting-path="ai_custom_features.profile"]');
      if (!target) return;
      target.scrollIntoView({ block: 'center' });
      target.querySelector<HTMLSelectElement>('select')?.focus({ preventScroll: true });
      focusedTarget.current = true;
    });
    return () => window.cancelAnimationFrame(frame);
  }, [open, busy, snapshot, initialField, activeSection]);

  useEffect(() => {
    if (!open || activeSection !== "notifications") return;
    client.notificationStatus().then(setNotificationResult).catch(() => setNotificationResult(null));
  }, [client, open, activeSection]);

  const activeSectionInfo = SETTINGS_SECTIONS.find((section) => section.id === activeSection) ?? SETTINGS_SECTIONS[0];
  const activeFields = snapshot?.fields.filter((field) => field.section === activeSection && (showTechnicalFields || field.presentation === "primary")) ?? [];
  const changeState = useMemo(() => {
    if (!snapshot) return { changed: {} as Record<string, unknown>, invalid: [] as string[] };
    const changed: Record<string, unknown> = {};
    const invalid: string[] = [];
    for (const field of snapshot.fields) {
      const raw = draft[field.path];
      const originalText = JSON.stringify(field.value);
      if (field.kind === "json" && typeof raw === "string") {
        try {
          const parsed = JSON.parse(raw);
          if (originalText !== JSON.stringify(parsed)) changed[field.path] = parsed;
        } catch (_) { invalid.push(field.path); }
      } else if (originalText !== JSON.stringify(raw)) {
        changed[field.path] = normalizeValue(field, raw);
      }
    }
    return { changed, invalid };
  }, [draft, snapshot]);
  const changed = changeState.changed;
  const changedCount = Object.keys(changed).length;
  const pendingCredentialProviders = useMemo(() => Object.entries(credentialDrafts)
    .filter(([, values]) => Object.values(values).some((value) => value.trim().length > 0))
    .map(([provider]) => provider), [credentialDrafts]);
  const pendingCredentialCount = pendingCredentialProviders.length;
  const totalPendingCount = changedCount + pendingCredentialCount;
  const activeSectionPaths = useMemo(() => new Set(
    snapshot?.fields.filter((field) => field.section === activeSection).map((field) => field.path) ?? [],
  ), [activeSection, snapshot]);
  const sectionChanged = Object.fromEntries(Object.entries(changed).filter(([path]) => activeSectionPaths.has(path)));
  const sectionChangedCount = Object.keys(sectionChanged).length;
  const sectionInvalid = changeState.invalid.filter((path) => activeSectionPaths.has(path));
  const visibleModelProvider = credentialProvider === "openai_shared" ? "openai" : ["openai", "deepseek", "kimi", "anthropic", "gemini"].includes(credentialProvider)
    ? credentialProvider : String(draft.ai_provider || "openai");
  const visibleModelDetails = snapshot?.model_catalog_details?.[visibleModelProvider] ?? [];
  const checkedAccountModels = accountModelCatalogs[credentialProvider];

  function modelOptions(
    path: string,
    candidateDraft: Record<string, unknown> = draft,
    includeCurrent = true,
  ): string[] {
    const providerPath = MODEL_PROVIDER_PATHS[path];
    const provider = providerPath === "__openai_fixed__" ? "openai" : providerPath ? String(candidateDraft[providerPath] || "openai") : "openai";
    const capability = MODEL_CAPABILITIES[path] ?? "chat_text";
    const fallback = snapshot?.model_catalogs?.[provider]?.[capability] ?? [];
    const discovered = capability !== "transcribe" ? accountModelCatalogs[path === "ai_data_routing.public_openai_model" ? "openai_shared" : provider] ?? [] : [];
    const current = String(candidateDraft[path] || "").trim();
    return Array.from(new Set([...(includeCurrent && current ? [current] : []), ...fallback, ...discovered]));
  }

  function updateDraftField(path: string, value: unknown) {
    if (path.startsWith("ai_provider") || path.includes("model") || path === "alpha_arena.engine") { diagnosticEpoch.current += 1; setProviderCheck(null); }
    setDraft((current) => {
      const next = { ...current, [path]: value };
      for (const [modelPath, providerPath] of Object.entries(MODEL_PROVIDER_PATHS)) {
        if (providerPath !== path) continue;
        const available = modelOptions(modelPath, next, false);
        const selected = String(next[modelPath] || "");
        if (!available.includes(selected)) next[modelPath] = available[0] ?? "";
      }
      return next;
    });
  }

  function openQuickStart() {
    setActiveSection("general");
    setGuideOpen(false);
    setQuickStartOpen(true);
    setQuickStartStep(1);
    setQuickStartAsset(null);
    setQuickStartSource("");
    setMessage("");
  }

  function quickStartRecommendation(): Record<string, unknown> {
    if (!snapshot || !quickStartAsset || !quickStartSource) return {};
    const candidate: Record<string, unknown> = {
      paper_trading: true,
      verbose_trade_logging: true,
      trade_enabled_exchanges: [],
      enable_stock_live_order: false,
      "stock_auto_trading.auto_start": false,
      "stock_broker_configs.kiwoom.allow_live_order": false,
      "stock_broker_configs.shinhan.allow_live_order": false,
      "stock_broker_configs.miraeAsset.allow_live_order": false,
      "stock_broker_configs.koreaInvestment.allow_live_order": false,
      "position_sizing_policy.mode": "account_risk",
    };
    if (quickStartAsset === "crypto") {
      candidate.enabled_exchanges = [quickStartSource];
      candidate.dynamic_thresholds_enabled = true;
      candidate.dynamic_thresholds_mode = "auto";
    } else {
      candidate.enabled_stock_brokers = [quickStartSource];
      candidate["stock_order_guardrails.enabled"] = true;
      candidate["stock_order_guardrails.enforce_market_hours"] = true;
    }
    const available = new Set(snapshot.fields.map((field) => field.path));
    return Object.fromEntries(Object.entries(candidate).filter(([path, value]) => (
      available.has(path) && JSON.stringify(draft[path]) !== JSON.stringify(value)
    )));
  }

  function stageQuickStart() {
    const recommendation = quickStartRecommendation();
    setDraft((current) => ({ ...current, ...recommendation }));
    setQuickStartStep(4);
    setMessage(Object.keys(recommendation).length
      ? `빠른 시작 안전안을 ${Object.keys(recommendation).length}개 변경 대기에 추가했습니다. 아직 저장되지 않았습니다.`
      : "현재 설정이 이미 선택한 빠른 시작 안전안과 같습니다. 연결 상태를 확인한 뒤 PAPER를 시작하세요.");
  }

  useEffect(() => {
    if (!["exchange_api", "ai_engine", "alpha"].includes(activeSection)) return;
    const providers = credentialProvidersForSection(activeSection);
    if (!providers.includes(credentialProvider)) setCredentialProvider(providers[0]);
  }, [activeSection, credentialProvider]);

  useEffect(() => {
    diagnosticEpoch.current += 1;
    setProviderCheck(null);
    setSupportSummary("");
    setShowCredentialDraft(false);
  }, [credentialProvider]);

  function requestClose() {
    if (busy) return;
    if (totalPendingCount) { setClosePromptOpen(true); return; }
    onClose();
  }

  function cancelSettings() {
    if (busy) return;
    if (totalPendingCount && !window.confirm("변경한 설정과 입력한 연결 정보를 저장하지 않고 취소할까요?")) return;
    onClose();
  }

  useEffect(() => {
    if (!open) return;
    const closeOnEscape = (event: KeyboardEvent) => { if (event.key === "Escape" && !busy) requestClose(); };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [busy, onClose, open, totalPendingCount]);

  async function save(
    scope: "section" | "all",
    baseSnapshot: SettingsSnapshot | null = snapshot,
    refreshRuntime = true,
  ): Promise<SettingsSnapshot | null> {
    if (!baseSnapshot) return null;
    const changesToSave = scope === "section" ? sectionChanged : changed;
    const invalidToSave = scope === "section" ? sectionInvalid : changeState.invalid;
    if (!Object.keys(changesToSave).length) return baseSnapshot;
    if (invalidToSave.length) return null;
    const critical = baseSnapshot.fields.some((field) => field.risk === "critical" && field.path in changesToSave);
    if (critical && !window.confirm("실거래 관련 중요 설정이 포함됩니다. 저장할까요?")) return null;
    const enablingPublicOpenAI = changesToSave["ai_data_routing.public_general_sharing_enabled"] === true
      && baseSnapshot.fields.find((field) => field.path === "ai_data_routing.public_general_sharing_enabled")?.value !== true;
    if (enablingPublicOpenAI && !window.confirm("공개 일반 질문용 OpenAI Project 경로를 켤까요? 이 경로는 조직 콘솔에서 데이터 공유를 직접 설정한 별도 Project용입니다. 전략·계좌·파일 질문에는 사용하면 안 되며, NoahAI는 공유 활성화나 무료 제공량을 확인·보장하지 않습니다.")) return null;
    setBusy(true);
    setMessage("");
    try {
      const next = await client.updateSettings(baseSnapshot.revision, changesToSave);
      const returnedValues = Object.fromEntries(next.fields.map((field) => [field.path, field.value]));
      const mismatched = Object.entries(changesToSave)
        .filter(([path, value]) => JSON.stringify(returnedValues[path]) !== JSON.stringify(value))
        .map(([path]) => path);
      if (!next.save_receipt?.verified || mismatched.length) {
        throw new Error(`설정 저장 후 값 검증에 실패했습니다. 변경 내용은 화면에 유지됩니다.${mismatched.length ? ` 불일치: ${mismatched.join(", ")}` : ""}`);
      }
      const savedPaths = new Set(Object.keys(changesToSave));
      setSnapshot(next);
      setDraft(Object.fromEntries(next.fields.map((field) => [
        field.path,
        scope === "section" && !savedPaths.has(field.path) && field.path in changed
          ? draft[field.path]
          : field.value,
      ])));
      const affected = Object.entries(next.apply_plan ?? {}).filter(([, value]) => value).map(([key]) => key);
      let successMessage = `${scope === "section" ? `${activeSectionInfo.label} 저장 완료` : "전체 설정 저장 완료"} · 적용 범위 ${affected.length ? affected.join(", ") : "즉시 반영"}`;
      if (next.runtime_refresh?.ok === false) {
        successMessage += " · 파일 저장은 완료됐지만 실행 중 설정 반영에 실패했습니다. 앱을 다시 시작하면 저장값이 적용됩니다.";
      }
      if (refreshRuntime) {
        try {
          await onSettingsSaved?.();
        } catch {
          successMessage += " · 파일 저장은 완료됐지만 화면 상태 새로고침에 실패했습니다. 앱을 다시 열어 확인하세요.";
        }
      }
      if (Object.keys(changesToSave).some((path) => path.startsWith("ai_cost_control."))) {
        try {
          const status = await client.assistantStatus();
          setAssistantStatus(status?.budget ?? status);
        } catch {
          successMessage += " · AI 사용량 카드는 새로고침 버튼으로 다시 확인하세요.";
        }
      }
      setMessage(successMessage);
      return next;
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "설정 저장에 실패했습니다.");
      return null;
    } finally {
      setBusy(false);
    }
  }

  async function saveAllPending(closeAfter: boolean) {
    if (!snapshot || changeState.invalid.length) return;
    let current: SettingsSnapshot | null = snapshot;
    let runtimeRefreshFailed = false;
    if (changedCount) current = await save("all", current, false);
    runtimeRefreshFailed = runtimeRefreshFailed || current?.runtime_refresh?.ok === false;
    for (const provider of pendingCredentialProviders) {
      if (!current) return;
      current = await saveCredential(false, provider, current, false);
      runtimeRefreshFailed = runtimeRefreshFailed || current?.runtime_refresh?.ok === false;
    }
    if (!current) return;
    let refreshFailed = false;
    try {
      await onSettingsSaved?.();
    } catch {
      refreshFailed = true;
    }
    setMessage(refreshFailed || runtimeRefreshFailed
      ? "설정 파일 저장은 완료됐습니다. 실행 중 반영 또는 화면 새로고침에 실패했으므로 앱을 다시 시작하면 저장값이 적용됩니다."
      : "모든 변경을 저장했습니다.");
    if (closeAfter) { setClosePromptOpen(false); onClose(); }
  }

  async function saveAndClose() { await saveAllPending(true); }

  function settingsGuideRecommendation(): Record<string, unknown> {
    if (!snapshot) return {};
    const candidates: Record<SettingsSectionId, Record<string, unknown>> = {
      general: {
        paper_trading: true,
        verbose_trade_logging: true,
        "ui_settings.always_on_top": false,
        "ui_settings.display_preset": "display_standard",
        demo_mode: false,
      },
      exchange_selection: {
        trade_enabled_exchanges: [],
        enable_stock_live_order: false,
        "stock_auto_trading.auto_start": false,
        "stock_broker_configs.kiwoom.allow_live_order": false,
        "stock_broker_configs.shinhan.allow_live_order": false,
        "stock_broker_configs.miraeAsset.allow_live_order": false,
        "stock_broker_configs.koreaInvestment.allow_live_order": false,
      },
      exchange_api: {},
      ai_engine: {
        assistant_response_mode: guideProfile === "beginner" ? "saver" : guideProfile === "advanced" ? "premium" : "standard",
        "ai_custom_runtime.enabled": false,
        "ai_custom_runtime.allow_limited_live": false,
        "ai_custom_features.profile": guideProfile === "balanced" ? "standard" : guideProfile,
      },
      notifications: {
        "notification_integrations.enabled": false,
        "notification_integrations.channels.discord.enabled": false,
        "notification_integrations.channels.telegram.enabled": false,
        "notification_integrations.events.guardrail_stop": true,
        "notification_integrations.events.loss_warning": true,
        "notification_integrations.events.risk_data_unavailable": true,
        "notification_integrations.events.market_regime_change": true,
        "notification_integrations.events.runtime_failure": true,
        "notification_integrations.events.update_available": true,
        "notification_integrations.loss_warning_percent": 5,
        "notification_integrations.cooldown_seconds": 300,
        ...Object.fromEntries([...CRYPTO_SOURCES, ...STOCK_SOURCES].map((venue) => [`notification_integrations.exchanges.${venue}`, true])),
      },
      advanced: {
        "advanced_trading_layers.profitability_validation.enabled": true,
        "advanced_trading_layers.portfolio_orchestration.enabled": true,
        "advanced_trading_layers.strategy_engine.enabled": true,
        "advanced_trading_layers.execution_optimizer.enabled": true,
        "advanced_trading_layers.ops_automation.enabled": true,
        "advanced_trading_layers.strategy_engine.high_vol_action": guideProfile === "beginner" ? "block" : "evaluate",
        "advanced_trading_layers.strategy_engine.consensus_threshold": guideProfile === "beginner" ? 0.7 : 0.6,
        "advanced_trading_layers.strategy_engine.cooldown_sec": guideProfile === "beginner" ? 120 : 60,
      },
      alpha: {
        "alpha_arena.enabled": false,
        "alpha_arena.initial_capital_benchmark": "10000",
        "alpha_arena.tick_interval_sec": 60,
      },
      system: {
        log_level: "INFO",
        detailed_logs_enabled: true,
        dynamic_thresholds_enabled: true,
        dynamic_thresholds_mode: "auto",
        dynamic_thresholds_high_multiplier: 1.5,
        dynamic_thresholds_manual_regime: "NORMAL",
      },
      update: {},
    };
    const available = new Set(snapshot.fields.map((field) => field.path));
    return Object.fromEntries(Object.entries(candidates[activeSection]).filter(([path, value]) => (
      available.has(path) && JSON.stringify(draft[path]) !== JSON.stringify(value)
    )));
  }

  function createSettingsGuideProposal() {
    const next = settingsGuideRecommendation();
    setGuideProposal(next);
    setMessage(Object.keys(next).length
      ? `${SETTINGS_GUIDE_PROFILE_LABELS[guideProfile]} 추천안을 만들었습니다. 아래 변경 내용을 확인한 뒤 변경 대기에 반영하세요.`
      : `${activeSectionInfo.label}에는 자동 변경할 안전 항목이 없거나 이미 권장 상태입니다. AI 답변과 연결 점검을 이용하세요.`);
  }

  function stageSettingsGuideProposal() {
    if (!Object.keys(guideProposal).length) return;
    setDraft((current) => ({ ...current, ...guideProposal }));
    setGuideProposal({});
    setMessage("AI 설정 추천안을 변경 대기에 반영했습니다. 아직 저장되지 않았습니다. 변경 내용과 위험 표시를 확인한 뒤 저장하세요.");
  }

  function stageDefaults(scope: "section" | "all") {
    if (!snapshot) return;
    const targetFields = snapshot.fields.filter((field) => (
      (scope === "all" || field.section === activeSection) && field.default_value !== undefined
    ));
    if (!targetFields.length) {
      setMessage("불러올 기본값이 없습니다.");
      return;
    }
    const criticalCount = targetFields.filter((field) => field.risk === "critical").length;
    if (criticalCount && !window.confirm(
      `${scope === "all" ? "전체" : activeSectionInfo.label} 기본값을 변경 대기에 불러올까요?\n중요 설정 ${criticalCount}개가 포함되며, 아직 저장되지는 않습니다.`,
    )) return;
    const defaults = Object.fromEntries(targetFields.map((field) => [field.path, field.default_value]));
    setDraft((current) => ({ ...current, ...defaults }));
    setMessage(`${scope === "all" ? "전체" : activeSectionInfo.label} 기본값을 변경 대기에 불러왔습니다. 비교 후 저장해야 적용됩니다. API 키와 연결 정보는 초기화하지 않습니다.`);
  }

  async function askSettingsGuide() {
    const question = guideQuestion.trim() || `설정 → ${activeSectionInfo.label}에서 ${SETTINGS_GUIDE_PROFILE_LABELS[guideProfile]} 사용자가 확인할 항목, 현재 상태의 의미, 권장 순서와 주의사항을 설명해줘. 비밀값은 표시하지 말고 설정을 저장하거나 거래를 실행하지 마.`;
    const requestId = ++guideRequestRef.current;
    const sectionAtRequest = activeSection;
    setGuideBusy(true); setGuideAnswer("");
    try {
      const response = await client.askAssistant(question, "settings", guideProfile === "balanced" ? "standard" : guideProfile, "guide", [], sectionAtRequest);
      if (guideRequestRef.current === requestId) setGuideAnswer(String(response.answer || "설정 도움 답변을 받지 못했습니다."));
    } catch (error) {
      if (guideRequestRef.current === requestId) setGuideAnswer(error instanceof Error ? error.message : "설정 AI 도움을 불러오지 못했습니다.");
    } finally {
      if (guideRequestRef.current === requestId) setGuideBusy(false);
    }
  }

  const credentialProviders = credentialProvidersForSection(activeSection);
  const credentialFields = credentialFieldsForProvider(credentialProvider);
  const credentialDraft = credentialDrafts[credentialProvider] ?? {};
  const selectedCredentialReady = Boolean(snapshot?.credential_status?.[credentialStatusKey(credentialProvider)]);
  const selectedCredentialFieldStatus = snapshot?.credential_field_status?.[credentialProvider] ?? {};
  const visibleCredentialStatus = Object.entries(snapshot?.credential_status ?? {}).filter(([name]) => (
    activeSection === "alpha"
      ? name === "alpha:deepseek"
      : activeSection === "ai_engine"
        ? name.startsWith("ai:")
        : name !== "ai" && !name.startsWith("ai:") && name !== "alpha:deepseek"
  ));

  async function saveCredential(
    clear = false,
    provider = credentialProvider,
    baseSnapshot: SettingsSnapshot | null = snapshot,
    refreshRuntime = true,
  ): Promise<SettingsSnapshot | null> {
    if (!baseSnapshot) return null;
    const providerFields = credentialFieldsForProvider(provider);
    const providerDraft = credentialDrafts[provider] ?? {};
    const values = clear
      ? Object.fromEntries(providerFields.map((field) => [field, ""]))
      : Object.fromEntries(providerFields
        .filter((field) => (providerDraft[field] ?? "").trim().length > 0)
        .map((field) => [field, providerDraft[field].trim()]));
    if (!clear && !Object.keys(values).length) { setMessage("새로 저장할 자격증명 값을 입력하세요."); return null; }
    if (clear && !window.confirm(`${provider.toUpperCase()} 연결 정보를 삭제할까요?`)) return null;
    setBusy(true);
    try {
      const next = await client.updateCredentials(baseSnapshot.revision, provider, values);
      if (!next.save_receipt?.verified) {
        throw new Error("연결 정보를 저장한 뒤 재확인하지 못했습니다. 입력값은 화면에 유지됩니다.");
      }
      diagnosticEpoch.current += 1;
      setProviderCheck(null);
      setSupportSummary("");
      setAccountModelCatalogs((current) => Object.fromEntries(Object.entries(current).filter(([scope]) => scope !== provider)));
      setSnapshot(next);
      setCredentialDrafts((current) => Object.fromEntries(Object.entries(current).filter(([name]) => name !== provider)));
      let successMessage = clear
        ? "연결 정보를 삭제했습니다."
        : "연결 정보 저장·재읽기 검증 완료 · 키의 실제 유효성은 아래 실제 연결 점검으로 확인하세요. 값은 다시 표시되지 않습니다.";
      if (next.runtime_refresh?.ok === false) {
        successMessage += " 파일 저장은 완료됐지만 실행 중 반영에 실패했습니다. 앱을 다시 시작하면 저장값이 적용됩니다.";
      }
      if (refreshRuntime) {
        try {
          await onSettingsSaved?.();
        } catch {
          successMessage += " 파일 저장은 완료됐지만 화면 상태 새로고침에 실패했습니다.";
        }
      }
      setMessage(successMessage);
      return next;
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "연결 정보 저장에 실패했습니다.");
      return null;
    } finally { setBusy(false); }
  }

  async function refreshNotificationStatus() {
    try { setNotificationResult(await client.notificationStatus()); }
    catch { setNotificationResult(null); }
  }

  async function saveNotificationCredential(provider: "notification:discord" | "notification:telegram", clear = false) {
    const next = await saveCredential(clear, provider, snapshot, false);
    if (next) await refreshNotificationStatus();
    return next;
  }

  async function runNotificationTest(channel: "discord" | "telegram") {
    const provider = `notification:${channel}` as "notification:discord" | "notification:telegram";
    const pending = credentialDrafts[provider] ?? {};
    if (Object.values(pending).some((value) => value.trim())) {
      const saved = await saveNotificationCredential(provider);
      if (!saved) return;
    }
    setBusy(true);
    setNotificationResult((current) => ({ ...(current ?? {}), last_test: null }));
    setMessage(`${channel === "discord" ? "Discord" : "Telegram"} 테스트 메시지를 보내는 중입니다…`);
    try {
      const result = await client.testNotification(channel);
      setNotificationResult((current) => ({ ...(current ?? {}), last_test: result }));
      setMessage(result.ok ? `${channel === "discord" ? "Discord" : "Telegram"} 테스트 메시지 전송을 확인했습니다.` : "테스트 메시지 전송을 확인하지 못했습니다. 연결 정보를 확인하세요.");
    } catch (error) {
      setNotificationResult((current) => ({ ...(current ?? {}), last_test: { ok: false, channel } }));
      setMessage(error instanceof Error ? error.message : "테스트 메시지를 보내지 못했습니다.");
    } finally { setBusy(false); }
  }

  async function discoverTelegram() {
    const provider = "notification:telegram" as const;
    const pending = credentialDrafts[provider] ?? {};
    if ((pending.bot_token ?? "").trim()) {
      const saved = await saveNotificationCredential(provider);
      if (!saved) return;
    }
    setBusy(true);
    setMessage("Telegram 봇에 Start 또는 /start를 보낸 대화방을 찾는 중입니다…");
    try {
      const result = await client.discoverTelegramChats();
      const chats = Array.isArray(result.chats) ? result.chats : [];
      setTelegramChats(chats);
      setMessage(chats.length
        ? `Telegram 대화방 ${chats.length}개를 찾았습니다. 받을 대화방을 선택한 뒤 연결 정보를 저장하세요.`
        : "대화방을 찾지 못했습니다. Telegram에서 봇을 열어 Start 또는 /start를 보낸 뒤 다시 찾으세요.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Telegram 대화방을 찾지 못했습니다.");
    } finally { setBusy(false); }
  }

  async function refreshDiagnostics() {
    setBusy(true); setMessage("");
    try {
      setDiagnostics(await client.settingsDiagnostics());
      setMessage("로컬 준비 상태를 다시 확인했습니다. 외부 API 연결은 별도 점검 버튼으로 실행합니다.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "설정 진단을 불러오지 못했습니다.");
    } finally { setBusy(false); }
  }

  async function runProviderCheck() {
    const provider = ["openai", "openai_shared", "deepseek", "kimi", "anthropic", "gemini", "alpha:deepseek"].includes(credentialProvider)
      ? credentialProvider : String(draft.ai_provider || "openai");
    const pending = credentialDrafts[provider] ?? {};
    if (Object.values(pending).some((value) => value.trim())) {
      const saved = await saveCredential(false, provider, snapshot, false);
      if (!saved) return;
    }
    const analystProvider = String(draft["ai_provider_profiles.analyst.provider"] || draft.ai_provider || "openai");
    const model = String(provider === "alpha:deepseek" ? draft["alpha_arena.engine"] || "deepseek-v4-flash" : provider === "openai_shared" ? draft["ai_data_routing.public_openai_model"] || "" : analystProvider === provider ? draft["ai_provider_profiles.analyst.model"] || "" : "");
    const selectionPending = provider === "openai_shared"
      ? Object.prototype.hasOwnProperty.call(changed, "ai_data_routing.public_openai_model")
      : analystProvider === provider && (
        Object.prototype.hasOwnProperty.call(changed, "ai_provider_profiles.analyst.provider")
        || Object.prototype.hasOwnProperty.call(changed, "ai_provider_profiles.analyst.model")
      );
    const checkEpoch = diagnosticEpoch.current;
    setAccountModelCatalogs((current) => Object.fromEntries(Object.entries(current).filter(([scope]) => scope !== provider)));
    setProviderCheck(null);
    setBusy(true); setMessage(`Provider 모델 목록과 ${model || "기본 모델"} 실제 호출을 확인하는 중입니다…`);
    try {
      const result = await client.checkAIProvider(provider, model, "chat_text");
      if (checkEpoch !== diagnosticEpoch.current) return;
      setProviderCheck({ ...result, credential_scope: provider, selection_pending: selectionPending });
      if (result.model_callable) {
        client.assistantStatus()
          .then((next) => setAssistantStatus(next?.budget ?? next))
          .catch(() => undefined);
      }
      if (Array.isArray(result.models) && result.catalog_checked) {
        setAccountModelCatalogs((current) => ({
          ...current,
          [provider]: Array.from(new Set(result.models.map(String))),
        }));
      }
      setMessage(result.model_callable
        ? `${provider.toUpperCase()} ${String(result.requested_model || model)} 실제 호출 확인 완료${selectionPending ? " · 현재 선택은 아직 저장되지 않았습니다" : ""}`
        : `${provider.toUpperCase()} 점검 미완료 · Provider 목록 연결과 선택 모델 호출 결과를 각각 확인하세요.`);
    } catch (error) {
      const reason = error instanceof Error ? error.message : "AI 제공사 점검에 실패했습니다.";
      if (checkEpoch !== diagnosticEpoch.current) return;
      setProviderCheck({ ok: false, credential_scope: provider, errors: [reason] });
      setMessage(reason);
    } finally { setBusy(false); }
  }

  function applyAssistantPreset(mode: "saver" | "standard" | "premium") {
    setDraft((current) => ({ ...current, assistant_response_mode: mode }));
    setMessage(`${mode === "saver" ? "절약형" : mode === "premium" ? "정밀형" : "균형형"} 설명 프리셋을 변경 대기에 추가했습니다. 저장 전까지 적용되지 않습니다.`);
  }

  function applyAdvancedPreset(mode: "dev" | "safe" | "aggressive") {
    const presets = {
      dev: { enabled: false, highVol: "block", consensus: 0.6, cooldown: 60 },
      safe: { enabled: true, highVol: "evaluate", consensus: 0.7, cooldown: 120 },
      aggressive: { enabled: true, highVol: "evaluate", consensus: 0.5, cooldown: 30 },
    } as const;
    const preset = presets[mode];
    setDraft((current) => ({
      ...current,
      "advanced_trading_layers.profitability_validation.enabled": preset.enabled,
      "advanced_trading_layers.portfolio_orchestration.enabled": preset.enabled,
      "advanced_trading_layers.strategy_engine.enabled": preset.enabled,
      "advanced_trading_layers.execution_optimizer.enabled": preset.enabled,
      "advanced_trading_layers.ops_automation.enabled": preset.enabled,
      "advanced_trading_layers.strategy_engine.high_vol_action": preset.highVol,
      "advanced_trading_layers.strategy_engine.consensus_threshold": preset.consensus,
      "advanced_trading_layers.strategy_engine.cooldown_sec": preset.cooldown,
    }));
    setMessage(`${mode} 프리셋을 변경 대기에 추가했습니다. 아래 미리보기와 저장 버튼을 확인하세요.`);
  }

  function stageDynamicThresholdDefaults() {
    setDraft((current) => ({
      ...current,
      dynamic_thresholds_enabled: true,
      dynamic_thresholds_mode: "auto",
      dynamic_thresholds_high_multiplier: 1.5,
      dynamic_thresholds_manual_regime: "NORMAL",
    }));
    setMessage("시장 국면 자동 보정 기본값을 변경 대기에 추가했습니다. 저장 전까지 적용되지 않습니다.");
  }

  async function runAccountConnectionCheck() {
    const source = credentialProvider.replace("stock:", "");
    const pending = credentialDrafts[credentialProvider] ?? {};
    if (Object.values(pending).some((value) => value.trim())) {
      const saved = await saveCredential(false, credentialProvider, snapshot, false);
      if (!saved) return;
    }
    const accountCheckEpoch = diagnosticEpoch.current;
    setSupportSummary("");
    setBusy(true); setMessage(`${source.toUpperCase()} 계정 연결을 실제 조회로 확인하는 중입니다…`);
    try {
      const result = await client.refreshAccounts([source], true);
      if (accountCheckEpoch !== diagnosticEpoch.current) return;
      const failure = accountConnectionFailure(result, source);
      if (failure) throw new Error(failure);
      const summary = `[NoahAI 연결 점검]\n시각: ${new Date().toISOString()}\n대상: ${source}\n결과: 성공\n응답 범위: ${Object.keys(result || {}).join(", ") || "계정 snapshot"}\n비밀값: 포함하지 않음`;
      setSupportSummary(summary);
      setMessage(`${source.toUpperCase()} 실제 계정 조회가 완료되었습니다.`);
    } catch (error) {
      if (accountCheckEpoch !== diagnosticEpoch.current) return;
      const reason = error instanceof Error ? error.message : "계정 연결 점검 실패";
      const action = /Windows 로컬 엔진의 문자 인코딩|local_runtime_encoding_error|codec can't encode|cp949/i.test(reason)
        ? "NoahAI UTF-8 런타임 패치 버전으로 업데이트하고 앱을 완전히 다시 시작하세요. 이 오류만으로 API 키를 재발급할 필요는 없습니다."
        : /PC 시각|서버 시각|시간 동기화|server timestamp|recv_?window|retcode.?10002|code.?-1021/i.test(reason)
          ? "Windows 설정 → 시간 및 언어 → 날짜 및 시간에서 자동 설정을 켜고 '지금 동기화'를 실행한 뒤 다시 점검하세요. API 키를 재발급할 필요는 없습니다."
        : "자격증명, API 권한, IP 허용목록, 거래 엔진 연결 상태를 확인하세요.";
      const summary = `[NoahAI 연결 점검]\n시각: ${new Date().toISOString()}\n대상: ${source}\n결과: 실패\n원인: ${reason}\n조치: ${action}\n비밀값: 포함하지 않음`;
      setSupportSummary(summary);
      setMessage(reason);
    } finally { setBusy(false); }
  }

  async function openBackups() {
    setBusy(true); setMessage("");
    try {
      const response = await client.settingsBackups();
      setBackups(response.backups);
      setBackupOpen(true);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "설정 백업 목록을 불러오지 못했습니다.");
    } finally { setBusy(false); }
  }

  async function restoreBackup(backup: SettingsBackup) {
    if (!snapshot) return;
    if (totalPendingCount) { setMessage("복구 전에 현재 변경과 연결 정보 입력을 저장하거나 취소하세요."); return; }
    if (!window.confirm(`${new Date(backup.created_at).toLocaleString()} 백업으로 복구할까요?\n복구 직전 현재 설정도 자동 백업됩니다.`)) return;
    setBusy(true); setMessage("");
    try {
      const next = await client.restoreSettings(snapshot.revision, backup.name);
      setSnapshot(next);
      setDraft(Object.fromEntries(next.fields.map((field) => [field.path, field.value])));
      setBackupOpen(false);
      let successMessage = "설정 복구 완료 · 적용 전 각 거래소와 PAPER/LIVE 범위를 다시 확인하세요.";
      try {
        await onSettingsSaved?.();
      } catch {
        successMessage += " 파일 복구는 완료됐지만 화면 상태 새로고침에 실패했습니다.";
      }
      setMessage(successMessage);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "설정 복구에 실패했습니다.");
    } finally { setBusy(false); }
  }

  if (!open) return null;
  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && requestClose()}>
      <section className="settings-center" role="dialog" aria-modal="true" aria-labelledby="settings-center-title">
        <header className="settings-window-header">
          <div><h2 id="settings-center-title">{t("⚙ 설정")}</h2><p>{t("처음이면 빠른 시작에서 PAPER와 한 기관만 고르세요. 기존 설정은 그대로 두고 싶다면 탭별 설명을 따라 필요한 항목만 변경할 수 있습니다.")}</p></div>
          <button className="settings-quick-start-open" type="button" onClick={openQuickStart}>{t("처음 사용 · 빠른 시작")}</button>
          <button className="settings-window-close" type="button" onClick={requestClose} aria-label={t("설정 창 닫기")} title={t("설정 닫기")}>×</button>
        </header>
        <div className="settings-live-warning"><span>{t("v3.9.1.43 · LIVE는 별도 권한입니다 · PAPER OFF + 주문 대상/증권 LIVE + API 준비 + 가드레일")}</span><button type="button" onClick={() => onAskAssistant("실거래 전 필수 준비, PAPER와 LIVE의 차이, API 권한과 주문 가드레일을 현재 설정 기준으로 설명해줘.", activeSection)}>{t("실거래 필수 안내")}</button></div>
        <section className={`settings-readiness-strip ${readinessOpen ? "open" : ""}`}>
          <header><strong>{t("AI 실행 준비도 진단")}</strong><button type="button" onClick={() => setReadinessOpen((value) => !value)}>{readinessOpen ? "상세 닫기" : t("상세 보기")}</button></header>
          {readinessOpen && <div className="readiness-grid"><span><b>{t("AI 키")}</b>{diagnostics?.ai?.configured ? "등록됨" : "미설정"}</span><span><b>{t("기본 Provider")}</b>{String(diagnostics?.ai?.provider || "—").toUpperCase()}</span><span><b>{t("거래 모드")}</b>{diagnostics?.trading?.paper_trading ? "PAPER" : diagnostics?.trading?.live_ready ? "LIVE 준비" : "LIVE 차단"}</span><span><b>{t("런타임")}</b>{diagnostics?.trading?.runtime_status || "확인 중"}</span><span><b>{t("회원 등급")}</b>{String(diagnostics?.membership?.user_grade || "확인 필요").toUpperCase()}</span><span><b>{t("회원 정책")}</b>{diagnostics?.membership?.policy_version || diagnostics?.membership?.status || "서버 확인 필요"}</span></div>}
        </section>
        <nav className="settings-section-tabs" aria-label={t("설정 영역")}>
          {SETTINGS_SECTIONS.map((section) => <button className={section.id === activeSection ? "active" : ""} key={section.id} title={`${section.label} · ${snapshot?.fields.filter((field) => field.section === section.id).length ?? 0}개 설정`} onClick={() => {
            guideRequestRef.current += 1;
            setActiveSection(section.id);
            setGuideQuestion("");
            setGuideAnswer("");
            setGuideBusy(false);
            setGuideProposal({});
            setShowTechnicalFields(false);
            if (section.id === "ai_engine" && !["openai", "deepseek", "kimi", "anthropic", "gemini"].includes(credentialProvider)) {
              const savedProvider = String(draft.ai_provider || "openai").toLowerCase();
              setCredentialProvider(["openai", "deepseek", "kimi", "anthropic", "gemini"].includes(savedProvider) ? savedProvider : "openai");
            }
            if (section.id === "exchange_api" && ["openai", "deepseek", "kimi", "anthropic", "gemini"].includes(credentialProvider)) {
              const savedExchange = String(draft.selected_exchange || "binance").toLowerCase();
              setCredentialProvider(CRYPTO_SOURCES.includes(savedExchange) ? savedExchange : "binance");
            }
            if (section.id === "exchange_api" && credentialProvider === "alpha:deepseek") setCredentialProvider("binance");
            if (section.id === "alpha") setCredentialProvider("alpha:deepseek");
          }} type="button">{t(section.label)}</button>)}
        </nav>
        <div className="settings-body">
          <main className="settings-fields">
            {activeSection === "general" && <section className="settings-language-row" aria-label={localized('표시 언어', 'Display language')}>
              <div><strong>{localized('표시 언어', 'Display language')}</strong><p>{localized('처음에는 시스템의 선호 언어를 참고합니다. 직접 선택하면 즉시 적용·별도 저장되며, 거래 설정은 바뀌지 않습니다.', 'Initially follows your system’s preferred language. Your choice is applied and saved separately immediately, without changing trading settings.')}</p></div>
              <LanguagePicker client={client} />
            </section>}
            <div className="settings-tab-commandbar">
              <div><strong>{t(activeSection === "general" ? "1. 운용 모드 · 변경 후 저장을 눌러야 적용됩니다." : activeSectionInfo.label)}</strong><p>{t(activeSectionInfo.description)}</p></div>
              <div className="settings-command-actions">
                <button className="secondary-button" type="button" onClick={() => setShowTechnicalFields((value) => !value)}>{showTechnicalFields ? t("기본 설정만 보기") : t("고급 설정 보기")}</button>
                <button className="secondary-button" type="button" disabled={busy} onClick={() => stageDefaults("section")}>{t("이 탭 기본값 불러오기")}</button>
                <button className="primary-button" type="button" onClick={() => setGuideOpen((value) => !value)}>{t("✦ AI에게 묻기 · 설정 도우미")}</button>
              </div>
              <div className="settings-command-save-row">
                <span>{sectionChangedCount ? `${sectionChangedCount}개 변경 대기` : "이 탭의 변경 내용 없음"}</span>
                <button className="settings-save-button" type="button" disabled={!sectionChangedCount || busy || Boolean(sectionInvalid.length)} onClick={() => void save("section")}>{t("▣ 현재 설정 저장")}</button>
              </div>
            </div>
            {guideOpen && <section className="settings-guide-panel" aria-label={`${activeSectionInfo.label} AI 설정 도우미`}>
              <header><div><strong>{activeSectionInfo.label}{t(" · AI 설정 도우미")}</strong><p>{t("질문 답변과 안전 추천안을 제공합니다. 비밀값·API 키·LIVE 권한은 자동 입력하거나 저장하지 않습니다.")}</p></div><button type="button" onClick={() => setGuideOpen(false)}>{t("도우미 닫기")}</button></header>
              <div className="settings-guide-controls">
                <label><span>{t("사용 수준")}</span><select value={guideProfile} onChange={(event) => { setGuideProfile(event.target.value as SettingsGuideProfile); setGuideProposal({}); }}><option value="beginner">{t("처음 사용 · 안전 우선")}</option><option value="balanced">{t("일반 사용 · 균형")}</option><option value="advanced">{t("숙련 사용자 · 상세 설명")}</option></select></label>
                <label className="settings-guide-question"><span>{t("무엇이 궁금한가요?")}</span><input value={guideQuestion} onChange={(event) => setGuideQuestion(event.target.value)} placeholder={t("예: 이 설정을 PAPER에서 안전하게 시작하려면 무엇을 확인해야 하나요?")} onKeyDown={(event) => { if (event.key === "Enter") void askSettingsGuide(); }} /></label>
                <button type="button" disabled={guideBusy} onClick={askSettingsGuide}>{guideBusy ? "답변 준비 중…" : "AI 답변 받기"}</button>
              </div>
              {guideAnswer && <div className="settings-guide-answer"><strong>{t("설정 안내 · ")}{activeSectionInfo.label}{t(" 문맥 고정")}</strong><pre>{guideAnswer}</pre><button type="button" onClick={() => onAskAssistant(`${guideQuestion || activeSectionInfo.label}에 대해 방금 본 설정 안내를 이어서 질문하고 싶습니다. 현재 저장값의 목적과 영향만 설명하고 설정을 직접 저장하거나 거래를 실행하지 마.`, activeSection)}>{t("대화형 AI에서 이어서 묻기")}</button></div>}
              <div className="settings-guide-proposal-actions"><button type="button" onClick={createSettingsGuideProposal}>{t("안전 추천안 만들기")}</button><span>{t("추천안은 현재 탭의 변경 대기에만 반영되며 저장은 별도 승인입니다.")}</span></div>
              {Object.keys(guideProposal).length > 0 && <div className="settings-guide-proposal"><strong>{t("변경 미리보기")}</strong>{Object.entries(guideProposal).map(([path, value]) => { const field = snapshot?.fields.find((item) => item.path === path); return <div key={path}><span>{field?.label || path}</span><code>{JSON.stringify(draft[path])} → {JSON.stringify(value)}</code><small>{field?.risk === "critical" ? "중요 설정 · 저장 시 추가 확인" : field?.help}</small></div>; })}<button type="button" onClick={stageSettingsGuideProposal}>{t("변경 대기에 반영")}</button></div>}
            </section>}
            {activeSection === "general" && quickStartOpen && <section className="settings-quick-start" aria-label={t("처음 사용 빠른 시작")}>
              <header><div><strong>{t("처음 사용 · 빠른 시작")}</strong><p>{t("외부 AI 호출 없이 한 질문씩 안전한 PAPER 시작값을 고릅니다. 새 운용 모드가 아니며 Level·전략·기존 고급 설정을 없애지 않습니다.")}</p></div><button type="button" onClick={() => setQuickStartOpen(false)}>{t("닫기")}</button></header>
              <div className="settings-quick-start-progress" aria-label={`빠른 시작 ${quickStartStep}/4 단계`}>
                {["자산 선택", "기관 선택", "안전 확인", "저장 안내"].map((label, index) => <span className={quickStartStep >= index + 1 ? "active" : ""} key={label}><b>{index + 1}</b>{label}</span>)}
              </div>
              {quickStartStep === 1 && <div className="settings-quick-start-question">
                <strong>{t("어떤 자산을 먼저 가상으로 연습할까요?")}</strong>
                <p>{t("나중에 다른 자산을 추가할 수 있습니다. 여기서는 첫 화면을 단순하게 만들기 위해 하나만 고릅니다.")}</p>
                <div><button type="button" onClick={() => { setQuickStartAsset("crypto"); setQuickStartSource(""); setQuickStartStep(2); }}><b>{t("코인")}</b><span>{t("현물 또는 선물 거래소")}</span></button><button type="button" onClick={() => { setQuickStartAsset("stock"); setQuickStartSource(""); setQuickStartStep(2); }}><b>{t("주식·ETF")}</b><span>{t("국내 증권사")}</span></button></div>
              </div>}
              {quickStartStep === 2 && quickStartAsset && <div className="settings-quick-start-question">
                <strong>{t("먼저 확인할 ")}{quickStartAsset === "crypto" ? t("거래소") : t("증권사")}{t(" 한 곳을 고르세요.")}</strong>
                <p>{t("이 선택은 관찰·분석 범위입니다. 실제 주문 권한은 열지 않습니다.")}</p>
                <div className="source-grid">{QUICK_START_SOURCES[quickStartAsset].map((source) => <button className={quickStartSource === source.id ? "selected" : ""} type="button" key={source.id} onClick={() => { setQuickStartSource(source.id); setQuickStartStep(3); }}><b>{source.label}</b><span>{source.detail}</span></button>)}</div>
                <button className="back" type="button" onClick={() => setQuickStartStep(1)}>{t("이전 질문")}</button>
              </div>}
              {quickStartStep === 3 && quickStartAsset && quickStartSource && <div className="settings-quick-start-review">
                <strong>{t("이렇게 시작합니다")}</strong>
                <div><span><b>{t("운용")}</b>{t("PAPER · 실주문 없음")}</span><span><b>{t("대상")}</b>{QUICK_START_SOURCES[quickStartAsset].find((item) => item.id === quickStartSource)?.label}</span><span><b>{t("투자금")}</b>{t("NoahAI 자동 위험관리")}</span><span><b>{t("보호")}</b>{t("LIVE 대상 해제 · 증권 주문 가드 유지")}</span></div>
                <p>{t("API 연결은 시세·계좌 조회에 필요할 수 있지만 외부 AI 키는 필수가 아닙니다. 이 단계는 비밀키를 입력하거나 거래를 시작하지 않습니다.")}</p>
                <footer><button type="button" onClick={() => setQuickStartStep(2)}>{t("이전")}</button><button className="primary" type="button" onClick={stageQuickStart}>{t("안전 시작안을 변경 대기에 넣기")}</button></footer>
              </div>}
              {quickStartStep === 4 && <div className="settings-quick-start-done">
                <strong>{t("빠른 시작 선택을 확인했습니다.")}</strong>
                <p>{t("아직 적용되지 않았습니다. 화면 아래의 ")}<b>{t("전체 설정 저장")}</b>{t("을 누르면 중요 설정 확인창이 한 번 더 표시됩니다. 저장 후 거래소 API 탭에서 선택 기관의 연결을 점검하고, 대시보드에서 해당 서비스를 직접 시작하세요.")}</p>
                <div><button type="button" onClick={() => { setQuickStartOpen(false); setActiveSection("exchange_api"); setCredentialProvider(quickStartAsset === "stock" ? `stock:${quickStartSource === "koreaInvestment" ? "kis" : quickStartSource.toLowerCase()}` : quickStartSource); }}>{t("다음: API 연결 확인")}</button><button type="button" onClick={() => onAskAssistant(`처음 사용 빠른 시작에서 ${quickStartAsset === "crypto" ? "코인" : "주식·ETF"} ${quickStartSource} PAPER를 선택했습니다. 지금 변경 대기와 저장 후 API 연결, 대시보드 시작 순서를 초보자에게 3단계로 설명해줘. 설정을 저장하거나 거래를 실행하지 마.`, "general")}>{t("AI에게 다음 순서 묻기")}</button></div>
              </div>}
            </section>}
            {activeSection === "general" && snapshot && <section className="settings-contract-status">
              <strong>{t("설정 정리 상태")}</strong>
              <p>{t("앱 v3.9.1.43 · 설정 스키마 ")}{snapshot.schema_version}{t(" · 현재 모드 ")}{diagnostics?.trading?.paper_trading ? "PAPER" : "LIVE 확인 필요"}{t(" · 계정 설정 ")}{snapshot.account_scope}</p>
              {snapshot.storage_status?.ok === false && <p className="error-text">{t("기존 settings.json의 문자 인코딩 또는 JSON 형식을 읽지 못했습니다. 원본 보호를 위해 저장이 차단됩니다. 파일을 삭제하지 말고 설정 백업 복구 또는 지원 로그 전달을 이용하세요.")}</p>}
              {snapshot.storage_status?.needs_normalization && <p>{t("기존 ")}{snapshot.storage_status.encoding}{t(" 설정을 호환해서 읽었습니다. 다음 검증 저장 시 UTF-8 정본으로 변환됩니다.")}</p>}
              <span>{t("기본 설정은 원본 화면의 사용자 항목이며, 고급 설정에는 정본 JSON의 기술 정책이 표시됩니다. 비밀값과 런타임 snapshot은 별도 보호 경로로 관리됩니다.")}</span>
            </section>}
            {activeSection === "general" && <section className="settings-autopilot-guide">
              <header><div><strong>{t("기본 자율운행 · 시작 전에 3가지만 확인하세요")}</strong><p>{t("전략 스튜디오 전략을 만들지 않아도 기본 자동매매가 작동합니다. 거래 이력이 0건이어도 20번을 기다리지 않고 조건이 맞는 첫 판단부터 PAPER 또는 허용된 LIVE 주문 후보를 처리합니다.")}</p></div><span>{t("거래 데이터 0건부터 실행 가능")}</span></header>
              <div className="settings-autopilot-flow"><b>{t("시작")}</b><i>→</i><span>{t("코인 자동 선정")}</span><i>→</i><span>{t("시장·기술 분석")}</span><i>→</i><span>{t("AI 연결 시 보강")}</span><i>→</i><span>{t("위험 검사")}</span><i>→</i><b>{t("주문·기록")}</b></div>
              <div className="settings-autopilot-responsibilities"><div><strong>{t("사용자가 한 번 확인")}</strong><p>{t("① PAPER/LIVE ② 분석·주문 거래소 ③ API 연결과 주문 권한")}</p></div><div><strong>{t("앱이 실행 중 자동 처리")}</strong><p>{t("후보 선정, 신호 판단, 포지션 크기, 익절·손절, 위험 차단, 결과 기록")}</p></div></div>
              <footer><button type="button" onClick={onOpenManual}>{t("매뉴얼에서 자세히 보기")}</button><button type="button" onClick={() => onAskAssistant("전략 스튜디오 전략을 사용하지 않는 기본 자율운행이 현재 내 PAPER/LIVE, 거래소 선택, API 연결 상태에서 어떻게 작동하는지 초보자 기준으로 설명해줘. 거래 이력 0건부터 시작되는 흐름과 사용자가 확인할 3가지만 먼저 알려줘.", activeSection)}>{t("AI에게 현재 상태 설명받기")}</button></footer>
            </section>}
            {(activeSection === "exchange_api" || activeSection === "ai_engine" || activeSection === "alpha") && <div className="credential-box settings-credential-panel">
              <strong>{t("연결 자격증명")}</strong>
              <p>{t("저장된 비밀값은 보안상 화면에 다시 보내지 않습니다. 대신 Provider와 필드별 저장 여부를 표시합니다.")}</p>
              <div className="credential-status-list">{visibleCredentialStatus.map(([name, ready]) => <span className={ready ? "ready" : ""} key={name}>{name === "ai:openai" ? "OPENAI 기본 보호" : name === "ai:openai_shared" ? "OPENAI 공개 질문용" : (name.startsWith("ai:") ? name.slice(3) : name).toUpperCase()} {ready ? "필수값 저장됨" : "필수값 미저장"}</span>)}</div>
              <select value={credentialProvider} onChange={(event) => setCredentialProvider(event.target.value)}>
                {credentialProviders.map((provider) => <option key={provider} value={provider}>{credentialProviderLabel(provider)}</option>)}
              </select>
              <div className={selectedCredentialReady ? "credential-selected-state ready" : "credential-selected-state"}><strong>{credentialProviderLabel(credentialProvider)}</strong><span>{selectedCredentialReady ? "필수 연결 정보가 이 계정 설정에 저장되어 있습니다." : "필수 연결 정보가 현재 계정 설정에 없습니다."}</span><small>{selectedCredentialReady ? "실제 API 연결 성공 여부는 아래 점검 버튼으로 별도 확인하세요." : "실행 중인 엔진에 예전 값이 남아 있어도 재시작 후에는 사용할 수 없습니다."}</small></div>
              <div className="credential-input-grid">{credentialFields.map((field) => {
                const stored = Boolean(selectedCredentialFieldStatus[field]);
                const label = CREDENTIAL_FIELD_LABELS[field] ?? field;
                return <label key={`${credentialProvider}:${field}`}><span>{label}<em className={stored ? "ready" : ""}>{stored ? "저장됨" : field === "base_url" ? "선택·미저장" : "미저장"}</em></span><input type={field === "base_url" ? "url" : showCredentialDraft ? "text" : "password"} autoComplete="off" placeholder={stored ? "•••••••• 저장됨 · 변경할 때만 새 값 입력" : label} value={credentialDraft[field] ?? ""} onChange={(event) => { diagnosticEpoch.current += 1; setProviderCheck(null); setSupportSummary(""); setAccountModelCatalogs((current) => Object.fromEntries(Object.entries(current).filter(([scope]) => scope !== credentialProvider))); setCredentialDrafts((current) => ({ ...current, [credentialProvider]: { ...(current[credentialProvider] ?? {}), [field]: event.target.value } })); }} /></label>;
              })}</div>
              <div className="credential-actions"><button className="secondary-button" type="button" disabled={busy} onClick={() => void saveCredential(false)}>{t("새 값 저장")}</button><button className="secondary-button" type="button" disabled={!Object.values(credentialDraft).some((value) => value.length > 0)} onClick={() => setShowCredentialDraft((value) => !value)}>{showCredentialDraft ? "입력값 숨기기" : t("입력값 보기")}</button><button className="danger-button" type="button" disabled={busy || !selectedCredentialReady} onClick={() => void saveCredential(true)}>{t("연결 삭제")}</button></div>
              {credentialDraft && Object.values(credentialDraft).some((value) => value.trim()) && <small>{t("입력한 연결 정보는 새 값 저장, 전체 설정 저장 또는 저장 후 닫기를 누르면 저장됩니다.")}</small>}
              <small>{t("입력값 보기는 현재 입력 중인 값만 보여 줍니다. 이미 저장된 비밀값은 다시 표시하지 않습니다.")}</small>
              {OFFICIAL_API_PORTALS[credentialProvider] && <a className="official-api-link" href={OFFICIAL_API_PORTALS[credentialProvider].url} target="_blank" rel="noreferrer">↗ {OFFICIAL_API_PORTALS[credentialProvider].label}{t("에서 발급·권한 확인")}</a>}
            </div>}
            {activeSection === "ai_engine" && <section className="settings-ai-budget-panel" aria-label={t("AI 비용 관리")}>
              <header><div><strong>{t("AI 비용 관리 · 외부 호출 한도")}</strong><p>{t("회원·거래 제한이 아니라 API 비용 폭주와 반복 실행을 막는 사용자 설정입니다. 카드에는 현재 저장된 한도가 표시되며, 아래 입력값을 바꾼 경우 `현재 설정 저장`을 눌러야 반영됩니다.")}</p></div><button type="button" onClick={() => client.assistantStatus().then((next) => setAssistantStatus(next?.budget ?? next)).catch(() => setAssistantStatus(null))}>{t("사용량 새로고침")}</button></header>
              <div className="settings-ai-budget-meters">
                <div className={assistantStatus?.daily_exhausted ? "exhausted" : ""}><span>{t("오늘 외부 호출 · 현재 저장 한도")}</span><strong>{assistantStatus?.daily_used ?? "—"} / {assistantStatus?.daily_limit ?? 30}{t("회")}</strong><small>{t("설정 범위 1~1,000회")}</small></div>
                <div className={assistantStatus?.monthly_exhausted ? "exhausted" : ""}><span>{t("이번 달 외부 호출 · 현재 저장 한도")}</span><strong>{assistantStatus?.monthly_used ?? "—"} / {assistantStatus?.monthly_limit ?? 500}{t("회")}</strong><small>{t("설정 범위 1~30,000회")}</small></div>
              </div>
              <div className="settings-ai-cost-estimate">
                <div><span>{t("오늘 정가 기준 예상 비용")}</span><strong>{Number(assistantStatus?.priced_calls?.today ?? 0) > 0 ? `약 $${Number(assistantStatus?.estimated_cost_usd?.today ?? 0).toFixed(6)}` : "산정 근거 없음"}</strong></div>
                <div><span>{t("이번 달 정가 기준 예상 비용")}</span><strong>{Number(assistantStatus?.priced_calls?.month ?? 0) > 0 ? `약 $${Number(assistantStatus?.estimated_cost_usd?.month ?? 0).toFixed(6)}` : "산정 근거 없음"}</strong></div>
                <small>{t("AI 어시스턴트·전략 스튜디오·차트 분석·전사처럼 사용자가 직접 실행한 외부 AI 호출의 로컬 정가 추정치입니다. 무료 토큰·데이터 공유 혜택·캐시·프로모션·세금이 반영된 실제 청구액은 Provider 콘솔이 정본입니다. 자동매매 백그라운드 AI와 Provider 계정 전체 청구액은 포함하지 않습니다. 구버전·실패 요청·토큰 미제공·단가 미등록 모델은 0원으로 만들지 않고 비용 미산출로 분리합니다. 미완료 시도 오늘 ")}{assistantStatus?.incomplete_attempts?.today ?? 0}{t("회 · 비용 미산출 완료 오늘 ")}{assistantStatus?.cost_unavailable_calls?.today ?? 0}{t("회")}</small>
              </div>
              {assistantStatus?.usage_by_model && Object.keys(assistantStatus.usage_by_model).length > 0 && <div className="settings-ai-actual-usage">
                <strong>{t("최근 로컬 원장 · 실제 응답 모델별 사용량")}</strong>
                {Object.entries(assistantStatus.usage_by_model).slice(-6).reverse().map(([modelName, raw]) => {
                  const row = (raw && typeof raw === "object" ? raw : {}) as Record<string, any>;
                  return <span key={modelName}><b>{modelName}</b><small>{Number(row.calls || 0)}{t("회 · ")}{Number(row.total_tokens || 0).toLocaleString()}{t(" 토큰")}</small></span>;
                })}
                <small>{t("성공 응답의 Provider 반환 모델을 기록합니다. Provider 콘솔의 Organization·Project·기간 필터와 함께 대조하세요.")}</small>
              </div>}
              <div className="settings-ai-budget-boundary"><div><strong>{t("한도에 포함")}</strong><span>{t("심층분석 · 차트/이미지 해석 · 영상/음성 전사 · 외부 AI 전략 보조")}</span></div><div><strong>{t("한도 후에도 계속")}</strong><span>{t("일반 안내 · 텍스트/Pine 로컬 규칙 분석 · 5분 따라 만들기 · 거래 엔진")}</span></div></div>
              <div className="settings-ai-budget-error"><strong>{t("상태 429를 구분하세요")}</strong><span><code>interactive_ai_budget_exceeded</code>{t("는 NoahAI가 Provider 요청 전에 막은 로컬 비용 보호입니다. 제공사 자체 429는 해당 Provider의 속도·쿼터·결제 제한이며 별도 문제입니다.")}</span><small>{t("Provider 전송을 시도한 요청은 응답 실패 여부와 관계없이 반복 폭주 방지를 위해 1회로 집계합니다. 현재 일일 집계는 UTC 00:00에 갱신됩니다(한국시간 09:00). 월간 집계도 UTC 달력 기준입니다.")}</small></div>
            </section>}
            {activeSection === "ai_engine" && <section className="settings-ai-routing-panel" aria-label={t("나만의 AI 구성")}>
              <header><div><strong>{t("나만의 AI 구성 · 작업별 모델")}</strong><p>{t("한 모델을 모든 작업에 강제하지 않고 비용·속도·정밀도에 따라 역할별 Provider와 모델을 선택합니다. 아래 표는 현재 화면 선택값이며 저장 전에는 실행에 반영되지 않습니다.")}</p></div></header>
              <div className="settings-ai-route-grid">
                {[
                  ["빈번·저비용", "ai_model_roles.frequent_cheap.provider", "ai_model_roles.frequent_cheap.model", "반복 구조화·저비용 작업"],
                  ["표준 분석", "ai_model_roles.standard.provider", "ai_model_roles.standard.model", "일반적인 구조화 분석"],
                  ["정밀·전략", "ai_model_roles.premium.provider", "ai_model_roles.premium.model", "Strategy Studio 외부 보조"],
                  ["AI 애널리스트", "ai_provider_profiles.analyst.provider", "ai_provider_profiles.analyst.model", "시장·차트 분석"],
                  ["AI 어시스턴트", "ai_provider_profiles.assistant.provider", "ai_provider_profiles.assistant.model", "사용자가 누른 심층질문"],
                ].map(([label, providerPath, modelPath, purpose]) => {
                  const pending = Object.prototype.hasOwnProperty.call(changed, providerPath) || Object.prototype.hasOwnProperty.call(changed, modelPath);
                  return <div key={label}><span>{label}<em>{pending ? "변경 대기 · 아직 미적용" : "저장됨 · 실행값"}</em></span><strong>{String(draft[providerPath] || "미선택").toUpperCase()} · {SETTING_OPTION_LABELS[String(draft[modelPath] || "")] ?? String(draft[modelPath] || "자동 선택")}</strong><small>{purpose}</small></div>;
                })}
                <div className="fixed"><span>{t("영상·음성 전사")}</span><strong>OPENAI · {SETTING_OPTION_LABELS[String(draft["ai_custom_transcription.model"] || "")] ?? String(draft["ai_custom_transcription.model"] || "gpt-4o-mini-transcribe")}</strong><small>{t("YouTube 공개 자막이 없을 때만 음성 전사 사용")}</small></div>
              </div>
              <div className="settings-ai-model-notice"><strong>{t("DeepSeek 4.1 표기에 관하여")}</strong><span>{t("공식 API 모델 ID는 현재 ")}<code>deepseek-v4-flash</code>{t("입니다. 이 별칭이 DeepSeek 서버에서 최신 Flash 버전으로 자동 갱신됩니다. 존재가 확인되지 않은 ")}<code>deepseek-v4.1-flash</code>{t(" 문자열은 추가하지 않습니다.")}</span><small>{t("실제 계정의 목록과 선택 모델 호출 가능 여부는 아래 실제 점검에서 따로 확인합니다. 비전 실험형은 deepseek-v4-flash-vision-exp로 별도 선택할 수 있습니다.")}</small></div>
              <div className="settings-ai-model-catalog">
                <header><div><strong>{visibleModelProvider.toUpperCase()}{t(" 모델 비교")}</strong><span>{t("호환 목록 ")}{visibleModelDetails.length}{t("개 · 모델 ")}{snapshot?.model_catalog_meta?.model_as_of ?? "기준일 확인 필요"}{t(" · 가격 ")}{snapshot?.model_catalog_meta?.price_as_of ?? "기준일 확인 필요"}</span></div>{snapshot?.model_catalog_meta?.pricing_urls?.[visibleModelProvider] && <a href={snapshot.model_catalog_meta.pricing_urls[visibleModelProvider]} target="_blank" rel="noreferrer">{t("공식 가격표 열기")}</a>}</header>
                <div className="settings-ai-model-grid">{visibleModelDetails.map((model) => {
                  const checked = Array.isArray(checkedAccountModels);
                  const available = checked && checkedAccountModels.includes(model.model);
                  const probeAvailable = Boolean(providerCheck?.model_callable) && providerCheck?.credential_scope === credentialProvider && String(providerCheck?.requested_model || "") === model.model;
                  const price = model.input_per_mtok_usd == null || model.output_per_mtok_usd == null
                    ? "단가 미등록 · 공식 가격표 확인"
                    : `입력 $${model.input_per_mtok_usd} · 출력 $${model.output_per_mtok_usd} / 100만 토큰`;
                  return <article key={`${visibleModelProvider}:${model.model}`}>
                    <header><strong>{SETTING_OPTION_LABELS[model.model] ?? model.model}</strong><em>{model.status_label}</em></header>
                    <span>{model.use} · {model.capabilities.join("/")}</span>
                    <p><b>{t("강점")}</b>{model.strength}</p><p><b>{t("주의")}</b>{model.limitation}</p>
                    <small>{price}{model.note ? ` · ${model.note}` : ""}</small>
                    <small className={available || probeAvailable ? "account-ready" : ""}>{probeAvailable ? `실제 호출 확인됨${String(providerCheck?.actual_model || "") && String(providerCheck?.actual_model || "") !== model.model ? ` · 응답 모델 ${String(providerCheck?.actual_model || "")}` : ""}` : checked ? (available ? "Provider 모델 목록에서 조회됨 · 실제 호출은 별도 확인" : "Provider 모델 목록에서 미확인 · 실제 호출 결과가 우선") : "계정 사용 가능 여부 미확인 · 실제 연결 점검 필요"}</small>
                  </article>;
                })}</div>
                <footer>{t("이 목록은 NoahAI가 연결할 수 있는 정적 호환 목록입니다. 공급자의 모든 모델을 뜻하지 않으며, 실제 호출 가능 여부는 사용자 계정의 모델 목록과 기능 점검 결과가 우선합니다.")}</footer>
              </div>
              <div className="settings-openai-sharing-notice">
                <strong>{t("OpenAI 공개 질문용 Project 분리 · 기본 OFF")}</strong>
                <b>{Boolean(draft["ai_data_routing.public_general_sharing_enabled"]) && snapshot?.credential_status?.["ai:openai_shared"] ? "사용 준비됨 · 질문마다 별도 선택" : "현재 기본 보호 경로만 사용"}</b>
                <span>{t("OpenAI API 데이터는 기본적으로 모델 학습에 사용되지 않지만 사용자가 조직 설정에서 명시적으로 공유에 동의하면 모델 개선에 사용될 수 있습니다. 무료 제공량·대상 모델·기간은 계정별로 다르며 NoahAI가 확인하거나 변경하지 않습니다.")}</span>
                <span>{t("이제 `OpenAI · 기본 보호 Project`와 `OpenAI · 공개 일반 질문용 Project` 키를 분리할 수 있습니다. 공개 경로는 위 설정을 켜고 AI 어시스턴트에서 사용자가 `공개 일반 질문`을 직접 선택한 1건에만 사용합니다. 전략·Pine·문서·차트·포지션·계좌·설정값·최근 대화는 항상 기본 보호 경로에 남습니다.")}</span>
                <span>{t("현재 작업별 Provider가 DeepSeek·Kimi·Claude·Gemini이면 기존 배치는 그대로 유지됩니다. 공개 일반 질문을 명시한 경우에만 별도 OpenAI 모델과 키를 사용하며 거래 판단·전략 생성 경로를 자동 변경하지 않습니다.")}</span>
                <span>{t("공유용 키가 없거나 설정이 꺼져 있으면 기본 보호 경로로 안전하게 돌아갑니다. NoahAI는 OpenAI 조직의 실제 데이터 공유 활성화 여부나 무료 제공량을 API 키만으로 확인하지 못하므로 조직 콘솔을 직접 확인해야 합니다. `store=false`는 요청 저장을 줄이는 별도 옵션이며 모델 학습 동의나 기본 악용 방지 보관 정책을 대신하지 않습니다.")}</span>
                <div><a href="https://developers.openai.com/api/docs/guides/your-data" target="_blank" rel="noreferrer">{t("OpenAI 공식 데이터 정책")}</a><a href="https://platform.openai.com/settings/organization/data-controls/sharing" target="_blank" rel="noreferrer">{t("내 조직 데이터 공유 설정 확인")}</a></div>
                <small>{t("NoahAI 일반 설정 안내는 로컬로 동작해 이 혜택이나 외부 토큰이 필요하지 않습니다. 실제 청구액은 OpenAI Usage가 정본이며 위 정가 예상액과 다를 수 있습니다.")}</small>
              </div>
            </section>}
            {(activeSection === "ai_engine" || activeSection === "alpha") && <section className="settings-parity-panel">
              {activeSection === "alpha" && <p>{t("AlphaArena 전용 키를 점검합니다. 엔진 변경은 먼저 현재 설정 저장을 누르세요. 실행 중 설정 변경은 실험을 정지시킵니다.")}</p>}<div className="settings-default-ai-note"><strong>{t("기본 자동매매와 전략 스튜디오는 별개입니다.")}</strong><span>{t("기본 모드는 외부 AI 키가 없어도 로컬 규칙·통계로 실행되며, 키가 연결되면 필요한 시장 이벤트에서 AI 판단을 보강합니다. ‘AI 최소 학습 표본 20’을 채워야 시작하는 절차는 없습니다.")}</span></div>
              <header><div><strong>{t("AI 모델·기능 실제 점검")}</strong><p>{t("Provider 모델 목록 조회 후 선택 모델을 비민감 고정 문장으로 1회 실제 호출합니다. AlphaArena는 전용 키와 저장된 엔진, 공개 질문용 키는 공개 질문 모델을 사용합니다. 진단도 외부 호출 1회와 실제 토큰 비용이 발생하며 AI 비용 관리에 기록됩니다.")}</p></div><button className="primary-button" type="button" disabled={busy || !selectedCredentialReady} onClick={runProviderCheck}>{t("선택 모델 1회 실제 호출 점검")}</button></header>
              <div className="settings-preset-row settings-ai-action-row"><span>{t("설명 프리셋")}</span><button type="button" onClick={() => applyAssistantPreset("saver")}>{t("절약형")}</button><button type="button" onClick={() => applyAssistantPreset("standard")}>{t("균형형")}</button><button type="button" onClick={() => applyAssistantPreset("premium")}>{t("정밀형")}</button><button type="button" onClick={() => onAskAssistant("AI 엔진/API를 처음 연결하는 사용자입니다. 공식 키 발급, 최소 권한, Provider와 모델 선택, 예상 비용, 연결 점검을 3단계로 안내해줘. 비밀키를 답변에 붙여 넣으라고 하지 말고 설정을 자동 저장하지 마.", activeSection)}>{t("초보자 연결 3단계")}</button><button type="button" onClick={() => onAskAssistant("현재 저장된 AI 엔진 설정의 등록 여부만 보고 비용 절약형·균형형·정밀형 차이를 설명해줘. 키 값은 표시하지 말고 변경 후보만 제안해줘.", activeSection)}>{t("AI 설정 도우미")}</button><button type="button" onClick={() => onAskAssistant("NoahAI 초기 설정을 5문항으로 진행해줘. 1) 투자 경험 2) 운용 서비스 3) PAPER/LIVE 범위 4) 위험 허용도 5) AI 비용 선호를 한 번에 하나씩 묻고, 마지막에 변경 후보와 영향만 요약해줘. 내 확인 전에는 설정을 저장하거나 거래를 실행하지 마.", activeSection)}>{t("AI로 초기 설정 (5문항)")}</button></div>
              {providerCheck && providerCheck.credential_scope === credentialProvider && <div className={providerCheck.model_callable ? "diagnostic-result ready" : "diagnostic-result error-text"}>
                <b>{providerCheck.model_callable ? "선택 모델 실제 호출 확인됨" : providerCheck.catalog_checked ? "Provider 목록 연결됨 · 선택 모델 호출 실패" : "Provider 연결 확인 실패"}</b>
                <span>{t("요청 모델 ")}{String(providerCheck.requested_model || "미확인")}{t(" · 실제 응답 모델 ")}{String(providerCheck.actual_model || "응답 없음")}</span>
                {providerCheck.selection_pending && <span>{t("이 진단은 현재 화면 선택값을 호출했습니다. 실제 작업에 사용하려면 위의 `현재 설정 저장`을 눌러야 합니다.")}</span>}
                <span>{providerCheck.model_listed ? "Provider 모델 목록에서도 확인됨" : "Provider 모델 목록에서는 미확인 · 실제 호출 결과를 우선 확인"}</span>
                {Array.isArray(providerCheck.models) && providerCheck.models.length > 0 && <small>{t("Provider가 반환한 모델 예시: ")}{providerCheck.models.slice(0, 8).join(", ")}</small>}
                {providerCheck.model_callable && <small>{t("진단 사용량: 입력 ")}{Number(providerCheck.probe_usage?.input_tokens || 0)}{t(" · 출력 ")}{Number(providerCheck.probe_usage?.output_tokens || 0)}{t(" · 전체 ")}{Number(providerCheck.probe_usage?.total_tokens || 0)}{t(" 토큰 · 외부 호출 1회 기록")}</small>}
                {!providerCheck.model_callable && <small>{(providerCheck.errors || []).join(" · ") || (providerCheck.network_checked ? "선택한 모델이 이 계정·Project에서 호출 가능한지 확인하세요." : "외부 API 요청 전 단계에서 중단됨 · 저장된 키와 설치 엔진을 확인하세요")}</small>}
              </div>}
              <div className="settings-voice-summary"><b>{t("음성 도우미")}</b><span>{t("입력 ")}{diagnostics?.ai?.voice?.enabled ? "사용" : "꺼짐"}{t(" · 답변 읽기 ")}{diagnostics?.ai?.voice?.auto_tts ? "사용" : "꺼짐"}{t(" · 언어 ")}{diagnostics?.ai?.voice?.lang || "ko-KR"}</span><small>{t("아래 음성 입력·읽기·언어·속도 항목에서 변경합니다.")}</small></div>
            </section>}
            {activeSection === "notifications" && <section className="notification-settings-panel">
              <RemoteMonitorSettings client={client} />
              <header><div><strong>{t("외부 알림 연결 · 거래 엔진과 독립 실행")}</strong><p>{t("메시지 발송은 별도 큐에서 처리되어 느린 메신저가 거래·설정·가드레일을 기다리게 하지 않습니다. PC와 NoahAI가 꺼져 있으면 로컬 알림은 발송되지 않습니다.")}</p></div><button type="button" onClick={() => onAskAssistant("Discord 웹훅 또는 Telegram 봇을 NoahAI 외부 알림에 연결하는 과정을 초보자 기준으로 한 단계씩 안내해줘. 비밀값을 채팅에 붙여 넣으라고 하지 말고 설정 화면 입력칸을 사용하게 안내해줘.", activeSection)}>{t("AI 연결 도우미")}</button></header>
              <div className="notification-channel-grid">
                <article className={snapshot?.credential_status?.["notification:discord"] ? "ready" : ""}>
                  <div className="notification-channel-title"><div><span>{t("가장 쉬움")}</span><h3>{t("Discord 웹훅")}</h3></div><b>{snapshot?.credential_status?.["notification:discord"] ? "저장됨" : "연결 필요"}</b></div>
                  <ol><li>{t("Discord 채널의 설정을 엽니다.")}</li><li>{t("연동 → 웹후크 → 새 웹후크 → URL 복사를 누릅니다.")}</li><li>{t("아래에 붙여 넣고 저장한 뒤 테스트합니다.")}</li></ol>
                  <label><span>{t("웹훅 URL · 저장 후 다시 표시하지 않음")}</span><input type={showCredentialDraft ? "text" : "password"} autoComplete="off" placeholder={snapshot?.credential_field_status?.["notification:discord"]?.webhook_url ? "•••••••• 저장됨 · 변경할 때만 입력" : "https://discord.com/api/webhooks/…"} value={credentialDrafts["notification:discord"]?.webhook_url ?? ""} onChange={(event) => setCredentialDrafts((current) => ({ ...current, "notification:discord": { ...(current["notification:discord"] ?? {}), webhook_url: event.target.value } }))} /></label>
                  <div className="notification-actions"><button type="button" disabled={busy} onClick={() => void saveNotificationCredential("notification:discord")}>{t("1. 연결 저장")}</button><button type="button" disabled={busy || !snapshot?.credential_status?.["notification:discord"]} onClick={() => void runNotificationTest("discord")}>{t("2. 테스트 보내기")}</button><button className="danger-button" type="button" disabled={busy || !snapshot?.credential_status?.["notification:discord"]} onClick={() => void saveNotificationCredential("notification:discord", true)}>{t("삭제")}</button></div>
                  <a href="https://support.discord.com/hc/ko/articles/228383668" target="_blank" rel="noreferrer">{t("↗ Discord 웹훅 안내")}</a>
                </article>
                <article className={snapshot?.credential_status?.["notification:telegram"] ? "ready" : ""}>
                  <div className="notification-channel-title"><div><span>{t("개인 알림 권장")}</span><h3>{t("Telegram 봇")}</h3></div><b>{snapshot?.credential_status?.["notification:telegram"] ? "저장됨" : "연결 필요"}</b></div>
                  <ol><li>{t("Telegram의 @BotFather에서 /newbot으로 봇 토큰을 발급합니다.")}</li><li>{t("토큰을 저장하고 만든 봇 대화에서 Start 또는 /start를 보냅니다.")}</li><li>{t("대화방 자동 찾기 → 받을 곳 선택 → 저장 → 테스트 순서로 진행합니다.")}</li></ol>
                  <label><span>{t("봇 토큰 · 저장 후 다시 표시하지 않음")}</span><input type={showCredentialDraft ? "text" : "password"} autoComplete="off" placeholder={snapshot?.credential_field_status?.["notification:telegram"]?.bot_token ? "•••••••• 저장됨 · 변경할 때만 입력" : "123456789:AA…"} value={credentialDrafts["notification:telegram"]?.bot_token ?? ""} onChange={(event) => setCredentialDrafts((current) => ({ ...current, "notification:telegram": { ...(current["notification:telegram"] ?? {}), bot_token: event.target.value } }))} /></label>
                  <label><span>{t("받을 대화방 ID · 자동 찾기 권장")}</span><input type="text" inputMode="numeric" autoComplete="off" placeholder={snapshot?.credential_field_status?.["notification:telegram"]?.chat_id ? "저장됨 · 바꿀 때 자동 찾기" : "대화방 자동 찾기로 선택"} value={credentialDrafts["notification:telegram"]?.chat_id ?? ""} onChange={(event) => setCredentialDrafts((current) => ({ ...current, "notification:telegram": { ...(current["notification:telegram"] ?? {}), chat_id: event.target.value } }))} /></label>
                  <div className="notification-actions telegram"><button type="button" disabled={busy} onClick={() => void saveNotificationCredential("notification:telegram")}>{t("1. 토큰/대화방 저장")}</button><button type="button" disabled={busy || !(snapshot?.credential_field_status?.["notification:telegram"]?.bot_token || credentialDrafts["notification:telegram"]?.bot_token)} onClick={() => void discoverTelegram()}>{t("2. 대화방 자동 찾기")}</button><button type="button" disabled={busy || !snapshot?.credential_status?.["notification:telegram"]} onClick={() => void runNotificationTest("telegram")}>{t("3. 테스트 보내기")}</button><button className="danger-button" type="button" disabled={busy || !(snapshot?.credential_field_status?.["notification:telegram"]?.bot_token || snapshot?.credential_field_status?.["notification:telegram"]?.chat_id)} onClick={() => void saveNotificationCredential("notification:telegram", true)}>{t("삭제")}</button></div>
                  {telegramChats.length > 0 && <div className="telegram-chat-list"><strong>{t("받을 대화방 선택")}</strong>{telegramChats.map((chat) => <button type="button" key={chat.chat_id} onClick={() => setCredentialDrafts((current) => ({ ...current, "notification:telegram": { ...(current["notification:telegram"] ?? {}), chat_id: chat.chat_id } }))}><span>{chat.label}</span><small>{chat.type} · {chat.chat_id}</small></button>)}</div>}
                  <a href="https://core.telegram.org/bots/tutorial" target="_blank" rel="noreferrer">{t("↗ Telegram 공식 봇 안내")}</a>
                </article>
              </div>
              <div className="notification-final-steps"><strong>{t("마지막 확인")}</strong><span>{t("① 연결 정보를 저장·테스트합니다. ② 아래에서 외부 알림과 사용할 채널을 ON으로 바꿉니다. ③ 받을 이벤트와 반복 방지 시간을 확인한 뒤 이 탭 저장을 누릅니다.")}</span><button type="button" onClick={() => setShowCredentialDraft((value) => !value)}>{showCredentialDraft ? "현재 입력값 숨기기" : "현재 입력값 보기"}</button></div>
              {notificationResult?.last_test?.ok && <div className="diagnostic-result ready"><b>{t("최근 테스트 성공")}</b><span>{String(notificationResult.last_test.channel).toUpperCase()}{t(" 메시지 전송을 확인했습니다.")}</span></div>}
            </section>}
            {activeSection === "advanced" && <section className="settings-legacy-guide advanced-guide">
              <h3>{t("5. 자동매매 안전 규칙 (선택)")}</h3>
              <p>{t("생성형 AI가 수익 규칙을 스스로 만드는 기능이 아닙니다. 전략이 만든 거래 후보를 수익성·집중도·시장 상태·슬리피지 같은 규칙으로 다시 검사하는 안전 계층입니다.")}</p>
              <p>{t("일반 사용자는 개별 숫자를 조절할 필요 없이 safe(권장)를 유지하고 PAPER에서 먼저 확인하세요. 세부 숫자는 ‘고급 설정 보기’를 눌렀을 때만 표시됩니다.")}</p>
              <strong>{t("프리셋 빠른 전환")}</strong>
              <div className="settings-preset-row"><button type="button" onClick={() => applyAdvancedPreset("dev")}>{t("전체 OFF (개발·진단)")}</button><button className="safe" type="button" onClick={() => applyAdvancedPreset("safe")}>{t("safe (신규 권장)")}</button><button className="aggressive" type="button" onClick={() => applyAdvancedPreset("aggressive")}>{t("aggressive (숙련자)")}</button></div>
              <small>{t("전체 OFF는 개발·진단 전용이고 aggressive는 충분한 검증 자료가 있는 숙련자용입니다. 프리셋도 저장 버튼을 누르기 전에는 적용되지 않습니다.")}</small>
            </section>}
            {activeSection === "alpha" && <section className="settings-legacy-guide alpha-guide">
              <h3>{t("6. AlphaArena 실험실")}</h3>
              <p>{t("숙련자용 독립 실험 모드 · 기본 OFF. Binance USDT 선물 전용이며 표준 자동매매의 수익성·포트폴리오·전략 합의 계층과 공유되지 않습니다.")}</p>
              <div className="alpha-capital-summary"><span>{t("초기 자금 기준")}</span><strong>{SETTING_OPTION_LABELS[String(draft["alpha_arena.initial_capital_benchmark"] ?? "10000")] ?? String(draft["alpha_arena.initial_capital_benchmark"] ?? "10000")}</strong><small>{t("LLM 비교·판단용 벤치마크이며 실제 주문 잔액이나 계좌 손실 한도가 아닙니다.")}</small></div>
              <strong>{t("현재 고정 가드레일과 기본값")}</strong>
              <span>{t("판단 주기 최소 30초 · 레버리지 10~20배 제한 · 진입마다 TP/SL 필수 · 심볼별 쿨다운 · 최대 동시 포지션 · 틱당 위험 상한")}</span>
              <div className="alpha-warning-card"><strong>{t("주의사항")}</strong><ul><li>{t("기본 OFF인 독립 실험 모드이며 표준 자동매매와 동시에 켜기 전에 별도 검증이 필요합니다.")}</li><li>{t("기존 TP/SL뿐 아니라 AlphaArena 자체 TP/SL·주문 가드도 모두 통과해야 합니다.")}</li><li>{t("LLM이 TP/SL을 지정하지 않거나 위험·쿨다운·포지션 한도를 넘으면 주문 후보가 차단됩니다.")}</li><li>{t("Windows 설치본과 실계정 장시간 E2E 전에는 LIVE 완료로 판정하지 않습니다.")}</li></ul></div>
            </section>}
            {activeSection === "exchange_api" && <section className="settings-parity-panel">
              <header><div><strong>{t("거래소·증권 계정 연결 점검")}</strong><p>{t("선택한 대상의 실제 계정 snapshot을 조회합니다. 주문은 제출하지 않습니다.")}</p></div><button className="primary-button" type="button" disabled={busy} onClick={runAccountConnectionCheck}>{t("저장된 키로 실제 연결 점검")}</button></header>
              <div className="settings-assistant-tools"><button type="button" onClick={() => onAskAssistant(`처음 연결하는 사용자입니다. ${credentialProvider.toUpperCase()} API 발급, 읽기·주문 권한 분리, IP 허용목록, PAPER/LIVE 확인, 연결 점검을 3단계로 안내해줘. 출금 권한은 금지하고 값을 자동 저장하지 마.`, activeSection)}>{t("초보자 연결 3단계")}</button><button type="button" onClick={() => onAskAssistant(`현재 ${credentialProvider.toUpperCase()} 등록 상태를 기준으로 연결 실패 원인과 최소 권한을 점검해줘. 비밀값은 표시하지 말고 주문도 실행하지 마.`, activeSection)}>{t("거래소·증권 설정 도우미")}</button></div>
              {supportSummary && <div className="support-summary"><pre>{supportSummary}</pre><div><button type="button" onClick={() => navigator.clipboard?.writeText(supportSummary)}>{t("지원 요약 복사")}</button><button type="button" onClick={() => downloadText("NoahAI-연결점검.txt", supportSummary)}>{t("지원 요약 파일 저장")}</button></div></div>}
            </section>}
            {(activeSection === "advanced" || activeSection === "alpha") && <section className="settings-scope-warning">
              <strong>{activeSection === "alpha" ? "연구·PAPER 비교 범위" : "전략·주문·위험 적용 범위"}</strong>
              <p>{t("표시값은 계정 설정 정본이며 저장 시 diff/revision 검증을 거칩니다. 중요 설정은 즉시 주문을 만들지 않지만, 실행 중 워커의 다음 평가부터 영향을 줄 수 있습니다.")}</p>
              <span>{activeSection === "alpha" ? "AlphaArena의 LIVE 실행은 별도 확인과 외부 검증 게이트가 열리기 전까지 차단됩니다." : "critical 항목 저장 전 PAPER/LIVE, 대상 거래소·증권사, 포지션 소유권을 다시 확인하세요."}</span>
            </section>}
            {activeSection === "advanced" && String(draft["position_sizing_policy.mode"] ?? "") === "legacy_venue" && <section className="settings-parity-panel">
              <header><div><strong>{t("기존 투자금 계산을 그대로 보존 중입니다")}</strong><p>{t("업데이트가 기존 LIVE 주문금액을 자동으로 키우지 않도록 거래소별 이전 계산을 유지했습니다. 오류가 아니며, 선택 전까지 기존 방식으로 동작합니다.")}</p></div><button type="button" onClick={() => updateDraftField("position_sizing_policy.mode", "account_risk")}>{t("자동 위험관리 불러오기")}</button></header>
              <small>{t("버튼은 설정 초안만 변경합니다. 계좌 평가금·손절거리 기반의 NoahAI 자동 위험관리를 사용하려면 아래 값을 검토한 뒤 저장해야 하며, 저장만으로 주문이 즉시 생성되지는 않습니다.")}</small>
            </section>}
            {activeSection === "system" && <section className="settings-parity-panel">
              <header><div><strong>{t("AI·런타임 준비 상태")}</strong><p>{t("네트워크 호출 없이 로컬 설정과 현재 런타임 연결을 진단합니다.")}</p></div><button type="button" disabled={busy} onClick={refreshDiagnostics}>{t("상태 새로고침")}</button></header>
              <div className="system-status-grid"><div><span>{t("AI 자동거래")}</span><strong>{diagnostics?.trading?.paper_trading ? "PAPER" : diagnostics?.trading?.live_ready ? "LIVE 준비" : "정지·차단"}</strong></div><div><span>{t("백엔드 AI 신호")}</span><strong>{diagnostics?.ai?.configured ? "키 등록됨" : "AI 키 필요"}</strong></div><div><span>{t("실시간 최적화")}</span><strong>{draft.dynamic_thresholds_enabled ? "자동 보정" : "수동·꺼짐"}</strong></div><div><span>{t("리스크 관리")}</span><strong>{draft["advanced_trading_layers.profitability_validation.enabled"] ? "가드 활성" : "설정 확인"}</strong></div></div>
              <div className="system-optimization-guide"><h3>{t("코인 시장상태 자동 보정 (규칙 기반)")}</h3><p>{t("코인 변동성을 저변동·보통·고변동으로 분류하고 RSI·모멘텀 진입 기준을 정해진 범위 안에서 바꿉니다. 생성형 AI가 임의로 학습하거나 전략을 다시 쓰는 기능이 아니며 주식 매매에는 적용되지 않습니다.")}</p><button type="button" onClick={stageDynamicThresholdDefaults}>{t("코인 자동 보정 권장값 불러오기")}</button><small>{t("일반 사용자는 자동 모드를 유지하면 됩니다. 세부 기준은 고급 설정 보기에서만 표시되며, 저장 버튼을 눌러야 적용됩니다.")}</small></div>
              <div className="system-warning-card"><strong>{t("사용자가 직접 확인할 항목")}</strong><p>{t("PAPER/LIVE, 분석·주문 거래소, API 주문 권한은 사용자가 선택해야 합니다. 신호 기준·슬리피지·쿨다운 같은 기술값은 권장 프리셋을 유지하고 PAPER에서 먼저 검증하세요.")}</p></div>
            </section>}
            {activeSection === "update" && <section className="settings-update-panel">
              <strong>{t("버전 정보 · 클라이언트 업데이트")}</strong>
              <p>{t("업데이트 확인과 다운로드는 거래 엔진을 중지하지 않습니다. 설치·재시작은 거래 워커 정지와 기록 저장이 완료된 경우에만 진행합니다.")}</p>
              <UpdateCenter client={client} accountScope={snapshot?.account_scope ?? ""} detailed currentVersion={platform?.release_version ? `v${platform.release_version}` : "v3.9.1.43"} />
              {!window.noahAI && <span>{t("브라우저 개발 실행에서는 데스크톱 업데이트를 사용할 수 없습니다.")}</span>}
              <RecordRecoveryPanel client={client} />
            </section>}
            {busy && !snapshot ? <div className="empty-state">{t("설정 정본을 불러오는 중입니다.")}</div> : activeFields.map((field) => (
              <label data-setting-path={field.path} className={`setting-row risk-${field.risk} presentation-${field.presentation}`} key={field.path}>
                <div><strong>{t(field.label)}</strong><p>{t(field.help)}</p>{showTechnicalFields && <code>{field.path}</code>}</div>
                {field.kind === "boolean" ? (
                  <input type="checkbox" checked={Boolean(draft[field.path])} onChange={(event) => setDraft({ ...draft, [field.path]: event.target.checked })} />
                ) : field.kind === "select" ? (
                  <select value={String(draft[field.path] ?? "")} onChange={(event) => updateDraftField(field.path, event.target.value)}>
                    {field.options.map((option) => <option value={option} key={option}>{field.path === STRATEGY_DIFFICULTY_PATH ? strategyDifficultyLabel(option) : t(SETTING_OPTION_LABELS[option] ?? option)}</option>)}
                  </select>
                ) : field.kind === "model_select" ? (
                  <select value={String(draft[field.path] ?? "")} onChange={(event) => updateDraftField(field.path, event.target.value)}>
                    {!String(draft[field.path] ?? "") && <option value="" disabled>{t("모델을 선택하세요")}</option>}
                    {modelOptions(field.path).map((option) => <option value={option} key={option}>{SETTING_OPTION_LABELS[option] ?? option}</option>)}
                  </select>
                ) : field.kind === "multiselect" ? (
                  <div className="setting-multiselect" role="group" aria-label={field.label}>
                    {field.options.map((option) => {
                      const selected = Array.isArray(draft[field.path]) ? draft[field.path] as string[] : [];
                      const observed = Array.isArray(draft.enabled_exchanges) ? draft.enabled_exchanges as string[] : [];
                      const disabled = field.path === "trade_enabled_exchanges" && !observed.includes(option);
                      return <label className={disabled ? "disabled" : ""} key={option}>
                        <input
                          type="checkbox"
                          checked={selected.includes(option)}
                          disabled={disabled}
                          onChange={(event) => {
                            const next = event.target.checked
                              ? [...selected, option]
                              : selected.filter((item) => item !== option);
                            const patch: Record<string, unknown> = { [field.path]: next };
                            if (field.path === "enabled_exchanges") {
                              const currentTrade = Array.isArray(draft.trade_enabled_exchanges) ? draft.trade_enabled_exchanges as string[] : [];
                              patch.trade_enabled_exchanges = currentTrade.filter((item) => next.includes(item));
                            }
                            setDraft({ ...draft, ...patch });
                          }}
                        />
                        <span>{SETTING_OPTION_LABELS[option] ?? option}</span>
                      </label>;
                    })}
                  </div>
                ) : field.kind === "json" ? (showTechnicalFields ?
                  <textarea className={changeState.invalid.includes(field.path) ? "json-setting invalid" : "json-setting"} spellCheck={false} value={typeof draft[field.path] === "string" ? String(draft[field.path]) : JSON.stringify(draft[field.path] ?? {}, null, 2)} onChange={(event) => setDraft({ ...draft, [field.path]: event.target.value })} />
                  : <span className="protected-structure-value">{t("고급 구조 · 현재값 유지")}</span>
                ) : field.kind === "text" ? (
                  <input type="text" value={String(draft[field.path] ?? "")} onChange={(event) => setDraft({ ...draft, [field.path]: event.target.value })} />
                ) : (
                  <input type="number" min={field.minimum ?? undefined} max={field.maximum ?? undefined} step={field.kind === "integer" ? 1 : "any"} value={Number(draft[field.path] ?? 0)} onChange={(event) => setDraft({ ...draft, [field.path]: event.target.value })} />
                )}
              </label>
            ))}
            {!busy && snapshot && !activeFields.length && activeSection !== "exchange_api" && <div className="empty-state">{activeSection === "advanced" ? "일반 사용자는 위 safe 프리셋만 선택하면 됩니다. 개별 숫자는 고급 설정 보기에서 확인할 수 있습니다." : "기본 사용자 설정이 없습니다. 필요한 경우 고급 설정 보기를 사용하세요."}</div>}
            {snapshot?.coverage && <details className="settings-coverage"><summary>{t("설정 정본 범위")}</summary><span>{snapshot.coverage.editable_top_level}/{snapshot.coverage.template_top_level}{t("개 최상위 항목 편집 · 계정 ")}{snapshot.account_scope}</span><p>{t("비밀값과 런타임 전용 값은 보호 경로에서 관리됩니다.")}</p></details>}
          </main>
        </div>
        <footer>
          <div><button className="primary-button" type="button" disabled={!totalPendingCount || busy || Boolean(changeState.invalid.length)} onClick={() => void saveAllPending(false)}>{busy ? "저장 중…" : "▣ 전체 설정 저장"}</button><button className="danger-button" type="button" onClick={cancelSettings}>{t("× 취소")}</button><button className="secondary-button" type="button" disabled={busy} onClick={() => stageDefaults("all")}>{t("전체 기본값 불러오기")}</button><button className="secondary-button" type="button" disabled={busy} onClick={openBackups}>{t("백업에서 복구")}</button><button className="secondary-button settings-close-action" type="button" disabled={busy} onClick={requestClose}>{t("닫기")}</button></div>
          <span className={message.includes("실패") || message.includes("conflict") || changeState.invalid.length ? "error-text" : ""}>{changeState.invalid.length ? `JSON 형식 오류: ${changeState.invalid.join(", ")}` : message || `일반 설정 ${changedCount}개 · 연결 정보 ${pendingCredentialCount}건 변경 대기`}</span>
        </footer>
        {backupOpen && <div className="settings-backup-layer" role="dialog" aria-modal="true" aria-label={t("설정 백업 복구")}>
          <section>
            <header><div><strong>{t("설정 백업 복구")}</strong><p>{t("최근 계정 설정 백업만 표시합니다. 파일 경로와 비밀값은 노출하지 않습니다.")}</p></div><button className="icon-button" type="button" onClick={() => setBackupOpen(false)} aria-label={t("백업 창 닫기")}>×</button></header>
            <div className="settings-backup-list">{backups.map((backup) => <button type="button" disabled={busy || Boolean(totalPendingCount)} onClick={() => restoreBackup(backup)} key={backup.name}><span>{new Date(backup.created_at).toLocaleString()}</span><small>{Math.max(1, Math.round(backup.size / 1024))}{t("KB · 복구")}</small></button>)}{!backups.length && <div className="empty-state">{t("복구할 설정 백업이 없습니다.")}</div>}</div>
            {totalPendingCount > 0 && <p className="error-text">{t("현재 변경과 연결 정보 입력을 저장하거나 취소한 뒤 복구하세요.")}</p>}
          </section>
        </div>}
        {closePromptOpen && <div className="settings-backup-layer settings-close-prompt" role="dialog" aria-modal="true" aria-label={t("설정 닫기 확인")}>
          <section><header><div><strong>{t("변경한 설정을 저장할까요?")}</strong><p>{t("저장하지 않은 설정 변경이 있습니다. 일반 설정 ")}{changedCount}{t("개와 연결 정보 ")}{pendingCredentialCount}{t("건을 저장·폐기하거나 계속 편집하세요.")}</p></div></header><div className="settings-close-prompt-actions"><button className="primary-button" type="button" disabled={busy || Boolean(changeState.invalid.length)} onClick={() => void saveAndClose()}>{t("저장 후 닫기")}</button><button className="danger-button" type="button" disabled={busy} onClick={() => { setClosePromptOpen(false); onClose(); }}>{t("저장하지 않고 닫기")}</button><button className="secondary-button" type="button" onClick={() => setClosePromptOpen(false)}>{t("계속 편집")}</button></div></section>
        </div>}
      </section>
    </div>
  );
}
