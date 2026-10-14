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

export function StrategyPaperTrial({version, days, disabled, onChange, market}: {
  version: StrategyVersion; days: number; disabled: boolean; onChange: (days: number) => void; market: 'stock' | 'crypto';
}) {
  const progress = version.paper_progress;
  const runtime = progress?.runtime;
  const promotion = progress?.promotion;
  const trades = progress?.trades ?? Number(version.paper_validation?.trades ?? 0);
  const minimum = progress?.required_trades ?? 3;
  const passed = promotion?.ready ?? Boolean(version.paper_validation?.passed);
  const observing = version.paper_observing || version.status === 'paper_observing';
  return <section className="strategy-paper-trial" aria-label={`${version.name} PAPER 시험 안내`}>
    <label>PAPER 결과 점검 시점 · 관찰 목표
      <select aria-label={`${version.name} v${version.version} PAPER 결과 점검 시점 (PAPER 시험 기간 · 관찰 목표)`} value={days}
        disabled={disabled || version.active || observing} onChange={event => onChange(Number(event.target.value))}>
        {[1, 3, 7].map(day => <option key={day} value={day}>{day}일 · {day === 1 ? '빠른 작동 점검' : day === 3 ? '반복 평가 확인' : '여러 날 관찰'}</option>)}
      </select>
    </label>
    <div className="strategy-paper-period-help">
      <strong>왜 기간을 정하나요?</strong>
      <p>거래 수·비용·위험 근거를 다시 확인할 시점을 정합니다. 거래를 막거나 자동 종료하는 날짜 제한이 아닙니다. 7일은 기본 선택값이며 모든 전략에 필요한 필수 기간은 아닙니다.</p>
      <p><strong>선택한 {days}일의 용도:</strong> {days === 1 ? '연결과 규칙이 작동하는지 빠르게 점검합니다. 성능 판단에는 표본이 부족할 수 있습니다.' : days === 3 ? '여러 차례의 평가 흐름을 확인합니다. 신호가 적거나 주식 휴장일이 겹치면 관찰을 이어가세요.' : '여러 날의 결과를 모아 검토합니다. 7일이 지나도 거래 표본이나 위험 근거가 부족하면 최종 적용은 대기합니다.'}</p>
      <p className="strategy-paper-market-guide"><strong>{market === 'stock' ? '주식·ETF에서 확인할 점' : '코인에서 확인할 점'}</strong><br />{market === 'stock' ? '현재 기간은 달력일 기준입니다. 주말·휴장일이 포함된 3일은 3거래일이 아닙니다. 장이 열리고 기관 연결·시세 수신이 정상이어야 평가 기회가 생깁니다. 휴장 중 목표에 도달해도 거래 표본이 없으면 적용할 수 없습니다.' : '코인은 통상 주말에도 24시간 거래되지만, 거래소 점검·연결 끊김·앱 종료 중에는 평가하지 못할 수 있습니다. 정상 연결에서도 진입 조건이 맞지 않으면 거래가 없을 수 있으므로 날짜와 실제 평가·청산 표본을 함께 확인하세요.'}</p>
    </div>
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
