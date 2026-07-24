from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Mapping, Optional

import requests


class RegulatoryDataProvider:
    """SEC/DART 재무 데이터 어댑터.

    SEC는 정책상 식별 가능한 User-Agent가 필요하고, DART는 사용자 API 키가
    필요하다. 누락 시 요청하지 않고 설정 오류를 반환한다.
    """

    SEC_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
    DART_URL = "https://opendart.fss.or.kr/api/fnlttSinglAcntAll.json"

    SEC_FACT_ALIASES: Dict[str, List[str]] = {
        "revenue": ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet"],
        "operating_income": ["OperatingIncomeLoss"],
        "net_income": ["NetIncomeLoss", "ProfitLoss"],
        "assets": ["Assets"],
        "liabilities": ["Liabilities"],
        "equity": ["StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"],
        "cash": ["CashAndCashEquivalentsAtCarryingValue", "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"],
        "debt": ["LongTermDebtAndFinanceLeaseObligationsCurrent", "LongTermDebtCurrent", "LongTermDebtNoncurrent"],
        "operating_cash_flow": ["NetCashProvidedByUsedInOperatingActivities"],
        "capital_expenditure": ["PaymentsToAcquirePropertyPlantAndEquipment"],
        "shares": ["CommonStockSharesOutstanding", "EntityCommonStockSharesOutstanding"],
        "eps": ["EarningsPerShareBasic"],
    }

    DART_ACCOUNT_ALIASES = {
        "매출액": "revenue",
        "영업이익": "operating_income",
        "당기순이익": "net_income",
        "자산총계": "assets",
        "부채총계": "liabilities",
        "자본총계": "equity",
        "현금및현금성자산": "cash",
        "영업활동현금흐름": "operating_cash_flow",
        "기본주당이익": "eps",
    }

    def __init__(self, session: Optional[requests.Session] = None, timeout: float = 12.0):
        self.session = session or requests.Session()
        self.timeout = max(1.0, float(timeout))

    def fetch_sec_companyfacts(self, cik: str | int, user_agent: str) -> Dict[str, Any]:
        if not str(user_agent or "").strip() or "@" not in str(user_agent):
            return {"status": "configuration_required", "error": "SEC user_agent must include contact email"}
        normalized = re.sub(r"\D", "", str(cik)).zfill(10)
        url = self.SEC_URL.format(cik=normalized)
        try:
            response = self.session.get(
                url,
                timeout=self.timeout,
                headers={"User-Agent": user_agent, "Accept-Encoding": "gzip, deflate"},
            )
            response.raise_for_status()
            payload = response.json()
            return {
                "status": "ok",
                "source": "sec_companyfacts",
                "source_url_or_id": url,
                "entity_name": payload.get("entityName"),
                "cik": normalized,
                "periods": self.normalize_sec_companyfacts(payload),
            }
        except Exception as exc:
            return {"status": "error", "error": f"{type(exc).__name__}:{exc}", "periods": []}

    def normalize_sec_companyfacts(self, payload: Mapping[str, Any]) -> List[Dict[str, Any]]:
        us_gaap = ((payload.get("facts") or {}).get("us-gaap") or {})
        periods: Dict[str, Dict[str, Any]] = defaultdict(dict)
        for target, concepts in self.SEC_FACT_ALIASES.items():
            selected_units: List[Dict[str, Any]] = []
            currency = ""
            for concept in concepts:
                fact = us_gaap.get(concept) or {}
                units = fact.get("units") or {}
                for unit_name in ("USD", "USD/shares", "shares"):
                    if units.get(unit_name):
                        selected_units = units[unit_name]
                        currency = "USD" if unit_name.startswith("USD") else ""
                        break
                if selected_units:
                    break
            for unit in selected_units:
                form = str(unit.get("form") or "")
                frame = str(unit.get("frame") or "")
                fiscal_year = unit.get("fy")
                fiscal_period = str(unit.get("fp") or "")
                if form not in {"10-K", "20-F", "40-F"} and not (frame.startswith("CY") and "Q" not in frame):
                    continue
                period = str(fiscal_year or frame.replace("CY", "") or unit.get("end") or "")
                if not period or fiscal_period not in {"", "FY"}:
                    continue
                current = periods[period].get(target)
                filed = str(unit.get("filed") or "")
                if current is None or filed >= str(periods[period].get(f"_{target}_filed") or ""):
                    periods[period][target] = unit.get("val")
                    periods[period][f"_{target}_filed"] = filed
                    periods[period]["currency"] = currency or periods[period].get("currency", "")
                    periods[period]["source"] = "sec_companyfacts"
                    periods[period]["as_of"] = filed
        output = []
        for period, values in sorted(periods.items()):
            cleaned = {key: value for key, value in values.items() if not key.startswith("_")}
            cleaned["period"] = period
            cleaned["is_annual"] = True
            output.append(cleaned)
        return output

    def fetch_dart_financials(
        self,
        corp_code: str,
        business_year: str | int,
        api_key: str,
        report_code: str = "11011",
        fs_div: str = "CFS",
    ) -> Dict[str, Any]:
        if not str(api_key or "").strip():
            return {"status": "configuration_required", "error": "DART API key required", "periods": []}
        try:
            response = self.session.get(
                self.DART_URL,
                params={
                    "crtfc_key": api_key,
                    "corp_code": str(corp_code),
                    "bsns_year": str(business_year),
                    "reprt_code": str(report_code),
                    "fs_div": str(fs_div),
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
            payload = response.json()
            if str(payload.get("status") or "000") != "000":
                return {"status": "error", "error": f"DART {payload.get('status')}: {payload.get('message')}", "periods": []}
            return {
                "status": "ok",
                "source": "opendart",
                "source_url_or_id": self.DART_URL,
                "periods": self.normalize_dart(payload.get("list") or [], str(business_year)),
            }
        except Exception as exc:
            return {"status": "error", "error": f"{type(exc).__name__}:{exc}", "periods": []}

    def normalize_dart(self, rows: Iterable[Mapping[str, Any]], business_year: str) -> List[Dict[str, Any]]:
        period: Dict[str, Any] = {
            "period": str(business_year),
            "currency": "KRW",
            "is_annual": True,
            "source": "opendart",
            "as_of": datetime.now(timezone.utc).isoformat(),
        }
        for row in rows:
            account = str(row.get("account_nm") or "").replace(" ", "")
            target = next(
                (value for alias, value in self.DART_ACCOUNT_ALIASES.items() if alias.replace(" ", "") in account),
                None,
            )
            if not target:
                continue
            amount = row.get("thstrm_amount")
            try:
                period[target] = float(str(amount).replace(",", ""))
            except Exception:
                continue
        return [period]


class CalendarFileProvider:
    """사용자가 권한을 가진 ICS 캘린더를 공통 이벤트로 변환한다."""

    @staticmethod
    def parse_ics(text: str, source: str = "ics") -> List[Dict[str, Any]]:
        lines = [line.strip() for line in str(text or "").replace("\r\n", "\n").split("\n")]
        events: List[Dict[str, Any]] = []
        current: Dict[str, str] = {}
        inside = False
        for line in lines:
            if line == "BEGIN:VEVENT":
                inside = True
                current = {}
                continue
            if line == "END:VEVENT":
                if inside and current.get("SUMMARY") and current.get("DTSTART"):
                    events.append(
                        {
                            "title": current["SUMMARY"],
                            "starts_at": CalendarFileProvider._ics_datetime(current["DTSTART"]),
                            "description": current.get("DESCRIPTION", ""),
                            "event_type": "calendar",
                            "importance": 2,
                            "source": source,
                            "source_url_or_id": current.get("UID", ""),
                        }
                    )
                inside = False
                continue
            if inside and ":" in line:
                key, value = line.split(":", 1)
                current[key.split(";", 1)[0]] = value
        return events

    @staticmethod
    def _ics_datetime(value: str) -> str:
        text = str(value or "")
        formats = ("%Y%m%dT%H%M%SZ", "%Y%m%dT%H%M%S", "%Y%m%d")
        for fmt in formats:
            try:
                dt = datetime.strptime(text, fmt)
                if fmt.endswith("Z"):
                    dt = dt.replace(tzinfo=timezone.utc)
                else:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt.isoformat()
            except Exception:
                continue
        return datetime.now(timezone.utc).isoformat()
