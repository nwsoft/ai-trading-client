// Stored instants need a timezone. Never infer the zone of a legacy wall clock.
export function userTime(value: unknown, options: {locale?: string; timeZone?: string} = {}) {
  const missing = value === null || value === undefined || value === '';
  const zoned = typeof value === 'string' && /(?:Z|[+-]\d{2}:?\d{2})$/i.test(value.trim());
  const date = typeof value === 'number' && Number.isFinite(value)
    ? new Date(value < 1e12 ? value * 1000 : value)
    : zoned ? new Date(String(value)) : null;
  const ko = (options.locale ?? 'ko-KR').startsWith('ko');
  if (!date || !Number.isFinite(date.getTime())) return {
    text: missing ? (ko ? '시각 미기록' : 'Time not recorded') : (ko ? '시각 확인 필요' : 'Time needs verification'),
    iso: undefined, utc: undefined,
  };
  const zone = options.timeZone ?? Intl.DateTimeFormat().resolvedOptions().timeZone;
  const parts = new Intl.DateTimeFormat('en-GB', {
    timeZone: zone, year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23', timeZoneName: 'shortOffset',
  }).formatToParts(date);
  const p = Object.fromEntries(parts.map(part => [part.type, part.value]));
  const offset = p.timeZoneName.replace('GMT', 'UTC');
  const zoneLabel = zone === 'Asia/Seoul' && ko ? `한국 시간, ${offset}` : offset;
  return {text: `${p.year}.${p.month}.${p.day} ${p.hour}:${p.minute}:${p.second} (${zoneLabel})`, iso: date.toISOString(), utc: date.toISOString()};
}
