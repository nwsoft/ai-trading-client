// Built renderer and synthetic read-only strategy evidence; no external traffic.
const {chromium}=require(process.env.NOAHAI_QA_PLAYWRIGHT||'playwright');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..'),dist=path.join(root,'webui/dist'),out=process.env.NOAHAI_QA_REPORT_DIR||path.join(root,'reports/v3926-strategy-evidence-20261006');
(async()=>{
 fs.mkdirSync(out,{recursive:true});const browser=await chromium.launch({headless:true,channel:'chrome'});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[],writes=[];
  const version={strategy_key:'fixture',version_id:'fixture-v1',version:1,name:'분리 검증 예시',status:'approved',active:false,paper_observing:false,
   rules:{target_scope:'asset:crypto',executable_entry:{all:[{field:'rsi',operator:'lte',value:30}]}},missing_conditions:[],xai:{summary:'합성 검증 자료'},guidance:{},execution_readiness:{ready:true},validation_subject:'custom_entry_logic',
   execution_validation:{mode:'historical_replay',metrics:{validation_source:'binance',validation_interval:'15m',candle_count:500,assessment_status:'evaluated'}},
   validation_lab:{sample:{total:10},performance:{total_net_pnl:5,total_return_percent:5,max_drawdown_percent:2,win_rate:.6,profit_factor:2},out_of_sample_net_pnl:3,walkforward:{pass_rate:.75},minimum_quality_gate:{passed:true},overfit_risk:{flagged:false},
    retrained_evaluation:{status:'candidate_ready_for_paper_review',auto_applied:false,folds:[{training_end_ms:1760000000000,test_start_ms:1760000900000,baseline_test_net_percent:1,candidate_test_net_percent:2,cost_2x_test_net_percent:1.5,passed:true}],proposal:{field:'rsi',original_value:30,candidate_value:33}}}};
  const manualData=JSON.parse(fs.readFileSync(path.join(root,'docs/USER_MANUAL_SECTIONS.json')));
  page.on('pageerror',e=>errors.push(e.message));
  await page.addInitScript(()=>window.noahAI={bootstrap:()=>({gatewayUrl:location.origin,gatewayToken:'fixture',desktop:false})});
  await page.route('**/*',async route=>{
   const req=route.request(),url=new URL(req.url()),ep=url.pathname;
   if(url.origin!=='http://127.0.0.1:4209')return route.abort();
   if(!ep.startsWith('/api/')){const file=path.join(dist,ep==='/'?'index.html':ep);return fs.existsSync(file)&&fs.statSync(file).isFile()?route.fulfill({body:fs.readFileSync(file),contentType:({'.js':'text/javascript','.css':'text/css','.html':'text/html'})[path.extname(file)]||'application/octet-stream'}):route.abort();}
   if(req.method()!=='GET'){writes.push(ep);return route.abort();}
   let data={};
   if(ep.endsWith('/session'))data={authenticated:true,account:'strategy-fixture',user:{id:'fixture',user_grade:'premium'}};
   else if(ep.endsWith('/platform'))data={release_version:JSON.parse(fs.readFileSync(path.join(root,'webui/package.json'))).build.buildVersion};
   else if(ep.endsWith('/features'))data=JSON.parse(fs.readFileSync(path.join(root,'config/web_ui_feature_inventory.json')));
   else if(ep.endsWith('/manual'))data=manualData;
   else if(ep.endsWith('/settings'))data={fields:[],revision:'fixture'};
   else if(ep.endsWith('/runtime/snapshot'))data={status:'attached',enabled_sources:['binance'],running_sources:[],paper_trading:true};
   else if(ep.endsWith('/strategies'))data={strategies:[{scope:'unified',strategy_key:'fixture',versions:[version]}]};
   else if(ep.endsWith('/logs'))data={lines:[]};
   await route.fulfill({contentType:'application/json',body:JSON.stringify(data)});
  });
  await page.goto('http://127.0.0.1:4209');
  await page.getByLabel('블록체인 세부 기능').getByRole('button',{name:'전략 스튜디오',exact:true}).click();
  await page.getByText('검증 근거 보기 · 과거 시세 재생',{exact:true}).click();
  await page.getByText('시간 순서 학습 후보 검증 · 자동 적용 없음',{exact:true}).click();
  await page.getByText('기준선보다 나은 후보 · 새 버전 검토 후 PAPER 검증 필요',{exact:true}).waitFor();
  const evidence=page.locator('.strategy-validation-evidence');
  assert.match(await evidence.innerText(),/기준선 1% \/ 후보 2% \/ 비용 2배 1.5%/);
  assert.match(await evidence.innerText(),/rsi 30 → 33/);
  assert.match(await evidence.innerText(),/LLM 모델 자체를 재학습한 결과가 아닙니다/);
  await evidence.scrollIntoViewIfNeeded();await page.screenshot({path:path.join(out,'evidence.png')});
  version.validation_lab.retrained_evaluation={status:'input_evidence_not_supported',input_sha256:null,replay_calls:0,folds:[],auto_applied:false,live_permission_granted:false};
  await page.reload();
  await page.getByLabel('블록체인 세부 기능').getByRole('button',{name:'전략 스튜디오',exact:true}).click();
  await page.getByText('검증 근거 보기 · 과거 시세 재생',{exact:true}).click();
  await page.getByText('시간 순서 학습 후보 검증 · 자동 적용 없음',{exact:true}).click();
  await page.getByText('규칙·시세 자료에 잘못된 숫자 또는 저장할 수 없는 값이 있어 평가하지 못했습니다 · 입력 확인 후 다시 검증하세요',{exact:true}).waitFor();
  assert.doesNotMatch(await evidence.innerText(),/검토 수치:|rsi 30 → 33|기준선 1% \/ 후보 2%/);
  await evidence.scrollIntoViewIfNeeded();await page.screenshot({path:path.join(out,'invalid-evidence.png')});
  await page.getByText('· UI 3.9.2.8',{exact:true}).waitFor();
  await page.getByRole('button',{name:'메뉴얼',exact:true}).click();
  const manual=page.getByRole('dialog');
  await manual.locator('.manual-tabs button').last().waitFor();
  assert.equal(await manual.locator('.manual-tabs button').count(),11);
  await manual.locator('.manual-quick-links').getByRole('button',{name:'업데이트',exact:true}).click();
  await manual.getByRole('heading',{name:'v3.9.2.8 최신 업데이트 — PAPER 청산 복구·전략 평가 입력 보호',exact:true}).waitFor();
  assert.match(await manual.locator('.manual-content').innerText(),/잘못된 숫자\(NaN·무한대\).*개선 후보를 승인하지 않습니다/);
  assert.equal(await manual.locator('.manual-guide-visual-node').first().locator('small').innerText(),'v3.9.2.8');
  assert.equal(await manual.locator('.manual-guide-visual-node').nth(1).locator('small').innerText(),'PAPER 청산 복구·전략 평가 입력 보호');
  assert.match(await manual.locator('.manual-intro-summary').innerText(),/잘못된 숫자\(NaN·무한대\)/);
  await page.screenshot({path:path.join(out,'dashboard-updates.png')});
  await manual.getByRole('heading',{name:'v3.9.2.8 최신 업데이트 — PAPER 청산 복구·전략 평가 입력 보호',exact:true}).scrollIntoViewIfNeeded();
  await page.screenshot({path:path.join(out,'dashboard-update-details.png')});
  // A later manual must update the cards without another hardcoded UI version.
  manualData.release_version='3.9.2.9';
  manualData.sections.find(section=>section.id==='updates').content=manualData.sections.find(section=>section.id==='updates').content.replaceAll('v3.9.2.8','v3.9.2.9');
  await manual.locator('.manual-close-button').click();
  await page.getByRole('button',{name:'메뉴얼',exact:true}).click();
  await manual.locator('.manual-quick-links').getByRole('button',{name:'업데이트',exact:true}).click();
  await manual.locator('.manual-guide-visual-node').first().getByText('v3.9.2.9',{exact:true}).waitFor();
  await manual.getByRole('heading',{name:'v3.9.2.9 최신 업데이트 — PAPER 청산 복구·전략 평가 입력 보호',exact:true}).waitFor();
  assert.deepEqual(errors,[]);assert.deepEqual(writes,[]);
  const result={result:'PASS',checks:17,errors,writes,fixtures:true,real_accounts:false};
  fs.writeFileSync(path.join(out,'result.json'),JSON.stringify(result,null,2));console.log(JSON.stringify(result));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
