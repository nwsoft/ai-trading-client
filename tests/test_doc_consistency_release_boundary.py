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
