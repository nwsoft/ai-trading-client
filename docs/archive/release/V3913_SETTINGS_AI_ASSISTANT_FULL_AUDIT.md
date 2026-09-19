# v3.9.1.3 설정·AI 어시스턴트 전수 상위호환 감사

기준일: 2026-08-22  
판정 범위: 소스 정본·Web 계약·레거시 사용자 설정·AI 어시스턴트 호출 경계  
배포 판정: Windows 재빌드·설치본 E2E 전 `pending_windows_rebuild`, `publish_ready=false`

## 결론

기존의 최상위 키 개수 검사는 중첩 설정, 실제 화면 노출, 런타임 소유자와 AI 대화 문맥을 증명하지 못했다. v3.9.1.3에서는 `settings_template.json`의 117개 최상위 항목과 646개 leaf를 다음처럼 전부 소유 분류하고 미분류 0개를 자동 게이트로 고정했다.

| 분류 | leaf | 의미 |
|---|---:|---|
| 직접 편집 | 132 | 자료형·선택값·범위 검증을 거쳐 경로 단위 저장 |
| 전문가 JSON | 261 | 비밀 하위값이 없는 고급 구조만 전체 JSON 편집 |
| 전용 관리 | 171 | 실행 governor, 증권 자율주행, 프리셋, Electron 등 전용 소유자가 관리 |
| 보호 | 82 | API 키·계좌·내부 마이그레이션·런타임 snapshot |
| 미분류 | 0 | 새 설정이 소유자 없이 추가되면 자동검사 실패 |

실행 명령:

```bash
PYTHONPATH=. .venv/bin/python scripts/audit_settings_ai_assistant_contract.py
```

## 발견해 수정한 실제 불일치

1. Web의 `assistant_response_mode`가 런타임 정본 `saver/standard/premium`이 아니라 `beginner/standard/advanced`를 저장하던 오류를 수정했다. 이미 잘못 저장된 값은 `beginner→saver`, `advanced→premium`으로 마이그레이션한다.
2. AI 커스텀 실험실 프로필이 정본 `lab` 대신 `laboratory`로 저장돼 일반 프로필로 되돌아갈 수 있던 오류를 수정하고 기존 값을 `lab`으로 복구한다.
3. 원본 설정의 AI 애널리스트·AI 어시스턴트별 Provider/모델, 3개 작업 티어, 영상 전사 시간·파일 상한, 음성 설정, 자동업데이트 정책을 Web의 명시적 필드로 연결했다.
4. Provider/모델 변경 시 `ai_provider`, `openai_model`, `assistant_ai_model`, `ai_models` 하위 호환 키도 같은 트랜잭션에서 동기화한다.
5. 증권사별 `enabled`와 `enabled_stock_brokers`가 서로 다른 상태로 남지 않게 한 트랜잭션에서 동기화한다.
6. 설정 탭별·전체 기본값 불러오기를 추가했다. 기본값은 변경 대기에만 올리고 사용자가 저장해야 적용되며 API 키·연결 정보는 지우지 않는다.
7. AI 어시스턴트 심층분석에 최근 대화 최대 12개와 저장된 문맥·출력 프리셋을 실제 적용한다. 일반 안내는 계속 로컬 정본이며 외부 비용이 없다.
8. AI 커스텀 Level 1·2·3을 저장 프로필과 연결했다. 초보자는 Level 1, 일반은 Level 2, 고급·실험실은 Level 3이 기본이며 Level 3은 고급 또는 실험실 저장 후 열린다.
9. 12단계 자세히는 로컬 정본이라 API 비용이 없고, 차트 분석·심층분석·무자막 전사는 버튼을 눌렀을 때만 외부 호출 예산을 사용한다.
10. 전략 입력 초기화, 저장 버튼 비활성 사유, `.noahstrategy` 계정 기본 저장소, PDF·YouTube 읽은 범위와 자막/전사/화면 근거 분리 표시는 기존 v3.9.1.2 보강을 유지하고 전수 감사 게이트에 포함했다.

## 저장·복구·writer 판정

- Web 활성 경로는 경로 단위 `patch_settings_paths`와 저장 후 재읽기 검증 영수증을 사용한다.
- 거래 실행 모듈의 설정 갱신도 소유 경로 patch만 허용한다.
- 전체 `save_settings`를 사용하는 `ui/`와 일부 `main.py` 경로는 Web sidecar에 패키징하지 않는 레거시 CTk 경로다. Windows sidecar TOC에서 레거시 UI 0개를 별도 검증한다.
- 백업 복구는 사용자가 `백업에서 복구`를 선택하고 revision 확인을 통과한 경우에만 실행한다.
- Teayu 원본 `data/260821_Teayu/config/settings.json`은 읽기 전용 계약 감사에서 스키마 `3.9.0.5`, LEARNING, 모순 0건이었다. 원본 파일은 수정하지 않았다.

## 아직 완료로 판정하지 않는 것

- Windows v3.9.1.3 설치기와 내장 `NoahAIEngine.exe`는 아직 재빌드되지 않았다.
- 제보 PC에서 저장→대기→닫기→재열기→앱 재시작, 기존 AI 키 호환, Provider 실제 네트워크, 마이크 권한, 차트 비전, 자동업데이트/롤백을 같은 산출물로 확인해야 한다.
- 실제 거래소·증권사 계정과 24~72시간 PAPER 검증 전에는 상위호환 배포 완료 또는 실거래 완료로 표시하지 않는다.
