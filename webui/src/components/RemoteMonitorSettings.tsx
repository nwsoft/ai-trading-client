import { t, localized, getLocale, intlLocale } from '../i18n';
import { useEffect, useRef, useState } from 'react';
import type { GatewayClient } from '../api';

export function RemoteMonitorSettings({client}: {client: GatewayClient}) {
  const [state,setState]=useState<Record<string,any>|null>(null);
  const [name,setName]=useState('내 NoahAI PC');
  const [allowPause,setAllowPause]=useState(false);
  const [allowControl,setAllowControl]=useState(false);
  const [shareDetails,setShareDetails]=useState(false);
  const initialized=useRef(false);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState('');
  useEffect(()=>{let active=true;const refresh=()=>client.remoteStatus().then(s=>{
    if(active){setState(s);if(!initialized.current){setName(s.name);setAllowPause(s.allow_pause===true);setAllowControl(s.allow_control===true);setShareDetails(s.share_details===true);initialized.current=true}}
  }).catch(()=>{if(active)setError('연결 설정을 불러오지 못했습니다.')});void refresh();const timer=setInterval(refresh,15000);return()=>{active=false;clearInterval(timer)}},[client]);
  async function save(enabled:boolean){
    if(enabled && allowControl && !window.confirm(t('현재 PC에 저장된 기관·PAPER/LIVE 모드·전략·운용 한도로 모바일 시작·재개를 허용할까요? LIVE는 실제 주문이 발생할 수 있습니다. 설정이나 전략이 바뀌면 다시 승인해야 합니다.')))return;
    setBusy(true);setError('');
    try{setState(await client.configureRemote(enabled,name,allowPause,allowControl,shareDetails))}
    catch{setError('저장하지 못했습니다. 로그인 상태와 PAPER/LIVE 기관 설정을 확인하세요.')}
    finally{setBusy(false)}
  }
  return <article className="remote-monitor-settings">
    <h3>{t("원격 관리 · 내 PC 상태 공유")}</h3>
    <p>{t("daltrading에서 기관별 운용 상태를 확인합니다. API 키·전략 원문은 전송하지 않습니다. 아래 권한은 각각 선택하며 기본 OFF입니다.")}</p>
    <label>{t("PC 이름 ")}<input maxLength={60} value={name} onChange={e=>setName(e.target.value)} /></label>
    <label><input type="checkbox" checked={allowPause} onChange={e=>setAllowPause(e.target.checked)} />{t(" 모바일에서 새 거래 일시정지 허용")}</label>
    <label><input type="checkbox" checked={allowControl} onChange={e=>setAllowControl(e.target.checked)} />{t(" 모바일에서 자율운행 시작·재개 허용 (PAPER/LIVE)")}</label>
    <label><input type="checkbox" checked={shareDetails} onChange={e=>setShareDetails(e.target.checked)} />{t(" 포지션 수·위험 상태·손익 요약 공유에 동의")}</label>
    <p>{t("일시정지는 새 진입만 막습니다. 보유 포지션 보호·청산은 유지되고 이미 제출한 주문은 체결될 수 있습니다. 시작·재개는 웹에서 비밀번호 재확인 후 PC가 위험·권한을 다시 검사합니다. PAPER/LIVE 전환·전량 청산은 제공하지 않습니다.")}</p>
    <div className="notification-actions">
      <button type="button" disabled={busy||!state} onClick={()=>void save(!state?.enabled)}>{state?.enabled?t("상태 공유 끄기"):t("상태 공유에 동의하고 연결")}</button>
      {state?.enabled && <button type="button" disabled={busy} onClick={()=>void save(true)}>{t("원격 권한 저장")}</button>}
      <a href={`https://daltrading.net/remote?lang=${getLocale()}`} target="_blank" rel="noopener noreferrer">{t("모바일 대시보드 열기")}</a>
    </div>
    <p role="status">{t(error||state?.error||(state?.enabled?'상태 공유 켜짐':'상태 공유 꺼짐'))}{state?.last_sent?` · ${localized('마지막 전송','Last sent')} ${new Date(state.last_sent*1000).toLocaleString(intlLocale())}`:''}</p>
    {state?.allow_control && <p>{t("승인 기관·모드: ")}{Object.entries(state.approved||{}).map(([source, value])=>`${source.toUpperCase()} ${(value as {mode:string}).mode.toUpperCase()}`).join(' · ')||t("없음")}{t(" · 설정 변경 후에는 원격 권한을 다시 저장하세요.")}</p>}
    {Object.keys(state?.entry_pauses||{}).map(source=><p key={source}>{source.toUpperCase()}{t(" 새 거래 ")}{state?.entry_pauses[source]?.status==='draining'?t("정지 요청 · 처리 중 주문 확인 중"):t("일시정지")} <button type="button" disabled={busy} onClick={async()=>{
      if(!window.confirm(`${source.toUpperCase()} ${localized('새 거래를 다시 허용할까요? 현재 PC의 전략·모드·한도로 동작하며 위험 차단은 유지됩니다.','Allow new entries again? Uses the current PC strategy, mode and limits; risk blocks remain active.')}`))return;
      setBusy(true);try{await client.resumeEntries(source);setState(await client.remoteStatus())}catch{setError('재개하지 못했습니다.')}finally{setBusy(false)}
    }}>{t("PC에서 새 거래 재개")}</button></p>)}
    <small>{t("PC와 NoahAI가 실행 중이어야 합니다. 수신 지연이 있으므로 긴급 청산 도구가 아닙니다. 공유를 끄거나 원격 연결을 해제해도 거래 상태와 일시정지는 바뀌지 않습니다. 손익 요약은 NoahAI 위험 평가 범위이며 거래소 전체 계좌 일별 손익이 아닙니다.")}</small>
  </article>;
}
