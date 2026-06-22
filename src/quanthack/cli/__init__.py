"""Command-line entry points for QuanHack workflows."""

from __future__ import annotations

import importlib
import sys
from collections.abc import Sequence


COMMANDS: dict[str, tuple[str, str]] = {
    "check-environment": (
        "quanthack.cli.check_environment",
        "Check Python and local environment readiness.",
    ),
    "project-status": ("quanthack.cli.project_status", "Show current project status."),
    "show-config": ("quanthack.cli.show_config", "Print configured hackathon settings."),
    "show-mode": (
        "quanthack.cli.show_competition_mode",
        "Show the current competition clock mode.",
    ),
    "show-prices": ("quanthack.cli.show_prices", "Inspect offline price CSV data."),
    "show-quotes": ("quanthack.cli.show_quotes", "Inspect offline quote CSV data."),
    "show-instruments": (
        "quanthack.cli.show_instruments",
        "Show official Syphonix instrument metadata.",
    ),
    "show-journal": ("quanthack.cli.show_journal", "Show recent dry-run journal records."),
    "show-positions": (
        "quanthack.cli.show_positions",
        "Reconstruct dry-run positions from the journal.",
    ),
    "risk-demo": ("quanthack.cli.risk_demo", "Run a simple risk engine decision demo."),
    "dry-run-trade": ("quanthack.cli.dry_run_trade", "Journal a manual dry-run trade."),
    "manual-ticket": (
        "quanthack.cli.manual_ticket",
        "Build a safe manual MT5 order ticket from a USD target.",
    ),
    "strategy-dry-run": (
        "quanthack.cli.strategy_dry_run",
        "Run the simple strategy through risk and journal.",
    ),
    "configured-strategy-dry-run": (
        "quanthack.cli.configured_strategy_dry_run",
        "Run the configured strategy through risk and journal.",
    ),
    "data-strategy-dry-run": (
        "quanthack.cli.data_strategy_dry_run",
        "Run configured strategy from offline price CSV data.",
    ),
    "quality-data-strategy-dry-run": (
        "quanthack.cli.quality_data_strategy_dry_run",
        "Run quality, strategy, risk, and dry-run journaling.",
    ),
    "live-dry-run": (
        "quanthack.cli.live_dry_run",
        "Run read-only CSV/MT5 live dry-run monitoring.",
    ),
    "live-trade": (
        "quanthack.cli.live_trade",
        "Run the LIVE MT5 trading loop (real orders; shadow unless opted in).",
    ),
    "mt5-flatten": (
        "quanthack.cli.mt5_flatten",
        "Kill-switch: close ALL open MT5 positions immediately.",
    ),
    "mt5-probe": (
        "quanthack.cli.mt5_probe",
        "Probe the read-only MT5 connection without placing orders.",
    ),
    "mt5-capture": (
        "quanthack.cli.mt5_capture",
        "Capture read-only MT5 quotes/account snapshots into CSV files.",
    ),
    "preflight": ("quanthack.cli.preflight", "Run local readiness checks."),
    "journal-summary": (
        "quanthack.cli.journal_summary",
        "Summarize the dry-run decision journal.",
    ),
    "html-report": (
        "quanthack.cli.build_html_report",
        "Build a standalone HTML dry-run report.",
    ),
    "dashboard": (
        "quanthack.cli.dashboard",
        "Run the local backtest and live-results dashboard.",
    ),
    "backtest": ("quanthack.cli.backtest", "Run one offline strategy backtest."),
    "portfolio-backtest": (
        "quanthack.cli.portfolio_backtest",
        "Run a shared-risk portfolio backtest.",
    ),
    "compare": ("quanthack.cli.compare_strategies", "Compare strategies by backtest."),
    "walk-forward": (
        "quanthack.cli.walk_forward",
        "Run chronological walk-forward evaluation.",
    ),
    "sweep": ("quanthack.cli.parameter_sweep", "Sweep momentum parameters."),
    "research-report": (
        "quanthack.cli.research_report",
        "Build the demo-ready research HTML report.",
    ),
    "strategy-demo": ("quanthack.cli.strategy_demo", "Inspect a strategy decision."),
    "ml-alpha-report": (
        "quanthack.cli.ml_alpha_report",
        "Evaluate the ML alpha signal on historical bars.",
    ),
    "time-series-report": (
        "quanthack.cli.time_series_report",
        "Classify trend/chop regimes with a Kalman-style filter.",
    ),
    "router-report": (
        "quanthack.cli.router_report",
        "Summarize router signal attribution from a backtest.",
    ),
    "portfolio-attribution-report": (
        "quanthack.cli.portfolio_attribution_report",
        "Summarize portfolio P&L by symbol, signal, hour, and side.",
    ),
    "experiment-leaderboard": (
        "quanthack.cli.experiment_leaderboard",
        "Rank walk-forward experiment summary CSVs.",
    ),
    "signal-diagnostics": (
        "quanthack.cli.signal_diagnostics",
        "Screen signal sleeves with fast forward-return diagnostics.",
    ),
    "router-optimize": (
        "quanthack.cli.router_optimize",
        "Optimize alpha-router weights with allocator-aware backtests.",
    ),
    "relative-strength-optimize": (
        "quanthack.cli.relative_strength_optimize",
        "Optimize relative-strength parameters with portfolio backtests.",
    ),
    "volatility-squeeze-optimize": (
        "quanthack.cli.volatility_squeeze_optimize",
        "Optimize volatility-squeeze parameters with portfolio backtests.",
    ),
    "dual-squeeze-optimize": (
        "quanthack.cli.dual_squeeze_optimize",
        "Optimize dual-squeeze parameters with portfolio backtests.",
    ),
    "trend-pullback-optimize": (
        "quanthack.cli.trend_pullback_optimize",
        "Optimize trend-pullback parameters with portfolio backtests.",
    ),
    "fixing-reversal-optimize": (
        "quanthack.cli.fixing_reversal_optimize",
        "Optimize fixing-reversal parameters with portfolio backtests.",
    ),
    "kalman-trend-optimize": (
        "quanthack.cli.kalman_trend_optimize",
        "Optimize Kalman trend parameters with portfolio backtests.",
    ),
    "macd-momentum-optimize": (
        "quanthack.cli.macd_momentum_optimize",
        "Optimize MACD momentum parameters with portfolio backtests.",
    ),
    "multi-horizon-momentum-optimize": (
        "quanthack.cli.multi_horizon_momentum_optimize",
        "Optimize multi-horizon momentum parameters with portfolio backtests.",
    ),
    "session-momentum-optimize": (
        "quanthack.cli.session_momentum_optimize",
        "Optimize session-filtered momentum parameters with portfolio backtests.",
    ),
    "opportunity-probe-optimize": (
        "quanthack.cli.opportunity_probe_optimize",
        "Optimize opportunity-probe parameters with portfolio backtests.",
    ),
    "champion-ensemble-optimize": (
        "quanthack.cli.champion_ensemble_optimize",
        "Optimize champion-ensemble weights with portfolio backtests.",
    ),
    "cross-rate-optimize": (
        "quanthack.cli.cross_rate_optimize",
        "Optimize FX cross-rate reversion parameters with fast diagnostics.",
    ),
    "validate-data": (
        "quanthack.cli.validate_market_data",
        "Validate price/quote CSV coverage and alignment.",
    ),
    "import-backtest-data": (
        "quanthack.cli.import_backtest_data",
        "Convert downloaded Parquet backtest data into QuanHack CSVs.",
    ),
    "generate-sample-data": (
        "quanthack.cli.generate_sample_data",
        "Generate deterministic competition sample data.",
    ),
    "portfolio-compare": (
        "quanthack.cli.portfolio_compare",
        "Compare strategies on a shared-risk portfolio.",
    ),
    "strategy-attribution": (
        "quanthack.cli.strategy_attribution",
        "Write per-symbol P&L attribution for one or more strategies.",
    ),
    "symbol-eligibility-optimize": (
        "quanthack.cli.symbol_eligibility_optimize",
        "Optimize strategy symbol eligibility from attribution.",
    ),
    "strategy-map-optimize": (
        "quanthack.cli.strategy_map_optimize",
        "Optimize per-symbol strategy maps with shared-risk backtests.",
    ),
    "adaptive-strategy-select": (
        "quanthack.cli.adaptive_strategy_select",
        "Walk-forward select the best recent portfolio strategy.",
    ),
    "portfolio-universe-scan": (
        "quanthack.cli.portfolio_universe_scan",
        "Rank diversified symbol baskets with portfolio backtests.",
    ),
    "portfolio-walk-forward": (
        "quanthack.cli.portfolio_walk_forward",
        "Validate portfolio basket selection on unseen windows.",
    ),
    "portfolio-fixed-warmup-walk-forward": (
        "quanthack.cli.portfolio_fixed_warmup_walk_forward",
        "Score a fixed portfolio on walk-forward windows after warmup history.",
    ),
    "portfolio-router-walk-forward": (
        "quanthack.cli.portfolio_router_walk_forward",
        "Tune alpha-router weights in portfolio walk-forward.",
    ),
}


def _print_help() -> None:
    print("QuanHack CLI")
    print("Usage: quanthack <command> [options]")
    print("Commands:")
    width = max(len(name) for name in COMMANDS)
    for name, (_, description) in COMMANDS.items():
        print(f"  {name:<{width}}  {description}")


def main(argv: Sequence[str] | None = None) -> None:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in {"-h", "--help"}:
        _print_help()
        return

    command = args[0]
    if command not in COMMANDS:
        available = ", ".join(COMMANDS)
        raise SystemExit(f"Unknown command '{command}'. Available commands: {available}")

    module_name, _ = COMMANDS[command]
    module = importlib.import_module(module_name)
    module.main(args[1:])
