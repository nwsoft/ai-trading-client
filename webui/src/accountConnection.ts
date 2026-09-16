export type AccountConnectionKind =
  | "success"
  | "missing"
  | "disabled"
  | "authentication"
  | "clock"
  | "runtime"
  | "network"
  | "response"
  | "unknown";

export interface AccountConnectionView {
  kind: AccountConnectionKind;
  connected: boolean;
  label: string;
  balanceLabel: string;
  reason: string;
}

function detailStatus(detail: Record<string, any> | null | undefined): string {
  return String(detail?.status || detail?.balance?.status || "").trim().toLowerCase();
}

function detailMessage(detail: Record<string, any> | null | undefined): string {
  const candidates = [
    detail?.message,
    detail?.error,
    detail?.balance?.message,
    detail?.balance?.error,
  ];
  return candidates.find((value) => typeof value === "string" && value.trim())?.trim() || "";
}

export function accountConnectionView(
  detail: Record<string, any> | null | undefined,
  source: string,
): AccountConnectionView {
  const provider = source.toUpperCase();
  const status = detailStatus(detail);
  const message = detailMessage(detail);
  const combined = `${status} ${message}`;

  if (status === "success") {
    return { kind: "success", connected: true, label: "API 인증 완료", balanceLabel: "계정 조회 완료", reason: "" };
  }
  if (status === "credential_required" || status === "no_api_keys") {
    return {
      kind: "missing", connected: false, label: "API 키 미설정", balanceLabel: "API 키 연결 필요",
      reason: `${provider} 저장 자격증명이 확인되지 않습니다. 연결 정보를 저장한 뒤 다시 점검하세요.`,
    };
  }
  if (status === "disabled") {
    return {
      kind: "disabled", connected: false, label: "거래소 사용 꺼짐", balanceLabel: "사용 거래소에서 제외됨",
      reason: `${provider}가 사용 거래소에서 비활성화되어 있습니다. 거래소 선택에서 활성화한 뒤 다시 점검하세요.`,
    };
  }
  if (status === "invalid_api_keys" || /invalid[_ ]?(api|access)|signature|not authorized|permission denied/i.test(combined)) {
    return {
      kind: "authentication", connected: false, label: "API 인증 실패", balanceLabel: "인증 실패",
      reason: `${provider}가 자격증명을 거부했습니다. 저장된 키·Secret, API 권한, IP 허용목록을 확인하세요.`,
    };
  }
  if (/codec can't encode|unicodeencodeerror|cp949|local_runtime_encoding_error/i.test(combined)) {
    return {
      kind: "runtime", connected: false, label: "앱 문자 처리 오류", balanceLabel: "로컬 런타임 오류",
      reason: "거래소 요청 전에 Windows 로컬 엔진의 문자 인코딩 처리에 실패했습니다. API 키나 거래소 권한 오류가 아닙니다.",
    };
  }
  if (status === "clock_skew" || /server timestamp|recv_?window|timestamp for this request|retcode.?10002|code.?-1021/i.test(combined)) {
    return {
      kind: "clock", connected: false, label: "PC 시간 동기화 필요", balanceLabel: "거래소 시간 불일치",
      reason: `${provider}가 PC 시각과 거래소 서버 시각의 차이로 요청을 거부했습니다. Windows 날짜/시간 자동 설정과 '지금 동기화'를 실행한 뒤 다시 확인하세요. API 키 재발급 사유가 아닙니다.`,
    };
  }
  if (["client_unavailable", "exchange_manager_unavailable", "controller_unavailable"].includes(status)) {
    return {
      kind: "runtime", connected: false, label: "거래 엔진 준비 실패", balanceLabel: "실행 어댑터 오류",
      reason: `${provider} 거래소 실행 어댑터를 준비하지 못했습니다. 앱을 다시 시작한 뒤 반복되면 지원 로그를 전달하세요.`,
    };
  }
  if (status === "connection_failed" || /timeout|network|connection|dns/i.test(combined)) {
    return {
      kind: "network", connected: false, label: "네트워크 연결 실패", balanceLabel: "거래소 응답 없음",
      reason: message || `${provider} 네트워크 연결 또는 거래소 서비스 상태를 확인하세요.`,
    };
  }
  if (["empty_response", "invalid_balance_response", "error"].includes(status)) {
    return {
      kind: "response", connected: false, label: "계정 조회 실패", balanceLabel: "계정 응답 확인 실패",
      reason: message || `${provider} 계정 응답을 확인하지 못했습니다. 이 상태만으로 API 키 오류라고 단정할 수 없습니다.`,
    };
  }
  return {
    kind: "unknown", connected: false, label: "연결 확인 실패", balanceLabel: "상태 확인 필요",
    reason: message || `${provider} 실제 계정 응답을 확인하지 못했습니다. (상태: ${status || "unknown"})`,
  };
}

export function accountConnectionFailure(result: Record<string, any>, source: string): string {
  const detail = result?.sources?.[source] ?? result?.sources?.[source.toLowerCase()] ?? result?.[source];
  return accountConnectionView(detail, source).reason;
}
