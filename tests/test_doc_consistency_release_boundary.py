import pytest

from scripts import doc_consistency_check as checker


@pytest.fixture(autouse=True)
def current_version(monkeypatch):
    monkeypatch.setattr(checker, "RELEASE_VERSION", "3.9.2.2")


def test_explicit_unpublished_candidate_changelog_is_allowed():
    text = (
        "## 2026-10-02 - v3.9.2.2 공개 기준\n\n"
        "## 2026-10-03 — v3.9.2.3 차기 수정 내역 (로컬 구현·미배포)\n"
        "v3.9.2.3 설치본은 아직 게시되지 않았다.\n"
    )
    assert checker.check_for_higher_version_mentions({"changelog": text}) == []


@pytest.mark.parametrize("surface", ["changelog", "user_guide", "policy"])
def test_undeclared_future_release_is_rejected(surface):
    errors = checker.check_for_higher_version_mentions({surface: "## v3.9.2.3 최신 업데이트\n"})
    assert len(errors) == 1 and "[VERSION_HIGH]" in errors[0]


def test_candidate_exception_does_not_apply_to_other_documents():
    text = "## 2026-10-03 — v3.9.2.3 차기 수정 내역 (로컬 구현·미배포)\n"
    assert checker.check_for_higher_version_mentions({"user_guide": text})


def test_other_future_versions_and_next_section_remain_blocked():
    text = (
        "## 2026-10-03 — v3.9.2.3 차기 수정 내역 (로컬 구현·미배포)\n"
        "v3.9.2.4\n"
        "## 다른 절\n"
        "v3.9.2.3\n"
    )
    assert len(checker.check_for_higher_version_mentions({"changelog": text})) == 2


def test_published_identity_cannot_remain_candidate_but_history_is_preserved(monkeypatch):
    monkeypatch.setattr(checker, 'RELEASE_VERSION', '3.9.2.5')
    monkeypatch.setattr(checker, 'PUBLIC_RELEASE_VERSION', '3.9.2.4')
    report = {'status': 'published_verified', 'version': '3.9.2.5'}
    errors = checker.check_publication_boundary({'changelog': '## v3.9.2.5 (로컬 소스 후보)\n설치본을 게시한 상태는 아닙니다.'}, report)
    assert any('PUBLIC_RELEASE_VERSION' in e for e in errors)
    assert any('changelog' in e for e in errors)
    monkeypatch.setattr(checker, 'PUBLIC_RELEASE_VERSION', '3.9.2.5')
    text = '## v3.9.2.5 공개\n\n## 이전 릴리스\n설치본을 게시한 상태는 아닙니다.'
    assert checker.check_publication_boundary({'changelog': text}, report) == []


def test_build_ready_without_verified_publication_does_not_promote_release():
    assert checker.check_publication_boundary({}, {'status': 'windows_verified_release_candidate', 'version': '3.9.2.2'}) == []


def test_anchor_before_heading_does_not_hide_stale_publication_status(monkeypatch):
    monkeypatch.setattr(checker, 'RELEASE_VERSION', '3.9.2.5')
    monkeypatch.setattr(checker, 'PUBLIC_RELEASE_VERSION', '3.9.2.5')
    text = '<a id="latest"></a>\n\n## v3.9.2.5\n설치본을 게시한 상태는 아닙니다.\n\n## 과거 이력\n'
    assert checker.check_publication_boundary({'test_status': text}, {'status': 'published_verified', 'version': '3.9.2.5'})
