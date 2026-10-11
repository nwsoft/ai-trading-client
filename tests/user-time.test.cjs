const {test}=require('node:test');
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),Module=require('node:module');
const ts=require('../webui/node_modules/typescript');
const file=path.resolve(__dirname,'../webui/src/userTime.ts'),m=new Module(file,module);
m._compile(ts.transpileModule(fs.readFileSync(file,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,file);
const {userTime}=m.exports;
test('screenshot UTC instant displays Korean wall clock with timezone; UTC preserved',()=>{
 const r=userTime('2026-10-11T06:56:06.230482+00:00',{timeZone:'Asia/Seoul'});
 assert.equal(r.text,'2026.10.11 15:56:06 (한국 시간, UTC+9)');
 assert.equal(r.iso,'2026-10-11T06:56:06.230Z');
});
test('device zone follows daylight saving and midnight correctly',()=>{
 assert.match(userTime('2026-10-11T06:56:06Z',{timeZone:'America/New_York'}).text,/2026.10.11 02:56:06 \(UTC-4\)/);
 assert.match(userTime('2026-12-11T06:56:06Z',{timeZone:'America/New_York'}).text,/01:56:06 \(UTC-5\)/);
 assert.match(userTime('2026-10-11T15:00:00Z',{timeZone:'Asia/Seoul'}).text,/2026.10.12 00:00:00/);
});
test('missing, invalid and zone-free instants never become now or zero',()=>{
 for(const v of [null,undefined,''])assert.equal(userTime(v).text,'시각 미기록');
 for(const v of ['bad','2026-10-11T06:56:06',false,NaN,Infinity])assert.equal(userTime(v).text,'시각 확인 필요');
 assert.equal(userTime(null,{locale:'en'}).text,'Time not recorded');
});
test('seconds, milliseconds and explicit offsets refer to the same instant',()=>{
 const options={timeZone:'UTC'},a=userTime('2026-10-11T15:56:06+09:00',options);
 const ms=Date.parse(a.iso);assert.equal(userTime(ms,options).text,a.text);assert.equal(userTime(ms/1000,options).text,a.text);
});
