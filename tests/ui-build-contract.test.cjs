const {test}=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {sourceHash,isCurrent,buildPlugin}=require('../webui/electron/ui-build-contract.cjs');
test('missing and stale renderer cannot masquerade as current engine version',()=>{
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'noah-ui-hash-'));
 fs.mkdirSync(path.join(root,'src'));fs.mkdirSync(path.join(root,'dist'));
 fs.writeFileSync(path.join(root,'package.json'),JSON.stringify({build:{buildVersion:'3.9.1.49'}}));
 fs.writeFileSync(path.join(root,'src/view.ts'),'old');assert.equal(isCurrent(root),false);
 const plugin=buildPlugin(root);let asset;
 plugin.generateBundle.call({emitFile:value=>asset=value});
 assert.equal(asset.fileName,'ui-build.json');
 fs.writeFileSync(path.join(root,'dist',asset.fileName),asset.source);assert.equal(isCurrent(root),true);
 const before=sourceHash(root);fs.writeFileSync(path.join(root,'src/view.ts'),'new');
 assert.notEqual(sourceHash(root),before);assert.equal(isCurrent(root),false);
});
