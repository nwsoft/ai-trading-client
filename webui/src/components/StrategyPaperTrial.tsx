import type {StrategyVersion} from '../types';

export function trialDuration(seconds: number | null | undefined): string {
  if (seconds == null || !Number.isFinite(seconds) || seconds < 0) return '미기록';
  if (seconds < 60) return `${seconds.toFixed(3)}초`;
  const total = Math.floor(seconds);
  const days = Math.floor(total / 86400), hours = Math.floor(total % 86400 / 3600);
  const minutes = Math.floor(total % 3600 / 60), rest = total % 60;
  return `${days ? `${days}일 ` : ''}${hours ? `${hours}시간 ` : ''}${minutes}분 ${rest}초`;
}

function localTime(value?: string | null) {
  if (!value || !Number.isFinite(Date.parse(value))) return '미기록';
  return `${new Date(value).toLocaleString('ko-KR')} (${Intl.DateTimeFormat().resolvedOptions().timeZone})`;
}

export function StrategyPaperTrial({version, days, disabled, onChange}: {
  version: StrategyVersion; days: number; disabled: boolean; onChange: (days: number) => void;
}) {
  const progress = version.paper_progress;
  const runtime = progress?.runtime;
  const promotion = progress?.promotion;
  const trades = progress?.trades ?? Number(version.paper_validation?.trades ?? 0);
  const minimum = progress?.required_trades ?? 3;
  const passed = promotion?.ready ?? Boolean(version.paper_validation?.passed);
  const observing = version.paper_observing || version.status === 'paper_observing';
  return <section className="strategy-paper-trial" aria-label={`${version.name} PAPER 시험 안내`}>
    <label>PAPER 시험 기간 · 관찰 목표
      <select aria-label={`${version.name} v${version.version} PAPER 시험 기간`} value={days}
        disabled={disabled || version.active || observing} onChange={event => onChange(Number(event.target.value))}>
        {[1, 3, 7].map(day => <option key={day} value={day}>{day}일</option>)}
      </select>
    </label>
    <p>시작·재개할 때 선택한 기간을 저장합니다. 목표에 도달하면 알려드리고 검증은 계속합니다. 일시정지는 직접 선택하세요. 기간을 바꾸려면 먼저 일시정지하세요.</p>
    <div className="strategy-paper-clocks">
      <div><strong>등록 후 경과</strong><span>{version.paper_observation_started_at ? trialDuration(progress?.permission_elapsed_seconds) : '시작 전'}</span><small>일시정지 제외 · 앱 종료 시간 포함</small></div>
      <div><strong>실제 진입 후보 규칙 평가시간</strong><span>{runtime?.status === 'partial' ? `일부 기록 누락 · ${trialDuration(runtime.seconds)}` : runtime?.status === 'observed' ? trialDuration(runtime.seconds) : runtime?.status === 'unavailable' ? '집계 조회 실패' : '아직 기록 없음'}</span><small>대기·앱 종료 시간을 추정해 더하지 않습니다.</small></div>
      <div><strong>최근 평가 확인</strong><span>{localTime(runtime?.last_evaluated_at)}</span><small>{runtime?.evaluations != null ? `완료 평가 ${runtime.evaluations}회` : '이전 실행시간은 소급 추정하지 않습니다.'}</small></div>
    </div>
    {progress?.target_reached && <p role="status" className="strategy-paper-goal">선택한 {progress.target_days ?? days}일 관찰 목표에 도달했습니다. 결과를 검토하세요. {observing ? '검증은 계속되며 자동 적용되지 않습니다.' : '현재 운용 상태는 위 상태 표시에서 확인하세요.'}</p>}
    <div className="strategy-paper-promotion"><strong>최종 적용 조건 · 기간과 별도</strong>
      <span>유효 PAPER 청산 {trades} / 최소 {minimum}건</span>
      <span>{promotion ? `기록된 위험 위반 ${promotion.guardrail_violations}건 · 위험 근거 미기록 ${promotion.unknown_risk_records == null ? '미기록' : `${promotion.unknown_risk_records}건`} · 비용·손익 미대조 ${promotion.unverified_trades}건` : '위험·원장 대조 결과를 확인하세요.'}</span>
      <b>{version.active ? '사용자 확인 후 적용됨' : passed ? '조건 충족 · 원장 재확인과 사용자 최종 확인 필요' : '적용 대기 · 거래 표본과 위험·비용 근거를 확인하세요.'}</b>
    </div>
    <details><summary>시간과 판정 기준 알아보기</summary>
      <p>1·3·7일은 결과를 다시 볼 관찰 목표입니다. 등록 후 경과는 실행 허용 구간의 달력 시간이며 실제 앱 가동시간이 아닙니다. 실제 진입 후보 규칙 평가시간은 엔진의 정상 완료된 진입 후보 규칙 평가 호출 구간만 중복 없이 합산한 소요시간입니다. 기관 전체 가동시간·포지션 보유시간과 다릅니다. 과거 기록이 없으면 미기록으로 남깁니다.</p>
      <p>기간 도달·수익 발생만으로 통과하지 않습니다. 유효 청산 표본·비용 및 손익 대조·기록된 위험 위반·실행 규칙을 확인하고, 최종 적용 때 원장을 다시 확인합니다. 최소 3건은 제품 기본 조건이며 통계적 충분성이나 향후 수익을 보장하지 않습니다. LIVE 권한과 실제 주문 전 위험 검사는 계속 적용됩니다.</p>
    </details>
  </section>;
}
