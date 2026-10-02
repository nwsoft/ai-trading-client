// Offline arithmetic audit only. Never executes the HTML, contacts a provider,
// authenticates receipts, or treats supplied decisions as ground truth.
const fs = require('node:fs');
const crypto = require('node:crypto');
function audit(rows) {
  if (!Array.isArray(rows) || !rows.length) throw new Error('Expected non-empty records');
  const latency = rows.map(r => r.latency_ms).sort((a,b) => a-b);
  if (latency.some(x => !Number.isFinite(x) || x < 0)) throw new Error('Invalid latency');
  const sum = key => rows.reduce((n,r) => n + r[key], 0);
  const n = rows.length;
  const median = n % 2 ? latency[(n-1)/2] : (latency[n/2-1]+latency[n/2])/2;
  const anomalies = [];
  for (const r of rows) {
    if (Math.abs(r.input_tokens * .042 / 1e6 - r.cost_usd) > 1e-12) anomalies.push(`${r.run_id}: price mismatch`);
    for (const [key,a] of Object.entries(r.answers || {})) {
      const values = Object.values(a.probabilities || {});
      if (values.length && (values.some(v => !Number.isFinite(v) || v<0 || v>1) || Math.abs(values.reduce((x,y)=>x+y,0)-1)>.00001)) anomalies.push(`${r.run_id}/${key}: invalid distribution`);
    }
  }
  return {
    verification: 'supplied-file arithmetic only; no authenticated calls or trading outcomes',
    count:n, input_tokens:sum('input_tokens'), output_tokens:sum('output_tokens'),
    latency_ms:{min:latency[0],median,mean:sum('latency_ms')/n,p95_nearest_rank:latency[Math.ceil(.95*n)-1],max:latency[n-1]},
    cost_usd:sum('cost_usd'), supplied_rounded_cost_krw:sum('cost_krw'),
    monthly_single_stream_10s_30days:{calls:259200,usd:sum('cost_usd')/n*259200,krw_at_report_1330:sum('cost_usd')/n*259200*1330},
    anomalies,
    decisions:rows.map(r=>({run:r.run_id,symbol:r.symbol,latency_ms:r.latency_ms,answers:r.answers})),
  };
}
module.exports = {audit};
if (require.main === module) {
  if (!process.argv[2]) throw new Error('Usage: node scripts/audit_jev_evidence.cjs path.json [report.html]');
  const data = fs.readFileSync(process.argv[2]);
  const result = audit(JSON.parse(data));
  result.json_sha256 = crypto.createHash('sha256').update(data).digest('hex');
  if (process.argv[3]) result.html_sha256 = crypto.createHash('sha256').update(fs.readFileSync(process.argv[3])).digest('hex');
  console.log(JSON.stringify(result,null,2));
}
