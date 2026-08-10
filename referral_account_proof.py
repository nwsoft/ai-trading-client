"""거래소 계정 UID를 사용자 PC에서 조회하고 daltrading에 귀속 확인을 요청한다.

API Secret과 Passphrase는 거래소 서명에만 사용하며 함수 반환값, 로그, 서버 요청에
절대 포함하지 않는다.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from urllib.parse import urlencode

import requests


@dataclass(frozen=True)
class ReferralAccountProof:
    exchange: str
    exchange_uid: str
    source: str
    inviter_id: str = ""
    affiliate_id: str = ""
    channel_code: str = ""
    observed_at: str = ""

    def server_payload(self) -> Dict[str, Any]:
        data = asdict(self)
        exchange_uid = data.pop("exchange_uid")
        exchange = data.pop("exchange")
        return {"exchange": exchange, "exchange_uid": exchange_uid, "evidence": data}


def _observed_at() -> str:
    return datetime.now(timezone.utc).isoformat()


def _require_success(response: requests.Response, exchange: str) -> Dict[str, Any]:
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError(f"{exchange} 계정 응답 형식이 올바르지 않습니다.")
    return payload


def fetch_bybit_referral_proof(
    api_key: str, secret_key: str, base_url: str = "https://api.bybit.com"
) -> ReferralAccountProof:
    timestamp = str(int(time.time() * 1000))
    recv_window = "5000"
    signature = hmac.new(
        secret_key.encode("utf-8"),
        f"{timestamp}{api_key}{recv_window}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    payload = _require_success(
        requests.get(
            f"{base_url.rstrip('/')}/v5/user/query-api",
            headers={
                "X-BAPI-API-KEY": api_key,
                "X-BAPI-TIMESTAMP": timestamp,
                "X-BAPI-RECV-WINDOW": recv_window,
                "X-BAPI-SIGN": signature,
            },
            timeout=8,
        ),
        "Bybit",
    )
    if int(payload.get("retCode", -1)) != 0 or not isinstance(payload.get("result"), dict):
        raise RuntimeError("Bybit 계정 UID 조회 권한을 확인하세요.")
    result = payload["result"]
    uid = str(result.get("userID") or "").strip()
    if not uid:
        raise RuntimeError("Bybit 계정 UID를 확인하지 못했습니다.")
    return ReferralAccountProof(
        "bybit", uid, "bybit_query_api",
        inviter_id=str(result.get("inviterID") or "").strip(),
        affiliate_id=str(result.get("affiliateID") or "").strip(),
        observed_at=_observed_at(),
    )


def fetch_bitget_referral_proof(
    api_key: str,
    secret_key: str,
    passphrase: str,
    base_url: str = "https://api.bitget.com",
) -> ReferralAccountProof:
    path = "/api/v2/spot/account/info"
    timestamp = str(int(time.time() * 1000))
    signature = base64.b64encode(
        hmac.new(
            secret_key.encode("utf-8"),
            f"{timestamp}GET{path}".encode("utf-8"),
            hashlib.sha256,
        ).digest()
    ).decode("ascii")
    payload = _require_success(
        requests.get(
            f"{base_url.rstrip('/')}{path}",
            headers={
                "ACCESS-KEY": api_key,
                "ACCESS-SIGN": signature,
                "ACCESS-TIMESTAMP": timestamp,
                "ACCESS-PASSPHRASE": passphrase,
                "locale": "en-US",
            },
            timeout=8,
        ),
        "Bitget",
    )
    data = payload.get("data")
    if str(payload.get("code") or "") != "00000" or not isinstance(data, dict):
        raise RuntimeError("Bitget 계정 UID 조회 권한을 확인하세요.")
    uid = str(data.get("userId") or "").strip()
    if not uid:
        raise RuntimeError("Bitget 계정 UID를 확인하지 못했습니다.")
    return ReferralAccountProof(
        "bitget", uid, "bitget_account_info",
        inviter_id=str(data.get("inviterId") or "").strip(),
        channel_code=str(data.get("channelCode") or "").strip(),
        observed_at=_observed_at(),
    )


def fetch_okx_referral_proof(
    api_key: str,
    secret_key: str,
    passphrase: str,
    base_url: str = "https://www.okx.com",
) -> ReferralAccountProof:
    path = "/api/v5/account/config"
    timestamp = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    signature = base64.b64encode(
        hmac.new(
            secret_key.encode("utf-8"),
            f"{timestamp}GET{path}".encode("utf-8"),
            hashlib.sha256,
        ).digest()
    ).decode("ascii")
    payload = _require_success(
        requests.get(
            f"{base_url.rstrip('/')}{path}",
            headers={
                "OK-ACCESS-KEY": api_key,
                "OK-ACCESS-SIGN": signature,
                "OK-ACCESS-TIMESTAMP": timestamp,
                "OK-ACCESS-PASSPHRASE": passphrase,
            },
            timeout=8,
        ),
        "OKX",
    )
    records = payload.get("data")
    data = records[0] if isinstance(records, list) and records and isinstance(records[0], dict) else {}
    uid = str(data.get("uid") or "").strip()
    if str(payload.get("code") or "") != "0" or not uid:
        raise RuntimeError("OKX 계정 UID 조회 권한을 확인하세요.")
    return ReferralAccountProof("okx", uid, "okx_account_config", observed_at=_observed_at())


def _load_access_token() -> str:
    from path_utils import get_token_file_path

    with open(get_token_file_path(), "r", encoding="utf-8") as token_file:
        token_data = json.load(token_file)
    token = str(token_data.get("access_token") or "").strip()
    if not token:
        raise RuntimeError("로그인 토큰이 없어 레퍼럴 자동 확인을 요청할 수 없습니다.")
    return token


def submit_referral_proof(
    proof: ReferralAccountProof,
    server_url: str = "https://daltrading.net",
    access_token: Optional[str] = None,
) -> Dict[str, Any]:
    """Secret 없는 UID/관계 결과만 전송하고 서버의 Affiliate 판정을 받는다."""
    response = requests.post(
        f"{server_url.rstrip('/')}/auth/referral-attribution/auto-verify",
        json=proof.server_payload(),
        headers={"Authorization": f"Bearer {access_token or _load_access_token()}"},
        timeout=12,
    )
    if response.status_code >= 400:
        try:
            detail = str(response.json().get("detail") or "")
        except Exception:
            detail = ""
        raise RuntimeError(detail or f"레퍼럴 자동 확인 요청 실패({response.status_code})")
    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError("레퍼럴 자동 확인 응답 형식이 올바르지 않습니다.")
    return payload


def verify_and_submit(
    exchange: str,
    api_key: str,
    secret_key: str,
    passphrase: str = "",
) -> Dict[str, Any]:
    normalized = str(exchange or "").strip().lower()
    if normalized == "bybit":
        proof = fetch_bybit_referral_proof(api_key, secret_key)
    elif normalized == "bitget":
        proof = fetch_bitget_referral_proof(api_key, secret_key, passphrase)
    elif normalized == "okx":
        proof = fetch_okx_referral_proof(api_key, secret_key, passphrase)
    else:
        raise RuntimeError("이 거래소는 Affiliate 자동 확인 권한 준비 후 지원됩니다.")
    return submit_referral_proof(proof)
