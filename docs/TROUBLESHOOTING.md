# 문제 해결 가이드 (TROUBLESHOOTING)

## 0) v3.9.0.3 Windows 설치본의 API 키 보안 저장 경고

증상:

`운영체제 보안 저장소(keyring)를 사용할 수 없습니다`

사용자 조치:

- Python, pip, requirements.txt, keyring을 직접 설치하지 않습니다.
- 필수 keyring 의존성을 제거한 v3.9.0.4 이상 공식 Windows 설치본으로 업데이트합니다.
- 업데이트 후 AI 키 입력란에 `v3.9.0.3 키 재입력 필요`가 표시된 Provider만 키를 한 번 다시 입력합니다.
- 다른 일반·거래소 설정은 보안 저장소와 관계없이 정상 저장되어야 합니다.

원인:

v3.9.0.3 후보에서 AI 키에만 Windows 자격 증명 관리자를 도입하면서 기존 무설치 정책 및 거래소·증권사 키의 로컬 저장 방식과 불일치가 생겼습니다. v3.9.0.4는 필수 keyring과 운영체제 보안 저장소 의존성을 철회했습니다.

이 경고는 Binance 거래소 키나 잔고 조회 문제와 별개입니다.

## 0-A) 거래소 탭이 계속 로딩 중

- 메인 운영 KPI는 로컬 DB·로그를 읽고, 거래소 탭의 잔고·포지션은 private 거래소 API를 별도로 조회합니다.
- v3.9.0.3 후보는 숨겨진 거래소 탭에서 최초 조회 예약이 사라질 수 있어, 실제 거래와 WebSocket은 정상인데 카드만 계속 `로딩 중`일 수 있습니다.
- v3.9.0.4는 모든 거래소 탭에서 실제 실행부의 연결을 재사용하고 탭 선택 즉시 조회를 깨웁니다. 12초 안에 값, API 키 없음, API 키 오류, 연결 실패, 조회 실패 중 하나를 표시합니다.
- 12초 뒤에도 `로딩 중`이면 v3.9.0.4 공식 설치본인지 확인하고 `runtime_stability.jsonl`, `trading.log`를 운영 지원에 전달합니다.
- 과거 AI keyring 경고를 해결하려고 거래소 키를 재발급하지 않습니다.

## 0-B) `default_tp/default_sl 입력 단위/범위 정규화` 경고

- `default_tp 0.18 → 0.0018`은 0.18%를, `default_sl 0.2 → 0.002`는 0.2%를 내부 fraction 단위로 옮기는 변환입니다. 주문 실패나 거래소 연결 오류가 아닙니다.
- v3.9.0.3 후보에서는 구값이 반복 주입되어 재실행 때마다 WARNING이 나타날 수 있었습니다.
- v3.9.0.4는 최초 로드에서 변환값을 설정에 저장하고 정상 단위 이전은 INFO로만 기록합니다.
- 설정 파일이 이미 `0.0018/0.002`인데도 같은 변환이 매 시작마다 반복된 원인은 균형 전략 프리셋이 표시값 `0.18/0.20`을 런타임에 다시 전달하던 결함이었습니다. 2026-07-30 v3.9.0.4 소스에서 프리셋 단위 계약과 Binance·통합 거래소 입력 방어를 함께 수정했습니다.
- 사용자가 설정 JSON을 직접 고치거나 별도 프로그램을 설치할 필요는 없습니다. 수정된 v3.9.0.4 설치본에서 반복 메시지가 없어야 하며, 실제 비정상 외부 입력을 복구할 때만 변환 로그가 다시 나올 수 있습니다.
- 매 시작 시 보이는 `TP/SL 설정 확인 완료 (주문 단위 fraction)`은 변환이 아니라 최종값 검증 결과입니다. 실제 변환이 발생한 경우에만 `레거시 퍼센트 단위 자동 변환`을 별도로 기록합니다.
- `0.18%/0.20%`는 균형 프로파일의 시작 기본값입니다. 모든 거래의 고정값이나 거래소별 확정값이 아니며 분석값, 승인된 사용자 전략, 변동성 조정과 RR 가드레일이 최종 주문값을 바꿀 수 있습니다.
- `NaN`, 음수, 가격값처럼 실제로 위험한 입력을 안전 기본값으로 되돌린 경우에만 WARNING을 유지합니다.

## 1) 소스 직접 실행 실패 (Exit Code 1)
증상: `python3 main.py` 실행 직후 종료됩니다.

조치 순서:
- 터미널 출력의 "===== 진단 정보 =====" 블록을 확인하세요.
  - CWD, Python 실행 경로, Version, Traceback이 표시됩니다.
- 흔한 원인과 해결
  - macOS 권한 문제: 시스템 설정 > 개인정보 보호 및 보안 > 파일 및 폴더 > 터미널/VS Code에 문서(Documents) 접근 허용
    - 첫 실행 후 팝업이 보이지 않았다면, 수동으로 설정에서 터미널/VS Code 항목의 Documents 체크를 ON하고 앱을 재실행하세요.
  - 파이썬(Tk 미포함): Homebrew Python 사용 시 Tk가 없을 수 있습니다 → 시스템 Python 3.11 사용 권장
  - 경로/한글 폴더: 유니코드 경로 지원 강화했지만, Documents 생성 권한이 없으면 실패할 수 있습니다 → 사용자 홈 권한 점검
  - 누락된 설정/리소스: `config/*_template.json`는 패키징에 포함됩니다. 소스 실행 시 `path_utils`가 사용자 Documents 하위에 템플릿을 복사합니다.

추가 확인:
- VS Code와 터미널이 동일한 Python 인터프리터를 사용 중인지 확인
- `pip install -r requirements.txt`로 의존성 설치
- 실패 로그(Traceback)를 이슈로 공유해 주세요.

위 `pip install` 안내는 개발자가 소스를 직접 실행할 때만 적용됩니다. Windows 공식 설치본 사용자에게는 적용되지 않습니다.

추가 점검 루틴
- `echo $NOAHAI_SKIP_LOGIN` 값이 예상과 일치하는지 확인(개발용 빠른 진입 시 true)
- `noahai_client/config/settings_template.json`과 `data/settings.json`의 키가 정상 병합되었는지 확인(classic_view 등)
- `path_utils.print_path_info()` 출력으로 config/log/analytics 경로가 의도대로인지 확인

## 2) UI가 뜨지만 데이터가 비정상
- 네트워크/프록시: HTTPS(443) 허용, 기업망 프록시 설정 반영
- OpenAI 오류: API Key 설정/쿼터/429/5xx 확인, 잠시 후 재시도
- 거래소 API 오류: 키/권한/서버 시간 동기화 확인
 - WebSocket 구독: `subscribe_symbol` 호출 후 10초 내 최신 티커가 도착하는지 확인(없으면 네트워크/심볼/권한 점검)
 - 심볼 검증: 내부 심볼 캐시로 유효성 검사. `BTCUSDT` 등 거래 가능한 심볼인지 확인

## 3) 문서/배포 관련
- 배포 체크리스트: DEPLOY_CHECKLIST.md
- 저장 경로/권한: STORAGE_PATHS.md
 - 빌드 가이드: BUILD_GUIDE.md (크로스플랫폼 `--platform` 안내)

## 4) 거래소별 특수 문제

### v3.8.9.22 패치 기준: 증권사 연결 빠른 점검 동선

증권사 연결 실패 시 아래 순서로 먼저 확인하세요.

1. 설정 > 거래소 API에서 계정 정보 입력 후 저장
2. 저장 직후 `증권사 1차 진단` 팝업이 뜨면 경고 항목 우선 확인
3. 설정 화면의 `연결 실패 5분 점검 가이드 열기` 버튼으로 상세 문서 실행
4. 상세 점검 문서(`STOCK_BROKER_WINDOWS_CONNECTION_CHECKLIST_20260611.md`) 순서대로 재검증

참고:
- 1차 진단은 선택된 증권사(키움/신한/미래에셋/한국투자증권)만 대상으로 점검합니다.
- 표시 항목: API 타입/버전, OS 제약(키움), app_key/app_secret 누락 가능성(신한/미래에셋/한국투자증권)

### 키움증권 연결 문제

#### 문제: "No module named 'pykiwoom'" (Windows 배포판)
**증상**:
```
ERROR - pykiwoom 초기화 실패: No module named 'pykiwoom' (ex=kiwoom)
WARNING - 키움증권 미연결 - 주식 목록 조회 불가
```

**원인**: Windows 배포판(AITrading.exe)에 `pykiwoom` 및 `PyQt5` 라이브러리 미포함.

**해결 (v3.8.9.16+ 빌드부터 자동 해결)**:
- Windows 빌드 PC에서 1회 실행: `pip install pykiwoom PyQt5`
- 이후 `python build_safe.py --platform windows` 로 재빌드하면 배포판에 자동 포함

**구 버전 사용자 임시 조치**:
- 환경설정 > 키움증권 API 설정 > API 버전을 `mock`으로 변경하면 연결 없이 데모 모드로 동작

---

#### 문제: `'QAxWidget' object has no attribute 'OnReceiveTrData'`
**증상**:
```
ERROR - pykiwoom 초기화 실패: 'QAxWidget' object has no attribute 'OnReceiveTrData' (ex=kiwoom)
```

**원인 분석**:  
pykiwoom은 내부적으로 `self.ocx = QAxWidget("KHOPENAPI.KHOpenAPICtrl.1")`을 생성합니다.  
Windows 레지스트리에 해당 ProgID(`KHOPENAPI.KHOpenAPICtrl.1`)가 없으면 QAxWidget이 **빈 객체**로 생성되고, 이후 `.OnReceiveTrData` 접근 시 AttributeError가 발생합니다.

**원인 체크리스트 (순서대로 확인)**:

1. **키움 OpenAPI+ 미설치** (가장 흔한 원인)
   - 키움증권 홈페이지(www1.kiwoom.com > 다운로드 > Open API > 키움 Open API+)에서 설치
   - 설치 후 KOA Studio를 실행하여 정상 연결되는지 먼저 확인

2. **OCX 등록 실패** — 설치됐으나 관리자 권한이 없어 OCX 등록이 안 된 경우
   - 키움 OpenAPI+ 설치 파일을 **우클릭 → 관리자 권한으로 실행**하여 재설치
   - 또는 명령 프롬프트(관리자)에서: `regsvr32 "C:\OpenApi\KHOPENAPI.ocx"`

3. **Python과 OpenAPI+ 비트 불일치** — Python 32/64bit와 설치된 OpenAPI+ 비트가 다른 경우
  - NoahAI의 현재 키움 실연결 경로에서는 **Windows 32bit Python 3.11.x + OpenAPI+** 조합을 우선 권장합니다.
  - 확인 방법: 설정 화면의 `Python 런타임 정보` 또는 `python -c "import struct; print(struct.calcsize('P')*8, 'bit')"`
  - 64bit Python에서 ActiveX 바인딩 실패(`setControl=False`, `OnReceiveTrData=False`)가 반복되면 32bit Python 전환을 먼저 점검하세요.
  - 앱 안의 `32bit Python 다운로드` / `설치 가이드 보기` 버튼으로 바로 이동할 수 있습니다.

4. **서비스 미등록** — 키움증권 홈페이지에서 Open API 서비스 신청이 안 된 경우
   - 키움증권 홈페이지 > 고객서비스 > 다운로드 > Open API > 서비스 사용 등록/해지

---

#### 문제: 키움증권 환경설정 입력해도 연결 안 됨
**증상**: 설정에서 ID/비밀번호/공인인증서 비밀번호 입력 후 저장해도 연결 실패

**원인 체크리스트**:
1. **OS 확인**: 키움 OpenAPI+는 Windows 전용. macOS/Linux에서는 `mock` 모드만 동작
2. **pykiwoom 설치 여부**: `pip show pykiwoom` 으로 확인. 없으면 설치 필요
3. **키움 OpenAPI+ 설치 및 서비스 등록 확인** (위 체크리스트 참고)
4. **allow_live_order 플래그**: 실주문을 위해서는 아래 2개가 모두 true 여야 함
   - 환경설정 > 증권 실주문 활성화 (`enable_stock_live_order`)
   - `data/settings.json` > `stock_broker_configs.kiwoom.allow_live_order: true`
5. **실행 모드**: `paper_trading=true`이면 위 두 값과 무관하게 PAPER이며 외부 주문이 나가지 않음
6. **런타임 준비**: 위 권한과 별도로 OpenAPI+ 로그인·OCX·계좌·SendOrder 준비상태가 정상이어야 함

**로그 확인 방법**: KIWOOM 탭 > 전체 로그 체크 → "ERROR" 또는 "키움증권 연결" 메시지 확인

#### 문제: 신한/미래에셋 API 이름은 맞는데 연결되지 않음

- 신한은 `partner_rest/shinhan_openapi_v2`, 미래에셋은 `partner_rest/mirae_partner_profile`을 사용합니다.
- 두 경로는 임의 공개 URL이 아니라 증권사 제휴 계약에서 받은 `partner_profile`의 운영 URL·토큰 경로·엔드포인트를 사용합니다.
- 프로필이 빠졌다면 다른 증권사의 URL로 대신 호출하지 않고 `계약 프로필 미완료`로 실패 폐쇄됩니다.
- `xingapi`는 LS증권 API이며 신한 설정으로 사용하면 안 됩니다.
- 상세 형식은 `docs/STOCK_BROKER_CONTRACTS_v3.9.0.5.md`를 확인하세요.

---

### OKX 거래소 문제 해결

#### 문제 1: 마진 타입 설정 실패 - "lever should be between 1 and 125"
**증상**:
```
ERROR | 마진 타입 설정 실패: okx setMarginMode() params["lever"] should be between 1 and 125
```

**원인**: OKX는 마진 타입 변경 시 레버리지 정보를 필수로 요구합니다.

**해결**: 
- ✅ **자동 해결됨 (v3.7.8+)**: OKX 어댑터가 현재 레버리지를 자동으로 조회하여 전달하도록 수정되었습니다.
- 수동 조치가 필요한 경우: OKX 웹사이트에서 해당 심볼의 레버리지를 먼저 설정한 후 거래를 시도하세요.

#### 문제 2: 주문 실행 실패 - "51010: You can't complete this request under your current account mode"
**증상**:
```
ERROR | 주문 실행 실패: okx {"code":"1","sCode":"51010","sMsg":"You can't complete this request under your current account mode"}
```

**원인**: OKX 계좌 모드가 선물 거래에 적합하지 않게 설정되어 있습니다.

**해결 방법**:
1. **OKX 웹사이트 로그인** (https://www.okx.com)
2. **거래 설정** → **계좌 모드** 선택
3. 다음 중 하나로 변경:
   - **Single-currency margin mode** (단일 통화 마진) - 권장
   - **Multi-currency margin mode** (다중 통화 마진)
4. 선물 거래 활성화 확인
5. 프로그램 재시작

**중요**: 이것은 코드 문제가 아닌 OKX 계정 설정 문제입니다. 반드시 OKX 웹사이트에서 계좌 모드를 변경해야 합니다.

#### 문제 3: 심볼 조회 오류 - "does not have market symbol"
**증상**:
```
ERROR | okx does not have market symbol KAVA/USDT:USDT
```

**원인**: 
- OKX가 해당 코인의 선물 거래를 지원하지 않음
- 또는 심볼 표기법이 다름

**해결**:
- OKX 웹사이트에서 해당 코인의 선물 거래 지원 여부 확인
- 지원하지 않는 코인은 거래 목록에서 제외
- 로그 레벨을 INFO로 설정하여 경고만 표시 (`log_level: "INFO"`)

#### 문제 4: 계좌 잔고 조회 실패
**증상**:
```
WARNING | 계좌 잔고 조회 실패: {}
```

**원인**: 위의 1~3번 문제로 인한 연쇄 오류

**해결**: 위의 문제들을 순차적으로 해결하면 자동으로 해결됩니다.

### Bybit / Bitget 거래소
- **마진 타입 설정**: v3.7.8+에서 방어적 코딩이 적용되어 레버리지 파라미터를 자동으로 전달합니다.
- 특별한 계좌 모드 설정은 필요하지 않습니다.

## 5) 개발 팁
- Pylance 경고가 남아도 런타임에는 문제 없을 수 있습니다. 다만, Optional 가드와 타입 정규화를 순차 반영 중입니다.
- WebSocket API 호출은 `subscribe_symbol/unsubscribe_symbol`, 데이터 조회는 `get_latest_*` 사용을 권장합니다.
 - 로그 소음 최소화: API 키 없는 거래소는 비활성 처리되며, 무효 심볼/구독은 생성되지 않습니다.

---

## 6) Pylance/타입 오류 모음과 빠른 해결

증상과 원인 → 해결 패턴:

- 오류: "websocket_manager는 None의 알려진 속성이 아님"
  - 원인: `self.binance_client.websocket_manager` 직접 접근
  - 해결: 지역 변수 + getattr 가드
    ```python
    client = getattr(self, 'binance_client', None)
    ws = getattr(client, 'websocket_manager', None) if client else None
    if not ws: return
    ```

- 오류: "str 클래스의 get 특성에 액세스할 수 없음"
  - 원인: `selected_coins`에 문자열과 dict가 혼재
  - 해결: 루프 시작 시 dict 정규화
    ```python
    c = coin if isinstance(coin, dict) else {'symbol': str(coin)}
    symbol = str(c.get('symbol', 'N/A'))
    ```

- 오류: "변수가 바인딩되지 않았을 수 있습니다(coin_symbol)"
  - 원인: try 블록 내부에서만 심볼 계산 후 except에서 사용
  - 해결: try 바깥에서 기본값 초기화
    ```python
    coin_symbol = 'UNKNOWN'
    try:
        coin_symbol = ...
    except Exception:
        self.logger.error(f'[{coin_symbol}] ...')
    ```

- 오류: Tkinter "invalid command name ...!text" (destroyed widget)
  - 원인: 메인루프 종료 후 위젯에 write
  - 해결: 위젯 생존 체크 + 안전 업데이트 헬퍼 사용
    ```python
    def _widget_alive(w):
        try:
            return w and getattr(w, 'winfo_exists', lambda: 0)() == 1
        except Exception:
            return False
    def _safe_text_set(w, text):
        if _widget_alive(w) and hasattr(w, 'configure'):
            w.configure(text=text)
    ```

- 팁: `trading_worker.running` 같은 플래그는 안전 추출 후 사용
  ```python
  run_flag = bool(getattr(getattr(self, 'trading_worker', None), 'running', True))
  if not run_flag:
      return
  ```

자세한 코딩 규칙은 `docs/TYPE_GUIDE.md`의 "필수 패턴 모음(회귀 방지)"를 참고하세요.

---

## 7) 초기 실행 과정 및 문제 해결 (2025-10-21)

### 초기 실행 과정 분석

#### 1단계: 사용자 상태 관리 및 경로 설정
```
2025-10-21 03:30:28 | INFO - 사용자 상태 관리 모듈 로드 완료 (ex=global)
2025-10-21 03:30:28 | INFO - 경로 일관성 디버깅 시작 (ex=global)
2025-10-21 03:30:28 | INFO - 현재 사용자 계정: nwsoft (ex=global)
2025-10-21 03:30:28 | INFO - 실제 파일 존재 여부 확인 (ex=global)
```

**확인 사항**:
- 사용자 계정 설정: `nwsoft`
- 데이터 디렉토리: `C:\Users\super\SynologyDrive\Works\크몽용바이낸스신버전\noahai_client\data\nwsoft`
- 설정 파일 존재 여부: `settings.json`, `token.json`, `theme_config.json`

#### 2단계: 로그인 및 인증
```
2025-10-21 03:30:30 | INFO - 로그인 성공, 백엔드 승인 완료 (ex=global)
2025-10-21 03:30:30 | INFO - on_login_success: 초기화 시작 (ex=global)
```

**확인 사항**:
- API 토큰 유효성: `access_token` 길이 164자
- 사용자 정보 설정: `nwsoft@hotmail.com`
- OpenAI API Key 상태: `sk-p***rH8A`

#### 3단계: 거래소 연결 및 WebSocket 설정
```
2025-10-21 03:30:30 | INFO - 🔄 WebSocket 연결을 백그라운드에서 시작합니다... (ex=binance)
2025-10-21 03:30:30 | INFO - ✅ Binance Futures WebSocket client connected successfully (ex=binance)
2025-10-21 03:30:31 | INFO - 바이낸스 선물 연결 성공 (python-binance) (ex=binance)
```

**확인 사항**:
- WebSocket 연결 상태: 성공
- 거래소 선택: `binance`
- API 클라이언트 초기화: 완료

#### 4단계: 트레이딩 컴포넌트 초기화
```
2025-10-21 03:30:32 | INFO - AI Manager 초기화 완료 - 모델: gpt-3.5-turbo (ex=global)
2025-10-21 03:30:32 | INFO - UnifiedTrader 초기화 완료 - 현재 거래소: binance (ex=binance)
2025-10-21 03:30:32 | INFO - ✅ TP/SL 설정 정규화 완료: tp=0.001800, sl=0.002000 (ex=binance)
2025-10-21 03:30:32 | INFO - Trader 초기화 완료 (고급 주문 기능 포함) (ex=binance)
```

**확인 사항**:
- AI Manager: `gpt-3.5-turbo` 모델
- UnifiedTrader: 바이낸스 거래소 설정
- TP/SL 설정: `tp=0.001800`, `sl=0.002000`
- Trader: 고급 주문 기능 포함

#### 5단계: 대시보드 초기화
```
2025-10-21 03:30:34 | INFO - Modern Dashboard 초기화 완료 (ex=global)
2025-10-21 03:30:34 | INFO - 대시보드 컴포넌트 설정 완료 (ex=global)
2025-10-21 03:30:34 | INFO - show_dashboard: mainloop 진입 (ex=global)
```

**확인 사항**:
- 대시보드 창 생성: `1400x900+580+270`
- 컴포넌트 연결: 거래소 관리자, API 신호 관리자
- 메인 루프 진입: 정상

### 해결된 문제: Trader 클래스 AttributeError

#### 문제 상황
```
'Trader' object has no attribute '_load_trade_stats_from_db'
'NoahAIClient' object has no attribute 'trader'
```

#### 원인 분석
1. **누락된 메서드**: `Trader` 클래스에 `_load_trade_stats_from_db` 메서드가 없었음
2. **누락된 메서드**: `Trader` 클래스에 `_restore_positions_from_exchange` 메서드가 없었음
3. **초기화 실패**: `Trader.__init__`에서 누락된 메서드 호출로 인한 `AttributeError`
4. **연쇄 실패**: `trader` 객체 초기화 실패로 인한 `NoahAIClient.trader` 속성 누락

#### 해결 과정

**1단계: 메서드 추가**
```python
# trading/trader.py에 추가된 메서드들
def _load_trade_stats_from_db(self):
    """DB에서 바이낸스 거래 통계 로드"""
    # recorder를 통해 DB에서 바이낸스 거래 통계 로드
    # self.trade_stats 업데이트

def _restore_positions_from_exchange(self):
    """거래소에서 실제 포지션 조회하여 복구"""
    # binance_client.get_positions() 호출
    # Position 객체 생성 및 self.active_positions에 추가
```

**2단계: 아키텍처 검증**
- **바이낸스**: `Trader` 클래스에서 처리 (올바름)
- **CCXT 거래소**: `UnifiedTrader` 클래스에서 처리 (올바름)
- **문서 일치**: `docs/TRADING_STATS_PERSISTENCE_SYSTEM.md`에 명시된 설계 의도

**3단계: 기능 검증**
- **거래 통계 영구 저장**: DB에서 로드하여 메모리에 복구
- **포지션 복구**: 실제 거래소에서 포지션 조회하여 복구
- **통계 관리**: 거래 통계 업데이트 및 DB 저장

#### 해결 결과
✅ **모든 초기화 정상 완료**: 로그에서 확인된 정상 초기화 과정
✅ **AttributeError 해결**: 누락된 메서드 추가로 해결
✅ **아키텍처 일치**: 바이낸스는 `Trader`, CCXT는 `UnifiedTrader`에서 처리
✅ **기능 완성**: 거래 통계 영구 저장 및 포지션 복구 시스템 완성

### 예방 조치

1. **문서 기반 개발**: 새로운 기능 추가 시 관련 문서 먼저 확인
2. **아키텍처 준수**: 바이낸스와 CCXT 거래소 간 명확한 역할 분리
3. **초기화 검증**: `__init__` 메서드에서 호출하는 모든 메서드 존재 여부 확인
4. **로그 모니터링**: 초기 실행 과정의 각 단계별 로그 확인

### 참고 문서
- `docs/TRADING_STATS_PERSISTENCE_SYSTEM.md`: 거래 통계 영구 저장 시스템
- `docs/ARCHITECTURE.md`: 시스템 아키텍처 및 역할 분리
- `docs/CHANGELOG.md`: 변경 이력 및 기능 추가 기록

---

## 8) 추가 AttributeError 해결 (2025-10-21)

### 해결된 문제: get_active_positions 및 stop_trading 메서드 누락

#### 문제 상황
```
'Trader' object has no attribute 'get_active_positions'
'Trader' object has no attribute 'stop_trading'
거래 사이클 실행 오류: 'Trader' object has no attribute 'get_active_positions'
```

#### 원인 분석
1. **누락된 메서드**: `Trader` 클래스에 `get_active_positions` 메서드가 없었음
2. **누락된 메서드**: `Trader` 클래스에 `stop_trading` 메서드가 없었음
3. **아키텍처 불일치**: `UnifiedTrader`에는 있지만 `Trader`에는 없는 메서드들
4. **거래 제어 실패**: 거래 중지 요청 시 메서드 누락으로 인한 오류

#### 해결 과정

**1단계: 메서드 추가**
```python
# trading/trader.py에 추가된 메서드들
def get_active_positions(self) -> Dict[str, Position]:
    """활성 포지션 조회 (바이낸스용)"""
    return self.active_positions

def stop_trading(self):
    """바이낸스 거래 중지"""
    # 모든 모니터링 플래그 중지
    # 모든 모니터링 스레드 종료 대기
    # 모니터링 관련 데이터 정리
```

**2단계: 아키텍처 일치**
- **바이낸스**: `Trader` 클래스에서 처리 (올바름)
- **CCXT 거래소**: `UnifiedTrader` 클래스에서 처리 (올바름)
- **메서드 일치**: 두 클래스 모두 동일한 인터페이스 제공

**3단계: 기능 검증**
- **포지션 조회**: 활성 포지션 정보 반환
- **거래 중지**: 모든 모니터링 스레드 안전하게 종료
- **데이터 정리**: 메모리 누수 방지

#### 해결 결과
✅ **거래 사이클 정상 실행**: `get_active_positions` 메서드 추가로 해결
✅ **거래 중지 정상 작동**: `stop_trading` 메서드 추가로 해결
✅ **아키텍처 일치**: 바이낸스와 CCXT 거래소 간 일관된 인터페이스
✅ **안전한 종료**: 모든 스레드와 리소스 정리

#### 예방 조치
1. **인터페이스 일치**: 바이낸스와 CCXT 거래소 간 동일한 메서드 제공
2. **메서드 검증**: 새로운 기능 추가 시 모든 클래스에 필요한 메서드 확인
3. **아키텍처 준수**: 역할 분리 원칙에 따른 일관된 인터페이스 유지
4. **테스트 강화**: 거래 시작/중지 기능의 정상 작동 확인

#### 수정된 파일
- `trading/trader.py`: 누락된 메서드 추가
- `docs/TROUBLESHOOTING.md`: 문제 해결 가이드 추가
- `docs/CHANGELOG.md`: 변경 이력 기록
