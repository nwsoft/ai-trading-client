export const REGIME_LABELS: Record<string,string> = {bull:'상승',bear:'하락',range:'횡보',volatile:'고변동',normal:'일반'};
export function regimeText(value: unknown) { return REGIME_LABELS[String(value)] || String(value || '미확인'); }
export function evidenceTime(value: unknown) {
  const n=Number(value); return Number.isFinite(n)&&n>0 ? new Date(n<1e11?n*1000:n).toLocaleString() : '기록 없음';
}
export function evidenceOld(value: unknown) {
  const n=Number(value); return !Number.isFinite(n)||n<=0||Date.now()/1000-n>900||n>Date.now()/1000+60;
}
export function CountRing({value,total,label}: {value:number;total:number;label:string}) {
  const valid=Number.isFinite(value)&&Number.isFinite(total)&&total>0&&value>=0&&value<=total;
  return <div className="operations-ring" role="img" aria-label={`${label}: ${valid?`${value}/${total}`:'대상 없음'}`}>
    <svg viewBox="0 0 120 120" aria-hidden="true"><circle cx="60" cy="60" r="49" className="ring-track"/><circle cx="60" cy="60" r="49" className="ring-value" pathLength="100" strokeDasharray={`${valid?value/total*100:0} 100`} transform="rotate(-90 60 60)"/></svg>
    <div><strong>{valid?`${value}/${total}`:'—'}</strong><span>{label}</span></div>
  </div>;
}
export function RegimeHistory({rows}: {rows?:Array<{observed:string;confirmed:string;symbol:string;timeframe:string;observed_at:number}>}) {
  const points=(rows||[]).filter(p=>Number.isFinite(p.observed_at)&&p.observed_at>0).slice(-24);
  if(!points.length) return <p className="operations-empty">이번 실행 세션의 국면 변화 이력이 없습니다. 과거 기록을 추정하지 않습니다.</p>;
  return <figure className="regime-history"><figcaption>이번 세션 국면 변화 · 최근 {points.length}개</figcaption>
    <div className="regime-history-track" role="img" aria-label={points.map(p=>`${evidenceTime(p.observed_at)} 관찰 ${regimeText(p.observed)}, 확정 ${regimeText(p.confirmed)}`).join('; ')}>
      {points.map((p,i)=><div key={`${p.observed_at}-${i}`} className={`regime-sample regime-${REGIME_LABELS[p.confirmed] ? p.confirmed : 'unknown'}`} title={`${evidenceTime(p.observed_at)} · ${p.symbol||'기관 국면'} ${p.timeframe}\n관찰 ${regimeText(p.observed)} / 확정 ${regimeText(p.confirmed)}`}><span>{regimeText(p.confirmed)}</span></div>)}
    </div><small>{evidenceTime(points[0].observed_at)} → {evidenceTime(points.at(-1)?.observed_at)} · 상태 전환 순서이며 시간 간격·상승 확률 그래프가 아닙니다.</small>
  </figure>;
}
