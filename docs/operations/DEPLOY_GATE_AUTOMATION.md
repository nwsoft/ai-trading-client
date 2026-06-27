# 배포 게이트 자동화

## 개요
- build_safe.py 실행 전에 release_gate.py를 자동 수행한다.
- 기존 빌드/업데이트 배포 방식은 유지된다.

## 실행 규칙
- 기본: dev 프로필
- 배포 직전: release 프로필 권장

명령 예시
- python build_safe.py --platform windows
- python build_safe.py --platform windows --gate-profile release
- python build_safe.py --platform windows --skip-gate

## release_gate 체크 항목
1. 핵심 증권 회귀 테스트
2. 지원 모드 매트릭스 검증
3. 전체 브로커 readiness 체인

## 실패 처리
- required 단계 실패 시 빌드 중단
- release 프로필은 readiness 실패도 빌드 차단
