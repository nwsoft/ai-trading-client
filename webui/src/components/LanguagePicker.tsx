import { useState } from 'react';
import type { GatewayClient } from '../api';
import { setLocale, useLocale, localized } from '../i18n';

export function LanguagePicker({client}: {client?: GatewayClient}) {
  const locale=useLocale();
  const [busy,setBusy]=useState(false),[error,setError]=useState('');
  return <span className="language-picker"><label><span>{localized('언어', 'Language')}</span><select aria-label="Language / 언어" value={locale} disabled={busy} onChange={async e=>{
    const next=e.target.value,previous=locale;setError('');setBusy(true);setLocale(next);
    try { if(client)await client.saveDisplayPreferences(next); }
    catch {setLocale(previous);setError(localized('언어를 저장하지 못했습니다. 다시 시도하세요.','Could not save your language. Please try again.'));}
    finally {setBusy(false);}
  }}><option value="ko">한국어</option><option value="en">English (Beta)</option></select></label>{error&&<small role="alert">{error}</small>}</span>;
}
