"""Read-only evidence of the existing short-window classifier, not a new policy."""
import math
import time


def record_fast_metrics(owner, source, **metrics):
    try:
        clean = {key:value for key,value in metrics.items()
                 if isinstance(value,(str,int,float)) and not isinstance(value,bool)
                 and (not isinstance(value,float) or math.isfinite(value))}
        clean['calculation_at'] = time.time()
        rows = getattr(owner,'_fast_regime_diagnostics',None)
        if not isinstance(rows,dict):rows={};owner._fast_regime_diagnostics=rows
        if len(rows)<11 or source in rows:rows[source]=clean
    except Exception:
        return
