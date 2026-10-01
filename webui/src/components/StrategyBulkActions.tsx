import {useEffect, useRef, useState} from 'react';
import type {GatewayClient} from '../api';
import {BULK_LIMIT, EXPORT_LIMIT, bulkDecision, bulkKey, strategyZip, type BulkOperation, type BulkRow} from '../strategyBulk';

type Result = {key: string; label: string; status: string; detail: string};
export function StrategyBulkActions({client, rows, selected, onSelection, disabled, onBusy, onRefresh}: {
  client: GatewayClient; rows: BulkRow[]; selected: Set<string>; onSelection: (value: Set<string>) => void;
  disabled: boolean; onBusy: (value: boolean) => void; onRefresh: () => void;
}) {
  const [running, setRunning] = useState(false), [results, setResults] = useState<Result[]>([]);
  const [progress, setProgress] = useState(''), [download, setDownload] = useState<{url: string; name: string} | null>(null);
  const stop = useRef(false), mounted = useRef(true), lock = useRef(false);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; stop.current = true; }; }, []);
  useEffect(() => () => { if (download) URL.revokeObjectURL(download.url); }, [download]);
  const targets = rows.filter(row => selected.has(bulkKey(row)));
  const names: Record<BulkOperation,string> = {delete:'선택 버전 삭제', pause:'선택 일시중지', paper:'선택 PAPER 검증', definition:'선택 전략 내보내기', package:'선택 패키지 내보내기'};
  async function run(operation: BulkOperation) {
    if (lock.current || disabled || !targets.length || targets.length > BULK_LIMIT) return;
    const note = operation === 'delete' ? '선택한 버전의 규칙만 삭제합니다. 다른 버전·거래 원장은 삭제하지 않습니다. 적용/검증 중인 버전은 보류합니다. 먼저 내보내기를 권장합니다.'
      : operation === 'pause' ? 'PAPER 검증은 근거를 보존하고 일시중지합니다. 적용 중인 전략은 신규 진입 풀에서 해제합니다. 기존 포지션 강제청산이나 거래소 전체 정지가 아닙니다.'
      : operation === 'paper' ? '승인된 실행 가능 버전만 PAPER 시작/재개합니다. 자동 승인·LIVE 전환·기존 검증 초기화는 하지 않습니다. 같은 전략의 다른 버전과 충돌하면 서버가 거부하며, 일반 10/프리미엄 30 평가 한도와 대기 정책은 유지합니다.'
      : '로컬 ZIP으로 저장합니다. 압축을 풀고 .noahstrategy 파일을 기존 전략 가져오기로 열 수 있습니다. 승인·활성 권한은 포함하지 않으며 허브로 전송하지 않습니다.';
    if (!window.confirm(`${names[operation]} · ${targets.length}개\n\n${note}\n\n개별 결과가 다를 수 있으며 완료된 작업은 일괄 취소되지 않습니다.`)) return;
    lock.current = true; stop.current = false; setRunning(true); onBusy(true); setResults([]); setDownload(null);
    const report: Result[] = [], files: Array<{name: string; content: string}> = [];
    let bytes = 0;
    try {
      for (const [index,row] of targets.entries()) {
        if (stop.current || !mounted.current) {
          report.push(...targets.slice(index).map(item => ({key:bulkKey(item), label:`${item.version.name} · v${item.version.version}`, status:'미실행', detail:'중단 요청으로 실행하지 않았습니다.'})));
          break;
        }
        const {version:v,scope} = row, decision = bulkDecision(row,operation);
        const result: Result = {key:bulkKey(row),label:`${v.name} · v${v.version} · ${scope}`,status:'보류',detail:decision.reason ?? ''};
        setProgress(`${index+1}/${targets.length} 처리 중`);
        if (decision.action) {
          try {
            if (operation === 'delete') await client.deleteStrategy(scope,v.strategy_key,v.version_id);
            else if (operation === 'definition' || operation === 'package') {
              const payload = await client.exportStrategyPackage(scope,v.strategy_key,v.version_id,operation==='definition');
              const content = typeof payload.package_json === 'string' ? payload.package_json : JSON.stringify(payload.package,null,2);
              if (!content) throw new Error('패키지 응답이 비어 있습니다.');
              const size = new TextEncoder().encode(content).length;
              if (bytes + size > EXPORT_LIMIT) { stop.current = true; throw new Error('20MB 한도 초과. 이전에 준비된 파일만 내려받을 수 있습니다.'); }
              bytes += size; files.push({name:`${scope}-${v.name}-v${v.version}`,content});
            } else await client.strategyAction({scope,strategy_key:v.strategy_key,version_id:v.version_id,action:decision.action,live_confirmation:false,operation_mode:'standard'});
            result.status = files.length && (operation==='definition'||operation==='package') ? '파일 준비' : '완료';
            result.detail = operation==='paper' ? 'PAPER 등록/재개 완료. 실제 평가 대상/대기는 실행 풀에서 확인하세요.' : decision.action==='deactivate' ? '적용 해제. 기존 포지션은 별도 보호 관리 대상입니다.' : '요청 처리 완료';
          } catch (error) {
            result.status = '실패·상태 확인'; result.detail = error instanceof Error ? error.message : '처리 결과를 확인하지 못했습니다.';
            // No automatic retries: a transport failure may follow a committed mutation.
          }
        }
        report.push(result);
        if (mounted.current) setResults([...report]);
      }
      if (files.length && mounted.current) {
        const url = URL.createObjectURL(new Blob([strategyZip(files)],{type:'application/zip'}));
        setDownload({url,name:`noahai-${operation}-${files.length}.zip`});
      }
    } catch (error) {
      report.push({key:'archive-error',label:'내보내기',status:'실패',detail:error instanceof Error ? error.message : '파일 생성 실패'});
    } finally {
      lock.current = false;
      if (mounted.current) {
        setResults([...report]);setProgress(stop.current ? '중단됨 · 완료 항목은 유지됩니다.' : '처리 완료 · 아래 개별 결과를 확인하세요.');setRunning(false);onBusy(false);
        onSelection(new Set()); if (operation==='delete'||operation==='pause'||operation==='paper') onRefresh();
      }
    }
  }
  return <section className="strategy-bulk" aria-label="선택 전략 작업">
    <div className="strategy-bulk-toolbar">
      <button type="button" className="secondary-button" disabled={disabled} onClick={()=>onSelection(new Set(rows.slice(0,BULK_LIMIT).map(bulkKey)))}>현재 목록 선택{rows.length>BULK_LIMIT?' · 앞 100개':''}</button>
      <button type="button" className="secondary-button" disabled={disabled||!selected.size} onClick={()=>onSelection(new Set())}>선택 해제</button>
      <strong>{targets.length}개 버전 선택</strong>
      {(Object.keys(names) as BulkOperation[]).map(op=><button key={op} type="button" className={op==='delete'?'danger-button':'secondary-button'} disabled={disabled||!targets.length||targets.length>BULK_LIMIT} onClick={()=>void run(op)}>{names[op]}</button>)}
      {running && <button type="button" onClick={()=>{stop.current=true;setProgress('현재 요청 완료 후 중단합니다.');}}>남은 작업 중단</button>}
    </div>
    <small>선택은 버전 단위입니다. 검색·필터·기관 변경 시 해제됩니다. 전략 내보내기는 정의만, 패키지는 검증 요약도 포함합니다. 미승인/실행 불가 항목은 자동 보완하지 않습니다.</small>
    <p role="status">{progress}</p>
    {download && <a className="secondary-button" href={download.url} download={download.name}>준비된 ZIP 다운로드</a>}
    {results.length>0 && <details open className="strategy-bulk-results"><summary>개별 처리 결과 {results.length}개</summary><ul>{results.map(r=><li key={r.key}><strong>{r.label}</strong> · {r.status}<br/>{r.detail}</li>)}</ul><small>통신 실패 항목은 새로고침으로 현재 상태를 확인한 뒤 다시 선택하세요. 자동 재시도하지 않습니다.</small></details>}
  </section>;
}
