export type FeatureSurface =
  | "trading_log"
  | "asset_info"
  | "trading_statistics"
  | "market_trend"
  | "ai_learning"
  | "ai_report"
  | "assistant"
  | "strategy"
  | "financial_intelligence"
  | "alpha_arena"
  | "source_workspace"
  | "portfolio"
  | "life_basic"
  | "life_advanced"
  | "ai_analyst"
  | "ai_analyst_scenario";

// Every feature in config/web_ui_feature_inventory.json must appear exactly once.
// Unknown features fail closed in App.tsx instead of falling back to a generic UI.
export const FEATURE_SURFACES: Record<string, FeatureSurface> = {
  "blockchain.logs": "trading_log",
  "blockchain.coin_info": "asset_info",
  "blockchain.statistics": "trading_statistics",
  "blockchain.trends": "market_trend",
  "blockchain.ai_learning": "ai_learning",
  "blockchain.ai_reports": "ai_report",
  "blockchain.ai_assistant": "assistant",
  "blockchain.ai_custom": "strategy",
  "blockchain.financial_intelligence": "financial_intelligence",
  "blockchain.alpha_arena": "alpha_arena",
  "blockchain.source_workspaces": "source_workspace",
  "stock.logs": "trading_log",
  "stock.info": "asset_info",
  "stock.statistics": "trading_statistics",
  "stock.trends": "market_trend",
  "stock.ai_learning": "ai_learning",
  "stock.ai_reports": "ai_report",
  "stock.ai_assistant": "assistant",
  "stock.ai_custom": "strategy",
  "stock.financial_intelligence": "financial_intelligence",
  "stock.source_workspaces": "source_workspace",
  "portfolio.insights": "portfolio",
  "portfolio.allocation": "portfolio",
  "portfolio.risk": "portfolio",
  "portfolio.performance": "portfolio",
  "personal_finance.service": "life_basic",
  "personal_finance.cashflow": "life_basic",
  "personal_finance.goals": "life_basic",
  "personal_finance.security": "life_advanced",
  "personal_finance.tax": "life_advanced",
  "ai_analyst.workspace": "ai_analyst",
  "ai_analyst.assistant": "assistant",
  "ai_analyst.summary": "financial_intelligence",
  "ai_analyst.scenario": "ai_analyst_scenario",
  "ai_analyst.intelligence": "financial_intelligence",
};

export function featureSurface(featureId?: string): FeatureSurface | "unmapped" {
  if (!featureId) return "unmapped";
  return FEATURE_SURFACES[featureId] ?? "unmapped";
}
