import logging
import threading

from trading.ai.ai_manager import AIManager


def _manager():
    manager = AIManager.__new__(AIManager)
    manager._settings = {
        "ai_cost_control": {
            "pattern_similarity_cache_sec": 300,
            "pattern_similarity_retry_cooldown_sec": 120,
            "pattern_similarity_max_cache_entries": 10,
        }
    }
    manager._pattern_similarity_cache = {}
    manager._pattern_similarity_last_attempt = {}
    manager._pattern_similarity_lock = threading.RLock()
    manager.logger = logging.getLogger(__name__)
    manager._enabled_for_role = lambda role: True
    manager._compose_similarity_prompt = lambda symbol, signal, patterns: "prompt"
    return manager


def test_pattern_similarity_reuses_same_state_despite_request_timestamp():
    manager = _manager()
    calls = []

    def _chat(*args, **kwargs):
        calls.append((args, kwargs))
        return {"action": "PROCEED", "reason": "not similar"}

    manager._chat_json_for_role = _chat
    patterns = [{"id": 1, "result": "LOSS"}]

    first = manager.analyze_pattern_similarity(
        "BTCUSDT",
        {"signal_type": "LONG", "confidence": 0.8, "timestamp": "first"},
        patterns,
    )
    second = manager.analyze_pattern_similarity(
        "BTCUSDT",
        {"signal_type": "LONG", "confidence": 0.8, "timestamp": "second"},
        patterns,
    )

    assert first == second
    assert len(calls) == 1


def test_pattern_similarity_changed_signal_gets_new_evaluation():
    manager = _manager()
    calls = []
    manager._chat_json_for_role = lambda *args, **kwargs: (
        calls.append(args) or {"action": "PROCEED"}
    )
    patterns = [{"id": 1, "result": "LOSS"}]

    manager.analyze_pattern_similarity(
        "BTCUSDT", {"signal_type": "LONG", "confidence": 0.8}, patterns
    )
    manager.analyze_pattern_similarity(
        "BTCUSDT", {"signal_type": "SHORT", "confidence": 0.8}, patterns
    )

    assert len(calls) == 2


def test_pattern_similarity_failure_has_retry_cooldown():
    manager = _manager()
    calls = []
    manager._chat_json_for_role = lambda *args, **kwargs: calls.append(args)
    signal = {"signal_type": "LONG", "confidence": 0.8}
    patterns = [{"id": 1, "result": "LOSS"}]

    assert manager.analyze_pattern_similarity("BTCUSDT", signal, patterns) is None
    assert manager.analyze_pattern_similarity("BTCUSDT", signal, patterns) is None
    assert len(calls) == 1
