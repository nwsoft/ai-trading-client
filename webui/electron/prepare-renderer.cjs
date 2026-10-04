// Source-checkout startup only. Packaged clients never install or compile code.
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const {spawn, spawnSync} = require('node:child_process');
const contract = require('./ui-build-contract.cjs');

function compatible(version) {
  const [major, minor] = String(version).replace(/^v/, '').split('.').map(Number);
  return major > 22 || (major === 22 && minor >= 12);
}
function buildNode() {
  if (compatible(process.versions.node)) return process.execPath;
  const home = process.env.NVM_DIR || path.join(os.homedir(), '.nvm');
  const versions = path.join(home, 'versions', 'node');
  let entries=[];
  try { entries=fs.readdirSync(versions).filter(compatible).sort((a,b)=>b.localeCompare(a,undefined,{numeric:true})); } catch {}
  for (const entry of entries) {
    const executable=path.join(versions,entry,'bin','node');
    const result=spawnSync(executable,['--version'],{encoding:'utf8',timeout:5000});
    if(result.status===0 && compatible(result.stdout.trim())) return executable;
  }
  throw new Error('화면 빌드에는 Node 22.12 이상이 필요합니다. 호환 Node를 설치한 뒤 다시 실행하세요.');
}
function run(executable,args,options) {
  return new Promise((resolve,reject)=>{
    const child=spawn(executable,args,{...options,stdio:'inherit'});
    const forward=signal=>child.kill(signal);
    const stop=()=>forward('SIGINT'),terminate=()=>forward('SIGTERM');
    process.once('SIGINT',stop);process.once('SIGTERM',terminate);
    const cleanup=()=>{process.removeListener('SIGINT',stop);process.removeListener('SIGTERM',terminate);};
    child.once('error',error=>{cleanup();reject(error);});
    child.once('exit',(code,signal)=>{cleanup();code===0&&!signal?resolve():reject(new Error(`화면 빌드 실패 (${signal||code}). 위 오류를 확인하세요.`));});
  });
}
async function build(root) {
  const node=buildNode();
  // Invoke installed JS entrypoints directly: synced executable bits and the
  // shell's older Node must not decide which compiler runs.
  const tsc=path.join(root,'node_modules/typescript/bin/tsc');
  const vite=path.join(root,'node_modules/vite/bin/vite.js');
  if(!fs.existsSync(tsc)||!fs.existsSync(vite)) throw new Error('화면 빌드 의존성이 없습니다. webui에서 npm ci --include=optional을 실행하세요.');
  const env={...process.env,PATH:path.dirname(node)+path.delimiter+(process.env.PATH||'')};
  delete env.ELECTRON_RUN_AS_NODE;
  const options={cwd:root,env};
  console.log(`현재 소스에 맞는 화면을 준비합니다. (Node ${spawnSync(node,['--version'],{encoding:'utf8'}).stdout.trim()})`);
  await run(node,[tsc,'--noEmit','-p','tsconfig.app.json'],options);
  await run(node,[tsc,'--noEmit','-p','tsconfig.node.json'],options);
  await run(node,[vite,'build'],options);
}
async function prepareRenderer(root,options={}) {
  const isCurrent=options.isCurrent||contract.isCurrent;
  const compile=options.build||build;
  if(isCurrent(root)) return {rebuilt:false};
  const lock=path.join(root,'.renderer-build.lock');
  const deadline=Date.now()+(options.waitMs??180000);
  let owns=false;
  while(!owns) {
    try {
      const fd=fs.openSync(lock,'wx',0o600);
      fs.writeFileSync(fd,JSON.stringify({pid:process.pid}));fs.closeSync(fd);owns=true;
    } catch(error) {
      if(error.code!=='EEXIST')throw error;
      try {
        const raw=fs.readFileSync(lock,'utf8');const owner=JSON.parse(raw);
        try {process.kill(owner.pid,0);} catch(probe) {
          if(probe.code==='ESRCH'&&fs.readFileSync(lock,'utf8')===raw){fs.unlinkSync(lock);continue;}
        }
      } catch {} // A live process may still be writing its lock. Never steal it.
      if(Date.now()>=deadline)throw new Error('다른 화면 빌드가 진행 중입니다. 완료 후 다시 실행하세요.');
      await new Promise(resolve=>setTimeout(resolve,250));
      if(!fs.existsSync(lock)&&isCurrent(root))return {rebuilt:false};
    }
  }
  try {
    if(isCurrent(root))return {rebuilt:false};
    await compile(root);
    if(!isCurrent(root))throw new Error('빌드 중 소스가 변경되었거나 화면 파일이 누락되었습니다. 동기화가 완료된 뒤 다시 실행하세요.');
    return {rebuilt:true};
  } finally {if(owns)fs.unlinkSync(lock);}
}
module.exports={compatible,buildNode,prepareRenderer};
if(require.main===module) prepareRenderer(path.resolve(__dirname,'..')).then(r=>console.log(r.rebuilt?'화면 준비 완료':'현재 화면 빌드 확인 완료')).catch(e=>{console.error(e.message);process.exitCode=1;});
