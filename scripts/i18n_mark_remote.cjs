// One-time explicit-source migration for the sibling portal; no user data is transformed.
const fs=require('node:fs'),path=require('node:path'),ts=require('../webui/node_modules/typescript');
const root=path.resolve(__dirname,'../../daltrading');
const dictionary=require(path.join(root,'config/remote_locale_en.json'));
const htmlFile=path.join(root,'templates/remote_dashboard.html');
let html=fs.readFileSync(htmlFile,'utf8');
html=html.replace(/>([^<>]*[가-힣][^<>]*)</g,(all,s)=>{
 if(s.includes('{{')||!Object.hasOwn(dictionary,s))return all;
 return `>{{ tr(${JSON.stringify(s)}) }}<`;
});
fs.writeFileSync(htmlFile,html);
const jsFile=path.join(root,'static/remote_dashboard.js');let source=fs.readFileSync(jsFile,'utf8');
const tree=ts.createSourceFile(jsFile,source,ts.ScriptTarget.Latest,true),edits=[];
function visit(n){
 if(ts.isStringLiteral(n)&&Object.hasOwn(dictionary,n.text)&&!(ts.isCallExpression(n.parent)&&n.parent.expression.getText(tree)==='tr'))edits.push([n.getStart(tree),n.end,`tr(${JSON.stringify(n.text)})`]);
 ts.forEachChild(n,visit);
}
visit(tree);for(const[a,b,v]of edits.sort((a,b)=>b[0]-a[0]))source=source.slice(0,a)+v+source.slice(b);
fs.writeFileSync(jsFile,source);
console.log('Remote presentation strings marked:',edits.length);
