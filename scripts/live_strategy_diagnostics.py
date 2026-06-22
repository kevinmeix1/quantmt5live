from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import datetime, timezone
from math import isfinite
from pathlib import Path

from quanthack.backtesting.portfolio_allocator import AllocatedTarget, SymbolIntent
from quanthack.cli.live_dry_run import _build_adapters, _parse_strategy_map
from quanthack.cli.live_trade import ALLOCATION_PROFILE_NAMES, _allocation_policy_for
from quanthack.core.config import load_config
from quanthack.core.env import load_env_file
from quanthack.market.market_data import QuoteSnapshot
from quanthack.trading.live_dry_run import (
    EPSILON_NOTIONAL,
    LiveDryRunEngine,
    LiveDryRunSettings,
    LiveRiskThrottle,
    _iteration_timestamp,
)
from quanthack.trading.mt5_executor import Mt5LiveExecutor


SYMBOLS = ("AUDUSD", "EURGBP", "EURUSD", "GBPUSD", "USDCAD", "USDCHF")
STRATEGY = "champion_ensemble"
STRATEGY_MAP = (
    "AUDUSD=macd_momentum",
    "EURGBP=champion_ensemble",
    "EURUSD=macd_momentum",
    "GBPUSD=champion_ensemble",
    "USDCAD=macd_momentum",
    "USDCHF=macd_momentum",
)
BLOCKED_STATES = (
    "cooldown_realized_drag",
    "observe",
    "keep_if_signal_aligned",
)
SMALL_ONLY_STATES = (
    "small_only_until_recovery",
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Write read-only live strategy diagnostics from MT5."
    )
    parser.add_argument("--config", default="configs/competition.toml")
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--journal", default="outputs/live_orders_journal.jsonl")
    parser.add_argument("--output-json", default="outputs/live_strategy_diagnostics_latest.json")
    parser.add_argument("--history-jsonl", default="outputs/live_strategy_diagnostics_history.jsonl")
    parser.add_argument("--output-text", default="outputs/live_strategy_diagnostics_latest.txt")
    parser.add_argument("--strategy", default=STRATEGY)
    parser.add_argument("--strategy-map", action="append", default=None)
    parser.add_argument("--symbol", action="append", default=None)
    parser.add_argument("--max-live-positions", type=int, default=2)
    parser.add_argument("--reduce-only-daily-loss-pct", type=float, default=0.0012)
    parser.add_argument("--reduce-only-rolling-sharpe", type=float, default=-2.0)
    parser.add_argument("--live-metrics-csv", default="outputs/live_metrics.csv")
    parser.add_argument("--sentiment-snapshot", default="outputs/fx_sentiment_snapshot.json")
    parser.add_argument("--sentiment-conflict-threshold", type=float, default=1.25)
    parser.add_argument("--symbol-state-snapshot", default="outputs/live_deal_attribution_latest.json")
    parser.add_argument("--blocked-symbol-state", action="append", default=None)
    parser.add_argument("--small-only-symbol-state", action="append", default=None)
    parser.add_argument("--small-only-max-notional-usd", type=float, default=25_000.0)
    parser.add_argument("--allocation-profile", choices=ALLOCATION_PROFILE_NAMES, default="default")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    snapshot = build_snapshot(args)
    _write_snapshot(
        snapshot,
        output_json=Path(args.output_json),
        history_jsonl=Path(args.history_jsonl),
        output_text=Path(args.output_text),
    )
    print(
        json.dumps(
            {
                "timestamp_utc": snapshot["timestamp_utc"],
                "allocation_profile": snapshot["allocation_profile"],
                "allocation_status": snapshot["allocation"]["status"],
                "requested_gross_notional_usd": snapshot["allocation"][
                    "requested_gross_notional_usd"
                ],
                "adjusted_gross_notional_usd": snapshot["allocation"][
                    "adjusted_gross_notional_usd"
                ],
                "statuses": {
                    symbol: item["status"] for symbol, item in snapshot["symbols"].items()
                },
            },
            sort_keys=True,
        )
    )


def build_snapshot(args: argparse.Namespace) -> dict:
    load_env_file(args.env_file)
    config = load_config(args.config)
    symbols = tuple(args.symbol or SYMBOLS)
    strategy_map = tuple(args.strategy_map or _default_strategy_map_for(symbols))
    adapter_args = _mt5_adapter_args(args)
    market_adapter, account_adapter = _build_adapters(
        adapter_name="mt5",
        config=config,
        args=adapter_args,
    )
    try:
        settings = LiveDryRunSettings(
            symbols=symbols,
            strategy_name=args.strategy,
            strategy_by_symbol=_parse_strategy_map(strategy_map),
            timeframe=config.live_dry_run.timeframe,
            bars=config.live_dry_run.bars,
            iterations=1,
            poll_seconds=0.0,
            journal_path=args.journal,
        )
        executor = Mt5LiveExecutor(
            journal_path=Path(args.journal),
            market_adapter=market_adapter,
            live=False,
            max_order_lots=0.10,
        )
        throttle = LiveRiskThrottle(
            max_active_positions=args.max_live_positions,
            reduce_only_daily_loss_pct=args.reduce_only_daily_loss_pct,
            reduce_only_rolling_sharpe=args.reduce_only_rolling_sharpe,
            metrics_csv=args.live_metrics_csv,
            sentiment_snapshot_path=args.sentiment_snapshot,
            sentiment_conflict_threshold=args.sentiment_conflict_threshold,
            symbol_state_snapshot_path=args.symbol_state_snapshot,
            blocked_symbol_states=tuple(args.blocked_symbol_state or BLOCKED_STATES),
            small_only_symbol_states=tuple(
                args.small_only_symbol_state or SMALL_ONLY_STATES
            ),
            small_only_max_notional_usd=args.small_only_max_notional_usd,
        )
        engine = LiveDryRunEngine(
            config=config,
            settings=settings,
            market_data=market_adapter,
            account_adapter=account_adapter,
            allocation_policy=_allocation_policy_for(
                settings.strategy_name,
                config,
                profile=args.allocation_profile,
            ),
            executor=executor,
            live_risk_throttle=throttle,
            validate_quote_age_against_wall_clock=True,
        )
        return _diagnose_engine(
            engine,
            settings=settings,
            allocation_profile=args.allocation_profile,
        )
    finally:
        close = getattr(market_adapter, "close", None)
        if callable(close):
            close()


def _diagnose_engine(
    engine: LiveDryRunEngine,
    *,
    settings: LiveDryRunSettings,
    allocation_profile: str = "default",
) -> dict:
    quotes = {symbol: engine.market_data.get_latest_quote(symbol) for symbol in settings.symbols}
    wall_clock_utc = datetime.now(timezone.utc)
    histories = {
        symbol: engine.market_data.get_recent_bars(
            symbol,
            timeframe=settings.timeframe,
            count=settings.bars,
        )
        for symbol in settings.symbols
    }
    engine._update_strategy_context(histories=histories, quotes=quotes)
    timestamp = _iteration_timestamp(
        quotes,
        validate_quote_age_against_wall_clock=engine.validate_quote_age_against_wall_clock,
        now=wall_clock_utc,
    )
    account = engine.account_adapter.get_account_snapshot(
        starting_equity=engine.config.competition.starting_equity,
        day_start_equity=engine._day_start_equity,
        peak_equity=engine._peak_equity,
    )
    portfolio = engine.executor.current_portfolio()
    raw_intents = tuple(
        engine._build_intent(
            symbol=symbol,
            strategy=engine._strategies[symbol],
            quote=quotes[symbol],
            bars=histories[symbol],
            portfolio=portfolio,
        )
        for symbol in settings.symbols
    )
    adjusted_intents = engine._apply_live_risk_throttle(
        raw_intents,
        account=account,
        portfolio=portfolio,
    )
    allocation = engine.allocator.allocate(
        adjusted_intents,
        equity=account.equity,
        timestamp=timestamp.isoformat(timespec="seconds"),
    )
    targets_by_symbol = {target.symbol: target for target in allocation.targets}
    adjusted_by_symbol = {intent.symbol: intent for intent in adjusted_intents}
    raw_by_symbol = {intent.symbol: intent for intent in raw_intents}

    return {
        "timestamp_utc": wall_clock_utc.isoformat(timespec="seconds"),
        "strategy": settings.strategy_name,
        "strategy_map": dict(settings.strategy_by_symbol),
        "allocation_profile": allocation_profile,
        "account": {
            "equity": account.equity,
            "daily_pnl_pct": account.daily_pnl_pct,
            "margin_level_pct": account.margin_level_pct,
            "positions": [asdict(position) for position in portfolio.positions],
        },
        "allocation": {
            "status": allocation.estimated_risk_status,
            "requested_gross_notional_usd": allocation.requested_gross_notional_usd,
            "adjusted_gross_notional_usd": allocation.adjusted_gross_notional_usd,
            "requested_net_notional_usd": allocation.requested_net_notional_usd,
            "adjusted_net_notional_usd": allocation.adjusted_net_notional_usd,
            "trim_reasons": allocation.trim_reasons,
        },
        "symbols": {
            symbol: _symbol_diagnostic(
                symbol=symbol,
                strategy=settings.strategy_for_symbol(symbol),
                quote=quotes[symbol],
                wall_clock_utc=wall_clock_utc,
                raw=raw_by_symbol[symbol],
                adjusted=adjusted_by_symbol[symbol],
                target=targets_by_symbol[symbol],
            )
            for symbol in settings.symbols
        },
    }


def _symbol_diagnostic(
    *,
    symbol: str,
    strategy: str,
    quote: QuoteSnapshot,
    wall_clock_utc: datetime,
    raw: SymbolIntent,
    adjusted: SymbolIntent,
    target: AllocatedTarget,
) -> dict:
    return {
        "strategy": strategy,
        "quote_timestamp_utc": quote.timestamp.isoformat(timespec="seconds"),
        "quote_wall_clock_skew_seconds": _quote_wall_clock_skew_seconds(
            quote.timestamp,
            wall_clock_utc,
        ),
        "spread_bps": _spread_bps(quote.bid, quote.ask),
        "current_notional_usd": raw.current_notional_usd,
        "raw_target_notional_usd": raw.target_notional_usd,
        "raw_change_notional_usd": raw.requested_change_notional_usd,
        "raw_reason": raw.reason,
        "raw_reason_bucket": _reason_bucket(raw.reason),
        "throttle_target_notional_usd": adjusted.target_notional_usd,
        "throttle_change_notional_usd": adjusted.requested_change_notional_usd,
        "throttle_reason": adjusted.reason,
        "allocation_target_notional_usd": target.adjusted_notional_usd,
        "allocation_change_notional_usd": target.change_notional_usd,
        "allocation_reasons": target.reasons,
        "primary_signal": target.primary_signal,
        "supporting_signals": target.supporting_signals,
        "conflicting_signals": target.conflicting_signals,
        "status": _intent_status(raw=raw, adjusted=adjusted, target=target),
    }


def _intent_status(*, raw: SymbolIntent, adjusted: SymbolIntent, target: AllocatedTarget) -> str:
    if abs(target.change_notional_usd) > EPSILON_NOTIONAL:
        return "actionable_allocation"
    if abs(raw.requested_change_notional_usd) <= EPSILON_NOTIONAL:
        return "strategy_no_change"
    if abs(adjusted.target_notional_usd - raw.target_notional_usd) > EPSILON_NOTIONAL:
        return "live_throttle_blocked"
    if target.was_trimmed:
        return "allocation_trimmed_to_no_change"
    return "allocation_no_change"


def _reason_bucket(reason: str) -> str:
    normalized = reason.lower()
    if "live throttle" in normalized:
        return "live_throttle"
    if "outside" in normalized and "utc hours" in normalized:
        return "session_gated"
    if "spread" in normalized:
        return "spread_gated"
    if "inside exit band" in normalized:
        return "threshold_gated"
    if "below" in normalized or "too small" in normalized:
        return "threshold_gated"
    if "holding" in normalized or normalized.startswith("hold"):
        return "hold"
    if "exit" in normalized:
        return "exit_signal"
    if "no " in normalized:
        return "no_signal"
    return "strategy"


def _spread_bps(bid: float, ask: float) -> float:
    mid = (bid + ask) / 2.0
    if mid <= 0 or not isfinite(mid):
        return 0.0
    return (ask - bid) / mid * 10_000.0


def _quote_wall_clock_skew_seconds(quote_timestamp: datetime, wall_clock_utc: datetime) -> float:
    if quote_timestamp.tzinfo is None:
        quote_timestamp = quote_timestamp.replace(tzinfo=timezone.utc)
    if wall_clock_utc.tzinfo is None:
        raise ValueError("wall_clock_utc must be timezone-aware")
    return round(
        (
            quote_timestamp.astimezone(timezone.utc)
            - wall_clock_utc.astimezone(timezone.utc)
        ).total_seconds(),
        3,
    )


def _write_snapshot(
    snapshot: dict,
    *,
    output_json: Path,
    history_jsonl: Path,
    output_text: Path,
) -> None:
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(snapshot, indent=2, sort_keys=True), encoding="utf-8")
    history_jsonl.parent.mkdir(parents=True, exist_ok=True)
    with history_jsonl.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(snapshot, sort_keys=True) + "\n")
    output_text.write_text(_snapshot_text(snapshot), encoding="utf-8")


def _snapshot_text(snapshot: dict) -> str:
    allocation = snapshot["allocation"]
    lines = [
        (
            f"{snapshot['timestamp_utc']} allocation={allocation['status']} "
            f"profile={snapshot.get('allocation_profile', 'default')} "
            f"requested_gross={allocation['requested_gross_notional_usd']:.2f} "
            f"adjusted_gross={allocation['adjusted_gross_notional_usd']:.2f}"
        ),
        "",
    ]
    for symbol, item in snapshot["symbols"].items():
        skew_seconds = float(item.get("quote_wall_clock_skew_seconds", 0.0) or 0.0)
        lines.append(
            f"{symbol}: status={item['status']} strategy={item['strategy']} "
            f"raw_change={item['raw_change_notional_usd']:.2f} "
            f"throttle_change={item['throttle_change_notional_usd']:.2f} "
            f"alloc_change={item['allocation_change_notional_usd']:.2f} "
            f"bucket={item['raw_reason_bucket']} "
            f"quote_skew={skew_seconds:+.0f}s reason={item['throttle_reason']}"
        )
    return "\n".join(lines) + "\n"


def _mt5_adapter_args(args: argparse.Namespace) -> argparse.Namespace:
    return argparse.Namespace(
        confirm_read_only_mt5=True,
        mt5_terminal_path=None,
        mt5_login=None,
        mt5_password=None,
        mt5_server=None,
        mt5_timeout_ms=180_000,
        mt5_portable=False,
        mt5_symbol_map=None,
    )


def _default_strategy_map_for(symbols: tuple[str, ...]) -> tuple[str, ...]:
    selected = set(symbols)
    return tuple(
        item
        for item in STRATEGY_MAP
        if item.split("=", 1)[0].strip().upper() in selected
    )


if __name__ == "__main__":
    main()
