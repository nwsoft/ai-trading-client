import type { StrategyVersion } from './types';

export type BulkRow = { scope: string; version: StrategyVersion };
export type BulkOperation = 'delete' | 'pause' | 'paper' | 'definition' | 'package';
export const BULK_LIMIT = 100;
export const EXPORT_LIMIT = 20 * 1024 * 1024;
export const bulkKey = ({scope, version}: BulkRow) => JSON.stringify([scope, version.strategy_key, version.version_id]);

// UI preflight only. Every mutation still passes the authoritative server policy.
export function bulkDecision(row: BulkRow, operation: BulkOperation): {action?: string; reason?: string} {
  const v = row.version;
  const active = v.active || v.status === 'active';
  const observing = v.paper_observing || v.status === 'paper_observing';
  if (operation === 'definition' || operation === 'package') return {action: operation};
  if (operation === 'delete') return active || observing
    ? {reason: '적용/검증 중입니다. 먼저 일시중지하고 상태를 확인하세요.'} : {action: 'delete'};
  if (operation === 'pause') return active ? {action: 'deactivate'} : observing
    ? {action: 'stop_paper'} : {reason: '현재 적용 또는 PAPER 검증 중이 아닙니다.'};
  if (active || observing) return {reason: '이미 적용 또는 PAPER 검증 중입니다.'};
  if ((v.execution_readiness ?? v.paper_execution_readiness)?.ready === false)
    return {reason: '실행 조건을 보완한 뒤 사용자 승인하세요.'};
  if (!['approved', 'execution_rejected', 'execution_validated', 'paper_rejected', 'paper_paused'].includes(v.status))
    return {reason: '사용자 승인 등 개별 단계 확인이 필요합니다. 자동 승인하지 않습니다.'};
  if (v.status === 'execution_validated' && !(v.execution_validation?.mode === 'historical_replay' && v.execution_validation?.passed))
    return {reason: '이 실행검증 상태에서는 개별 버전 단계를 확인하세요.'};
  return {action: 'start_paper'};
}

// Small bounded store-only ZIP: no extra dependency, compression worker or network.
export function strategyZip(files: Array<{name: string; content: string}>): Uint8Array<ArrayBuffer> {
  const enc = new TextEncoder(), chunks: Uint8Array[] = [], central: Uint8Array[] = [];
  let offset = 0, centralSize = 0, total = 0;
  if (!files.length || files.length > BULK_LIMIT) throw new Error('내보낼 파일 수는 1~100개여야 합니다.');
  const crc = (bytes: Uint8Array) => {
    let value = 0xffffffff;
    for (const byte of bytes) { value ^= byte; for (let i = 0; i < 8; i++) value = (value >>> 1) ^ (value & 1 ? 0xedb88320 : 0); }
    return (value ^ 0xffffffff) >>> 0;
  };
  for (const [index, file] of files.entries()) {
    // Prefix prevents collisions; no path, drive prefix or control characters.
    const name = enc.encode(`${index + 1}-${file.name.replace(/[\\/:*?"<>|\x00-\x1f]/g, '_').slice(0, 140)}.noahstrategy`);
    const data = enc.encode(file.content); total += data.length;
    if (total > EXPORT_LIMIT) throw new Error('내보내기 20MB 한도입니다. 선택 수를 줄여 다시 시도하세요.');
    const checksum = crc(data), local = new Uint8Array(30 + name.length), lv = new DataView(local.buffer);
    lv.setUint32(0, 0x04034b50, true); lv.setUint16(4, 20, true); lv.setUint16(6, 0x800, true);
    lv.setUint16(12, 33, true); // 1980-01-01, stable valid ZIP date
    lv.setUint32(14, checksum, true); lv.setUint32(18, data.length, true); lv.setUint32(22, data.length, true);
    lv.setUint16(26, name.length, true); local.set(name, 30);
    const entry = new Uint8Array(46 + name.length), ev = new DataView(entry.buffer);
    ev.setUint32(0, 0x02014b50, true); ev.setUint16(4, 20, true); ev.setUint16(6, 20, true); ev.setUint16(8, 0x800, true);
    ev.setUint16(14, 33, true); ev.setUint32(16, checksum, true); ev.setUint32(20, data.length, true); ev.setUint32(24, data.length, true);
    ev.setUint16(28, name.length, true); ev.setUint32(42, offset, true); entry.set(name, 46);
    chunks.push(local, data); central.push(entry); centralSize += entry.length; offset += local.length + data.length;
  }
  const end = new Uint8Array(22), view = new DataView(end.buffer);
  view.setUint32(0, 0x06054b50, true); view.setUint16(8, files.length, true); view.setUint16(10, files.length, true);
  view.setUint32(12, centralSize, true); view.setUint32(16, offset, true);
  const out = new Uint8Array(offset + centralSize + end.length); let at = 0;
  for (const chunk of [...chunks, ...central, end]) { out.set(chunk, at); at += chunk.length; }
  return out;
}
