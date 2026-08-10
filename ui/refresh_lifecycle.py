"""대시보드 반복 갱신의 Tk/CTk 가시성 생명주기."""

from __future__ import annotations

import time
from typing import Any, Callable, Optional


def schedule_visible_refresh(
    host: Any,
    owner_widget: Any,
    delay_ms: int,
    callback: Callable[[], Any],
) -> Optional[Any]:
    """숨김 중 API 호출을 멈추되 예약 생명주기는 유지한다.

    CustomTkinter 탭 전환 중 실제 선택 탭의 자식도 잠시 ``viewable=False``를
    반환할 수 있고, 일부 Windows 조합은 이후 Map 이벤트를 다시 보내지 않는다.
    이때 예약을 삭제하지 않고 2초 뒤 가시성만 재확인해 영구 정지를 막는다.
    """
    if owner_widget is None or callback is None:
        return None
    try:
        registry = getattr(owner_widget, "_noah_visible_refresh_registry", None)
        if not isinstance(registry, dict):
            registry = {}
            setattr(owner_widget, "_noah_visible_refresh_registry", registry)

        key = id(callback)
        state = registry.get(key)
        if state is None:
            state = {
                "job": None,
                "disposed": False,
                "hidden_retry_ms": 2000,
                "hidden_skips": 0,
                "last_run_monotonic": 0.0,
            }
            registry[key] = state

            def _run():
                state["job"] = None
                try:
                    if (
                        state["disposed"]
                        or getattr(host, "_is_destroying", False)
                        or not host.winfo_exists()
                        or not owner_widget.winfo_exists()
                    ):
                        return
                    if not owner_widget.winfo_viewable():
                        state["hidden_skips"] = int(state.get("hidden_skips", 0)) + 1
                        _queue(int(state.get("hidden_retry_ms", 2000)))
                        return
                except Exception:
                    return
                state["hidden_skips"] = 0
                state["last_run_monotonic"] = time.monotonic()
                callback()

            def _queue(delay=0):
                if state["disposed"] or state["job"] is not None:
                    return
                state["job"] = host.safe_after(max(0, int(delay)), _run)

            def _on_map(event=None):
                if event is not None and getattr(event, "widget", None) is not owner_widget:
                    return
                _queue(0)

            def _on_unmap(event=None):
                if event is not None and getattr(event, "widget", None) is not owner_widget:
                    return
                job_id = state.get("job")
                if job_id is not None:
                    try:
                        host.after_cancel(job_id)
                    except Exception:
                        pass
                    try:
                        host.after_jobs.remove(job_id)
                    except (ValueError, AttributeError):
                        pass
                state["job"] = None
                if not state.get("disposed", False):
                    _queue(int(state.get("hidden_retry_ms", 2000)))

            def _on_destroy(event=None):
                if event is not None and getattr(event, "widget", None) is not owner_widget:
                    return
                state["disposed"] = True
                _on_unmap()

            state["queue"] = _queue
            owner_widget.bind("<Map>", _on_map, add="+")
            owner_widget.bind("<Unmap>", _on_unmap, add="+")
            owner_widget.bind("<Destroy>", _on_destroy, add="+")

        queue_refresh = state.get("queue")
        if callable(queue_refresh):
            queue_refresh(delay_ms)
        return state.get("job")
    except Exception:
        return None
