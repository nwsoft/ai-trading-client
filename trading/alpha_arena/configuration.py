"""One credential/model contract for AlphaArena execution and explicit probes."""
from copy import deepcopy


def alpha_arena_ai_settings(settings: dict) -> dict:
    arena = dict(settings.get("alpha_arena") or {})
    engine = str(arena.get("engine") or "deepseek-v4-flash")
    if engine in {"deepseek-3.1", "deepseek-chat-v3.1", "deepseek-chat"}:
        engine = "deepseek-v4-flash"
    if engine not in {"deepseek-v4-flash", "deepseek-v4-pro"}:
        raise ValueError("AlphaArena는 현재 DeepSeek Flash/Pro만 지원합니다.")
    key = str(arena.get("deepseek_api_key") or "").strip()
    if not key:
        raise ValueError("설정 → AlphaArena에서 전용 DeepSeek API 키를 저장하세요.")
    routed = deepcopy(settings)
    # Never fall back to a general or public-sharing account credential.
    routed["ai_provider"] = "deepseek"
    routed["ai_credentials"] = {"deepseek": {"api_key": key, "base_url": "https://api.deepseek.com"}}
    routed["ai_provider_profiles"] = {"analyst": {"provider": "deepseek", "model": engine}}
    routed["openai_api_key"] = ""
    routed["ai_data_routing"] = {"enabled": False}
    return routed
