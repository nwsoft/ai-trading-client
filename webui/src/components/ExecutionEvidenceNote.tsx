import { localized } from '../i18n';

export function executionEvidenceCount(count: number, status?: string) {
  if (status === 'unsupported') return localized('조회 미지원', 'History unavailable');
  if (status === 'not_checked') return localized('조회 전', 'Not checked');
  const coverage = ['stored_only','partial'].includes(status || '')
    ? localized(' · 수집 범위 기준', ' · collected records') : '';
  return `${count.toLocaleString()}${localized('개', ' fills')}${coverage}`;
}

export function ExecutionEvidenceNote({status, rows, count}: {status?: string; rows?: Array<Record<string, any>>; count?: number}) {
  return <details className="spot-holding-scope" style={{fontSize:14,lineHeight:1.6}}>
    <summary>{localized('완료 거래와 체결 기록은 어떻게 다른가요?', 'Completed trades vs. fill records')}</summary>
    <p>{localized('완료 거래는 NoahAI에 기록된 청산 거래 수입니다. 체결 기록은 진입·청산·분할체결을 각각 셉니다. 따라서 완료 거래 3건이 체결 7개로 구성될 수 있으며 두 숫자가 같을 필요는 없습니다.',
      'Completed trades count NoahAI closure records. Fill records count entry, exit and partial fills separately. Three completed trades can contain seven fills; the counts need not match.')}</p>
    <p>{localized('완료 거래의 손익은 대조 완료된 거래만 합산합니다. 체결금액은 진입과 청산 양쪽이 포함될 수 있어 거래 표의 진입금액과 다를 수 있습니다.',
      'Closed-trade PnL includes reconciled trades only. Filled notional may include both entry and exit fills, unlike the entry notional in the trade table.')}</p>
    {['stored_only','partial','not_checked','unsupported'].includes(status || '') && <p>{localized('체결 수는 앱에 수집된 내역 기준입니다. 선택 기간의 기관 전체 내역이 모두 수집됐다는 뜻은 아닙니다. 대조 완료 3/3도 해당 기간의 3건에 대한 결과이며 다른 기간의 미확정 기록과는 별개입니다.',
      'The fill count uses records collected by this app, not proven complete account history. A 3/3 reconciliation result covers those three trades, not unresolved records in other periods.')}</p>}
    {rows && <>
      <p>{localized('선택 기간에 수집된 체결', 'Collected fills in the selected period')}: {count ?? rows.length} · {localized('최근 내역 표시', 'Recent records shown')}: {rows.length}</p>
      <ul>{rows.map((row,index) => <li key={String(row.id ?? index)} style={{overflowWrap:'anywhere'}}>
        {String(row.exchange ?? '').toUpperCase()} · {String(row.symbol ?? '—')} · {String(row.side ?? '—').toUpperCase()} · {localized('수량', 'Quantity')} {String(row.quantity ?? '—')} · {localized('주문', 'Order')} {String(row.order_id ?? '—')} · {localized('체결 ID', 'Fill ID')} {String(row.trade_id ?? '—')} · {String(row.executed_at ?? '—')}
      </li>)}</ul>
    </>}
  </details>;
}
