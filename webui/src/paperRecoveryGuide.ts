import guide from './generated/paper-recovery-guide.json';
export function paperRecoveryGuide(question:string,locale='ko'):string|null{
 if(question.includes('NOAH_STRATEGY_EXPLANATION_V1\n')||question.includes('[MARKET_TREND_SNAPSHOT]'))return null;
 const normalized=question.toLowerCase().replace(/\s+/g,'');
 return guide.triggers.some(t=>normalized.includes(t.toLowerCase()))?(locale==='en'?guide.en:guide.ko):null;
}
