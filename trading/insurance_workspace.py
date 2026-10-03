"""Local, user-confirmed insurance facts. No recommendations or network access.

The vault password is independent of the NoahAI password. Only authenticated
gateway callers may use this service. Documents are untrusted data, never prompts.
"""
from __future__ import annotations

import base64
import copy
import hashlib
import io
import json
import multiprocessing
import os
import re
import secrets
import threading
import time
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from filelock import FileLock, Timeout

SCHEMA = 1
MAX_FILE = 20 * 1024 * 1024
MAX_VAULT = 20 * 1024 * 1024  # aggregate originals, not 20 MB per contract
MAX_BACKUP = 42 * 1024 * 1024
RULE_VERSION = "insurance-facts-1"
NOTICE = "사용자 확인 자료의 사실 정리이며 보험사 검증·가입·해지 권유·보험금 지급 확정이 아닙니다. 외부 전송과 가계부 자동 기록은 하지 않습니다."


class InsuranceError(ValueError):
    """Only stable non-sensitive codes may cross the gateway."""


def _now():
    return datetime.now(timezone.utc).isoformat()


def _text(value, limit=500):
    if not isinstance(value, str) or len(value) > limit:
        raise InsuranceError("insurance_invalid_field")
    return value.strip()


def _money(value):
    if value is None or value == "":
        return None
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise InsuranceError("insurance_invalid_amount")
    try:
        n = Decimal(str(value))
        if not n.is_finite() or n < 0 or n > Decimal("1000000000000") or n.as_tuple().exponent < -2:
            raise InvalidOperation
        return str(n)
    except (InvalidOperation, ValueError):
        raise InsuranceError("insurance_invalid_amount") from None


def _day(value):
    if not value:
        return None
    try:
        return date.fromisoformat(_text(value, 10)).isoformat()
    except ValueError:
        raise InsuranceError("insurance_invalid_date") from None


def _extract_document(raw, connection):
    """Spawned process; bounded wall time in parent, no files/URLs/LLM calls."""
    try:
        if raw.startswith(b"%PDF-"):
            import logging
            logging.getLogger("pypdf").disabled = True
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(raw), strict=True)
            if reader.is_encrypted:
                raise InsuranceError("insurance_encrypted_pdf")
            if not 1 <= len(reader.pages) <= 100:
                raise InsuranceError("insurance_page_limit")
            pages = []
            total = 0
            for page in reader.pages:
                contents = page.get_contents()
                if contents is not None and len(contents.get_data()) > 8 * 1024 * 1024:
                    raise InsuranceError("insurance_document_complexity")
                text = page.extract_text() or ""
                total += len(text)
                if total > 500_000:
                    raise InsuranceError("insurance_text_limit")
                pages.append(text)
            result = {"mime": "application/pdf", "pages": pages,
                      "extraction": "local_text" if any(p.strip() for p in pages) else "manual_required"}
        elif raw.startswith(b"\x89PNG\r\n\x1a\n") or raw.startswith(b"\xff\xd8\xff"):
            import warnings
            from PIL import Image
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                im = Image.open(io.BytesIO(raw))
                if im.format not in {"PNG", "JPEG"} or im.width * im.height > 20_000_000:
                    raise InsuranceError("insurance_image_limit")
                mime = "image/png" if im.format == "PNG" else "image/jpeg"
                im.verify()
            result = {"mime": mime, "pages": [""], "extraction": "manual_required"}
        else:
            raise InsuranceError("insurance_unsupported_format")
        connection.send({"result": result})
    except InsuranceError as exc:
        connection.send({"error": str(exc)})
    except Exception:
        connection.send({"error": "insurance_document_unreadable"})
    finally:
        connection.close()


class InsuranceWorkspace:
    def __init__(self, data_dir: Path, account: str):
        self.owner = hashlib.sha256(str(account).encode()).hexdigest()
        self.directory = Path(data_dir) / "insurance_private" / self.owner
        self.path = self.directory / "vault.enc"
        self._mutex = threading.RLock()
        self._cipher = None
        self._salt = None
        self._data = None
        self._last_use = 0.0
        self._job = None
        self._cancel = threading.Event()
        self._disk_digest = None
        self._expiry_timer = None
        self._expires_at = 0.0

    def _require(self):
        if self._cipher and time.monotonic() >= self._expires_at:
            self.lock()
        if self._cipher is None:
            raise InsuranceError("insurance_vault_locked")
        self._last_use = time.monotonic()

    def _arm_timeout(self):
        if self._expiry_timer:
            self._expiry_timer.cancel()
        self._expires_at = time.monotonic() + 900
        def expire():
            with self._mutex:
                if time.monotonic() >= self._expires_at:
                    self.lock()
        self._expiry_timer = threading.Timer(900, expire)
        self._expiry_timer.daemon = True
        self._expiry_timer.start()

    @staticmethod
    def _key(password, salt):
        if not isinstance(password, str) or not 12 <= len(password) <= 256:
            raise InsuranceError("insurance_password_length")
        return Fernet(base64.urlsafe_b64encode(hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 600_000)))

    def _decode(self, raw, password):
        try:
            if not 26 <= len(raw) <= MAX_BACKUP or not raw.startswith(b"NOAHINS1\n"):
                raise InsuranceError("insurance_backup_invalid")
            salt = raw[9:25]
            cipher = self._key(password, salt)
            data = json.loads(cipher.decrypt(raw[25:]))
            if data.get("schema") != SCHEMA or data.get("owner") != self.owner:
                raise InsuranceError("insurance_backup_account_or_version")
            if not isinstance(data.get("policies"), dict) or not isinstance(data.get("documents"), dict):
                raise InsuranceError("insurance_backup_invalid")
            return salt, cipher, data
        except (InvalidToken, UnicodeError, json.JSONDecodeError, TypeError, AttributeError):
            raise InsuranceError("insurance_password_or_file_invalid") from None

    def unlock(self, password):
        with self._mutex:
            if self._job and self._job["state"] == "extracting":
                raise InsuranceError("insurance_job_busy")
            if self.path.exists():
                if self.path.stat().st_size > MAX_BACKUP:
                    raise InsuranceError("insurance_backup_invalid")
                raw = self.path.read_bytes()
                salt, cipher, data = self._decode(raw, password)
                self._disk_digest = hashlib.sha256(raw).digest()
            else:
                salt = secrets.token_bytes(16)
                cipher = self._key(password, salt)
                data = {"schema": SCHEMA, "owner": self.owner, "policies": {}, "documents": {}, "analyses": []}
                self._disk_digest = None
            self._salt, self._cipher, self._data = salt, cipher, data
            self._last_use = time.monotonic()
            if not self.path.exists():
                self._persist(data)
            self._arm_timeout()
            return self.snapshot()

    def lock(self):
        with self._mutex:
            self._cancel.set()
            self._cipher = self._salt = self._data = None
            self._disk_digest = None
            if self._expiry_timer:
                self._expiry_timer.cancel()
                self._expiry_timer = None
        return {"state": "locked"}

    def _persist(self, data):
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        try:
            with FileLock(str(self.directory / "write.lock"), timeout=2):
                self._persist_locked(data)
        except Timeout:
            raise InsuranceError("insurance_storage_busy") from None

    def _persist_locked(self, data):
        # Optimistic disk concurrency protects against a second app / restore.
        actual = hashlib.sha256(self.path.read_bytes()).digest() if self.path.exists() else None
        if actual != self._disk_digest:
            raise InsuranceError("insurance_vault_changed_unlock_again")
        raw = b"NOAHINS1\n" + self._salt + self._cipher.encrypt(json.dumps(data, ensure_ascii=False, allow_nan=False).encode())
        if len(raw) > MAX_BACKUP:
            raise InsuranceError("insurance_storage_limit")
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        tmp = self.directory / (secrets.token_hex(12) + ".tmp")
        try:
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(tmp, self.path)
        finally:
            tmp.unlink(missing_ok=True)
        self._data = data
        self._disk_digest = hashlib.sha256(raw).digest()

    def snapshot(self):
        with self._mutex:
            try:
                self._require()
            except InsuranceError:
                return {"schema_version": SCHEMA, "state": "locked", "exists": self.path.exists(), "notice": NOTICE}
            policies = list(self._data["policies"].values())
            return copy.deepcopy({"schema_version": SCHEMA, "state": "unlocked", "notice": NOTICE,
                "policies": policies, "documents": [{k: v for k, v in d.items() if k != "content"}
                    for d in self._data["documents"].values()], "summary": self._summary(policies),
                "job": self._job, "analyses": self._data["analyses"][-20:]})

    @staticmethod
    def _summary(policies):
        totals, missing, attention, period_review = {}, 0, [], 0
        active = [p for p in policies if p["confirmed"] and p["kind"] == "policy" and p["status"] == "active"]
        today = date.today().isoformat()
        for p in active:
            uncertain_period = (p["start"] and p["start"] > today) or (p["end"] and p["end"] < today) or (p["payment_end"] and p["payment_end"] < today)
            if uncertain_period:
                period_review += 1
                attention.append(f"{p['product']}: 보장/납입 기간과 유지 상태를 재확인하세요. 현재 납입 소계에서 보류했습니다.")
                continue
            if p["renewal_date"] and (date.fromisoformat(p["renewal_date"]) - date.today()).days <= 30:
                attention.append(f"{p['product']}: 갱신 확인일 {p['renewal_date']} · 새 보험료·보장을 확인하세요.")
            if p["end"] and (date.fromisoformat(p["end"]) - date.today()).days <= 30:
                attention.append(f"{p['product']}: 만기일 {p['end']} · 납입 종료와 보장 종료를 구분하세요.")
            monthly = p["monthly_premium"]
            if monthly is None:
                missing += 1
            else:
                totals[p["currency"]] = totals.get(p["currency"], Decimal(0)) + Decimal(monthly)
        return {"confirmed_contracts": len(active), "unconfirmed_contracts": sum(not p["confirmed"] for p in policies),
            "unknown_premiums": missing, "known_monthly_subtotals": {k: str(v) for k, v in totals.items()},
            "period_review_count": period_review, "attention": attention,
            "complete": bool(active) and missing == 0 and period_review == 0, "ledger_written": False, "cash_asset_added": False}

    def summary(self):
        # Dashboard reads never wait for encryption/extraction to finish.
        if not self._mutex.acquire(blocking=False):
            return {"state": "busy", "ledger_written": False}
        try:
            try:
                self._require()
            except InsuranceError:
                return {"state": "locked", "ledger_written": False}
            return {"state": "unlocked", **self._summary(list(self._data["policies"].values()))}
        finally:
            self._mutex.release()

    def _evidence(self, rows):
        if not isinstance(rows, list) or len(rows) > 20:
            raise InsuranceError("insurance_invalid_evidence")
        result = []
        for row in rows:
            if not isinstance(row, dict) or set(row) - {"document_id", "page", "quote"}:
                raise InsuranceError("insurance_invalid_evidence")
            doc = self._data["documents"].get(row.get("document_id"))
            page = row.get("page")
            quote = _text(row.get("quote", ""), 2000)
            if not doc or type(page) is not int or not 1 <= page <= len(doc["pages"]) or not quote:
                raise InsuranceError("insurance_invalid_evidence")
            extracted = doc["pages"][page - 1]
            if extracted.strip() and quote not in extracted:
                raise InsuranceError("insurance_quote_not_found")
            result.append({"document_id": doc["id"], "page": page, "quote": quote,
                           "basis": "text_match" if extracted.strip() else "user_transcription"})
        return result

    def save_policy(self, fields, policy_id=None, expected_revision=None):
        with self._mutex:
            self._require()
            allowed = {"provider", "product", "subject_alias", "kind", "status", "currency", "premium", "cycle",
                       "start", "end", "payment_end", "renewal_date", "coverages", "evidence", "confirmed", "rights_confirmed"}
            if not isinstance(fields, dict) or set(fields) - allowed or fields.get("rights_confirmed") is not True:
                raise InsuranceError("insurance_rights_required")
            old = self._data["policies"].get(policy_id) if policy_id else None
            if policy_id and (not old or expected_revision != old["revision"]):
                raise InsuranceError("insurance_revision_conflict")
            if not old and len(self._data["policies"]) >= 100:
                raise InsuranceError("insurance_storage_limit")
            p = {k: _text(fields.get(k, ""), 160) for k in ("provider", "product", "subject_alias")}
            if not p["product"]:
                raise InsuranceError("insurance_product_required")
            enums = {"kind": {"policy", "quote"}, "status": {"active", "expired", "cancelled", "lapsed", "unknown"},
                     "currency": {"KRW", "USD", "EUR", "JPY"}, "cycle": {"monthly", "quarterly", "annual", "unknown"}}
            for key, options in enums.items():
                if fields.get(key) not in options:
                    raise InsuranceError("insurance_invalid_field")
                p[key] = fields[key]
            p["premium"] = _money(fields.get("premium"))
            divisor = {"monthly": 1, "quarterly": 3, "annual": 12}.get(p["cycle"])
            p["monthly_premium"] = str((Decimal(p["premium"]) / divisor).quantize(Decimal(".01"), rounding=ROUND_HALF_UP)) if p["premium"] is not None and divisor else None
            for key in ("start", "end", "payment_end", "renewal_date"):
                p[key] = _day(fields.get(key))
            if p["start"] and p["end"] and p["start"] > p["end"]:
                raise InsuranceError("insurance_invalid_date")
            p["evidence"] = self._evidence(fields.get("evidence", []))
            coverages = fields.get("coverages", [])
            if not isinstance(coverages, list) or len(coverages) > 60:
                raise InsuranceError("insurance_invalid_field")
            p["coverages"] = []
            for c in coverages:
                if not isinstance(c, dict) or set(c) - {"name", "benefit_kind", "amount", "conditions", "exclusions", "waiting", "reduction", "deductible", "renewal", "evidence"}:
                    raise InsuranceError("insurance_invalid_field")
                row = {k: _text(c.get(k, ""), 2000) for k in ("name", "conditions", "exclusions", "waiting", "reduction", "deductible")}
                if not row["name"] or c.get("benefit_kind") not in {"fixed", "indemnity", "unknown"} or c.get("renewal") not in {"yes", "no", "unknown"}:
                    raise InsuranceError("insurance_invalid_field")
                row.update(benefit_kind=c["benefit_kind"], renewal=c["renewal"], amount=_money(c.get("amount")), evidence=self._evidence(c.get("evidence", [])))
                p["coverages"].append(row)
            p.update(id=policy_id or secrets.token_hex(16), revision=(old["revision"] + 1 if old else 1),
                     confirmed=fields.get("confirmed") is True, updated_at=_now(), basis="user_confirmed" if fields.get("confirmed") is True else "draft")
            data = copy.deepcopy(self._data)
            data["policies"][p["id"]] = p
            for a in data["analyses"]:
                if p["id"] in a["versions"]:
                    a["state"] = "needs_reanalysis"
            self._persist(data)
            return self.snapshot()

    def delete(self, kind, item_id, confirmed):
        with self._mutex:
            self._require()
            if confirmed is not True or kind not in {"policies", "documents"} or item_id not in self._data[kind]:
                raise InsuranceError("insurance_delete_confirmation_required")
            data = copy.deepcopy(self._data)
            del data[kind][item_id]
            affected = {item_id} if kind == "policies" else set()
            if kind == "documents":
                for p in data["policies"].values():
                    refs = p["evidence"] + [e for c in p["coverages"] for e in c["evidence"]]
                    if any(e["document_id"] == item_id for e in refs):
                        p["confirmed"] = False
                        p["basis"] = "source_deleted"
                        p["revision"] += 1
                        affected.add(p["id"])
                        p["evidence"] = [e for e in p["evidence"] if e["document_id"] != item_id]
                        for c in p["coverages"]:
                            c["evidence"] = [e for e in c["evidence"] if e["document_id"] != item_id]
            # Explicit deletion also removes historical analysis text that contained the deleted facts.
            data["analyses"] = [a for a in data["analyses"] if not affected.intersection(a["versions"])]
            self._persist(data)
            if kind == "documents" and self._job and self._job.get("document_id") == item_id:
                self._job = None
            return self.snapshot()

    def import_document(self, content, rights_confirmed):
        with self._mutex:
            self._require()
            if rights_confirmed is not True:
                raise InsuranceError("insurance_rights_required")
            if self._job and self._job["state"] == "extracting":
                raise InsuranceError("insurance_job_busy")
            if not isinstance(content, str) or len(content) > (MAX_FILE + 2) // 3 * 4:
                raise InsuranceError("insurance_file_limit")
            try:
                raw = base64.b64decode(content, validate=True)
            except (ValueError, TypeError):
                raise InsuranceError("insurance_unsupported_format") from None
            if not raw or len(raw) > MAX_FILE:
                raise InsuranceError("insurance_file_limit")
            digest = hashlib.sha256(raw).hexdigest()
            for d in self._data["documents"].values():
                if d["hash"] == digest:
                    return {"state": "already_registered", "document_id": d["id"]}
            if len(self._data["documents"]) >= 5 or sum(d["bytes"] for d in self._data["documents"].values()) + len(raw) > MAX_VAULT:
                raise InsuranceError("insurance_storage_limit")
            self._cancel = threading.Event()
            self._job = {"id": secrets.token_hex(16), "state": "extracting", "started_at": _now()}
            thread = threading.Thread(target=self._run_import, args=(raw, digest, self._job["id"], self._cancel), daemon=True)
            thread.start()
            return copy.deepcopy(self._job)

    def _run_import(self, raw, digest, job_id, cancelled):
        ctx = multiprocessing.get_context("spawn")
        receive, send = ctx.Pipe(duplex=False)
        process = ctx.Process(target=_extract_document, args=(raw, send), daemon=True)
        result, error = None, "insurance_document_unreadable"
        try:
            process.start()
            send.close()
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline and not cancelled.is_set():
                import psutil
                if process.is_alive() and psutil.Process(process.pid).memory_info().rss > 256 * 1024 * 1024:
                    error = "insurance_document_complexity"
                    break
                if receive.poll(.1):
                    response = receive.recv()
                    result, error = response.get("result"), response.get("error")
                    break
                if not process.is_alive():
                    break
            else:
                error = "insurance_job_cancelled" if cancelled.is_set() else "insurance_extraction_timeout"
        except Exception:
            error = "insurance_document_unreadable"
        finally:
            if process.pid is not None:
                if process.is_alive():
                    process.terminate()
                process.join(timeout=2)
                if process.is_alive():
                    process.kill()
                    process.join(timeout=1)
            receive.close()
            send.close()
        with self._mutex:
            if not self._job or self._job["id"] != job_id:
                return
            if cancelled.is_set() or self._cipher is None:
                self._job.update(state="cancelled", error="insurance_job_cancelled")
            elif result:
                try:
                    data = copy.deepcopy(self._data)
                    doc = {"id": job_id, "hash": digest, "bytes": len(raw), "registered_at": _now(),
                           "extractor_version": RULE_VERSION, "content": base64.b64encode(raw).decode(), **result}
                    data["documents"][job_id] = doc
                    self._persist(data)
                    self._job.update(state="needs_confirmation", document_id=job_id)
                except Exception:
                    self._job.update(state="failed", error="insurance_save_failed")
            else:
                self._job.update(state="failed", error=error)

    def cancel(self):
        with self._mutex:
            self._require()
            self._cancel.set()
            return {"state": "cancellation_requested"}

    def document(self, document_id):
        with self._mutex:
            self._require()
            d = self._data["documents"].get(document_id)
            if not d:
                raise InsuranceError("insurance_source_missing")
            return {"mime": d["mime"], "content": d["content"], "pages": d["pages"]}

    def suggest_fields(self, document_id):
        """Conservative local hints; conflict/missing stays unfilled, no auto-save."""
        with self._mutex:
            self._require()
            doc = self._data["documents"].get(document_id)
            if not doc:
                raise InsuranceError("insurance_source_missing")
            candidates = {"product": [], "provider": [], "premium": []}
            for number, page in enumerate(doc["pages"], 1):
                for key, pattern in (("product", r"(?:상품명|보험상품명)\s*[:：]\s*([^\n\r]{1,160})"),
                                     ("provider", r"(?:보험사|보험회사)\s*[:：]\s*([^\n\r]{1,160})"),
                                     ("premium", r"(?:월\s*보험료|월\s*납입\s*보험료)\s*[:：]?\s*((?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d{1,2})?)\s*(만|천)?\s*원")):
                    for m in re.finditer(pattern, page):
                        value = m.group(1).strip()
                        if key == "premium":
                            try:
                                value = _money(str(Decimal(value.replace(",", "")) * {"만": 10000, "천": 1000, None: 1}[m.group(2)]))
                            except InsuranceError:
                                continue
                        candidates[key].append({"value": value, "evidence": {"document_id": document_id, "page": number, "quote": m.group(0)}})
                        if len(candidates[key]) >= 100:
                            break
            fields, evidence, conflicts = {}, [], []
            for key, items in candidates.items():
                unique = {i["value"] for i in items}
                if len(unique) == 1:
                    fields[key] = items[0]["value"]
                    evidence.append(items[0]["evidence"])
                elif len(unique) > 1:
                    conflicts.append(key)
            if "premium" in fields:
                fields.update(cycle="monthly", currency="KRW")
            return {"fields": fields, "evidence": evidence, "conflicts": conflicts, "state": "needs_confirmation",
                    "notice": "명시된 상품명·보험사·월 보험료만 찾은 로컬 초안입니다. 상충값은 채우지 않았습니다. 조건·기간·단위·현재 계약 적용 여부를 직접 확인하세요. 자동 저장·승인 없음."}

    def compare(self, ids):
        with self._mutex:
            self._require()
            if not isinstance(ids, list) or not 1 <= len(ids) <= 2 or len(set(ids)) != len(ids):
                raise InsuranceError("insurance_select_contracts")
            policies = [self._data["policies"].get(i) for i in ids]
            if any(not p or not p["confirmed"] for p in policies):
                raise InsuranceError("insurance_confirmation_required")
            questions = ["가입 당시 약관·특약과 현재 등록 자료가 일치하나요?", "면책·감액 기간, 자기부담, 제외 조건과 갱신 보험료를 보험사에 확인하세요."]
            facts = []
            for p in policies:
                facts.append({"product": p["product"], "status": p["status"], "kind": p["kind"], "currency": p["currency"],
                              "monthly_premium": p["monthly_premium"], "coverages": copy.deepcopy(p["coverages"]), "evidence": p["evidence"]})
                if not p["evidence"]:
                    questions.append(f"{p['product']}: 계약 근거 문서를 연결해 주세요. 수동 입력은 보험사 검증값이 아닙니다.")
                for c in p["coverages"]:
                    if not c["conditions"] or not c["exclusions"] or not c["evidence"]:
                        questions.append(f"{p['product']} / {c['name']}: 지급 조건·제외·근거를 추가 확인하세요.")
            difference = None
            overlap = []
            if len(policies) == 2:
                a, b = policies
                if a["currency"] == b["currency"] and a["monthly_premium"] is not None and b["monthly_premium"] is not None:
                    difference = {"amount": str(Decimal(b["monthly_premium"]) - Decimal(a["monthly_premium"])), "currency": a["currency"], "meaning": "두 번째 - 첫 번째 월 환산 보험료. 절감액이나 동등 보장을 뜻하지 않음"}
                for ca in a["coverages"]:
                    for cb in b["coverages"]:
                        if ca["name"].strip().casefold() == cb["name"].strip().casefold():
                            overlap.append({"name": ca["name"], "same_subject": bool(a["subject_alias"] and a["subject_alias"] == b["subject_alias"]), "explanation": "명칭이 같은 등록 항목입니다. 동일 보장·중복 지급을 뜻하지 않습니다. 실손은 비례보상 여부, 정액은 각 계약 지급 조건을 확인하세요. 중복만으로 해지를 권하지 않습니다."})
                questions.append("교체 시 신규 인수 여부·면책 재시작·보장 축소·해약환급 손실을 확인하세요. 유지도 선택지입니다.")
            analysis = {"id": secrets.token_hex(16), "state": "analysis_ready", "rule_version": RULE_VERSION, "at": _now(),
                        "versions": {p["id"]: p["revision"] for p in policies}, "facts": facts, "premium_difference": difference,
                        "possible_overlap": overlap, "questions": questions, "notice": NOTICE,
                        "missing_coverage_meaning": "등록 자료에서 확인하지 못한 보장은 미가입이나 보장 0을 뜻하지 않습니다."}
            data = copy.deepcopy(self._data)
            data["analyses"] = (data["analyses"] + [analysis])[-20:]
            self._persist(data)
            return copy.deepcopy(analysis)

    def report(self, analysis_id):
        with self._mutex:
            self._require()
            a = next((a for a in self._data["analyses"] if a["id"] == analysis_id), None)
            if not a or a["state"] != "analysis_ready":
                raise InsuranceError("insurance_reanalysis_required")
            lines = ["NoahAI 내 보험 상담 준비 · 사용자 확인 자료", a["at"], NOTICE]
            lines.append("비교 자료 버전: " + " / ".join(f"{k[:8]} v{v}" for k, v in a["versions"].items()))
            labels = {"active": "유지 중", "expired": "만기", "cancelled": "해지", "lapsed": "실효", "unknown": "미확인",
                      "fixed": "정액", "indemnity": "실손", "yes": "갱신형", "no": "비갱신형"}
            for fact in a["facts"]:
                lines.append(f"{fact['product']} · 월 환산 {fact['monthly_premium'] if fact['monthly_premium'] is not None else '미확인'} {fact['currency']} · {labels[fact['status']]}")
                for c in fact["coverages"]:
                    lines.append(f"보장: {c['name']} / {labels[c['benefit_kind']]} / 가입금액 {c['amount'] if c['amount'] is not None else '미확인'} {fact['currency']} (지급 확정액 아님)")
                    for key, title in (("conditions", "지급 조건"), ("exclusions", "보장 제외"), ("waiting", "면책"), ("reduction", "감액"), ("deductible", "자기부담"), ("renewal", "갱신")):
                        value = labels[c[key]] if key == "renewal" else c[key]
                        lines.append(f"  {title}: {value or '미확인'}")
                    lines.extend(f"  근거: 문서 {e['document_id'][:8]} / {e['page']}쪽 ({e['basis']})" for e in c["evidence"])
            if a["premium_difference"]:
                d = a["premium_difference"]
                lines.append(f"월 환산 보험료 차이: {d['amount']} {d['currency']} · {d['meaning']}")
            lines += ["확인할 질문", *a["questions"], a["missing_coverage_meaning"]]
            text = "\n".join(lines)
            text = re.sub(r"\b\d{6}[- ]?[1-8]\d{6}\b|\b01[016789][- .]?\d{3,4}[- .]?\d{4}\b|[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[가림]", text)
            return {"text": text, "export_requires_review": True, "notice": "자동 가림은 완전하지 않습니다. 건강·연락처·계약번호 등을 직접 확인하고 필요한 내용만 저장하세요. 외부 전송 없음."}

    def backup(self):
        with self._mutex:
            self._require()
            return {"content": base64.b64encode(self.path.read_bytes()).decode(), "encrypted": True}

    def restore(self, content, password, confirmed):
        with self._mutex:
            if confirmed is not True or self.path.exists():
                raise InsuranceError("insurance_restore_empty_vault_only")
            if not isinstance(content, str) or len(content) > MAX_BACKUP * 4 // 3 + 4:
                raise InsuranceError("insurance_backup_invalid")
            try:
                raw = base64.b64decode(content, validate=True)
            except ValueError:
                raise InsuranceError("insurance_backup_invalid") from None
            salt, cipher, data = self._decode(raw, password)
            self._salt, self._cipher, self._data = salt, cipher, data
            self._disk_digest = None
            self._last_use = time.monotonic()
            self._persist(data)
            self._arm_timeout()
            return self.snapshot()

    def finance_plan(self, operation="list", scenario=None, plan_id=None, reminder_date=None):
        """Personal scenarios use the existing account-bound encrypted vault."""
        from trading.finance_product_intelligence import ProductCatalog, compare_scenario
        with self._mutex:
            self._require()
            data = copy.deepcopy(self._data)
            plans = data.setdefault("finance_plans", {})
            if operation == "save":
                if len(plans) >= 50 or len(json.dumps(scenario, ensure_ascii=False, allow_nan=False)) > 100000:
                    raise InsuranceError("finance_plan_limit")
                try:
                    catalog = ProductCatalog(self.directory.parents[1] / "finance_product_catalog.sqlite3").snapshot()
                    result = compare_scenario(scenario, catalog)
                except ValueError:
                    raise InsuranceError("finance_invalid_scenario") from None
                plan_id = secrets.token_hex(12)
                plans[plan_id] = {"id": plan_id, "saved_at": _now(), "scenario": scenario, "result": result}
                self._persist(data)
            elif operation == "delete":
                if plan_id not in plans:
                    raise InsuranceError("finance_plan_not_found")
                del plans[plan_id]
                self._persist(data)
            elif operation == "reminder":
                if plan_id not in plans:
                    raise InsuranceError("finance_plan_not_found")
                try:
                    if reminder_date:date.fromisoformat(reminder_date)
                except (ValueError,TypeError):
                    raise InsuranceError("finance_reminder_date_invalid") from None
                plans[plan_id]['reminder_date']=reminder_date or None
                self._persist(data)
            elif operation != "list":
                raise InsuranceError("finance_invalid_operation")
            from trading.finance_followup import review_saved_plans
            catalog=ProductCatalog(self.directory.parents[1] / "finance_product_catalog.sqlite3").snapshot()
            output=copy.deepcopy(list(plans.values()))
            return {"plans": output, "reviews":review_saved_plans(output,catalog), "state": "unlocked"}

    def finance_handoff(self, operation="list", **kwargs):
        from trading.finance_handoff import FinanceHandoff
        from trading.finance_connections import FinanceConnectionError
        try:
            return FinanceHandoff(self).dispatch(operation, **kwargs)
        except FinanceConnectionError as exc:
            raise InsuranceError(str(exc)) from None
        except (ValueError, KeyError, TypeError):
            raise InsuranceError("finance_handoff_invalid_or_unavailable") from None

    def dispatch(self, action, payload):
        routes = {"finance_handoff": self.finance_handoff, "finance_plan": self.finance_plan, "unlock": self.unlock, "lock": self.lock, "summary": self.summary, "save_policy": self.save_policy,
                  "delete": self.delete, "import_document": self.import_document, "cancel": self.cancel,
                  "document": self.document, "suggest_fields": self.suggest_fields, "compare": self.compare, "report": self.report,
                  "backup": self.backup, "restore": self.restore}
        if action not in routes or not isinstance(payload, dict):
            raise InsuranceError("insurance_invalid_action")
        try:
            return routes[action](**payload)
        except TypeError:
            raise InsuranceError("insurance_invalid_field") from None
