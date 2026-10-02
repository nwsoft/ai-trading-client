const test=require('node:test');
const assert=require('node:assert/strict');
const {audit}=require('./audit_jev_evidence.cjs');
const row=ms=>({run_id:'fixture',symbol:'TEST',latency_ms:ms,input_tokens:100,output_tokens:10,cost_usd:.0000042,cost_krw:.0056,answers:{action:{probabilities:{A:.4,B:.6}}}});
test('median is recomputed and receipt claims are never certified',()=>{
 const r=audit([row(100),row(200),row(300),row(600)]);
 assert.equal(r.latency_ms.median,250);
 assert.equal(r.latency_ms.p95_nearest_rank,600);
 assert.match(r.verification,/no authenticated/);
 assert.deepEqual(r.anomalies,[]);
});
test('invalid input and cost/distribution discrepancies are visible',()=>{
 assert.throws(()=>audit([]));assert.throws(()=>audit([row(NaN)]));
 const r=row(100);r.cost_usd=1;r.answers.action.probabilities.A=.8;
 assert.equal(audit([r]).anomalies.length,2);
});
