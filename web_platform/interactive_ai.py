"""Explicit, budgeted external AI calls for the Web UI.

Automatic trading inference keeps its existing governor.  This module owns a
separate interactive ledger so a user question cannot consume trading budget
and a background loop cannot masquerade as a user-requested analysis.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from trading.ai.provider_catalog import PRICE_SNAPSHOT_AS_OF, provider_price_rows
from trading.ai.provider_router import AIProviderRouter


class InteractiveProviderFailure(RuntimeError):
    """Preserve invocation identity without leaking provider response bodies."""

    def __init__(self, *, provider: str, model: str, code: str, status_code=None):
        self.provider = provider
        self.model = model
        self.code = code
        self.status_code = status_code
        self.provider_called = True
        super().__init__("AI 제공사가 빈 응답을 반환했습니다." if code == "empty_response" else f"interactive_provider_failed:{code}")


class InteractiveAIService:
    def __init__(
        self,
        *,
        data_dir: Path,
        router_factory: Callable[..., Any] = AIProviderRouter.from_settings,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.data_dir = Path(data_dir)
        self.router_factory = router_factory
        self.clock = clock
        self.usage_path = self.data_dir / "ai_interactive_usage.json"
        self.cache_path = self.data_dir / "cache" / "ai_interactive_cache.json"
        self._lock = threading.RLock()

    def _now_parts(self) -> tuple[float, str, str]:
        now = float(self.clock())
        stamp = datetime.fromtimestamp(now, timezone.utc)
        return now, stamp.strftime("%Y-%m-%d"), stamp.strftime("%Y-%m")

    @staticmethod
    def _read(path: Path, default: dict[str, Any]) -> dict[str, Any]:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else dict(default)
        except (OSError, ValueError, json.JSONDecodeError):
            return dict(default)

    @staticmethod
    def _write(path: Path, value: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, path)

    @staticmethod
    def _policy(settings: dict[str, Any]) -> dict[str, int]:
        cfg = dict(settings.get("ai_cost_control") or {})
        return {
            "daily": max(1, min(int(cfg.get("max_daily_interactive_calls", 30) or 30), 1000)),
            "monthly": max(1, min(int(cfg.get("max_monthly_interactive_calls", 500) or 500), 30000)),
            "cache_sec": max(0, min(int(cfg.get("interactive_cache_sec", 900) or 0), 86400)),
        }

    def status(self, settings: dict[str, Any]) -> dict[str, Any]:
        now, day, month = self._now_parts()
        policy = self._policy(settings)
        usage = self._read(self.usage_path, {"daily": {}, "monthly": {}, "tokens": {}, "denied": {}})
        stamp = datetime.fromtimestamp(now, timezone.utc)
        next_daily = datetime(stamp.year, stamp.month, stamp.day, tzinfo=timezone.utc) + timedelta(days=1)
        if stamp.month == 12:
            next_monthly = datetime(stamp.year + 1, 1, 1, tzinfo=timezone.utc)
        else:
            next_monthly = datetime(stamp.year, stamp.month + 1, 1, tzinfo=timezone.utc)
        daily_used = int((usage.get("daily") or {}).get(day, 0) or 0)
        monthly_used = int((usage.get("monthly") or {}).get(month, 0) or 0)
        completed_today = int(((usage.get("completed_calls") or {}).get("daily") or {}).get(day, 0) or 0)
        completed_month = int(((usage.get("completed_calls") or {}).get("monthly") or {}).get(month, 0) or 0)
        priced_today = int(((usage.get("priced_calls") or {}).get("daily") or {}).get(day, 0) or 0)
        priced_month = int(((usage.get("priced_calls") or {}).get("monthly") or {}).get(month, 0) or 0)
        return {
            "daily_used": daily_used,
            "daily_limit": policy["daily"],
            "monthly_used": monthly_used,
            "monthly_limit": policy["monthly"],
            "daily_exhausted": daily_used >= policy["daily"],
            "monthly_exhausted": monthly_used >= policy["monthly"],
            "period_timezone": "UTC",
            "next_daily_reset_at": next_daily.isoformat(),
            "next_monthly_reset_at": next_monthly.isoformat(),
            "cache_sec": policy["cache_sec"],
            "token_usage": dict(usage.get("tokens") or {}),
            "estimated_cost_usd": {
                "today": round(float(((usage.get("costs") or {}).get("daily") or {}).get(day, 0) or 0), 8),
                "month": round(float(((usage.get("costs") or {}).get("monthly") or {}).get(month, 0) or 0), 8),
                "total": round(float((usage.get("costs") or {}).get("total", 0) or 0), 8),
            },
            "completed_usage_calls": {
                "today": completed_today,
                "month": completed_month,
            },
            "priced_calls": {"today": priced_today, "month": priced_month},
            "cost_unavailable_calls": {
                "today": max(0, completed_today - priced_today),
                "month": max(0, completed_month - priced_month),
            },
            "incomplete_attempts": {
                "today": max(0, daily_used - completed_today),
                "month": max(0, monthly_used - completed_month),
            },
            "usage_by_role": dict(usage.get("usage_by_role") or {}),
            "usage_by_model": dict(usage.get("usage_by_model") or {}),
            "usage_by_privacy_route": dict(usage.get("usage_by_privacy_route") or {}),
            "pricing_as_of": PRICE_SNAPSHOT_AS_OF,
        }

    def reserve_operation(self, settings: dict[str, Any], *, role: str) -> dict[str, Any]:
        """Reserve exactly one explicit provider request before it is sent."""
        _, day, month = self._now_parts()
        policy = self._policy(settings)
        with self._lock:
            ledger = self._read(self.usage_path, {"daily": {}, "monthly": {}, "tokens": {}, "denied": {}})
            daily = int((ledger.get("daily") or {}).get(day, 0) or 0)
            monthly = int((ledger.get("monthly") or {}).get(month, 0) or 0)
            if daily >= policy["daily"] or monthly >= policy["monthly"]:
                denied = ledger.setdefault("denied", {})
                key = f"{day}:{str(role or 'interactive')}"
                denied[key] = int(denied.get(key, 0) or 0) + 1
                self._write(self.usage_path, ledger)
                raise RuntimeError("interactive_ai_budget_exceeded")
            ledger.setdefault("daily", {})[day] = daily + 1
            ledger.setdefault("monthly", {})[month] = monthly + 1
            self._write(self.usage_path, ledger)
        return {"allowed": True, "daily": daily + 1, "monthly": monthly + 1, "role": role}

    def budgeted_client(
        self,
        settings: dict[str, Any],
        client: Any,
        *,
        role: str,
        provider: str = "",
        model: str = "",
    ) -> Any:
        service = self

        class BudgetedClient:
            def _record(self, *, operation_role: str) -> None:
                usage = dict(client.get_last_usage() or {}) if hasattr(client, "get_last_usage") else {}
                service.record_usage(
                    str(provider or getattr(client, "provider", "unknown") or "unknown"),
                    usage,
                    model=str(usage.get("model") or model or getattr(client, "model", "") or ""),
                    role=operation_role,
                )

            def is_ready(self) -> bool:
                return bool(client and client.is_ready())

            def chat_json(self, *args: Any, **kwargs: Any) -> Any:
                service.reserve_operation(settings, role=role)
                result = client.chat_json(*args, **kwargs)
                if result is not None:
                    self._record(operation_role=role)
                return result

            def vision_json(self, *args: Any, **kwargs: Any) -> Any:
                operation_role = f"{role}_vision"
                service.reserve_operation(settings, role=operation_role)
                result = client.vision_json(*args, **kwargs)
                if result is not None:
                    self._record(operation_role=operation_role)
                return result

            def transcribe_audio(self, *args: Any, **kwargs: Any) -> Any:
                operation_role = f"{role}_transcription"
                service.reserve_operation(settings, role=operation_role)
                result = client.transcribe_audio(*args, **kwargs)
                if result:
                    self._record(operation_role=operation_role)
                return result

            def get_last_usage(self) -> dict[str, Any]:
                return dict(client.get_last_usage() or {}) if hasattr(client, "get_last_usage") else {}

        return BudgetedClient()

    def record_usage(
        self,
        provider: str,
        usage: dict[str, Any],
        *,
        model: str = "",
        role: str = "interactive",
        privacy_route: str = "protected_default",
    ) -> None:
        """Add one completed explicit provider call to the local cost ledger."""
        normalized = str(provider or "unknown").strip().lower()
        # The provider response is the execution fact.  A configured alias is
        # only the request intent and must not overwrite a returned snapshot or
        # resolved model ID in cost/usage attribution.
        normalized_model = str(usage.get("model") or model or "unknown").strip() or "unknown"
        normalized_role = str(role or "interactive").strip() or "interactive"
        normalized_privacy_route = str(privacy_route or "protected_default").strip() or "protected_default"
        _, day, month = self._now_parts()
        estimated_cost = self._estimate_cost(normalized, normalized_model, usage)
        with self._lock:
            ledger = self._read(self.usage_path, {"daily": {}, "monthly": {}, "tokens": {}, "denied": {}})
            tokens = ledger.setdefault("tokens", {})
            provider_tokens = dict(tokens.get(normalized) or {})
            for key in ("input_tokens", "cached_input_tokens", "output_tokens", "total_tokens"):
                provider_tokens[key] = int(provider_tokens.get(key, 0) or 0) + int(usage.get(key, 0) or 0)
            tokens[normalized] = provider_tokens
            completed = ledger.setdefault("completed_calls", {})
            completed.setdefault("daily", {})[day] = int((completed.get("daily") or {}).get(day, 0) or 0) + 1
            completed.setdefault("monthly", {})[month] = int((completed.get("monthly") or {}).get(month, 0) or 0) + 1
            for bucket_name, bucket_key in (("usage_by_role", normalized_role), ("usage_by_model", f"{normalized}:{normalized_model}")):
                bucket = ledger.setdefault(bucket_name, {})
                row = dict(bucket.get(bucket_key) or {})
                row["calls"] = int(row.get("calls", 0) or 0) + 1
                row["total_tokens"] = int(row.get("total_tokens", 0) or 0) + int(usage.get("total_tokens", 0) or 0)
                if estimated_cost is None:
                    row["unpriced_calls"] = int(row.get("unpriced_calls", 0) or 0) + 1
                else:
                    row["estimated_cost_usd"] = round(float(row.get("estimated_cost_usd", 0) or 0) + estimated_cost, 8)
                bucket[bucket_key] = row
            route_bucket = ledger.setdefault("usage_by_privacy_route", {})
            route_row = dict(route_bucket.get(normalized_privacy_route) or {})
            route_row["calls"] = int(route_row.get("calls", 0) or 0) + 1
            route_row["total_tokens"] = int(route_row.get("total_tokens", 0) or 0) + int(usage.get("total_tokens", 0) or 0)
            route_bucket[normalized_privacy_route] = route_row
            if estimated_cost is not None:
                priced = ledger.setdefault("priced_calls", {})
                priced.setdefault("daily", {})[day] = int((priced.get("daily") or {}).get(day, 0) or 0) + 1
                priced.setdefault("monthly", {})[month] = int((priced.get("monthly") or {}).get(month, 0) or 0) + 1
                costs = ledger.setdefault("costs", {})
                costs.setdefault("daily", {})[day] = round(float((costs.get("daily") or {}).get(day, 0) or 0) + estimated_cost, 8)
                costs.setdefault("monthly", {})[month] = round(float((costs.get("monthly") or {}).get(month, 0) or 0) + estimated_cost, 8)
                costs["total"] = round(float(costs.get("total", 0) or 0) + estimated_cost, 8)
            self._write(self.usage_path, ledger)

    @staticmethod
    def _cache_key(*, provider: str, model: str, workload: str, prompt: str, context: str, privacy_route: str = "protected_default") -> str:
        payload = json.dumps(
            {"provider": provider, "model": model, "workload": workload, "prompt": prompt, "context": context, "privacy_route": privacy_route},
            ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @staticmethod
    def _estimate_cost(provider: str, model: str, usage: dict[str, Any]) -> float | None:
        rows = provider_price_rows(provider)
        row = next((item for item in rows if str(item.get("model")) == model), None)
        if not row or row.get("input") is None or row.get("output") is None:
            return None
        # Some providers and older adapters return a successful response
        # without token usage.  Unknown usage is not an exact zero-dollar call.
        # A total-only counter cannot be split across different input/output
        # prices.  Treat it as unavailable rather than inventing a zero-dollar
        # estimate or guessing the split.
        if not any(
            int(usage.get(key, 0) or 0) > 0
            for key in ("input_tokens", "cached_input_tokens", "output_tokens")
        ):
            return None
        input_tokens = int(usage.get("input_tokens", 0) or 0)
        cached_tokens = min(input_tokens, int(usage.get("cached_input_tokens", 0) or 0))
        output_tokens = int(usage.get("output_tokens", 0) or 0)
        # Cached pricing differs by provider and is not consistently available;
        # count it as ordinary input so this estimate never understates by design.
        billable_input = input_tokens if input_tokens else cached_tokens
        return round((billable_input * float(row["input"]) + output_tokens * float(row["output"])) / 1_000_000, 8)

    def ask(
        self,
        *,
        settings: dict[str, Any],
        workload: str,
        question: str,
        context: str,
        system_prompt: str,
        max_tokens: int,
        privacy_class: str = "private",
    ) -> dict[str, Any]:
        normalized_privacy = "public_general" if str(privacy_class).strip().lower() == "public_general" else "private"
        if normalized_privacy == "public_general":
            router = self.router_factory(settings, workload=workload, privacy_class=normalized_privacy)
        else:
            # Keep the legacy two-argument factory contract for runtime bridges
            # and tests. All unspecified calls remain on the protected path.
            router = self.router_factory(settings, workload=workload)
        provider = str(router.spec.provider)
        model = str(router.adapter.model)
        privacy_route = str(getattr(router, "privacy_route", "protected_default") or "protected_default")
        privacy_reason = str(getattr(router, "privacy_reason", "기본 보호 경로") or "기본 보호 경로")
        if not router.adapter.is_ready():
            raise ValueError(f"{provider} API 자격증명이 설정되지 않았습니다.")
        now, day, month = self._now_parts()
        policy = self._policy(settings)
        cache_key = self._cache_key(provider=provider, model=model, workload=workload, prompt=question, context=context, privacy_route=privacy_route)
        with self._lock:
            cache = self._read(self.cache_path, {"entries": {}})
            cached = dict((cache.get("entries") or {}).get(cache_key) or {})
            if cached and now - float(cached.get("created_at_epoch", 0) or 0) <= policy["cache_sec"]:
                return {**cached["result"], "cache_hit": True, "budget": self.status(settings)}

            self.reserve_operation(settings, role=workload)

        response = router.adapter.chat_text(
            system_prompt,
            f"사용자 질문:\n{question}\n\n검증된 계정 컨텍스트:\n{context[:16000]}",
            max_tokens=max(200, min(int(max_tokens), 4000)),
        )
        if not response.ok:
            error = response.error
            raise InteractiveProviderFailure(provider=provider, model=model,
                                             code=str(error.code) if error else "no_response",
                                             status_code=error.status_code if error else None)
        content = str(response.content or "").strip()
        if not content:
            # A transport-level success with no user-visible content is not a
            # successful answer.  Never cache it as one; the application layer
            # can fall back to the versioned local product knowledge instead.
            raise InteractiveProviderFailure(provider=provider, model=model, code="empty_response")
        usage = dict(response.usage or {})
        estimated_cost = self._estimate_cost(response.provider, response.model, usage)
        result = {
            "answer": content,
            "provider_called": True,
            "provider": response.provider,
            "model": response.model,
            "usage": usage,
            "estimated_cost_usd": estimated_cost,
            "pricing_as_of": PRICE_SNAPSHOT_AS_OF,
            "cache_hit": False,
            "data_scope": normalized_privacy,
            "privacy_route": privacy_route,
            "privacy_reason": privacy_reason,
        }
        self.record_usage(provider, usage, model=response.model, role=workload, privacy_route=privacy_route)
        with self._lock:
            if policy["cache_sec"] > 0:
                entries = cache.setdefault("entries", {})
                entries[cache_key] = {"created_at_epoch": now, "result": result}
                if len(entries) > 200:
                    oldest = sorted(entries, key=lambda key: float(entries[key].get("created_at_epoch", 0) or 0))[:-200]
                    for key in oldest:
                        entries.pop(key, None)
                self._write(self.cache_path, cache)
        result["budget"] = self.status(settings)
        return result
