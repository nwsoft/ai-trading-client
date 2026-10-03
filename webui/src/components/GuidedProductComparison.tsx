import { ProductIntelligenceWorkspace } from './ProductIntelligenceWorkspace';
import { useState, type KeyboardEvent } from 'react';
import type { GatewayClient } from '../api';
import { InsuranceWorkspace } from './InsuranceWorkspace';
import { AssistantWorkspace } from './AssistantWorkspace';
import { loanEstimate, savingEstimate, type LoanMethod, type SavingMethod } from '../financeComparison';
import './GuidedProductComparison.css';

type Tab = 'overview' | 'loan' | 'insurance' | 'savings';
type Offer = { name: string; rate: string; extra: string; source: string; checked: string; conditions: string };
type Estimate = { basis: string; rows: Array<NonNullable<ReturnType<typeof loanEstimate>> | NonNullable<ReturnType<typeof savingEstimate>>>; names: string[] };
const tabs: Array<[Tab, string]> = [['overview', '전체 안내'], ['loan', '대출 비교'], ['insurance', '보험 비교'], ['savings', '예금·적금 비교']];
const fresh = (): Offer[] => [0, 1].map(() => ({ name: '', rate: '', extra: '', source: '', checked: '', conditions: '' }));
const won = (n: number | null) => n === null ? '미확인' : `${Math.round(n).toLocaleString('ko-KR')}원`;
const guide: Record<Exclude<Tab, 'overview'>, { title: string; intro: string; steps: string[]; questions: string[]; glossary: Array<[string, string]> }> = {
  loan: { title: '얼마를 빌리고, 매달 얼마를 갚게 될까요?', intro: '금리만 보지 말고 월 상환액·전체 이자·수수료를 함께 비교하세요. 직접 받은 두 조건을 같은 금액·기간으로 계산합니다.',
    steps: ['빌릴 금액·기간 정하기', '받은 두 금리·비용 입력', '월 부담과 총비용 확인'],
    questions: ['원리금균등과 원금균등은 어떻게 다른가요?', '중도상환수수료와 변동금리는 어디에서 확인하나요?', '최저 광고 금리와 내가 받는 금리가 왜 다른가요?'],
    glossary: [['원리금균등', '원금과 이자를 합한 월 상환액이 일정하도록 계산합니다. 실제 납입액은 금융사의 일수·반올림 방식에 따라 달라집니다.'], ['원금균등', '매달 같은 원금을 갚습니다. 남은 원금이 줄어들며 이자와 월 상환액도 줄어듭니다.'], ['만기일시', '기간 중에는 이자만 내고 마지막 달에 원금을 한꺼번에 갚는 가정입니다. 만기 목돈 부담을 확인하세요.'], ['금리·추가 비용', '연 금리를 % 단위로 입력합니다. 부대비용이 미확인이면 총비용도 미확인입니다. 중도상환·연체 비용과 금리 변경은 별도 확인합니다.']] },
  savings: { title: '목돈을 맡길까요, 매달 모을까요?', intro: '예금은 지금 가진 목돈, 적금은 앞으로 매달 넣을 돈입니다. 같은 연 금리라도 돈이 맡겨진 기간이 달라 이자가 다릅니다.',
    steps: ['목돈 예금 / 매월 적금 선택', '납입액·기간·금리 입력', '원금·이자·세금 나눠 보기'],
    questions: ['예금과 적금은 같은 금리인데 왜 이자가 다른가요?', '최고 금리의 우대 조건을 어떻게 확인하나요?', '만기 전에 해지할 때 무엇이 달라지나요?'],
    glossary: [['예금과 적금', '예금은 원금 전체가 기간 내내, 적금은 매달 새로 넣은 돈이 남은 기간만큼 이자를 만드는 가정입니다.'], ['세전·세후', '세전은 세금을 빼기 전, 세후는 입력한 세율 가정으로 뺀 금액입니다. 실제 과세 유형은 상품·개인 조건을 확인해야 합니다.'], ['우대금리', '급여이체·카드 사용 등 조건 충족 여부를 확인하세요. 최고 금리가 모두에게 적용되는 것은 아닙니다.'], ['계산 범위', '기본 계산은 단리·정시 납입 가정입니다. 맞춤 비교의 상세 조건에서 복리·중도해지·목표·만기 분산을 선택할 수 있습니다. 약관에 따른 납입 누락·우대 적용 상한은 별도 확인합니다.']] },
  insurance: { title: '보험료보다 먼저, 무엇을 보장하는지 확인해요', intro: '보험이 없어도 필요한 보장과 예산부터 정할 수 있습니다. 기존 보험이 있다면 증권·보장내역과 새 견적을 대조하세요. 부족한 정보는 확인할 질문으로 남기며 해지나 가입을 자동 권하지 않습니다.',
    steps: ['가입 상태·필요한 보장 정하기', '예산·받은 견적·약관 확인', '설계 비교·상담 질문 준비'],
    questions: ['보험증권에서 어떤 항목부터 확인하나요?', '실손과 정액 보장은 어떻게 다른가요?', '보험을 바꾸기 전에 무엇을 확인해야 하나요?'],
    glossary: [['보험료와 가입금액', '보험료는 내가 내는 돈, 가입금액은 약정의 기준 금액입니다. 가입금액이 언제나 그대로 지급되는 것은 아닙니다.'], ['면책·감액', '보장이 제외되는 조건이나 기간, 지급액이 줄어드는 조건을 뜻합니다. 가입 시점의 약관을 확인하세요.'], ['갱신과 납입 종료', '갱신 시 보험료·조건이 달라질 수 있습니다. 돈을 내는 기간과 보장받는 기간은 다를 수 있습니다.'], ['두 보험 비교', '가격이 낮아도 보장·제외·피보험자·가입 시기가 다를 수 있습니다. 같은 이름의 보장이 있어도 불필요한 중복이라고 단정하지 않습니다.']] },
};

function CashFlow({ values, scale }: { values: number[]; scale: number }) {
  const max = Math.max(scale, 1);
  const points = values.map((v, i) => `${8 + (values.length === 1 ? 0 : i / (values.length - 1) * 284)},${72 - v / max * 62}`).join(' ');
  return <figure className="product-flow"><figcaption>월 상환 흐름 · {values.length}개월 · 최대 {won(Math.max(...values))}</figcaption><svg viewBox="0 0 300 80" role="img" aria-label={`첫 달 ${won(values[0])}, 마지막 달 ${won(values[values.length - 1])}. 월별 상환액 추이`}><path d="M8 72H292" stroke="currentColor" opacity=".3" /><polyline points={points} fill="none" stroke="currentColor" strokeWidth="3" /><circle cx="8" cy={72 - values[0] / max * 62} r="3" fill="currentColor" /></svg><div><span>첫 달 {won(values[0])}</span><span>마지막 {won(values[values.length - 1])}</span></div></figure>;
}

export function GuidedProductComparison({ client }: { client: GatewayClient }) {
  const [tab, setTab] = useState<Tab>('overview');
  const [visitedInsurance, setVisitedInsurance] = useState(false);
  const [loan, setLoan] = useState({ amount: '', months: '', method: 'annuity' as LoanMethod, offers: fresh(), example: false });
  const [saving, setSaving] = useState({ amount: '', months: '', method: 'deposit' as SavingMethod, offers: fresh(), example: false });
  const [results, setResults] = useState<Partial<Record<'loan' | 'savings', Estimate>>>({});
  const [error, setError] = useState('');
  const [question, setQuestion] = useState('');
  const [assistantQuestion, setAssistantQuestion] = useState('');
  function navigate(next: Tab) { setTab(next); setError(''); setQuestion(''); setAssistantQuestion(''); if (next === 'insurance') setVisitedInsurance(true); }
  function keys(e: KeyboardEvent<HTMLButtonElement>, index: number) {
    let target = index;
    if (e.key === 'ArrowRight') target = (index + 1) % tabs.length;
    else if (e.key === 'ArrowLeft') target = (index + tabs.length - 1) % tabs.length;
    else if (e.key === 'Home') target = 0;
    else if (e.key === 'End') target = tabs.length - 1;
    else return;
    e.preventDefault(); navigate(tabs[target][0]); document.getElementById(`product-tab-${tabs[target][0]}`)?.focus();
  }
  const mode = tab === 'savings' ? 'savings' : 'loan';
  const draft = mode === 'loan' ? loan : saving;
  const result = results[mode];
  function clearResult(kind: 'loan' | 'savings') { setResults(old => ({ ...old, [kind]: undefined })); setError(''); }
  function update(key: 'amount' | 'months', value: string) {
    if (mode === 'loan') setLoan({ ...loan, [key]: value }); else setSaving({ ...saving, [key]: value }); clearResult(mode);
  }
  function offer(index: number, key: keyof Offer, value: string) {
    const offers = draft.offers.map((row, i) => i === index ? { ...row, [key]: value } : row);
    if (mode === 'loan') setLoan({ ...loan, offers }); else setSaving({ ...saving, offers }); clearResult(mode);
  }
  function reset(example: boolean) {
    if ((draft.amount || draft.offers.some(o => o.rate)) && !window.confirm('현재 이 탭의 입력과 결과를 바꿉니다. 계속할까요?')) return;
    const offers = fresh();
    if (example) offers.forEach((o, i) => { o.name = `가상 조건 ${i === 0 ? 'A' : 'B'}`; o.rate = mode === 'loan' ? (i ? '5' : '4') : (i ? '3.5' : '3'); o.extra = mode === 'loan' ? (i ? '0' : '100000') : '15.4'; o.source = '학습용 가상 수치 · 실제 판매 상품 아님'; });
    if (mode === 'loan') setLoan({ amount: example ? '10000000' : '', months: example ? '24' : '', method: 'annuity', offers, example });
    else setSaving({ amount: example ? '10000000' : '', months: example ? '12' : '', method: 'deposit', offers, example });
    clearResult(mode);
  }
  function calculate() {
    const rows = draft.offers.map(o => mode === 'loan' ? loanEstimate(loan.amount, loan.months, o.rate, o.extra, loan.method) : savingEstimate(saving.amount, saving.months, o.rate, o.extra, saving.method));
    if (rows.some(r => !r)) { clearResult(mode); setError('금액·기간·두 연 금리를 확인하세요. 기간은 1~600개월, 금액·적립 총원금은 1조 원 이하 정수, 비율은 0~100입니다. 비용·세율도 잘못된 값은 계산하지 않습니다.'); return; }
    setError(''); setResults(old => ({ ...old, [mode]: { basis: draft.example ? '학습용 가상 예시' : '직접 입력 · 금융사 미검증', rows: rows as Estimate['rows'], names: draft.offers.map((o, i) => o.name.trim() || `조건 ${i ? 'B' : 'A'}`) } }));
  }
  return <section className="product-studio data-workspace">
    <header className="panel product-hero"><div><span className="eyebrow">FINANCE GUIDE · 이해하고 비교하기</span><h2>내게 필요한 금융, 한 단계씩</h2><p>빌릴 돈 · 지킬 보장 · 모을 돈. 먼저 목적을 고르고, 같은 기준으로 차이를 확인하세요.</p></div><span className="product-local-badge">기본 계산은 내 PC에서 · 자동 신청 없음</span></header>
    <nav className="product-tabs" role="tablist" aria-label="금융상품 비교 종류">{tabs.map(([key, title], i) => <button key={key} id={`product-tab-${key}`} role="tab" type="button" aria-selected={tab === key} aria-controls={`product-panel-${key}`} tabIndex={tab === key ? 0 : -1} onKeyDown={e => keys(e, i)} onClick={() => navigate(key)}>{title}</button>)}</nav>
    {tab === 'overview' && <section role="tabpanel" id="product-panel-overview" aria-labelledby="product-tab-overview" className="panel">
      <h3>무엇부터 알아보고 싶으세요?</h3><div className="product-purpose-grid">{(['loan', 'insurance', 'savings'] as const).map((key, i) => <article key={key}><span className="product-number">0{i + 1}</span><h3>{tabs.find(t => t[0] === key)?.[1]}</h3><p>{guide[key].intro}</p><ul>{guide[key].steps.map(s => <li key={s}>{s}</li>)}</ul><button className="primary-button" type="button" onClick={() => navigate(key)}>{key === 'loan' ? '매달 갚을 돈 알아보기' : key === 'savings' ? '만기에 모일 돈 알아보기' : '내 보장부터 이해하기'}</button></article>)}</div>
      <h3>전체 비교 준비 상태</h3><div className="product-readiness">{(['loan', 'savings'] as const).map(key => <button type="button" key={key} onClick={() => navigate(key)}><strong>{key === 'loan' ? '대출 부담' : '예적금 계획'}</strong><span>{results[key] ? `${results[key]!.basis} · 두 조건 계산됨` : '아직 입력하지 않았습니다'}</span></button>)}<button type="button" onClick={() => navigate('insurance')}><strong>보험 보장</strong><span>암호화 보험 탭에서 확인 · 여기서 자료를 불러오지 않음</span></button></div><p className="workspace-copy">대출·보험·예적금은 목적이 달라 하나의 ‘최고 상품’ 순위로 합치지 않습니다. 아직 금융회사 전체 상품이나 실시간 견적을 연결한 서비스는 아닙니다.</p>
      <details><summary>처음이라면: 준비할 자료와 개인정보 안내</summary><p>대출·예적금은 금융사 안내의 금리·기간·비용·조건을 준비하세요. 보험은 본인에게 제공 권한이 있는 증권·약관을 준비하세요. 주민번호·계좌번호·건강정보는 질문에 넣지 마세요.</p><p>계산 입력은 이 화면의 메모리에만 있습니다. 상위 화면 이동·앱 종료 시 사라집니다. 내부 탭 전환과 아래 AI 도움은 입력을 유지하며, 보험 저장은 별도 암호화 저장소를 사용합니다.</p></details>
    </section>}
    {tab !== 'overview' && <article className="panel product-guide"><h3>{guide[tab].title}</h3><p>{guide[tab].intro}</p><ol className="product-steps">{guide[tab].steps.map((s, i) => <li key={s}><b>{i + 1}</b>{s}</li>)}</ol><details><summary>용어가 어렵다면 · 쉬운 설명 펼치기</summary><dl>{guide[tab].glossary.map(([word, meaning]) => <div key={word}><dt>{word}</dt><dd>{meaning}</dd></div>)}</dl></details></article>}
    {(['loan', 'insurance', 'savings'] as const).map(kind => <div key={kind} hidden={tab !== kind}><ProductIntelligenceWorkspace client={client} kind={kind} /></div>)}
    {(tab === 'loan' || tab === 'savings') && <section role="tabpanel" id={`product-panel-${tab}`} aria-labelledby={`product-tab-${tab}`} className="panel product-calculator">
      <div className="product-section-heading"><h3>1. 같은 기준으로 조건 입력</h3><div className="command-row"><button type="button" onClick={() => reset(true)}>가상 예시로 연습</button><button type="button" onClick={() => reset(false)}>비우고 내 조건 입력</button></div></div>
      <p className={draft.example ? 'product-example' : 'workspace-copy'}>{draft.example ? '가상 예시입니다. 편집해도 실제 상품으로 바뀌지 않습니다. 내 조건은 비우고 새로 입력하세요.' : '직접 받은 조건을 입력하세요. 입력값은 금융사가 확인한 견적·가입 가능 판정이 아닙니다.'}</p>
      <div className="product-input-grid"><label>{mode === 'loan' ? '빌릴 금액 (원)' : saving.method === 'deposit' ? '한 번에 맡길 목돈 (원)' : '매달 넣을 금액 (원)'}<input inputMode="numeric" type="number" min="1" max="1000000000000" step="1" value={draft.amount} onChange={e => update('amount', e.target.value)} placeholder="예: 10000000" /></label><label>기간 (개월)<input type="number" min="1" max="600" step="1" value={draft.months} onChange={e => update('months', e.target.value)} placeholder="예: 12" /></label>
      {mode === 'loan' ? <label>갚는 방식<select aria-label="갚는 방식" value={loan.method} onChange={e => { setLoan({ ...loan, method: e.target.value as LoanMethod }); clearResult(mode); }}><option value="annuity">원리금균등 · 월 상환액 일정</option><option value="principal">원금균등 · 월 상환액 감소</option><option value="bullet">만기일시 · 마지막에 원금 상환</option></select></label> : <label>모으는 방식<select aria-label="모으는 방식" value={saving.method} onChange={e => { setSaving({ ...saving, method: e.target.value as SavingMethod, amount: '' }); clearResult(mode); }}><option value="deposit">정기예금 · 목돈 한 번</option><option value="installment">정기적금 · 매월 같은 금액</option></select></label>}</div>
      <div className="product-offers">{draft.offers.map((o, i) => <fieldset key={i}><legend>조건 {i ? 'B' : 'A'}</legend><label>이름 · 선택<input aria-label={`조건 ${i ? 'B' : 'A'} 이름`} maxLength={80} value={o.name} onChange={e => offer(i, 'name', e.target.value)} placeholder="예: 내가 받은 견적" /></label><label>적용할 연 금리 (%)<input aria-label={`조건 ${i ? 'B' : 'A'} 연 금리`} type="number" min="0" max="100" step="0.01" value={o.rate} onChange={e => offer(i, 'rate', e.target.value)} placeholder="예: 4.5" /></label><label>{mode === 'loan' ? '추가 비용 합계 (원) · 선택' : '이자에 적용할 세율 (%) · 선택'}<input aria-label={`조건 ${i ? 'B' : 'A'} ${mode === 'loan' ? '추가 비용' : '세율'}`} type="number" min="0" max={mode === 'loan' ? '1000000000000' : '100'} step={mode === 'loan' ? '1' : '0.1'} value={o.extra} onChange={e => offer(i, 'extra', e.target.value)} placeholder="모르면 비워 두세요" /></label><small>{mode === 'loan' ? '비용을 모르면 전체 비용도 미확인입니다. 없음이 확인된 경우에만 0을 입력하세요.' : '세율은 직접 확인해 입력하세요. 비과세가 확인된 경우에만 0. 예시의 15.4%는 학습 가정입니다.'}</small><details><summary>받은 조건의 출처·확인일·우대 조건 기록</summary><label>출처 메모<input maxLength={300} value={o.source} onChange={e => offer(i, 'source', e.target.value)} /></label><label>내가 확인한 날짜<input type="date" value={o.checked} onChange={e => offer(i, 'checked', e.target.value)} /></label><label>변동금리·우대 조건·기타 확인 사항<textarea maxLength={600} value={o.conditions} onChange={e => offer(i, 'conditions', e.target.value)} /></label><small>사용자 메모이며 공식 검증이나 자동 조건 반영이 아닙니다.</small></details></fieldset>)}</div>
      {error && <p role="alert" className="error-text">{error}</p>}<button className="primary-button" type="button" onClick={calculate}>두 조건 계산하기 · 저장/신청 안 함</button>
      <p className="workspace-copy">{mode === 'loan' ? '금리가 기간 내내 같고 매달 정상 상환하는 가정입니다. 일수·원 단위 반올림·변동금리·중도상환·연체·거치기간은 반영하지 않습니다. 표시 비용은 APR(연간 총비용률)이 아닙니다.' : '단리·월 단위 가정입니다. 적금은 매월 초 납입해 마지막 납입도 1개월 이자를 받습니다. 실제 일수·복리·납입 지연·우대 조건·중도해지 차이는 금융사에서 확인하세요.'}</p>
      {result && <section className="product-results" aria-live="polite"><h3>2. 숫자를 읽고 차이 이해하기</h3><p>{result.basis} · 같은 금액·기간·방식 · 입력을 바꾸면 이전 결과는 지워집니다.</p><div className="product-result-grid">{result.rows.map((r, i) => <article key={i}><h4>{result.names[i]}</h4><span className="product-rate">연 {r.rate}%</span>{'payments' in r ? <><strong className="product-main-number">{won(r.first)}<small>첫 달 원금 + 이자</small></strong><CashFlow values={r.payments} scale={Math.max(...result.rows.flatMap(row => 'payments' in row ? row.payments : [0]))} /><dl><div><dt>빌린 원금</dt><dd>{won(r.principal)}</dd></div><div><dt>전체 기간 이자</dt><dd>{won(r.interest)}</dd></div><div><dt>입력한 추가 비용</dt><dd>{won(r.fees)}</dd></div><div><dt>원금 + 이자 + 비용</dt><dd>{won(r.total)}</dd></div></dl>{loan.method === 'bullet' && <p className="product-example">마지막 달에는 원금도 갚습니다: {won(r.last)}</p>}</> : <><strong className="product-main-number">{won(r.maturity)}<small>입력 세율 가정의 만기 수령액</small></strong><dl><div><dt>총 납입 원금</dt><dd>{won(r.principal)}</dd></div><div><dt>세전 이자</dt><dd>{won(r.interest)}</dd></div><div><dt>입력 세율의 세금</dt><dd>{won(r.tax)}</dd></div><div><dt>세후 이자</dt><dd>{won(r.netInterest)}</dd></div></dl>{r.tax === null && <p>세율 미확인: 세전 이자까지만 계산했습니다.</p>}</>}</article>)}</div>
      <p className="workspace-copy">{mode === 'loan' ? '월 상환 그래프는 두 조건에 같은 세로축을 적용합니다. 추가 비용은 그래프 밖의 별도 합계입니다.' : '원금과 이자를 구분하세요. 이자 막대는 원금 수익률이나 상품 추천 점수가 아닙니다.'}</p><div className="product-bars"><h4>{mode === 'loan' ? '이자만 비교 · 추가 비용 별도' : '세전 이자 비교 · 세금 별도'}</h4>{result.rows.map((r, i) => <div key={i}><span>{result.names[i]}</span><progress aria-label={`${result.names[i]} 이자 비교`} value={r.interest} max={Math.max(...result.rows.map(r => r.interest), 1)} /><strong>{won(r.interest)}</strong></div>)}</div><p className="product-takeaway">{mode === 'loan' ? '전체 기간 이자 차이' : '세전 이자 차이'}: {won(Math.abs(result.rows[0].interest - result.rows[1].interest))}. {mode === 'loan' ? '이자가 낮아도 추가 비용·상환 방식·실제 승인 조건을 확인해야 합니다.' : '이자가 높아도 우대요건·가입 한도·중도해지 조건을 확인해야 합니다.'} 가입 추천이나 확정 절감액이 아닙니다.</p>
      <details><summary>3. 금융사에 물어볼 확인 목록</summary><ul>{(mode === 'loan' ? ['이 금리가 나에게 실제 적용되는지, 언제까지 유효한지', '변동 주기·금리 인상 시 월 부담·중도상환 비용', '인지세·보증료 등 추가 비용과 대출 심사 조건'] : ['우대 조건과 적용 금액 한도를 내가 충족하는지', '실제 세율·비과세 자격과 예금보호 적용 여부', '중도해지·납입 누락 시 금리와 만기 예상 수령액']).map(q => <li key={q}>{q}</li>)}</ul></details></section>}
    </section>}
    <section hidden={tab !== 'insurance'} role="tabpanel" id="product-panel-insurance" aria-labelledby="product-tab-insurance">
      {tab === 'insurance' && <details className="panel product-insurance-example"><summary>보험 비교 예시 보기 · 내 계약에는 저장하지 않음</summary><div className="product-result-grid"><article><h4>가상 계약 A</h4><p>월 50,000원 · 특정 질환 정액 보장</p><p>지급 조건·면책 기간은 원문 확인 필요</p></article><article><h4>가상 계약 B</h4><p>월 35,000원 · 다른 보장 범위</p><p>피보험자·갱신·보장 제외는 원문 확인 필요</p></article></div><p>15,000원 차이만으로 B가 낫거나 그만큼 절약된다고 결론 내릴 수 없습니다. 같은 보장인지부터 확인합니다.</p></details>}
      {visitedInsurance && <InsuranceWorkspace client={client} />}
    </section>
    {tab !== 'overview' && <section className="panel product-help"><h3>모르면 여기에서 질문하세요</h3><p>자주 묻는 질문을 골라 초안을 만들거나 직접 적으세요. 내 입력 조건·보험 원문을 자동 첨부하지 않습니다.</p><div className="command-row">{guide[tab].questions.map(q => <button type="button" key={q} onClick={() => setQuestion(`${q} 초보자가 이해하도록 가상 예시로 설명하고 확인할 사항을 알려줘. 출처와 확인 시점을 구분하고, 내 조건에서 비교할 기준·빠진 정보·다음 확인 질문을 알려줘.`)}>{q}</button>)}</div><label>AI에게 물어볼 질문 초안<textarea maxLength={2000} value={question} onChange={e => setQuestion(e.target.value)} placeholder="예: 두 조건에서 어떤 차이를 먼저 봐야 하나요?" /></label><button type="button" disabled={!question.trim()} onClick={() => setAssistantQuestion(question)}>AI 도움 열기 · 아직 전송하지 않음</button><p className="workspace-copy">아래 기존 어시스턴트에서 직접 전송합니다. 외부 AI 사용 여부·비용·범위 안내를 확인하세요. 개인정보·건강정보는 넣지 마세요.</p>{assistantQuestion && <div className="product-assistant"><button type="button" onClick={() => setAssistantQuestion('')}>도움 닫기 · 비교 입력 유지</button><AssistantWorkspace client={client} service="personal_finance" initialQuestion={assistantQuestion} /></div>}</section>}
  </section>;
}
