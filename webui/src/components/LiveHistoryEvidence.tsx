export interface LiveHistoryEvidenceData {
  status: string;
  error: string;
  total_count: number;
  confirmed_count: number;
  reference_count: number;
  first_exit_time: string;
  last_exit_time: string;
  detail_limit: number;
  groups: Array<{ category: string; currency: string; count: number; stored_pnl_count: number; missing_pnl_count: number; stored_pnl_sum: number | null }>;
  recent_records: Array<{ symbol: string; exchange: string; asset_class: string; currency: string; stored_pnl: number | null; category: string; reconciliation_status: string; exit_time: string }>;
}

const labels: Record<string, string> = {
  confirmed: "체결 대조 완료", unreconciled: "대조 전 · 체결/순손익 근거 부족",
  imported: "가져오기 기록 · 중복/귀속 대조 필요", external: "수동·외부 거래 · 자동매매 성과 제외",
};
function amount(value: number | null, currency: string) {
  return value == null ? "저장값 없음" : `${value.toLocaleString(undefined, { maximumFractionDigits: 4 })} ${currency === "UNKNOWN" ? "통화 미확인" : currency}`;
}

export function LiveHistoryEvidence({ data }: { data?: LiveHistoryEvidenceData }) {
  if (!data) return null;
  return <article className="panel live-history-evidence" aria-label="과거 LIVE 기록 확인">
    <h2>과거 LIVE 기록 확인</h2>
    {data.status !== "available" ? <p role="status">과거 원장을 확인하지 못했습니다. 거래가 없다는 뜻은 아닙니다. {data.error === "database_missing" ? "저장된 거래 DB가 없습니다." : "거래 DB와 스키마를 확인하세요."}</p> : <>
      <p><strong>저장된 종료 기록 {data.total_count.toLocaleString()}건</strong> · 체결 대조 완료 {data.confirmed_count.toLocaleString()}건 · 별도 참고 {data.reference_count.toLocaleString()}건</p>
      {data.total_count > 0 ? <p>기록 기간: {data.first_exit_time} ~ {data.last_exit_time} · 현재 선택 범위의 전체 기록 건수이며 위 성과 표본의 최근 건수 제한과 다릅니다.</p> : <p>현재 선택 범위의 저장된 LIVE 종료 기록이 없습니다. PAPER 기록은 성과 원장에서 별도로 선택하세요.</p>}
      {data.reference_count > 0 && <>
        <p className="inline-notice">과거 기록은 보존되어 있습니다. 체결·수수료·귀속 근거가 부족한 기록은 확정 순손익·승률·시나리오 표본에 합산하지 않습니다. 최근 실거래가 없어도 아래에서 확인할 수 있습니다.</p>
        <p>아래 저장 손익은 과거 파일의 pnl 값 그대로이며 수수료 포함 여부가 확인된 순손익이 아닙니다. 가져오기/수동·외부 기록은 중복 가능성 때문에 별도로 표시합니다. 통화 미확인 값은 합계를 제공하지 않습니다.</p>
        <div style={{ overflowX: "auto" }}><table className="data-table"><thead><tr><th>확정 성과 제외 사유</th><th>통화</th><th>기록 수</th><th>과거 저장 손익 합계 · 참고</th><th>손익 누락</th></tr></thead><tbody>
          {data.groups.filter((row) => row.category !== "confirmed").map((row) => <tr key={`${row.category}-${row.currency}`}><td>{labels[row.category] ?? row.category}</td><td>{row.currency}</td><td>{row.count.toLocaleString()}건</td><td>{row.currency === "UNKNOWN" ? "통화 확인 필요" : amount(row.stored_pnl_sum, row.currency)}</td><td>{row.missing_pnl_count}건</td></tr>)}
        </tbody></table></div>
        <details><summary>과거 참고 기록 상세 보기 · 최근 {data.recent_records.length}건</summary><div style={{ overflowX: "auto" }}><table className="data-table"><thead><tr><th>종료 시각</th><th>거래소·증권사</th><th>종목</th><th>저장 손익 · 대조 전</th><th>분류</th></tr></thead><tbody>
          {data.recent_records.map((row, index) => <tr key={index}><td>{row.exit_time}</td><td>{row.exchange}</td><td>{row.symbol}</td><td>{amount(row.stored_pnl, row.currency)}</td><td>{labels[row.category] ?? row.category}</td></tr>)}
        </tbody></table></div></details>
        <p>확정 성과에 반영하려면 해당 거래소·증권사의 과거 체결·수수료 내역과 주문 연결 근거를 대조해야 합니다. 이 화면은 조회 전용으로 원장·검증 상태를 변경하지 않으며, 새 거래를 실행해도 과거 기록이 자동 확정되지는 않습니다. 과거 손익으로 현재 잔고·자산 비중을 추정하지 않습니다.</p>
      </>}
    </>}
  </article>;
}
