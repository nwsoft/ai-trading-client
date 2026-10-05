"""Calendar-based availability check from explicitly supplied planning dates."""
from datetime import date
from calendar import monthrange


def availability(profile,months,terms,liquid=False):
    start=profile.get('planned_start_date');need=profile.get('use_date')
    start=date.fromisoformat(start) if start else None;need=date.fromisoformat(need) if need else None
    if start and need and need<start:raise ValueError('finance_use_date_before_start')
    if liquid:
        ready=terms.get('immediate_withdrawal_confirmed') is True
        return {'fits_use_date':True if ready else None,'available_on':start.isoformat() if ready and start else None,'basis':'즉시 인출 가능 여부를 확인한 입력. 실제 이체 한도·영업 시간은 별도 확인.'}
    maturity=None
    if start:
        total=start.year*12+start.month-1+int(months);year,month=divmod(total,12);month+=1
        maturity=date(year,month,min(start.day,monthrange(year,month)[1]))
    return {'fits_use_date':None if not need or not maturity else maturity<=need,'available_on':maturity.isoformat() if maturity else None,'basis':'직접 입력한 가입 예정일과 기간의 달력상 만기 가정. 휴일 처리·기관 실제 가입일은 별도 확인.'}
