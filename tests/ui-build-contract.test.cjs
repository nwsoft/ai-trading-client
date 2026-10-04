const {test}=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {sourceHash,isCurrent,buildPlugin}=require('../webui/electron/ui-build-contract.cjs');
test('missing and stale renderer cannot masquerade as current engine version',()=>{
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'noah-ui-hash-'));
 fs.mkdirSync(path.join(root,'src'));fs.mkdirSync(path.join(root,'dist'));fs.writeFileSync(path.join(root,'dist/index.html'),'<html></html>');
 fs.writeFileSync(path.join(root,'package.json'),JSON.stringify({build:{buildVersion:'3.9.1.49'}}));
 fs.writeFileSync(path.join(root,'src/view.ts'),'old');assert.equal(isCurrent(root),false);
 const plugin=buildPlugin(root);let asset;
 plugin.generateBundle.call({emitFile:value=>asset=value});
 assert.equal(asset.fileName,'ui-build.json');
 fs.writeFileSync(path.join(root,'dist',asset.fileName),asset.source);assert.equal(isCurrent(root),true);
 const before=sourceHash(root);fs.writeFileSync(path.join(root,'src/view.ts'),'new');
 assert.notEqual(sourceHash(root),before);assert.equal(isCurrent(root),false);
});

test('missing index or referenced JS is not a usable renderer',()=>{
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'noah-ui-files-'));
 fs.mkdirSync(path.join(root,'dist'));fs.writeFileSync(path.join(root,'package.json'),JSON.stringify({build:{buildVersion:'test'}}));
 fs.writeFileSync(path.join(root,'dist/ui-build.json'),JSON.stringify({source_sha256:sourceHash(root)}));
 assert.equal(isCurrent(root),false);
 fs.writeFileSync(path.join(root,'dist/index.html'),'<script src="/assets/main.js"></script>');assert.equal(isCurrent(root),false);
 fs.mkdirSync(path.join(root,'dist/assets'));fs.writeFileSync(path.join(root,'dist/assets/main.js'),'ready');assert.equal(isCurrent(root),true);
 fs.rmSync(root,{recursive:true,force:true});
});
test('a source change during compilation cannot certify mixed output',()=>{
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'noah-ui-race-'));
 fs.writeFileSync(path.join(root,'package.json'),JSON.stringify({build:{buildVersion:'test'}}));
 const plugin=buildPlugin(root);plugin.buildStart();fs.writeFileSync(path.join(root,'index.html'),'changed');
 assert.throws(()=>plugin.generateBundle.call({emitFile:()=>assert.fail('must not certify')}),/source changed/);
 fs.rmSync(root,{recursive:true,force:true});
});
