import type {StrategyCatalog,StrategyVersion} from './types';
export function strategyCatalogView(groups:StrategyCatalog['strategies'],query:string,status:string,sort:string) {
  const needle=query.trim().toLocaleLowerCase();
  function matches(v:StrategyVersion) {
    if(status==='active')return v.active;
    if(status==='paper')return v.paper_observing || v.status==='paper_observing';
    if(status==='passed')return v.paper_validation?.passed===true;
    if(status==='repair')return (v.execution_readiness??v.paper_execution_readiness)?.ready===false;
    return true;
  }
  return groups.map(group=>({...group,versions:group.versions.filter(v=>matches(v) && (!needle || [v.name,group.strategy_key,v.version_id,v.source_reference,group.scope].join(' ').toLocaleLowerCase().includes(needle)))}))
    .filter(group=>group.versions.length).sort((a,b)=>{
      const latest=(g:typeof a)=>g.versions.reduce((last,v)=>Math.max(last,Date.parse(String((v as any).created_at))||0),0);
      const name=(g:typeof a)=>g.versions.at(-1)?.name||g.strategy_key;
      const order=sort.startsWith('name')?name(a).localeCompare(name(b),'ko',{numeric:true}):latest(a)-latest(b);
      return (sort.endsWith('desc')?-order:order) || `${a.scope}:${a.strategy_key}`.localeCompare(`${b.scope}:${b.strategy_key}`);
    });
}
