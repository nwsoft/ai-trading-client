const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const ts=require('../webui/node_modules/typescript');
const root=path.resolve(__dirname,'../webui/src/i18n');
function runtime({languages=[],saved=[],systemLanguage,storageDisabled=false}={}){
 const storage=new Map(saved),out={};
 const sandbox={exports:out,require:id=>id==='react'?{useSyncExternalStore:(_,get)=>get()}:require(path.join(root,id)),window:{noahAI:{bootstrap:()=>({systemLanguage})}},navigator:{languages},localStorage:{getItem:k=>{if(storageDisabled)throw Error('disabled');return storage.get(k)??null;},setItem:(k,v)=>storage.set(k,v)},document:{documentElement:{lang:''}}};
 vm.runInNewContext(ts.transpileModule(fs.readFileSync(path.join(root,'index.ts'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,esModuleInterop:true}}).outputText,sandbox);
 return {i:out,storage,doc:sandbox.document};
}
test('Korean default, English selection, unsupported fallback and account isolation',()=>{
 const {i,doc}=runtime();assert.equal(i.getLocale(),'ko');assert.equal(i.t('설정'),'설정');
 i.setLocale('en');assert.equal(i.t('설정'),'Settings');assert.equal(doc.documentElement.lang,'en');
 i.setLocaleAccount('alice');assert.equal(i.getLocale(),'en');i.setLocale('ko');
 i.setLocaleAccount('bob');assert.equal(i.getLocale(),'en');i.setLocaleAccount('alice');assert.equal(i.getLocale(),'ko');
 i.setLocale('unsupported');assert.equal(i.getLocale(),'ko');
});
test('Initial OS hint, browser fallback and unsupported languages do not infer country',()=>{
 assert.equal(runtime({systemLanguage:'ko-KR',languages:['en-US']}).i.getLocale(),'ko');
 assert.equal(runtime({systemLanguage:'en-GB',languages:['ko-KR']}).i.getLocale(),'en');
 assert.equal(runtime({languages:['en-US']}).doc.documentElement.lang,'en');
 assert.equal(runtime({languages:['ja-JP','en-US']}).i.getLocale(),'ko');
 assert.equal(runtime({systemLanguage:'fr-FR'}).i.getLocale(),'ko');
 assert.equal(runtime({systemLanguage:'en-US',storageDisabled:true}).i.getLocale(),'en');
});
test('Explicit account and guest choices override system hint across reloads',()=>{
 const saved=[['noahai.locale.guest','ko'],['noahai.locale.alice','en']];
 const {i}=runtime({systemLanguage:'en-US',saved});assert.equal(i.getLocale(),'ko');
 i.setLocaleAccount('alice');assert.equal(i.getLocale(),'en');i.setLocaleAccount('bob');assert.equal(i.getLocale(),'ko');
 assert.equal(runtime({systemLanguage:'ko-KR',saved:[['noahai.locale.guest','en']]}).i.getLocale(),'en');
});
test('Language control belongs to login footer and General settings, not dashboard header',()=>{
 const src=path.resolve(root,'..');
 assert.match(fs.readFileSync(path.join(src,'components/LoginScreen.tsx'),'utf8'),/<footer className="legacy-login-language"><LanguagePicker/);
 assert(!fs.readFileSync(path.join(src,'App.tsx'),'utf8').includes('<LanguagePicker'));
 assert.match(fs.readFileSync(path.join(src,'components/SettingsCenter.tsx'),'utf8'),/activeSection === "general" && <section className="settings-language-row"/);
});
test('Unknown original evidence and financial precision remain unchanged',()=>{
 const {i}=runtime();i.setLocale('en');
 for(const original of ['전략 원문 RSI < 30', 'pnl_reconciliation_required', '-0.250001 USDT', '2026-09-18T00:03:13Z', '<script>alert(1)</script>', '__proto__', 'constructor'])assert.equal(i.t(original),original);
 assert.equal(i.t(' 설정 '),' Settings ');
});
test('Catalogs are bounded, nonempty and contain no markup or unresolved placeholders',()=>{
 const catalog={};for(const file of ['en.json','en.core.json','en.replay.json','en.studio.json']){
   for(const [key,value]of Object.entries(require(path.join(root,file)))){
    assert.equal(typeof value,'string');assert(value.trim());assert(!/<script|\$\{|\{\{/i.test(value));
    if(catalog[key])assert.equal(catalog[key],value,`conflicting key ${key}`);catalog[key]=value;
   }
 }
 assert(Object.keys(catalog).length>=400);
});

test('Translated select options retain explicit canonical values',()=>{
 const src=path.resolve(root,'..');
 function walk(d){return fs.readdirSync(d,{withFileTypes:true}).flatMap(e=>e.isDirectory()?walk(path.join(d,e.name)):e.name.endsWith('.tsx')?[path.join(d,e.name)]:[]);}
 for(const file of walk(src)){
  const tree=ts.createSourceFile(file,fs.readFileSync(file,'utf8'),ts.ScriptTarget.Latest,true,ts.ScriptKind.TSX);
  function visit(n){
   if(ts.isJsxElement(n)&&n.openingElement.tagName.getText(tree)==='option'&&n.children.some(c=>ts.isJsxExpression(c)&&c.expression&&c.expression.getText(tree).startsWith('t('))){
    assert(n.openingElement.attributes.properties.some(p=>p.name?.getText(tree)==='value'),`implicit translated value in ${file}`);
   }
   ts.forEachChild(n,visit);
  }visit(tree);
 }
});
