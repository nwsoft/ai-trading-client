import json
from pathlib import Path
from unittest.mock import Mock, patch

from user_status_manager import UserStatusManager


ROOT = Path(__file__).resolve().parents[1]


def _manager(tmp_path) -> UserStatusManager:
    manager = UserStatusManager.__new__(UserStatusManager)
    manager.backend_api = None
    manager.settings = {}
    manager.policy_update_callback = None
    manager.status_thread = None
    manager.is_running = False
    manager.check_interval = 60
    manager.initial_delay = 5
    manager.server_url = "https://daltrading.net"
    manager.env_file = str(tmp_path / "token.json")
    manager._last_status_failure_terminal = False
    Path(manager.env_file).write_text(
        json.dumps(
            {
                "access_token": "test-token",
                "user_info": {"id": "ref-user", "session_id": "session-123", "user_grade": "referral"},
            }
        ),
        encoding="utf-8",
    )
    return manager


def test_missing_openai_key_does_not_exit_or_block_dashboard() -> None:
    source = (ROOT / "main.py").read_text(encoding="utf-8")
    login_block = source[source.index("    def on_login_success"):source.index("    def show_api_setup_dialog")]
    verify_block = source[source.index("    def verify_api_keys_after_setup"):source.index("    def on_settings_saved")]

    assert "self.show_api_setup_dialog()" not in login_block
    assert "sys.exit" not in verify_block
    assert "AI 기능만 비활성" in login_block


def test_fix_patch_manual_explains_startup_status_and_affiliate_admin_boundary() -> None:
    manual = (ROOT / "ui/widgets/user_manual_widget.py").read_text(encoding="utf-8")

    for marker in (
        "Fix Patch 1 — 레퍼럴 첫 실행·자동확인 운영 안정화",
        "AI 기능만 비활성",
        "일시적인 네트워크 오류·5xx",
        "SSH나 `.env` 파일 편집은 기본 운영 절차가 아닙니다",
        "일반 사용자는 Affiliate 자동확인용 운영자 키를 입력하지 않습니다",
        "pending_windows_rebuild",
    ):
        assert marker in manual


def test_transient_status_failure_does_not_request_forced_exit(tmp_path) -> None:
    manager = _manager(tmp_path)
    response = Mock(status_code=503)
    with patch("user_status_manager.requests.post", return_value=response):
        assert manager.check_user_status() is False
    assert manager._last_status_failure_terminal is False


def test_explicit_force_quit_is_terminal(tmp_path) -> None:
    manager = _manager(tmp_path)
    response = Mock(status_code=200)
    response.json.return_value = {
        "is_active": True,
        "force_quit": True,
        "message": "다른 장치에서 로그인되었습니다.",
    }
    with patch("user_status_manager.requests.post", return_value=response):
        assert manager.check_user_status() is False
    assert manager._last_status_failure_terminal is True
