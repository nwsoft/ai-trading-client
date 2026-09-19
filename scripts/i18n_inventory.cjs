// Read-only TypeScript AST inventory of static UI text. Not string execution.
const fs=require('node:fs'),path=require('node:path');
const ts=require('../webui/node_modules/typescript');
const root=path.resolve(__dirname,'../webui/src');
const rows=new Map();
function walkdir(dir){return fs.readdirSync(dir,{withFileTypes:true}).flatMap(e=>e.isDirectory()?walkdir(path.join(dir,e.name)):/\.tsx?$/.test(e.name)?[path.join(dir,e.name)]:[])}
for(const file of walkdir(root)){
 const source=ts.createSourceFile(file,fs.readFileSync(file,'utf8'),ts.ScriptTarget.Latest,true);
 function visit(n){
  if(ts.isJsxText(n)||ts.isStringLiteral(n)||ts.isNoSubstitutionTemplateLiteral(n)){
   const value=ts.isJsxText(n)?n.text.replace(/\s+/g,' ').trim():n.text;
   if(/[가-힣]/.test(value)){
    const row=rows.get(value)||{text:value,files:[],jsx:false};
    const name=path.relative(root,file);if(!row.files.includes(name))row.files.push(name);
    row.jsx ||= ts.isJsxText(n)||ts.isJsxAttribute(n.parent);rows.set(value,row);
   }
  }
  ts.forEachChild(n,visit);
 }
 visit(source);
}
const result=[...rows.values()];
if(process.argv.includes('--json'))process.stdout.write(JSON.stringify(result,null,2));
else {console.log(JSON.stringify({unique:result.length,jsx:result.filter(r=>r.jsx).length},null,2));for(const r of result.filter(r=>r.jsx))console.log(JSON.stringify(r.text));}
