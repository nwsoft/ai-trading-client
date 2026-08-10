from unittest.mock import Mock, patch

from referral_account_proof import (
    ReferralAccountProof,
    fetch_bitget_referral_proof,
    fetch_bybit_referral_proof,
    fetch_okx_referral_proof,
    submit_referral_proof,
)


def _response(payload, status_code=200):
    response = Mock()
    response.status_code = status_code
    response.json.return_value = payload
    response.raise_for_status.return_value = None
    return response


def test_bybit_local_proof_contains_uid_relation_but_no_credentials() -> None:
    with patch(
        "referral_account_proof.requests.get",
        return_value=_response(
            {"retCode": 0, "result": {"userID": "12345", "inviterID": "77", "affiliateID": "88"}}
        ),
    ):
        proof = fetch_bybit_referral_proof("public-key", "private-secret")
    payload = proof.server_payload()
    assert payload["exchange_uid"] == "12345"
    assert payload["evidence"]["inviter_id"] == "77"
    assert "secret" not in repr(payload).lower()
    assert "public-key" not in repr(payload)


def test_bitget_and_okx_local_uid_parsing() -> None:
    with patch(
        "referral_account_proof.requests.get",
        return_value=_response(
            {"code": "00000", "data": {"userId": "BG9", "inviterId": "INV", "channelCode": "NOAH"}}
        ),
    ):
        bitget = fetch_bitget_referral_proof("key", "secret", "passphrase")
    assert bitget.exchange_uid == "BG9"
    assert bitget.channel_code == "NOAH"

    with patch(
        "referral_account_proof.requests.get",
        return_value=_response({"code": "0", "data": [{"uid": "OKX7"}]}),
    ):
        okx = fetch_okx_referral_proof("key", "secret", "passphrase")
    assert okx.exchange_uid == "OKX7"


def test_server_submission_never_sends_user_credentials() -> None:
    proof = ReferralAccountProof("okx", "OKX7", "okx_account_config")
    response = _response({"status": "verified", "membership_policy": {}})
    with patch("referral_account_proof.requests.post", return_value=response) as post:
        result = submit_referral_proof(proof, access_token="login-token")
    assert result["status"] == "verified"
    sent = post.call_args.kwargs["json"]
    assert set(sent) == {"exchange", "exchange_uid", "evidence"}
    assert "login-token" not in repr(sent)
