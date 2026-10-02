import { useEffect, useState } from "react";
import type { GatewayClient } from "../api";
import { t } from "../i18n";
import "./InsuranceWorkspace.css";

type Row = Record<string, any>;
const labels: Record<string, string> = {
  active: "유지 중", expired: "만기", cancelled: "해지", lapsed: "실효", unknown: "미확인",
  policy: "기존 계약", quote: "비교용 견적", monthly: "매월", quarterly: "분기", annual: "매년",
  fixed: "정액", indemnity: "실손", yes: "갱신형", no: "비갱신형", draft: "확인 전",
  user_confirmed: "사용자 확인", source_deleted: "원문 삭제 · 재확인 필요",
  extracting: "원문 추출 중", needs_confirmation: "원문 대조 필요", failed: "처리 실패", cancelled_job: "작업 취소",
  analysis_ready: "사용자 확인 자료 분석", needs_reanalysis: "자료 변경 · 다시 비교 필요",
  local_text: "로컬 텍스트 추출", manual_required: "수동 확인 필요 · 자동 OCR 미사용",
};
const errors: Record<string, string> = {
  insurance_vault_locked: "저장소가 잠겼습니다. 보험 자료 전용 비밀번호로 다시 여세요.",
  insurance_password_length: "보험 자료 전용 비밀번호는 12~256자로 입력하세요. NoahAI 로그인 비밀번호와 별개입니다.",
  insurance_password_or_file_invalid: "비밀번호가 다르거나 파일이 손상되었습니다. 원본을 보존하고 비밀번호를 확인하세요.",
  insurance_backup_account_or_version: "다른 계정 또는 지원하지 않는 저장소 버전의 백업입니다.",
  insurance_restore_empty_vault_only: "복원은 보험 저장소가 없는 동일 계정의 새 설치에서만 가능합니다. 현재 자료를 자동 덮어쓰지 않습니다.",
  insurance_invalid_amount: "금액은 단위 없이 0 이상의 숫자(소수 두 자리까지)로 입력하세요. 미확인은 비워 두세요.",
  insurance_invalid_date: "날짜와 보장 시작·종료 순서를 확인하세요.",
  insurance_rights_required: "본인 또는 제공 권한이 있는 자료임을 확인해 주세요.",
  insurance_confirmation_required: "비교 전에 선택한 계약의 입력값과 원문을 대조하고 확인 저장하세요.",
  insurance_revision_conflict: "다른 화면에서 자료가 변경되었습니다. 다시 읽고 수정하세요.",
  insurance_vault_changed_unlock_again: "다른 앱에서 저장소가 변경되었습니다. 잠근 뒤 다시 열어 최신 자료를 확인하세요.",
  insurance_encrypted_pdf: "암호 PDF는 여기서 해제하지 않습니다. 비밀정보 없는 사본을 직접 준비하거나 수동 입력하세요.",
  insurance_unsupported_format: "PDF·PNG·JPEG만 지원합니다. 확장자가 아닌 실제 파일 형식을 확인하세요.",
  insurance_document_unreadable: "문서가 손상되었거나 읽을 수 없습니다. 원본을 확인하거나 수동 입력하세요.",
  insurance_storage_limit: "저장 한도입니다. 문서는 최대 5개·원본 합계 20MB, 계약 100개까지입니다. 백업 후 불필요한 자료를 정리하세요.",
  insurance_file_limit: "빈 파일 또는 20MB 초과 파일입니다. 자료를 확인해 주세요.",
  insurance_page_limit: "PDF는 1~100쪽만 지원합니다. 필요한 약관 페이지를 직접 분리하고 누락 여부를 확인하세요.",
  insurance_job_busy: "이 계정에서 문서 한 개를 처리하고 있습니다. 완료를 기다리거나 취소하세요.",
  insurance_extraction_timeout: "30초 안에 문서를 읽지 못했습니다. 수동 입력하거나 단순한 사본으로 다시 시도하세요.",
  insurance_invalid_evidence: "근거 문서·쪽 번호·인용문을 확인하세요.",
  insurance_quote_not_found: "인용문이 선택한 페이지의 추출 텍스트와 일치하지 않습니다. 해당 페이지에서 직접 복사해 주세요.",
  insurance_reanalysis_required: "입력 자료가 바뀌었습니다. 다시 비교한 뒤 보고서를 만드세요.",
  insurance_save_failed: "문서 저장을 완료하지 못했습니다. 저장소를 다시 열고 저장 공간을 확인하세요.",
  insurance_document_complexity: "문서 처리량 한도를 초과했습니다. 필요한 페이지의 단순한 사본을 준비하거나 수동 입력하세요.",
  insurance_text_limit: "추출 텍스트가 50만 자를 초과했습니다. 조용히 잘라 비교하지 않으므로 자료 범위를 직접 나누어 주세요.",
  insurance_request_limit: "요청 크기 한도를 초과했습니다. 문서·백업 크기를 확인하세요.",
  insurance_storage_busy: "다른 앱에서 보험 자료를 저장 중입니다. 잠시 뒤 다시 시도하세요.",
  insurance_job_cancelled: "문서 처리를 취소했습니다. 계약이 자동 생성되거나 승인되지 않았습니다.",
  insurance_source_missing: "근거 원문이 없습니다. 자료를 다시 등록하고 계약을 재확인하세요.",
  insurance_invalid_field: "입력 형식이나 지원 범위를 확인하세요. 최신 화면에서 다시 입력해 주세요.",
  insurance_backup_invalid: "지원하는 보험 백업 형식이 아닙니다. 암호화 백업 원본을 확인하세요.",
  insurance_account_changed: "로그인 계정이 변경되어 이전 요청을 표시하지 않았습니다. 현재 계정에서 보험 저장소를 다시 열어 주세요.",
};
const blank = (): Row => ({ provider: "", product: "", subject_alias: "", kind: "policy", status: "unknown", currency: "KRW", premium: "", cycle: "unknown", start: "", end: "", payment_end: "", renewal_date: "", evidence: [], coverages: [], confirmed: false, rights_confirmed: false });
const coverage = (): Row => ({ name: "", benefit_kind: "unknown", amount: "", conditions: "", exclusions: "", waiting: "", reduction: "", deductible: "", renewal: "unknown", evidence: [] });
function label(value: string) { return t(labels[value] ?? value); }
function message(error: unknown) {
  const raw = error instanceof Error ? error.message : String(error);
  const code = Object.keys(errors).find((code) => raw.includes(code));
  return code ? t(errors[code]) : t("보험 작업을 완료하지 못했습니다. 입력값·저장 공간·앱 버전을 확인하세요.");
}
function download(content: BlobPart, type: string, name: string) {
  const url = URL.createObjectURL(new Blob([content], { type }));
  const a = document.createElement("a"); a.href = url; a.download = name; a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
async function encode(file: File) {
  return new Promise<string>((resolve, reject) => {
    const reader = new FileReader(); reader.onload = () => resolve(String(reader.result).split(",")[1]);
    reader.onerror = () => reject(new Error("insurance_document_unreadable")); reader.readAsDataURL(file);
  });
}
function decode(encoded: string) { return Uint8Array.from(atob(encoded), (c) => c.charCodeAt(0)); }

function Evidence({ value, documents, onChange }: { value: Row[]; documents: Row[]; onChange: (value: Row[]) => void }) {
  return <fieldset><legend>{t("근거 연결 · 없으면 수동 입력으로 표시")}</legend>
    {value.map((e, index) => { const change = (key: string, val: unknown) => onChange(value.map((row, i) => ({ document_id: row.document_id, page: row.page, quote: row.quote, ...(i === index ? { [key]: val } : {}) }))); return <div className="insurance-evidence" key={index}>
      <label>{t("근거 문서")}<select value={e.document_id} onChange={(ev) => change("document_id", ev.target.value)}><option value="">{t("문서 선택")}</option>{documents.map((d, i) => <option key={d.id} value={d.id}>{t("문서")} {i + 1} · {d.hash.slice(0, 8)}</option>)}</select></label>
      <label>{t("근거 쪽 번호")}<input type="number" min="1" max="100" value={e.page} onChange={(ev) => change("page", Number(ev.target.value))} /></label><label className="insurance-wide">{t("원문 인용 · 텍스트는 그대로 복사, 이미지는 직접 대조")}<textarea maxLength={2000} value={e.quote} onChange={(ev) => change("quote", ev.target.value)} /></label><button type="button" onClick={() => onChange(value.filter((_, i) => i !== index))}>{t("근거 연결 제거")}</button>
    </div>; })}<button type="button" disabled={!documents.length || value.length >= 20} onClick={() => onChange([...value.map(({ document_id, page, quote }) => ({ document_id, page, quote })), { document_id: documents[0]?.id, page: 1, quote: "" }])}>{t("근거 연결 추가")}</button>
  </fieldset>;
}

export function InsuranceBudgetSummary({ client }: { client: GatewayClient }) {
  const [summary, setSummary] = useState<Row | null>(null);
  const [error, setError] = useState("");
  return <section className="panel insurance-budget-link"><h3>{t("보험료 계획 · 실제 지출과 별도")}</h3><p>{t("생활금융 → 금융상품 → 내 보험 이해·비교에서 확인한 계약만 집계합니다. 보험 가입금액을 자산에 더하거나 가계부에 자동 기록하지 않습니다.")}</p><button type="button" onClick={() => client.insuranceWorkspace?.("summary").then((r) => { setSummary(r); setError(""); }).catch((e) => setError(message(e)))}>{t("보험료 계획 확인")}</button>{summary && (summary.state === "unlocked" ? <p>{t("확인된 월 환산 소계")}: {Object.entries(summary.known_monthly_subtotals ?? {}).map(([k, v]) => `${v} ${k}`).join(" · ") || t("계산할 자료 없음")} · {t("보험료 미확인")}: {summary.unknown_premiums}{t("건")}. {t("실제 납부액·예산 잔액과 다릅니다.")}</p> : <p>{t("보험 저장소가 잠겼거나 처리 중입니다. 내 보험 이해·비교에서 열고 다시 확인하세요.")}</p>)}{error && <p role="alert">{error}</p>}</section>;
}

export function InsuranceWorkspace({ client }: { client: GatewayClient }) {
  const [data, setData] = useState<Row>({ state: "locked" });
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [draft, setDraft] = useState<Row>(blank);
  const [editing, setEditing] = useState<Row | null>(null);
  const [selected, setSelected] = useState<string[]>([]);
  const [analysis, setAnalysis] = useState<Row | null>(null);
  const [report, setReport] = useState<Row | null>(null);
  const [exportReviewed, setExportReviewed] = useState(false);
  const [source, setSource] = useState<Row | null>(null);
  const [page, setPage] = useState(1);
  const [uploadRights, setUploadRights] = useState(false);
  const [notice, setNotice] = useState("");
  const [editorOpen, setEditorOpen] = useState(false);
  const request = (action?: string, payload?: Record<string, unknown>) => {
    if (!client.insuranceWorkspace) return Promise.reject(new Error("insurance_upgrade_required"));
    return client.insuranceWorkspace(action, payload);
  };
  const clearPrivateView = () => { setDraft(blank()); setEditing(null); setSelected([]); setAnalysis(null); setReport(null); setSource(null); setExportReviewed(false); setNotice(""); setUploadRights(false); setEditorOpen(false); };
  const refresh = async () => { const next = await request(); setData(next); if (next.state !== "unlocked") clearPrivateView(); };
  useEffect(() => { let active = true; request().then((r) => { if (active) setData(r); }).catch((e) => { if (active) setError(message(e)); }); return () => { active = false; }; }, [client]);
  useEffect(() => {
    if (data.job?.state !== "extracting") return;
    const timer = setInterval(() => { void refresh().catch((e) => setError(message(e))); }, 1000);
    return () => clearInterval(timer);
  }, [data.job?.state, client]);
  useEffect(() => {
    if (data.state !== "unlocked") return;
    const timer = setTimeout(() => {
      // Clear sensitive rendering even when the local gateway is unavailable.
      clearPrivateView(); setData({ state: "locked", exists: true });
      void request("lock").catch((e) => setError(message(e)));
    }, 15 * 60 * 1000);
    return () => clearTimeout(timer);
  }, [data.state, client]);
  async function run(work: () => Promise<void>) {
    setBusy(true); setError("");
    try { await work(); } catch (e) { setError(message(e)); } finally { setBusy(false); }
  }
  const change = (key: string, value: unknown) => setDraft((p) => ({ ...p, [key]: value, confirmed: key === "confirmed" ? value : false }));
  const documents: Row[] = data.documents ?? [];
  const policies: Row[] = data.policies ?? [];
  const jobBusy = data.job?.state === "extracting";
  const summary = data.summary ?? {};
  const invalidate = () => { setAnalysis(null); setReport(null); setExportReviewed(false); setNotice(""); };
  const edit = (p: Row) => { const d = blank(); Object.keys(d).forEach((key) => { if (key in p) d[key] = p[key] ?? ""; }); const refs = (rows: Row[]) => rows.map(({ document_id, page, quote }) => ({ document_id, page, quote })); d.evidence = refs(d.evidence); d.coverages = d.coverages.map((c: Row) => ({ ...c, evidence: refs(c.evidence) })); d.confirmed = false; d.rights_confirmed = false; setDraft(d); setEditing(p); setEditorOpen(true); invalidate(); };
  const select = (key: string, options: string[]) => <label>{t(({ kind: "자료 구분", status: "계약 상태", currency: "통화", cycle: "납입 주기" } as Record<string, string>)[key])}<select aria-label={t(({ kind: "자료 구분", status: "계약 상태", currency: "통화", cycle: "납입 주기" } as Record<string, string>)[key])} value={draft[key]} onChange={(e) => change(key, e.target.value)}>{options.map((o) => <option key={o} value={o}>{label(o)}</option>)}</select></label>;

  return <article className="panel insurance-workspace" aria-label={t("내 보험 이해·비교")}>
    <header className="panel-heading"><div><span className="eyebrow">LOCAL INSURANCE FACTS</span><h2>{t("내 보험 이해·비교")}</h2></div>{data.state === "unlocked" && <button type="button" disabled={busy} onClick={() => run(async () => { await request("lock"); clearPrivateView(); setData({ state: "locked", exists: true }); })}>{t("보험 저장소 잠그기")}</button>}</header>
    <p>{t("내 자료의 보장과 보험료를 이해하고 상담 질문을 준비합니다. 전 보험사 추천·가입·해지·보험금 지급 판정 서비스가 아닙니다.")}</p>
    <p className="workspace-copy">{t("문서·건강정보는 외부 AI나 상담사에게 전송하지 않습니다. 계정별 암호화 저장, 15분 후 잠금. 비밀번호 분실 시 복구할 수 없으므로 암호화 백업과 비밀번호를 안전하게 별도 보관하세요.")}</p>
    {error && <p className="inline-notice error-text" role="alert">{error}</p>}
    {notice && data.state === "unlocked" && <p className="inline-notice" role="status">{notice}</p>}
    {data.state !== "unlocked" ? <section className="insurance-unlock">
      <label>{t("보험 자료 전용 비밀번호 · 12자 이상")}<input type="password" autoComplete="off" value={password} maxLength={256} onChange={(e) => setPassword(e.target.value)} /></label>
      <button type="button" disabled={busy || password.length < 12} onClick={() => run(async () => { try { setData(await request("unlock", { password })); } finally { setPassword(""); } })}>{t(data.exists ? "보험 저장소 열기" : "암호화 보험 저장소 만들기")}</button>
      {!data.exists && <label className="insurance-file">{t("동일 계정 암호화 백업 복원 · 백업 비밀번호 입력 후 선택")}<input type="file" accept=".noahinsurance" disabled={busy || password.length < 12} onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; if (f) void run(async () => { if (f.size > 42 * 1024 * 1024) throw new Error("insurance_file_limit"); try { setData(await request("restore", { content: await encode(f), password, confirmed: true })); } finally { setPassword(""); } }); }} /></label>}
    </section> : <>
      <section className="insurance-summary" aria-label={t("확인된 보험 요약")}><div><span>{t("유지 중 확인 계약")}</span><strong>{summary.confirmed_contracts ?? 0}{t("건의 계약")}</strong></div><div><span>{t("확인된 월 환산 소계 · 납부 실적 아님")}</span><strong>{Object.entries(summary.known_monthly_subtotals ?? {}).map(([k, v]) => `${v} ${k}`).join(" · ") || t("계산할 자료 없음")}</strong></div><div><span>{t("보험료 미확인 / 확인 전 계약")}</span><strong>{summary.unknown_premiums ?? 0} / {summary.unconfirmed_contracts ?? 0}</strong></div></section>
      <p>{t("미확인은 0원이 아닙니다. 견적·해지·실효·확인 전 계약은 위 소계에서 제외합니다. 실제 가계부와 중복 기록하지 않으며 가입금액을 자산에 더하지 않습니다.")}</p>
      {!!summary.attention?.length && <div role="status"><strong>{t("기간·갱신 확인 필요")}</strong><ul>{summary.attention.map((item: string, i: number) => <li key={i}>{item}</li>)}</ul></div>}
      <details><summary>{t("1. 원문 등록·대조 · PDF / PNG / JPEG")}</summary>
        <p>{t("파일당 20MB·PDF 100쪽, 원본 합계 20MB·5개, 한 번에 1개 처리합니다. 텍스트 PDF를 로컬 추출하며 스캔·이미지는 수동 확인합니다. 자동 추출값은 계약에 자동 반영되지 않습니다.")}</p>
        <label className="insurance-check"><input type="checkbox" checked={uploadRights} onChange={(e) => setUploadRights(e.target.checked)} />{t("본인 또는 제공·처리 권한이 있는 자료입니다. 주민번호·불필요한 건강정보는 사전에 가렸습니다.")}</label>
        <input aria-label={t("보험 원문 선택")} type="file" accept=".pdf,.png,.jpg,.jpeg" disabled={busy || jobBusy || !uploadRights} onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; if (f) void run(async () => { if (f.size > 20 * 1024 * 1024) throw new Error("insurance_file_limit"); await request("import_document", { content: await encode(f), rights_confirmed: uploadRights }); await refresh(); }); }} />
        {data.job && <p role="status">{label(data.job.state === "cancelled" ? "cancelled_job" : data.job.state)}{data.job.error && ` · ${message(data.job.error)}`}{jobBusy && <button type="button" onClick={() => run(async () => { await request("cancel"); })}>{t("추출 취소")}</button>}</p>}
        <div className="insurance-documents">{documents.map((d, index) => <div key={d.id}><span>{t("문서")} {index + 1} · {d.pages.length}{t("쪽")} · {label(d.extraction)}</span><button type="button" disabled={busy} onClick={() => run(async () => { setSource({ id: d.id, ...await request("document", { document_id: d.id }) }); setPage(1); })}>{t("원문 대조")}</button><button type="button" disabled={busy || jobBusy} onClick={() => { if (window.confirm(t("원문을 삭제하면 연결된 계약 확인과 분석이 무효화됩니다. 삭제할까요? 백업 사본은 별도로 삭제해야 합니다."))) void run(async () => { await request("delete", { kind: "documents", item_id: d.id, confirmed: true }); setSource(null); invalidate(); await refresh(); }); }}>{t("원문 삭제")}</button></div>)}</div>
      </details>
      {source && <button type="button" disabled={busy} onClick={() => {
        if ((draft.product || draft.coverages.length) && !window.confirm(t("현재 입력 중인 초안을 원문 기반 새 초안으로 바꿀까요? 저장된 계약은 바꾸지 않습니다."))) return;
        void run(async () => { const r = await request("suggest_fields", { document_id: source.id }); setDraft({ ...blank(), ...r.fields, evidence: r.evidence }); setEditing(null); setEditorOpen(true); invalidate(); setNotice(`${r.notice}${r.conflicts.length ? ` · 상충으로 비워 둔 항목: ${r.conflicts.join(", ")}` : ""}`); });
      }}>{t("이 원문에서 입력 초안 만들기 · 자동 승인 안 함")}</button>}
      <div className={`insurance-editor${source ? " with-source" : ""}`}>
        {source && <aside className="insurance-source" aria-label={t("원문 대조")}><h3>{t("원문 대조")}</h3><button type="button" onClick={() => setSource(null)}>{t("대조 닫기")}</button><label>{t("페이지")}<input type="number" min="1" max={source.pages.length} value={page} onChange={(e) => setPage(Math.max(1, Math.min(source.pages.length, Number(e.target.value) || 1)))} /></label>{source.mime.startsWith("image/") ? <img alt={t("등록한 보험 원문 · 수동 대조용")} src={`data:${source.mime};base64,${source.content}`} /> : <><pre>{source.pages[page - 1] || t("이 페이지는 추출 텍스트가 없습니다. 원본을 열어 수동 대조하세요.")}</pre><button type="button" onClick={() => { if (window.confirm(t("원본 PDF를 암호화하지 않고 저장합니다. 민감정보와 문서 내 링크를 확인하고 신뢰하는 뷰어로만 여세요. 계속할까요?"))) download(decode(source.content), "application/pdf", "insurance-source.pdf"); }}>{t("원본 PDF 로컬 저장·확인")}</button><small>{t("추출 텍스트는 표·배치를 보존하지 않을 수 있습니다. 원본 PDF와 대조하세요.")}</small></>}</aside>}
        <details open={editorOpen} onToggle={(e) => setEditorOpen(e.currentTarget.open)}><summary>{t("2. 계약·보장 입력 및 확인")}</summary><p>{t("미확인 금액·날짜·조건은 비워 두세요. 금액은 선택 통화 단위의 숫자이며 만원·천원을 자동 추정하지 않습니다.")}</p>
          {editing && <p>{t("수정 중")}: {editing.product} · v{editing.revision}</p>}
          <div className="insurance-fields">{[["provider", "보험사"], ["product", "상품·계약 이름"], ["subject_alias", "피보험자 별칭 · 실명/주민번호 불필요"]].map(([key, title]) => <label key={key}>{t(title)}<input value={draft[key]} maxLength={160} onChange={(e) => change(key, e.target.value)} /></label>)}
          {select("kind", ["policy", "quote"])}{select("status", ["unknown", "active", "expired", "cancelled", "lapsed"])}{select("currency", ["KRW", "USD", "EUR", "JPY"])}
          <label>{t("회차 보험료 · 미확인은 빈칸")}<input type="number" min="0" step="0.01" value={draft.premium} onChange={(e) => change("premium", e.target.value)} /></label>{select("cycle", ["unknown", "monthly", "quarterly", "annual"])}
          {[["start", "보장 시작일"], ["end", "보장 만기일"], ["payment_end", "납입 종료일"], ["renewal_date", "다음 갱신 확인일"]].map(([key, title]) => <label key={key}>{t(title)}<input type="date" value={draft[key]} onChange={(e) => change(key, e.target.value)} /></label>)}</div>
          <Evidence value={draft.evidence} documents={documents} onChange={(value) => change("evidence", value)} />
          <h4>{t("보장 항목 · 조건/제외를 함께 확인")}</h4><p className="workspace-copy">{t("정액은 약정 조건 충족 시 정한 금액, 실손은 실제 손해와 한도·자기부담·다른 계약을 함께 확인합니다. 명칭만으로 지급 여부나 불필요한 중복을 판단하지 않습니다.")}</p>
          {draft.coverages.map((c: Row, index: number) => { const update = (key: string, value: unknown) => change("coverages", draft.coverages.map((row: Row, i: number) => i === index ? { ...row, [key]: value } : row)); return <fieldset key={index} className="insurance-coverage"><legend>{t("보장")} {index + 1}</legend><div className="insurance-fields"><label>{t("원문 보장명")}<input value={c.name} maxLength={2000} onChange={(e) => update("name", e.target.value)} /></label><label>{t("지급 방식")}<select aria-label={t("지급 방식")} value={c.benefit_kind} onChange={(e) => update("benefit_kind", e.target.value)}>{["unknown", "fixed", "indemnity"].map((o) => <option value={o} key={o}>{label(o)}</option>)}</select></label><label>{t("가입금액 · 지급 확정액 아님")}<input type="number" min="0" step="0.01" value={c.amount ?? ""} onChange={(e) => update("amount", e.target.value)} /></label><label>{t("갱신")}<select aria-label={t("갱신")} value={c.renewal} onChange={(e) => update("renewal", e.target.value)}>{["unknown", "yes", "no"].map((o) => <option value={o} key={o}>{label(o)}</option>)}</select></label>
          {[["conditions", "지급 조건"], ["exclusions", "보장 제외"], ["waiting", "면책 기간"], ["reduction", "감액 기간/비율"], ["deductible", "자기부담"]].map(([key, title]) => <label key={key}>{t(title)}<textarea maxLength={2000} value={c[key]} onChange={(e) => update(key, e.target.value)} /></label>)}</div><Evidence value={c.evidence} documents={documents} onChange={(value) => update("evidence", value)} /><button type="button" onClick={() => change("coverages", draft.coverages.filter((_: Row, i: number) => i !== index))}>{t("이 보장 입력 제거")}</button></fieldset>; })}
          <button type="button" disabled={draft.coverages.length >= 60} onClick={() => change("coverages", [...draft.coverages, coverage()])}>{t("보장 항목 추가")}</button>
          <label className="insurance-check"><input type="checkbox" checked={draft.rights_confirmed} onChange={(e) => change("rights_confirmed", e.target.checked)} />{t("본인 또는 제공 권한이 있는 자료를 입력했습니다.")}</label>
          <label className="insurance-check"><input type="checkbox" checked={draft.confirmed} onChange={(e) => change("confirmed", e.target.checked)} />{t("원문과 입력값·단위·기간을 대조했습니다. 사용자 확인은 보험사 검증이나 지급 보장이 아닙니다.")}</label>
          <div className="command-row"><button type="button" disabled={busy || !draft.product.trim() || !draft.rights_confirmed} onClick={() => run(async () => { await request("save_policy", { fields: draft, policy_id: editing?.id ?? null, expected_revision: editing?.revision ?? null }); setDraft(blank()); setEditing(null); setEditorOpen(false); invalidate(); await refresh(); })}>{t(draft.confirmed ? "확인한 계약 저장" : "확인 전 초안 저장")}</button><button type="button" onClick={() => { setDraft(blank()); setEditing(null); }}>{t("새 입력 / 수정 취소")}</button></div>
        </details>
      </div>
      <section><h3>{t("3. 내 계약과 선택지 · 최대 2개 사실 비교")}</h3>{!policies.length && <p>{t("등록한 계약이 없습니다. 원문 대조 후 직접 입력하세요. 예시 상품은 내 계약으로 추가하지 않습니다.")}</p>}
      <div className="insurance-policy-list">{policies.map((p) => <article key={p.id}><label className="insurance-check"><input type="checkbox" checked={selected.includes(p.id)} onChange={(e) => { setSelected((s) => e.target.checked ? [...s, p.id].slice(-2) : s.filter((id) => id !== p.id)); invalidate(); }} /><strong>{p.product}</strong> · v{p.revision}</label><p>{label(p.kind)} · {label(p.status)} · {label(p.basis)} · {t("월 환산")} {p.monthly_premium ?? t("미확인")} {p.currency}</p><p>{t("만기")}: {p.end || t("미확인")} · {t("납입 종료")}: {p.payment_end || t("미확인")} · {t("갱신 확인")}: {p.renewal_date || t("미확인")}</p><div className="command-row"><button type="button" onClick={() => edit(p)}>{t("수정·근거 확인")}</button><button type="button" disabled={busy} onClick={() => { if (window.confirm(t("이 계약과 연결된 비교 기록을 삭제할까요? 원문과 백업 사본은 별도로 삭제합니다."))) void run(async () => { await request("delete", { kind: "policies", item_id: p.id, confirmed: true }); setSelected([]); setDraft(blank()); setEditing(null); setEditorOpen(false); invalidate(); await refresh(); }); }}>{t("계약 삭제")}</button></div></article>)}</div>
      <button type="button" disabled={busy || !selected.length} onClick={() => run(async () => { setAnalysis(await request("compare", { ids: selected })); setReport(null); setExportReviewed(false); await refresh(); })}>{t(selected.length === 2 ? "선택한 두 자료 비교" : "선택한 계약 점검")}</button></section>
      {analysis && <section className="insurance-analysis"><h3>{t("확인된 사실 → 쉬운 설명 → 확인할 질문")}</h3><p>{analysis.notice}</p>{analysis.premium_difference && <p>{t("월 환산 보험료 차이")}: {analysis.premium_difference.amount} {analysis.premium_difference.currency} · {analysis.premium_difference.meaning}</p>}
      <div className="insurance-comparison">{analysis.facts.map((f: Row, i: number) => <article key={i}><h4>{f.product}</h4>{f.coverages.length ? f.coverages.map((c: Row, j: number) => <section key={j}><strong>{c.name}</strong><p>{label(c.benefit_kind)} · {c.amount ?? t("미확인")} {f.currency} · {label(c.renewal)}</p><dl>{[["conditions", "지급 조건"], ["exclusions", "보장 제외"], ["waiting", "면책"], ["reduction", "감액"], ["deductible", "자기부담"]].map(([key, title]) => <div key={key}><dt>{t(title)}</dt><dd>{c[key] || t("미확인")}</dd></div>)}</dl>{c.evidence.map((e: Row, n: number) => <p key={n}>{t("근거")}: {e.document_id.slice(0, 8)} / {e.page}{t("쪽")} · {e.basis === "text_match" ? t("원문 텍스트 일치") : t("사용자 전사")}</p>)}</section>) : <p>{t("보장 항목 미등록 · 보장 없음이 아님")}</p>}</article>)}</div>
      {analysis.possible_overlap.map((o: Row, i: number) => <p key={i}>{o.name}: {o.explanation} {!o.same_subject && t("피보험자 동일 여부도 확인 필요합니다.")}</p>)}<ul>{analysis.questions.map((q: string, i: number) => <li key={i}>{q}</li>)}</ul><p>{analysis.missing_coverage_meaning}</p><button type="button" disabled={busy} onClick={() => run(async () => { setReport(await request("report", { analysis_id: analysis.id })); setExportReviewed(false); })}>{t("상담 질문지 미리보기")}</button></section>}
      {report && <section><h3>{t("로컬 보고서 · 전송하지 않음")}</h3><p>{report.notice}</p><textarea className="insurance-report" aria-label={t("내보낼 보고서 내용")} value={report.text} onChange={(e) => { setReport({ ...report, text: e.target.value }); setExportReviewed(false); }} /><label className="insurance-check"><input type="checkbox" checked={exportReviewed} onChange={(e) => setExportReviewed(e.target.checked)} />{t("내용과 민감정보를 직접 검토했습니다. 아래 저장은 암호화되지 않은 TXT입니다.")}</label><button type="button" disabled={!exportReviewed} onClick={() => download(report.text, "text/plain;charset=utf-8", "noah-insurance-questions.txt")}>{t("검토한 질문지 TXT 저장")}</button></section>}
      <details><summary>{t("이전 분석 · 자료 버전과 재확인 상태")}</summary>{(data.analyses ?? []).map((a: Row) => <p key={a.id}>{a.at} · {label(a.state)} · {Object.values(a.versions).map((v) => `v${v}`).join(" / ")}</p>)}</details>
      <div className="command-row"><button type="button" disabled={busy || jobBusy} onClick={() => run(async () => { const r = await request("backup"); download(decode(r.content), "application/octet-stream", "noah-insurance.noahinsurance"); })}>{t("암호화 백업 저장")}</button><button type="button" disabled={busy} onClick={() => run(refresh)}>{t("다시 읽기")}</button></div>
      <p className="workspace-copy">{t("백업은 보험 저장소가 없는 동일 계정의 새 설치에서 복원합니다. 기존 계약·원문을 삭제해도 별도로 저장한 백업·보고서는 지워지지 않습니다. 보험사/상담원 자동 연결은 제공하지 않습니다.")}</p>
    </>}
  </article>;
}
