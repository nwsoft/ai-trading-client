import { localized } from './i18n';

export const STRATEGY_DIFFICULTY_PATH = 'ai_custom_features.profile';
const profiles: Record<string, [number, string, string]> = {
  beginner: [1, '초보자', 'Beginner'],
  standard: [2, '일반', 'Standard'],
  advanced: [3, '고급', 'Advanced'],
  lab: [4, '실험실', 'Lab'],
};

export function strategyDifficultyLabel(profile: string): string {
  const [level, ko, en] = profiles[profile === 'laboratory' ? 'lab' : profile] ?? profiles.standard;
  return `Level ${level} (${localized(ko, en)})`;
}
