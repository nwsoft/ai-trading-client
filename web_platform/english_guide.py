"""Reviewed English beta operating guide. No machine translation or model calls."""
from config.app_version import RELEASE_VERSION

SECTIONS = [
    ('intro', 'Start here', '''NoahAI English beta

Choose English (Beta) below the sign-in form or in Settings → General → Display language. Your choice is applied and saved separately immediately. Saved choices take priority; without one, an English system preference starts in English and other languages fall back to Korean. No country or IP lookup is used. The choice changes presentation and explicitly requested AI explanations, not trading permissions, market data, currencies or accounting time zones. Some advanced explanations, diagnostic messages and legacy material remain in Korean. Source documents, strategy names and logs are preserved as received.

Start with one venue in PAPER. In Settings → First-time setup, select the asset and venue, review pending changes and save. Connect the necessary market-data / account API, then start that venue from the dashboard. A displayed API credential is not proof that all API capabilities work.

NoahAI runs on your PC. Keep the PC awake and the app running. Analysis and historical results are not promises of future performance.'''),
    ('dashboard', 'Dashboard and venues', '''Select Crypto or Stocks / ETFs, then select a venue. A selected tab is a viewing scope, not permission to trade. The venue's current PAPER/LIVE and running status are the authority.

Positions and statistics follow their displayed mode and date range. LIVE history and PAPER validation history are separate. Previous PAPER evidence remains available during LIVE operation; it is not real-account profit. Refresh only rereads data—it does not start trading.

Stocks / ETFs use the broker's supported instrument, market hours, currency and data availability. Missing intraday candles must not be substituted with daily candles without disclosure.'''),
    ('settings', 'Settings and safety', '''Settings changes are pending until you save and confirm relevant risk settings. Display language is saved separately and does not invalidate a remote trading approval. Changing actual trading settings or strategy rules can require renewed remote approval.

LIVE requires separate membership / venue authorization, an explicitly enabled LIVE execution scope, API readiness and passing guardrails. Turning PAPER off alone is not sufficient. Never paste API secrets into AI chat. Saved secrets are not returned to the UI.

Use Settings → AI engines / APIs to configure providers. A live model test makes one external request and may cost money. Local guides and UI translations do not call an external AI service.'''),
    ('ai', 'AI help and explanations', '''Open AI assistant or Ask AI about this result. In English mode, an explicitly requested Deep analysis asks the provider to explain the supplied evidence in English. Provider costs and existing privacy rules still apply. The local Guide does not call a provider; detailed legacy guidance may remain in Korean and is labeled as original material.

Ask: “Explain the strategy's entry, exit, stop loss and missing conditions in simple English. Distinguish source claims from NoahAI validation.” You can ask follow-up questions. AI explanations do not approve, save or execute a strategy. Do not accept inferred conditions as confirmed user intent.'''),
    ('strategy', 'Strategy Studio: source to execution', '''1. Enter text / Pine Script, or choose a supported document, image, video or URL. Confirm the timeframe and compatible venues.
2. Analyze the source. Review XAI findings: what was actually read, source evidence, explicit rules, missing conditions and warnings. A YouTube link is not proof that the full video was read; check caption / transcription / frame coverage.
3. Use guided questions to clarify missing conditions. AI examples are suggestions, not automatic rule changes. Confirm your own answers; the original source remains separate.
4. Revalidate and save a version. Then approve that version and run validation. Saved, approved, validated and applied are different states.
5. Inspect historical replay and PAPER evidence. Applying a strategy still requires the correct venue, mode, account limits and execution checks. LIVE is never enabled by translation or AI conversation.

Use Ask AI about this result for a plain-language explanation of the current analysis. Unsupported conditions are not replaced with guessed rules.'''),
    ('backtest', 'Replay charts and validation', '''After approving a supported strategy version, run Historical replay with a supported symbol, timeframe and candle count. In the saved version, expand Historical replay chart to view the candles, simulated entry / exit markers, closed-trade compounded return curve and trade table. Click a trade row to focus its interval; Fit range shows the complete span.

Chart time is UTC candle-start time, not actual exchange fill time. Green BUY and red SELL represent order sides: SELL can open a short position. Read the entry / exit labels rather than assuming every BUY is an entry.

The curve compounds cost-adjusted per-trade returns. It is not actual account equity, leveraged performance or unrealized PnL. Modeled costs exclude funding and market impact. When stop loss and take profit are both reached in one candle, the conservative stop-loss assumption applies.

No chart means missing or inconsistent original evidence, not zero profit. Older summary-only records remain readable. Replay does not replace PAPER, LIVE or passport verification. Crypto and stock / ETF data availability differ; inspect the recorded venue and timeframe.'''),
    ('statistics', 'PnL and reconciliation', '''Compare like with like: account, venue, instrument, mode, currency, period and accounting time zone. English date formatting must not change the day boundary used for PnL.

NoahAI-linked closed-trade net PnL is different from exchange full-account daily PnL. Fees, taxes, funding, transfers, manual trades and unrealized positions can change the comparison basis. Read the reconciliation status and cost basis. Unresolved trades are not zero-profit trades; a reconciled subtotal is not the complete result.

Sync venue fills rereads available evidence. Recalculate display updates statistics. Setting a display baseline does not delete the ledger. Do not bypass a reconciliation block merely to resume entries. Give support redacted logs and trade identifiers, never API secrets.'''),
    ('remote', 'Mobile remote management', '''On the PC, open Settings → Alerts / Reports → Remote management. Enable status sharing and choose each optional permission. Start / resume and detailed summaries are off unless explicitly permitted. Save the approved venue / mode / settings scope.

Sign in to daltrading in your mobile browser and open My NoahAI. PC login and browser login are separate sessions. Check the latest received time. A sleeping, disconnected or closed PC cannot act on a command.

Pause new entries blocks new entry orders while keeping existing position protection and exits active. Already submitted orders may still fill. Start / resume requires website password confirmation and fresh PC-side permission, risk and session checks. A submitted request is not proof of execution; wait for the PC acknowledgement.

Unlinking a PC revokes its remote connection. It does not close positions, stop the trading engine or clear an entry pause. Remote mode switching, full liquidation and strategy editing / replay are not offered. This is not an emergency liquidation tool.'''),
    ('alerts', 'Notifications', '''Configure and test Discord or Telegram in Settings → Alerts / Reports, then enable the intended events and save. The PC must be running to send local alerts. Delivery can be delayed.

This English beta does not translate all trading-engine notifications. Original risk messages, numbers and error codes remain unchanged. Never interpret a missing translation as an absence of risk. Daily-risk summaries and exchange account PnL have different scopes; read the stated basis and timestamp.

No API key, strategy source or account number should be included in a public support message.'''),
    ('updates', 'Updates', '''v3.9.1.42 adds English beta presentation and remote controls with explicit PC permissions. The client installer is released separately from website updates.

Check for updates in Settings → Updates. Checking and downloading do not stop trading. Installation / restart requires safe engine shutdown and record persistence. Do not replace an active installation while orders are in flight. A source test is not evidence that a Windows installer has been verified.'''),
    ('support', 'Limits and support', '''English beta covers navigation, selected operating controls, remote management and this guide. Some advanced settings, generated explanations and original logs remain Korean. Choose Korean at any time; switching language does not reset trading data.

No country is inferred from your language, IP or exchange selection. Selecting English does not grant access to a venue or establish eligibility in a jurisdiction. Product availability and authorization remain separate.

When reporting a problem, include the client version, venue, mode, selected period, timezone, error code and redacted evidence. Do not send passwords, API keys or unredacted secrets.'''),
]

def manual_snapshot():
    sections = [{'id': key, 'label': label, 'content': content} for key, label, content in SECTIONS]
    return {'schema_version': '1.0.0', 'source': 'web_platform/english_guide.py',
            'source_reference': 'reviewed_english_beta_guide', 'source_sha256': '',
            'release_version': RELEASE_VERSION, 'locale': 'en', 'sections': sections,
            'content': '\n\n'.join('# '+s['label']+'\n\n'+s['content'] for s in sections)}

def local_answer(original, service):
    key = {'ai_custom': 'strategy', 'settings': 'settings', 'stock': 'dashboard',
           'blockchain': 'statistics'}.get(service, 'ai')
    content = next(content for ident, _, content in SECTIONS if ident == key)
    return ('English beta · Local operating guide (no external AI request)\n\n'
            'This is general operating guidance, not an English translation of your account-specific diagnosis. '
            'For an English explanation of the supplied evidence, explicitly choose Deep analysis; provider usage may be charged.\n\n'
            + content + '\n\nOriginal Korean diagnostic / guidance (preserved):\n\n' + original)
