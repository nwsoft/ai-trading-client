import {getLocale} from '../i18n';
import {userTime} from '../userTime';

export function UserTime({value}: {value: unknown}) {
  const time = userTime(value, {locale: getLocale()});
  return time.iso ? <time dateTime={time.iso} title={`저장 시각: ${String(value)} · UTC: ${time.utc}`}>{time.text}</time> : <span>{time.text}</span>;
}
