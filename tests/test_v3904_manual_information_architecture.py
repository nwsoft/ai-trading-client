from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_v3904_manual_is_written_for_installed_users_and_keeps_usage_out_of_history():
    manual_path = ROOT / "ui" / "widgets" / "user_manual_widget.py"
    manual = manual_path.read_text(encoding="utf-8")

    user_surfaces = [
        manual,
        (ROOT / "docs" / "USER_GUIDE.md").read_text(encoding="utf-8"),
        (ROOT / "USER_GUIDE_AI_EXECUTION.md").read_text(encoding="utf-8"),
        (ROOT / "docs" / "SETTINGS_REFERENCE_v3.9.0.5.md").read_text(
            encoding="utf-8"
        ),
    ]
    forbidden_release_engineering_phrases = (
        "배포 전",
        "업데이트 배포 대상",
        "Windows 빌드 전",
        "재빌드 전 후보",
    )
    for surface in user_surfaces:
        for phrase in forbidden_release_engineering_phrases:
            assert phrase not in surface

    dashboard_start = manual.index("def create_dashboard_guide_tab")
    updates_start = manual.index("def create_updates_tab")
    dashboard_section = manual[dashboard_start:]
    updates_section = manual[updates_start:dashboard_start]

    assert 'tab_widget.add("시작·설정")' in dashboard_section
    assert "처음 설정하는 순서" in dashboard_section
    assert "세 가지 실행 모드" in dashboard_section
    assert "세 가지 실행 모드" not in updates_section
    assert "v3.9.0.8 Fix 3 최신 업데이트" in updates_section
    assert "빈 잔고·계정 응답을 성공으로 저장하던 문제" in updates_section
    assert "기능·설정·오류 검색" in manual
    assert "AI에게 묻기" in manual
    assert "StrategyUniversePolicy" in manual
    assert "각각 실행(기본)" in manual
    assert "전체 시장(권장)" in manual

    audit = (
        ROOT / "docs" / "INTEGRATED_AUDIT_v3.9.0.5_20260731.md"
    ).read_text(encoding="utf-8")
    assert "이 조치는 모든 설치 사용자 대상이 아니다" in audit
    assert "단순히 `keyring` 경고를 본 사용자" in audit
