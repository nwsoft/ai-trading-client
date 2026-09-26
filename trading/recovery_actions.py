"""Read-only next-step contract shared by every account/venue recovery job."""


def recovery_action(reason):
    if reason == 'history_api_permission_required':
        return {'kind':'history_permission_required','retry_without_new_evidence':False,
                'required_evidence':['read_order_history_permission'],
                'action_ko':'거래소가 과거 주문 조회 권한을 거절했습니다. 연결된 API 키의 조회 권한·허용 IP·API 버전을 확인하세요. 주문 권한을 늘릴 필요는 없습니다. 공식 체결 파일 가져오기도 이용할 수 있습니다.',
                'action_en':'Check order-history read permission, allowed IP and API version, or import the official statement. No additional order permission is needed.'}
    if reason == 'position_anchor_not_flat':
        return {'kind':'current_holding_requires_reconciliation','retry_without_new_evidence':False,
                'required_evidence':['current_quantity','complete_execution_and_transfer_history'],
                'action_ko':'현재 같은 종목을 보유하고 있어 과거 청산 구간을 분리하지 못했습니다. 매도를 요구하는 안내가 아닙니다. 실제 보유·주문·입출고 내역을 확인하고, 원본에서 청산 귀속이 확인되는 공식 파일을 가져오세요.',
                'action_en':'Current holdings prevent a flat-cycle proof; do not sell merely to recover records. Review holdings, orders and transfers and import original attribution evidence.'}
    if reason == 'open_position_history_unsupported':
        return {'kind':'open_position_evidence_required','retry_without_new_evidence':False,
                'required_evidence':['entry_order_id','current_positions','closing_executions_and_fees'],
                'action_ko':'이 기관의 API만으로 청산 주문을 찾지 못했습니다. 공식 체결 내역 파일 가져오기에서 전체 진입·청산 구간 CSV를 선택하고 열·시간대·본인 계좌를 확인한 뒤 저장·점검하세요. 부분 기간이나 혼합 보유분은 확정하지 않습니다. 잔고 0을 손익 0으로 바꾸지 않습니다.',
                'action_en':'The venue API cannot discover this missing close. Import the complete official CSV cycle, review columns, timezone and account, then run recovery. Partial periods or mixed ownership remain unresolved; flat is not zero PnL.'}
    if reason == 'execution_time_outside_position':
        return {'kind':'execution_time_review_required','retry_without_new_evidence':False,
                'required_evidence':['original_entry_time','provider_execution_time_and_timezone'],
                'action_ko':'연결된 체결 시각이 진입 전이거나 현재보다 미래입니다. 원본 진입 시각과 거래소 체결 시각·시간대, PC 시계를 확인하세요. 시각을 임의로 바꾸거나 같은 자료로 반복 복구하지 마세요.',
                'action_en':'The linked execution predates entry or is in the future. Check original entry/provider times, timezone and PC clock; do not guess a replacement timestamp.'}
    if reason in {'provider_history_collecting','provider_query_failed','position_anchor_changed','provider_connection_required','credential_scope_changed','execution_storage_incomplete'}:
        return {'kind':'retry_after_check','retry_without_new_evidence':True,
                'required_evidence':['provider_connection','complete_history_pages','stable_position_snapshot'],
                'action_ko':'기관 연결·조회 상태를 확인하세요. 수집 중이면 완료를 기다리고, 조회 중 포지션이 바뀌었다면 신규 진입을 일시정지한 뒤 이어서 점검하세요.',
                'action_en':'Check provider connectivity and collection status. Wait for collection; if positions changed, pause new entries before continuing.'}
    if reason == 'execution_mode_evidence_missing':
        return {'kind':'original_evidence_required','retry_without_new_evidence':False,
                'required_evidence':['original_session_mode','entry_order_id','provider_execution_history'],
                'action_ko':'해당 거래 시각의 원본 실행 로그에서 PAPER/LIVE와 진입 주문 번호를 확인해야 합니다. 원본 로그·거래소 체결 내역을 보존하세요. 현재 설정값으로 과거 모드를 추정하지 않으며 반복 점검만으로 해결되지 않습니다.',
                'action_en':'Preserve original session logs and provider executions proving mode and entry order. Current settings cannot prove historical mode; retrying alone cannot resolve this.'}
    if reason in {'position_cycle_ambiguous','exit_lot_allocation_required','entry_order_allocation_required','order_attribution_conflict','partial_or_quantity_mismatch'}:
        return {'kind':'allocation_review_required','retry_without_new_evidence':False,
                'required_evidence':['all_entry_exit_fill_ids','fill_quantities_prices_fees','manual_trade_or_transfer_history'],
                'action_ko':'동일 종목의 전체 진입·청산 체결 번호, 수량·가격·수수료와 수동 거래/입출고 내역이 필요합니다. 섞인 거래의 배분을 확정하지 못한 상태입니다. 자료를 보존해 지원 점검을 요청하세요. 현재 자동 배분 지원 밖인 경우 반복 실행으로 해결되지 않습니다.',
                'action_en':'Preserve all entry/exit fill IDs, quantities, prices, fees and manual trades/transfers. Allocation is unresolved; request review. Unsupported allocation is not fixed by repeated runs.'}
    if reason in {'provider_pnl_or_cost_evidence_incomplete','provider_realized_pnl_unavailable','fee_or_fill_data_incomplete','entry_fee_evidence_missing','entry_fee_conversion_required','income_reconciliation_required','cycle_gross_reconciliation_required'}:
        return {'kind':'settlement_evidence_required','retry_without_new_evidence':False,
                'required_evidence':['provider_realized_pnl','entry_exit_fees_and_currency','funding_or_settlement_history'],
                'action_ko':'거래소의 실현손익·진입/청산 수수료와 통화·정산 내역이 필요합니다. 정산 지연이면 반영 후 점검하세요. 자료가 있는데 불일치하면 내역을 보존해 지원 점검을 요청하세요. 누락 금액을 0으로 처리하지 않습니다.',
                'action_en':'Provider realized PnL, entry/exit fees and currencies, and settlement history are needed. Retry after settlement; preserve conflicting evidence for review. Missing amounts are not zero.'}
    return {'kind':'history_evidence_required','retry_without_new_evidence':False,
            'required_evidence':['entry_exit_order_ids','complete_provider_execution_history','original_trade_time_and_mode'],
            'action_ko':'진입 주문 번호와 전체 체결 구간, 원본 시각·모드를 확인하세요. API 보존기간 밖이거나 조회 미지원이면 공식 체결 CSV를 앱의 파일 가져오기에서 검토·저장하고 다시 점검하세요. 거래가 섞였거나 필요한 열이 없으면 적용하지 않으며 같은 자료의 반복 실행으로 해결되지 않습니다.',
            'action_en':'Check entry order, complete execution coverage and original time/mode. When API history is unavailable, review and import the official CSV in the app and rerun recovery. Mixed trades or missing fields are not certified.'}
