# 대시보드/설정 리디자인 계획 (Draft v2, 이력 보관)

작성일: 2025-09-25  
개정 사유: 사용자 피드백(거래소별 시작/정지 유지, 서비스 전환 시 미파괴 프레임, AI 탭/버튼 이중화, 설정에서 키 입력 경로 부재) 반영

---
## 1. 개요 & 핵심 변화 요약
이 문서는 Draft v1의 "글로벌 단일화" 접근이 실제 사용 흐름(거래소 개별 재가동/중단 필요)과 충돌한 문제를 바로잡고, **계층적 제어(Hierarchical Control)** 와 **단일 로그 소스**, **명확한 키 입력 경로**를 확립하는 것을 목표로 한다.

핵심 변화:
1. 글로벌 & 거래소별 Start/Stop **동시 유지 (Tri-State)**
2. 모든 서비스(블록체인/부동산/주식/기타투자/애널리스트) 전환 시 **이전 하위 프레임 완전 destroy**
3. 상단 TopBar의 AI 학습/AI 리포트 버튼 → 기본(또는 classic_view 조건) **고정 탭**으로 이동, 버튼 제거
4. 기본 전역 "실시간 거래 로그" = 중앙 LogStream (ring buffer) / 각 거래소 패널 로그는 **필터링 뷰**
5. Settings Modal에 **Exchanges / AI & Models 탭 신설**: API Key, Secret, Passphrase, 활성화 Toggle, OpenAI Key/모델, 연결 테스트
6. 현재 settings.json 보존 → 신규 UI는 기존 키 필드 로드 & 마스킹 & 변경 Diff 적용
7. Print 제거 & logger 레벨/필터 UI 제공
8. 단계적 안전 적용 (회귀 차단을 위한 작은 커밋 단위)

---
## 2. 세부 문제 재정리 (사용자 관점)
| 번호 | 문제 | 현재 동작(관찰) | 요구/해결 방향 |
|------|------|----------------|----------------|
| 1 | 서비스 전환 잔여 프레임 | 블록체인 이외 카테고리 선택 후 이전 거래소 하위 영역 잔존 | 모든 서비스 전환 시 destroy_callbacks + Frame children 전부 제거 |
| 2 | Start/Stop 의미 혼재 | 상단 글로벌 + 거래소 패널 내부 버튼 동시 존재, 역할 설명 없음 | 두 계층 유지하되 Tri-State/Tooltip/아이콘 차별화 |
| 3 | 로그 이중화 | 전역 기본 로그 + 거래소 패널 로그 별도/중복 가능성 | 중앙 LogStream + per-exchange filtered view, 저장은 1곳 |
| 4 | AI 학습/리포트 버튼 이중성 | TopBar 버튼 + (있어야 할) 기본 탭 불일치 | 기본(또는 classic_view) 탭 고정 + TopBar 버튼 제거 |
| 5 | 설정에서 키 입력 경로 모호 | 어디서 거래소 API/OpenAI 키 입력인지 UI 명확하지 않음 | Settings → Exchanges / AI & Models 탭 명시적 제공 |
| 6 | 미구현 서비스 공간 점유 | Placeholder가 해제되지 않음 | PlaceholderFactory + Lazy Destroy 패턴 |
| 7 | 상태 산재 | 변수 다수 파일 분산 | AppState + Pub/Sub (state_bus) 중앙화 |
| 8 | 적용 시점 모호 | 저장 후 무엇이 재초기화 되는지 불명확 | SettingsDiffEngine: diff→ action log → 사용자 피드백 토스트 |
| 9 | Print 혼재 | print 다수 | logger wrapper + 레벨/필터 설정 UI |
| 10 | 확장 어려움 | if-else 기반 조건 분기 | ServiceRegistry (name→factory) 구조 |

---
## 3. 디자인 원칙 (Revised Principles)
1. Hierarchical Control: 글로벌(ALL) vs 개별(Exchange) → 공존·역할 명확화
2. Single Source Logging: 생산(append)은 1곳, 소비는 필터 기반 다중 뷰
3. Destroy on Switch: 어떤 서비스든 전환 시 이전 UI 메모리/이벤트 완전 분리
4. Explicit Key Entry: 모든 API/OpenAI 키는 Settings Modal 내부에서만 관리 (파일 직접 편집 지양)
5. Diff-based Apply: 전체 리로드 최소화, 변경 영향 범위만 재초기화
6. Observable State: AppState + 이벤트 브로드캐스트로 UI 반응성 확보
7. Incremental Migration: 회귀 최소화를 위해 독립 가능한 작은 단계로 적용
8. Backward Compatibility: 기존 settings.json 구조 유지 (키필드명 동일)
9. Transparency: 사용자에게 ‘무엇이 바뀌었는지/어떤 모듈 재초기화했는지’ 피드백
10. Recoverability: 설정 적용 실패 시 롤백 및 오류 로그 제공

---
## 4. 정보구조 (Updated IA)
```
TopBar
 ├─ [전체 시작/정지 (Tri-State)]  [설정]  [테마]
 │    (AI 학습/리포트 버튼 제거; classic_view=True 시 자동 탭 포커스)
 └─ Service Switcher: 블록체인 / 부동산 / 주식증권 / 기타투자 / 애널리스트

Main Area (CTkTabview)
 ├─ (기본) 📊 실시간 거래 로그 (Global Aggregated)
 ├─ (기본) 🤖 AI 학습
 ├─ (기본) 📑 AI 리포트
 ├─ (동적) 거래소별 탭: Binance / OKX / Bybit ... (블록체인 서비스 선택 시만 mount)
 └─ (향후) 다른 서비스 전용 탭들 (mount 시점 lazy)
```

---
## 5. 제어 모델 (Control Model)
### Tri-State 정의
```
running = {ex for ex in enabled_exchanges if ex in running_exchanges}
if not running: GLOBAL=STOPPED
elif running == enabled_exchanges: GLOBAL=RUNNING
else: GLOBAL=PARTIAL
```
아이콘/라벨 예:
| 상태 | 아이콘 | 라벨 | Tooltip |
|------|--------|------|---------|
| STOPPED | ▶️ | 전체 시작 | 활성화된 모든 거래소 자동거래 시작 |
| RUNNING | ⏹️ | 전체 정지 | 실행 중인 모든 거래소 중지 |
| PARTIAL | 🔁 | 부분 실행(재시작) | 일부만 실행 중 – 전체 재시작 가능 |

### 개별 거래소 패널
| 버튼 | 동작 | 실패 처리 |
|------|------|-----------|
| Start | unified_trader.start_trading(exchange) | API 키 누락 → 경고 & 설정 이동 링크 |
| Stop  | unified_trader.stop_trading(exchange)  | 이미 정지 상태 → no-op, 라벨 갱신 |

글로벌 → 내부적으로 per-exchange start/stop 루프 수행 + 실패/성공 통계 요약 후 토스트 출력.

---
## 6. 로그 아키텍처
1. LogStreamService: `deque(maxlen=N)` + append(record) + subscribers
2. Global Log Tab: 전체 스트림 + 필터(Exchange, Level, Category)
3. Exchange Panel Log: Global 필터 copy(base_filters + exchange=ex)
4. 파일 저장: 단일 로거 핸들러 (회전/보존 정책 유지)
5. 이점: 중복 수집 제거, 메모리/CPU 절감, 동기화 문제 해소

---
## 7. Settings Modal (신규 구조)
| 탭 | 필드 | 기능 | 적용 방식 |
|----|------|------|-----------|
| General | 언어, 테마, 기본 통화 | 즉시 적용 | state_bus 이벤트 |
| Exchanges | 표: Exchange, API Key(mask), Secret(mask), Passphrase, Enabled(Toggle), Test | 저장 시 diff→ 재생성 | 개별 재초기화 |
| AI & Models | OpenAI Key(mask), 모델 선택, 테스트 호출 | 저장 후 테스트 | AIManager 재초기화 |
| Trading | leverage, tp/sl, auto_coin_selection, risk prefs | 저장 시 부분 재적용 | UnifiedTradingManager.reload_settings |
| Logs & Debug | log_level, clear logs, position_sizing_debug | 즉시 | logger 재설정 |
| Advanced | symbol filters 편집(JSON), dynamic thresholds, overrides | 저장 후 일부 재시작 표시 | 영향 범위 표시 |

Diff Engine Pseudo:
```
old = load_settings(); new = form_values
actions = compute_diff(old,new)
for a in actions: apply(a) with rollback guard
persist(new)
toast(summary(actions))
```

---
## 8. 상태 모델
```python
@dataclass
class AppState:
    current_service: str
    enabled_exchanges: set[str]
    running_exchanges: set[str]
    settings: dict
    ai_ready: bool
    log_filters: dict
    classic_view: bool
```
업데이트 이벤트: SERVICE_CHANGED, EXCHANGE_STARTED, EXCHANGE_STOPPED, SETTINGS_APPLIED, LOG_FILTER_CHANGED

---
## 9. 마이그레이션 단계 (Incremental Plan)
| 단계 | 작업 | 산출물/검증 |
|------|------|-------------|
| 1 | Settings Modal Scaffold + Exchanges/AI 탭 구현 | 키 로드/저장 + 마스킹 + 테스트 더미 함수 |
| 2 | LogStreamService 도입 + Global Log Tab 교체 | 기존 로그 호출 경로 리다이렉트, 중복 제거 |
| 3 | Service Switch Destroy 로직(모든 서비스) | 전환 후 이전 위젯 미존재 확인 |
| 4 | AI 학습/리포트 기본 탭 고정 + TopBar 버튼 제거 | classic_view 플래그 동작 검증 |
| 5 | Tri-State 글로벌 제어 + Tooltip/아이콘 | Partial 케이스 유닛 테스트 |
| 6 | Exchange Panel 내부 Start/Stop 정리 & 상태 뱃지 | Invalid Key 시 비활성 UI 표시 |
| 7 | Print 제거 & logger wrapper + level 즉시 반영 | print grep=0 확인 |
| 8 | Dashboard 파일 분리 (navigation.py, panels/*) | 원본 대비 기능 회귀 없음 |
| 9 | 문서/가이드 갱신 (USER_GUIDE, ARCHITECTURE) | 변경 반영 diff 목록 |

---
## 10. 수용 기준 (Acceptance Criteria)
1. 서비스 전환 시 이전 프레임 객체 참조 해제 (id() 추적/weakref 검사)  
2. 글로벌 상태 아이콘이 실행 상태 정확히 반영(STOPPED/RUNNING/PARTIAL)  
3. Settings에서 Binance API Key 입력 후 저장 → 해당 거래소 Start 성공 (키 누락 시 경고)  
4. OpenAI Key 저장 후 테스트 호출 성공 시 AI 탭 ‘READY’ 배지 표시  
5. 전역 로그 필터로 특정 거래소만 표시 & 교차 확인(다른 패널 동일 결과)  
6. print() 호출 0 (grep)  
7. 회귀 테스트(기존 멀티거래소 런타임 스모크) PASS  

---
## 11. 위험 & 대응
| 위험 | 설명 | 대응 |
|------|------|------|
| Incremental 중 혼재 상태 | 신규/구 버전 UI 혼재 | feature flag + 단계 완료 후 flag 제거 |
| 로그 동시성 | 다중 스레드 append 경쟁 | thread-safe wrapper + deque 보호락 |
| API Key 노출 | UI 디버그 출력 | 마스킹 + copy 제한 + 클립보드 경고 |
| Diff 오판 | 잘못된 재초기화 | action 단위 try/rollback + summary log |
| Partial 상태 UX 혼란 | 사용자 의미 이해 부족 | Tooltip + 문서 + 첫 실행 온보딩 |

---
## 12. 구현 체크리스트
- [ ] SettingsModal 새 구조 (Exchanges / AI & Models)
- [ ] compute_diff / apply_diff 유틸
- [ ] API Key Test 함수 (ping or time endpoint)
- [ ] LogStreamService (deque + subscribe)
- [ ] Global Log Tab 교체 + 필터 UI
- [ ] Exchange Panel 로그 -> 필터 뷰 연동
- [ ] Service Destroy 유틸 (destroy_children(frame))
- [ ] Tri-State 버튼 컴포넌트 (상태→아이콘/라벨)
- [ ] Start/Stop 이벤트 → AppState 동기화
- [ ] AI 탭 고정 + classic_view 처리
- [ ] print 제거 스크립트(grep 검증) & logger wrapper
- [ ] 파일 분할 (navigation.py, panels/exchange.py, panels/logs.py, panels/ai.py)
- [ ] 문서: UPDATED_DASHBOARD.md, ARCHITECTURE.md 반영

---
## 13. 향후 확장 (Post v2)
- 사용자 정의 열/위젯 Layout 저장
- Plugin Registry (3rd-party 패널 주입)
- 역할 기반 제한(읽기 전용 모드)
- 국제화 리소스 번들(i18n) 적용

---
## 14. 적용 우선순위 재정렬
1) Settings 키 입력 경로 (Exchanges / AI)  
2) LogStream + 로그 단일화  
3) 서비스 destroy 확립  
4) Tri-State 글로벌 제어  
5) AI 탭 고정 & TopBar 정리  
6) Exchange 패널 개선 (상태 뱃지)  
7) 파일 분할 & 상태 버스  
8) 문서/튜토리얼 정리  

---
## 15. 다음 액션
사용자 재확인 후 단계 1 구현 착수 (브랜치: `feature/dashboard-v2`)

---
(끝)
