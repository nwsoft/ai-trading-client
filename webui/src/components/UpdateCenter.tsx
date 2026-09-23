import { t } from '../i18n';
import { useEffect, useRef, useState } from "react";
import type { GatewayClient } from "../api";

type UpdateState = "idle" | "checking" | "current" | "available" | "downloading" | "ready" | "preparing" | "installing" | "error" | "development";
const pendingUpdateNotifications = new Set<string>();

export function UpdateCenter({ client, onOpenGuide, detailed = false, currentVersion = "v3.9.1.46", accountScope = "" }: { client?: GatewayClient; onOpenGuide?: () => void; detailed?: boolean; currentVersion?: string; accountScope?: string } = {}) {
  const [state, setState] = useState<UpdateState>(window.noahAI ? "checking" : "development");
  const [version, setVersion] = useState("");
  const [installedVersion, setInstalledVersion] = useState(currentVersion);
  const [percent, setPercent] = useState(0);
  const [message, setMessage] = useState("");
  const [schedule, setSchedule] = useState<Record<string, unknown>>({});
  const notifiedVersions = useRef(new Set<string>());

  useEffect(() => {
    const updater = window.noahAI?.updater;
    if (!updater) return;
    const notifyAvailable = (targetVersion: string, current: string) => {
      const target = String(targetVersion || "").trim();
      const storageKey = `noahai:update-notified:${encodeURIComponent(accountScope)}:${target}`;
      if (!client || !accountScope || !target || notifiedVersions.current.has(storageKey) || pendingUpdateNotifications.has(storageKey) || window.localStorage.getItem(storageKey) === "queued") return;
      notifiedVersions.current.add(storageKey);
      pendingUpdateNotifications.add(storageKey);
      client.notifyUpdateAvailable(target, current)
        .then((result) => {
          if (result.queued === true) window.localStorage.setItem(storageKey, "queued");
          else notifiedVersions.current.delete(storageKey);
        })
        .catch(() => {
          // 외부 메신저 장애가 업데이트 확인이나 거래 실행을 방해하지 않는다.
          notifiedVersions.current.delete(storageKey);
        }).finally(() => pendingUpdateNotifications.delete(storageKey));
    };
    let active = true;
    let receivedEvent = false;
    const receive = (status: Record<string, unknown>) => {
      if (!active) return;
      const next = String(status.state ?? "idle") as UpdateState;
      setState(next); setVersion(String(status.version ?? ""));
      if (status.currentVersion) setInstalledVersion(String(status.currentVersion));
      setPercent(Number(status.percent ?? 0)); setMessage(String(status.message ?? ""));
      setSchedule(status);
      if (next === "available" || next === "ready") notifyAvailable(String(status.version ?? ""), String(status.currentVersion ?? currentVersion));
    };
    const unsubscribe = updater.onStatus((status) => { receivedEvent = true; receive(status); });
    // Reading cached state must not trigger another network request on tab open.
    updater.getStatus().then((status) => { if (!receivedEvent) receive(status); })
      .catch(() => { if (active) setMessage("업데이트 상태를 읽지 못했습니다. 다시 확인하세요."); });
    return () => { active = false; unsubscribe(); };
  }, [client, currentVersion, accountScope]);

  const label = state === "checking" ? "업데이트 확인 중"
    : state === "current" || state === "development" ? "실거래 필수 · 업데이트·사용법"
      : state === "available" ? `${version || "새 버전"} 다운로드`
        : state === "downloading" ? `다운로드 ${percent.toFixed(0)}%`
          : state === "ready" ? `${version || "업데이트"} 설치·재시작`
            : state === "preparing" ? "안전 종료 확인 중"
              : state === "installing" ? "업데이트 설치 중"
            : state === "error" ? "업데이트 오류" : "업데이트";

  async function act() {
    const updater = window.noahAI?.updater;
    if (state === "development" || state === "current") {
      onOpenGuide?.();
      if (state === "development" || onOpenGuide) return;
    }
    if (!updater) return;
    if (state === "available") await updater.download();
    else if (state === "ready") {
      if (window.confirm("업데이트를 설치하기 위해 NoahAI를 안전하게 종료하고 재시작할까요? 사용자 데이터는 유지됩니다.")) await updater.install();
    } else if (state === "error" || state === "idle" || state === "current") {
      setState("checking"); await updater.check();
    }
  }

  const reportError = (error: unknown) => { setState("error"); setMessage(error instanceof Error ? error.message : "업데이트 요청 실패"); };
  const actionButton = <button className={`update-button state-${state}`} type="button" title={message || `업데이트 상태: ${state}`} disabled={["checking", "downloading", "preparing", "installing"].includes(state)} onClick={() => void act().catch(reportError)}>{label}</button>;
  if (!detailed) return actionButton;
  const statusText = state === "development" ? "개발 실행 · GitHub 배포 확인은 설치본에서 제공"
    : state === "current" ? "최신 버전"
      : state === "available" ? "업데이트 사용 가능"
        : state === "checking" ? "GitHub 릴리스 확인 중"
          : state === "error" ? "확인 실패"
            : label;
  return <div className="update-version-console">
    <div><span>{t("현재 버전")}</span><strong>{currentVersion || installedVersion}</strong></div>
    <div><span>{t("GitHub 확인 버전")}</span><strong>{version || (state === "checking" ? "확인 중…" : "확인되지 않음")}</strong></div>
    <div><span>{t("업데이트 상태")}</span><strong className={`state-${state}`}>{statusText}</strong></div>
    <div><span>{t("자동 다운로드")}</span><strong>{schedule.autoDownloadEnabled ? "ON" : "OFF"}</strong></div>
    <div><span>{t("종료 시 자동 설치")}</span><strong>{schedule.autoInstallOnAppQuitEnabled ? "ON" : "OFF"}</strong></div>
    <div><span>{t("마지막 확인 시도")}</span><strong>{schedule.lastCheckAt ? new Date(Number(schedule.lastCheckAt)).toLocaleString("ko-KR") : "아직 확인하지 않음"}</strong></div>
    <div><span>{t("다음 자동 확인")}</span><strong>{schedule.nextCheckAt ? new Date(Number(schedule.nextCheckAt)).toLocaleString("ko-KR") : schedule.autoCheckEnabled ? "진행 중인 확인 완료 후 예약" : "자동 확인 꺼짐 또는 개발 실행"}</strong></div>
    <div className="update-version-actions">
      {actionButton}
      <button className="update-check-button" type="button" disabled={["checking", "downloading", "ready", "preparing", "installing"].includes(state)} onClick={() => void window.noahAI?.updater.check().catch(reportError)}>{t("지금 버전 확인")}</button>
      <a href="https://github.com/nwsoft/ai-trading-client/releases/latest" target="_blank" rel="noreferrer">{t("최신 릴리스 열기")}</a>
    </div>
    <p>{t("앱이 실행 중일 때 저장한 주기마다 확인합니다. 자동 다운로드와 종료 시 자동 설치는 설정값을 따르며, 설치 전에는 거래 엔진의 안전 종료를 확인합니다.")}</p>
    {message && <p>{message}</p>}
  </div>;
}
