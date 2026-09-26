// Do not mutate compiler-proven fields merely by opening/saving a form.
export const COMPILED_FIELDS = ['entry', 'exit', 'stop_loss', 'take_profit', 'position_size',
  'market_conditions', 'signal_mode', 'entry_signal', 'executable_entry', 'executable_exit',
  'independent_entries', 'exit_policy', 'risk_model', 'engine_settings', 'entry_contract'];

export function preserveCompiledRules(parsed: Record<string, any>, form: Record<string, any>, declared: boolean) {
  const result = { ...form };
  if (!declared && ['compiler_authoritative', 'trusted_template'].includes(parsed.source_grounding?.status)) {
    for (const field of COMPILED_FIELDS) {
      if (Object.prototype.hasOwnProperty.call(parsed, field)) result[field] = parsed[field];
      else delete result[field];
    }
  }
  return result;
}

export function asNoahBaseDraft(original: Record<string, any>) {
  const rules = JSON.parse(JSON.stringify(original));
  rules.previous_entry_contract = { entry: rules.entry, executable_entry: rules.executable_entry,
    independent_entries: rules.independent_entries, source_grounding: rules.source_grounding };
  rules.entry_contract = { mode: 'noah_base', confirmed_by_user: true };
  rules.entry = 'NoahAI 기본 진입 + 사용자 위험·청산값 (원문 진입 전략 실행 아님)';
  rules.signal_mode = 'confirm'; rules.entry_signal = '';
  rules.executable_entry = { all: [], any: [] }; delete rules.independent_entries;
  rules.source_grounding = { status: 'user_declared_override', confirmed_by_user: true };
  // Keep source, unsupported-condition diagnostics and risk/exit evidence.
  return rules;
}
