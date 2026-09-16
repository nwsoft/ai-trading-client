const BASE_GUIDE = `[로그 레벨 의미]
- INFO: 정상 동작/진행 상황 안내
- WARNING: 즉시 중단은 아니지만 점검이 필요한 경고
- ERROR: 기능 실패 또는 예외 발생

[자주 나오는 항목]
- 거래소 연결/인증: API 키, 네트워크, 권한 문제 확인
- 주문/체결: 주문 요청, 체결 결과, 실패 사유
- 전략/분석: 신호 생성 이유, 임계값 변화, 리스크 판단
- 시스템: 스케줄러, 데이터 수집, 파일/DB I/O 상태

[초심자 추천 읽는 순서]
1. ERROR가 있는지 먼저 확인
2. WARNING 원인을 확인
3. 같은 시각의 INFO를 함께 읽어 전후 맥락 파악

[빠른 질문 예시 - AI 어시스턴트]
- '방금 ERROR 로그 원인과 조치 순서를 3단계로 알려줘'
- '이 경고가 주문 실패와 연관 있는지 로그 기준으로 설명해줘'
- '지금 상태에서 바로 확인할 설정 항목만 요약해줘'

자세한 운영 정책/용어는 인앱 매뉴얼의 '실시간 거래 로그' 관련 안내에서도 확인할 수 있습니다.`;

function contextualGuide(service: string, source: string) {
  if (!source || source === "all") {
    return `[전역 로그 질문 예시]
- '최근 ERROR만 거래소별로 묶어 우선순위 정리해줘'
- 'WARNING 중 즉시 조치가 필요한 항목만 추려줘'
- '서비스별(코인/증권) 공통 원인인지 분리해서 설명해줘'`;
  }
  if (service === "stock") {
    return `[증권 로그 질문 예시]
- '방금 주문 거부 원인을 계좌/시간/종목 조건 기준으로 설명해줘'
- '오늘 미체결 로그만 추려서 조치 순서 알려줘'
- '실주문 허용 설정과 연결 상태가 정상인지 점검해줘'`;
  }
  return `[코인 로그 질문 예시]
- '펀딩비/시장방향 로그와 진입 신호가 충돌했는지 점검해줘'
- '거래소 인증 오류가 재시도 가능한지 즉시 조치 순서 알려줘'
- '최근 청산 로그 기준으로 리스크 설정 조정 포인트를 알려줘'`;
}

export function LogHelpDialog({
  open,
  service,
  source = "all",
  onClose,
  onOpenManual,
}: {
  open: boolean;
  service: string;
  source?: string;
  onClose: () => void;
  onOpenManual: () => void;
}) {
  if (!open) return null;
  return <div className="log-help-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
    <section className="log-help-dialog" role="dialog" aria-modal="true" aria-labelledby="log-help-title">
      <h2 id="log-help-title">실시간 로그 해석 가이드</h2>
      <pre>{BASE_GUIDE}{"\n\n"}{contextualGuide(service, source)}</pre>
      <footer><button type="button" onClick={() => { onClose(); onOpenManual(); }}>사용자 매뉴얼(업데이트) 열기</button><button className="secondary-button" type="button" onClick={onClose}>닫기</button></footer>
    </section>
  </div>;
}
