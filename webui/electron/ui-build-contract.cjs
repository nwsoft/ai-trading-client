const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');

function sourceHash(root) {
  const names=[];
  function visit(relative) {
    const file=path.join(root,relative);
    if (!fs.existsSync(file)) return;
    if (fs.statSync(file).isDirectory()) for (const entry of fs.readdirSync(file).sort()) visit(path.join(relative,entry));
    else names.push(relative);
  }
  for(const name of ['src','public','index.html','package.json','package-lock.json','vite.config.ts','electron/ui-build-contract.cjs']) visit(name);
  const hash=crypto.createHash('sha256');
  for(const name of names.sort()) hash.update(name.split(path.sep).join('/')).update('\0').update(fs.readFileSync(path.join(root,name))).update('\0');
  return hash.digest('hex');
}
function buildPlugin(root) {
  return {name:'noah-renderer-build-contract',generateBundle() {
    this.emitFile({type:'asset',fileName:'ui-build.json',source:JSON.stringify({
      version:JSON.parse(fs.readFileSync(path.join(root,'package.json'))).build.buildVersion,
      source_sha256:sourceHash(root),built_at:new Date().toISOString(),
    })});
  }};
}
function isCurrent(root) {
  try {return JSON.parse(fs.readFileSync(path.join(root,'dist/ui-build.json'))).source_sha256===sourceHash(root);}
  catch {return false;}
}
module.exports={sourceHash,buildPlugin,isCurrent};
