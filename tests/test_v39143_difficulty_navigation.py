from pathlib import Path


def test_difficulty_target_and_saved_refresh_are_wired_without_remount():
    studio = Path('webui/src/components/StrategyStudio.tsx').read_text(encoding='utf-8')
    app = Path('webui/src/App.tsx').read_text(encoding='utf-8')
    settings = Path('webui/src/components/SettingsCenter.tsx').read_text(encoding='utf-8')
    assert 'onClick={onOpenDifficultySettings ?? onOpenSettings}' in studio
    assert '}, [client, settingsRevision]);' in studio
    assert 'settingsRevision={settingsRevision}' in app
    assert 'setSettingsInitialField("ai_custom_features.profile")' in app
    assert 'setSettingsInitialField(undefined)' in app
    assert 'initialField === STRATEGY_DIFFICULTY_PATH ? "ai_engine" : "general"' in settings
    assert 'target.scrollIntoView({ block: \'center\' })' in settings
    assert "focus({ preventScroll: true })" in settings
    assert 'field.path === STRATEGY_DIFFICULTY_PATH ? strategyDifficultyLabel(option)' in settings
    assert 'next.save_receipt?.verified' in settings
    assert 'key={settingsRevision}' not in app


def test_difficulty_label_mapping_is_shared_and_display_only():
    source = Path('webui/src/strategyDifficulty.ts').read_text(encoding='utf-8')
    for pair in ["[1, '초보자', 'Beginner']", "[2, '일반', 'Standard']", "[3, '고급', 'Advanced']", "[4, '실험실', 'Lab']"]:
        assert pair in source
    assert 'fetch(' not in source
    assert 'strategyDifficultyLabel(featureProfile)' in Path('webui/src/components/StrategyStudio.tsx').read_text(encoding='utf-8')
