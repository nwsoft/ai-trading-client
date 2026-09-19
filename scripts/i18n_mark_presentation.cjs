// One-time, repeatable mechanical migration. Only JSX presentation is marked;
// action handlers, comparison operands, values and user-supplied data are not.
const fs=require('node:fs'),path=require('node:path');
const ts=require('../webui/node_modules/typescript');
const root=path.resolve(__dirname,'../webui/src');
const catalog=Object.assign({},...['en.json','en.core.json','en.replay.json','en.studio.json'].map(f=>require('../webui/src/i18n/'+f)));
function files(d){return fs.readdirSync(d,{withFileTypes:true}).flatMap(e=>e.isDirectory()?files(path.join(d,e.name)):/\.tsx$/.test(e.name)?[path.join(d,e.name)]:[])}
for(const file of files(root)){
 if(file.endsWith('LanguagePicker.tsx'))continue;
 let source=fs.readFileSync(file,'utf8');
 const tree=ts.createSourceFile(file,source,ts.ScriptTarget.Latest,true,ts.ScriptKind.TSX),edits=[];
 function add(n,value){edits.push([n.getStart(tree),n.end,value]);}
 function presentation(n){
   let p=n.parent,child=n;
   while(p&&!ts.isJsxExpression(p)){
    if(ts.isConditionalExpression(p)){if(p.condition===child)return false;}
    else if(ts.isParenthesizedExpression(p)){}
    else if(ts.isBinaryExpression(p)&&[ts.SyntaxKind.BarBarToken,ts.SyntaxKind.QuestionQuestionToken].includes(p.operatorToken.kind)&&p.right===child){}
    else return false;
    child=p;p=p.parent;
   }
   return p&&!ts.isJsxAttribute(p.parent);
 }
 function visit(n){
  const displayFields = file.endsWith('StrategyStudio.tsx') ? ['mode.label','mode.description','preset.label','option.label'] : file.endsWith('AssistantWorkspace.tsx') ? ['profile.placeholder','profile.title'] : [];
  if(ts.isJsxExpression(n)&&n.expression&&displayFields.includes(n.expression.getText(tree))){
    add(n.expression,`t(${n.expression.getText(tree)})`);return;
  }
  if(ts.isJsxElement(n)&&n.openingElement.tagName.getText(tree)==='option'&&!n.openingElement.attributes.properties.some(p=>p.name?.getText(tree)==='value')){
    const meaningful=n.children.filter(c=>!ts.isJsxText(c)||c.text.trim());
    if(meaningful.length===1){
      const child=meaningful[0];
      const value=ts.isJsxText(child)?child.text.trim():ts.isJsxExpression(child)&&child.expression&&ts.isCallExpression(child.expression)&&child.expression.expression.getText(tree)==='t'&&ts.isStringLiteral(child.expression.arguments[0])?child.expression.arguments[0].text:null;
      if(value!==null){const pos=n.openingElement.end-1;edits.push([pos,pos,` value={${JSON.stringify(value)}}`]);}
    }
  }
  if(ts.isJsxText(n)&&/[가-힣]/.test(n.text)){
   // Preserve JSX's rendered whitespace, not indentation/newlines from source.
   const lines=n.text.split(/\r?\n/);let rendered='';
   lines.forEach((line,i)=>{let s=line.replace(/\t/g,' ');if(i)s=s.replace(/^ +/,'');if(i<lines.length-1)s=s.replace(/ +$/,'');if(s)rendered+=s+(i<lines.length-1?' ':'');});
   rendered=rendered.replaceAll('&lt;','<').replaceAll('&gt;','>').replaceAll('&amp;','&').replaceAll('&quot;','"').replaceAll('&#39;',"'");
   edits.push([n.pos,n.end,`{t(${JSON.stringify(rendered)})}`]);return;
  }
  if(ts.isJsxAttribute(n)&&['title','placeholder','aria-label'].includes(n.name.text)&&n.initializer&&ts.isStringLiteral(n.initializer)&&/[가-힣]/.test(n.initializer.text)){
   add(n.initializer,`{t(${JSON.stringify(n.initializer.text)})}`);return;
  }
  if(ts.isStringLiteral(n)&&Object.hasOwn(catalog,n.text)&&presentation(n))add(n,`t(${JSON.stringify(n.text)})`);
  ts.forEachChild(n,visit);
 }
 visit(tree);
 if(!edits.length)continue;
 for(const [a,b,v] of edits.sort((a,b)=>b[0]-a[0]))source=source.slice(0,a)+v+source.slice(b);
 if(!/import\s*\{[^}]*\bt\b[^}]*\}\s*from\s*['"](?:\.\.\/|\.\/)i18n['"]/.test(source))source=`import { t } from '${file===path.join(root,'App.tsx')?'./i18n':'../i18n'}';\n`+source;
 fs.writeFileSync(file,source);
 console.log(path.relative(root,file),edits.length);
}
