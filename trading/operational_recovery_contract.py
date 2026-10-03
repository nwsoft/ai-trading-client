"""Known operational reasons and bounded actions. This module grants no orders."""
REGISTRY_VERSION='recovery-3923-1'
REGISTRY={
 'pnl_reconciliation_required':('손익 근거 미대조',['record_recovery','recheck'],'거래·수수료·손익 근거 대조 완료'),
 'return_evidence_required':('수익률 산정 근거 부족',['record_recovery','recheck'],'원금/수익률 원본 근거 확인'),
 'hard_stop_mdd_exceeded':('손실 보호 한도 초과',['paper_validation','review_strategy','recheck'],'손실 보호와 모든 위험 기준 재통과'),
 'win_rate_below_threshold':('승률 기준 미달',['review_policy','paper_validation','recheck'],'선택한 성과 정책과 손실 보호 충족'),
 'sharpe_below_threshold':('수익 변동 대비 성과 부족',['review_policy','paper_validation','recheck'],'선택한 성과 정책과 손실 보호 충족'),
 'mdd_above_threshold':('낙폭 기준 미달',['review_policy','paper_validation','recheck'],'선택한 성과 정책과 손실 보호 충족'),
 'expectancy_below_threshold':('거래당 기대 수익 기준 미달',['review_policy','paper_validation','recheck'],'선택한 성과 정책과 손실 보호 충족'),
 'walkforward_below_threshold':('거래 구간 안정성 기준 미달',['review_policy','paper_validation','recheck'],'선택한 성과 정책과 손실 보호 충족'),
 'market_data_stale':('시세 자료 오래됨',['review_connection','recheck'],'새 시세와 지연 기준 확인'),
 'connection_unavailable':('연결 확인 필요',['review_connection','recheck'],'해당 기관 인증과 읽기 연결 확인'),
 'account_permission_required':('계정 운용 권한 확인 필요',['review_permission'],'사용자가 계정 권한을 다시 확인'),
 'order_status_unknown':('주문 처리 결과 불명',['query_existing_order'],'기존 주문 상태 대조 전 재주문 금지'),
 'policy_inheritance_error':('정책 상속 설정 검토 필요',['preview_policy_repair','recheck'],'원본 백업·선택 차이 검토·재시작 후 실효 정책 대조'),
 'candidate_data_missing':('후보 판단 자료 부족',['review_data','recheck'],'필요 지표·시세 근거 충족'),
 'user_stopped':('사용자 정지',['user_start_confirmation'],'사용자의 별도 시작 지시'),
}


def recovery_contract(reasons):
    rows=[]
    for reason in dict.fromkeys(reasons or []):
        known=REGISTRY.get(reason)
        rows.append({'reason':reason,'known':known is not None,'title':known[0] if known else '미등록 원인 · 진단 자료 확인',
                     'allowed_actions':known[1] if known else ['export_diagnostic'],
                     'resume_condition':known[2] if known else '원인 확인과 해당 수정 검증 필요'})
    actions=sorted({a for row in rows for a in row['allowed_actions']})
    return {'version':REGISTRY_VERSION,'reasons':rows,'allowed_actions':actions,
            'automatic_local_recheck_allowed':bool(rows) and all(r['known'] and 'recheck' in r['allowed_actions'] for r in rows),
            'max_local_rechecks':3,'retry_seconds':[5,10,20],
            'automatic_live_resume':False,'raw_records_deleted':False,'credentials_changed':False,
            'note':'재진단은 현재 근거만 다시 계산합니다. 정책·원장 변경은 각 도구의 확인 절차를 거치며 주문 권한·보유 보호를 초기화하지 않습니다.'}
