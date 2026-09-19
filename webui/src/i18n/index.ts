import { useSyncExternalStore } from 'react';
import english from './en.json';
import coreEnglish from './en.core.json';
import replayEnglish from './en.replay.json';
import studioEnglish from './en.studio.json';

export type Locale = 'ko' | 'en';
const listeners = new Set<() => void>();
let account = 'guest';
/** Initial display hint only; never infer country, currency or trading permissions. */
export function systemLocale(): Locale {
  let preferred = '';
  try {
    if (typeof window !== 'undefined') preferred = window.noahAI?.bootstrap().systemLanguage || '';
  } catch { /* Browser preview / unavailable desktop bridge. */ }
  if (!preferred && typeof navigator !== 'undefined') preferred = navigator.languages?.[0] || navigator.language || '';
  return preferred.toLowerCase().split(/[-_]/)[0] === 'en' ? 'en' : 'ko';
}
function readLocale(scope: string): Locale {
  try {
    for (const key of [`noahai.locale.${encodeURIComponent(scope)}`, 'noahai.locale.guest']) {
      const saved = localStorage.getItem(key);
      if (saved === 'ko' || saved === 'en') return saved;
    }
  } catch { /* System hint still works with storage disabled. */ }
  return systemLocale();
}
let locale: Locale = readLocale(account);
if (typeof document !== 'undefined') document.documentElement.lang = locale;
export function getLocale(): Locale { return locale; }
export function intlLocale(): string { return locale === 'en' ? 'en-US' : 'ko-KR'; }
export function setLocale(value: string, persist = true): void {
  const next: Locale = value === 'en' ? 'en' : 'ko';
  locale = next;
  if (persist) { try { localStorage.setItem(`noahai.locale.${encodeURIComponent(account)}`, next); } catch { /* Private/storage-disabled browsers still work. */ } }
  document.documentElement.lang = next;
  for (const listener of listeners) listener();
}
export function setLocaleAccount(value: string): void {
  account = value || 'guest';
  setLocale(readLocale(account), false);
}
export function useLocale(): Locale {
  return useSyncExternalStore(listener => { listeners.add(listener); return () => { listeners.delete(listener); }; }, getLocale, () => 'ko');
}
function normalize(value: string): string { return value.replace(/\s+/g, ' ').trim(); }
const catalog: Record<string, string> = {...english, ...coreEnglish, ...replayEnglish, ...studioEnglish};
/** Only explicitly marked product copy is localized. Inputs and payloads are untouched. */
export function t(source: string): string {
  if (locale !== 'en') return source;
  const key = normalize(source);
  if (!Object.hasOwn(catalog, key)) return source;
  const translated = catalog[key];
  const leading = source.match(/^\s*/)?.[0] || '';
  const trailing = source.match(/\s*$/)?.[0] || '';
  return leading + translated + trailing;
}
export function localized(ko: string, en: string): string { return locale === 'en' ? en : ko; }
