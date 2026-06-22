"""LIVE MT5 trading loop (places real orders on the competition account).

Reuses the read-only live-dry-run plumbing (MT5 adapters, symbol validation,
strategy map) but swaps the journaling executor for ``Mt5LiveExecutor``.

SAFETY GATES (all must line up before a single real order is sent):
  * ``--adapter mt5`` is required.
  * Without ``--i-understand-live-orders`` it runs in SHADOW mode (computes and
    journals intended orders, sends nothing).
  * ``--max-order-lots`` hard-caps any single order.
  * Every order still passes the RiskEngine inside the loop.

Recommended go-live order: mt5-probe (read-only) -> this command in shadow mode
-> one tiny manual-ticket order -> this command with --i-understand-live-orders
and a small --max-order-lots.
"""
from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from quanthack.backtesting.allocation_profiles import (
    ALLOCATION_PROFILE_DEFAULT,
    ALLOCATION_PROFILE_DIRECTIONAL_PROBE,
    ALLOCATION_PROFILE_NAMES,
    allocation_policy_for_strategy,
)
from quanthack.backtesting.portfolio_allocator import AllocationPolicy
from quanthack.cli.live_dry_run import (
    _build_adapters,
    _parse_strategy_map,
    _validate_requested_symbols,
)
from quanthack.core.config import load_config
from quanthack.core.env import load_env_file
from quanthack.strategies.strategy import STRATEGY_NAMES
from quanthack.trading.live_dry_run import (
    LiveDryRunEngine,
    LiveDryRunError,
    LiveDryRunIteration,
    LiveDryRunNoSuccessfulIterationsError,
    LiveRiskThrottle,
    LiveDryRunSettings,
)
from quanthack.trading.mt5_executor import Mt5LiveExecutor


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Run a LIVE MT5 trading loop (real orders).")
    p.add_argument("--config", default="configs/competition.toml")
    p.add_argument("--env-file", default=".env")
    p.add_argument("--adapter", choices=["mt5"], default="mt5")
    p.add_argument("--strategy", choices=STRATEGY_NAMES, default=None)
    p.add_argument("--strategy-map", action="append", default=None, metavar="SYMBOL=STRATEGY")
    p.add_argument("--symbol", action="append", default=None)
    p.add_argument("--timeframe", default=None)
    p.add_argument("--bars", type=int, default=None)
    p.add_argument("--iterations", type=int, default=None)
    p.add_argument("--poll-seconds", type=float, default=None)
    p.add_argument("--journal", default="outputs/live_orders_journal.jsonl")
    p.add_argument("--mt5-terminal-path", default=None)
    p.add_argument("--mt5-login", type=int, default=None)
    p.add_argument("--mt5-password", default=None)
    p.add_argument("--mt5-server", default=None)
    p.add_argument("--mt5-timeout-ms", type=int, default=60_000)
    p.add_argument("--mt5-portable", action="store_true")
    p.add_argument("--mt5-symbol-map", action="append", default=None,
                   help="Map canonical to broker symbol, e.g. EURUSD=EURUSD.pro")
    p.add_argument("--max-order-lots", type=float, default=1.0,
                   help="Hard cap on any single order (safety backstop).")
    p.add_argument("--max-live-positions", type=int, default=None,
                   help="Block fresh/increased live risk once this many symbols are open.")
    p.add_argument("--reduce-only-daily-loss-pct", type=float, default=None,
                   help="If daily P/L is below this loss pct, only allow reductions/exits.")
    p.add_argument("--reduce-only-rolling-sharpe", type=float, default=None,
                   help="If latest rolling Sharpe is at/below this value, only allow reductions/exits.")
    p.add_argument("--live-metrics-csv", default="outputs/live_metrics.csv",
                   help="Metrics CSV used for rolling-Sharpe live throttling.")
    p.add_argument("--sentiment-snapshot", default=None,
                   help="Optional FX sentiment JSON snapshot used to block conflicting fresh risk.")
    p.add_argument("--sentiment-conflict-threshold", type=float, default=None,
                   help="Block fresh/increased targets when pair sentiment opposes the target by this score.")
    p.add_argument("--symbol-state-snapshot", default=None,
                   help="Optional symbol-state JSON snapshot used to block fresh risk for cooldown symbols.")
    p.add_argument("--blocked-symbol-state", action="append", default=None,
                   help="Symbol-state value that blocks fresh/increased risk; repeatable.")
    p.add_argument("--small-only-symbol-state", action="append", default=None,
                   help="Symbol-state value that caps fresh/increased risk; repeatable.")
    p.add_argument("--small-only-max-notional-usd", type=float, default=None,
                   help="Maximum signed target notional for small-only symbol states.")
    p.add_argument("--allocation-profile", choices=ALLOCATION_PROFILE_NAMES,
                   default=ALLOCATION_PROFILE_DEFAULT,
                   help="Optional live allocation profile. 'directional_probe' permits "
                        "bounded one-sided signals while preserving live throttles.")
    p.add_argument("--i-understand-live-orders", action="store_true",
                   help="REQUIRED to place real orders. Without it, runs in shadow mode.")
    return p


def _print_live_progress(
    index: int,
    iteration: LiveDryRunIteration | None,
    error: LiveDryRunError | None,
) -> None:
    if error is not None:
        print(
            f"[live-trade] skipped iteration {index + 1}: {error.message}",
            flush=True,
        )
        return
    if iteration is None:
        return
    statuses = ",".join(record.status for record in iteration.records) or "no_order"
    print(
        f"[live-trade] iteration={index + 1} "
        f"timestamp={iteration.timestamp.isoformat(timespec='seconds')} "
        f"records={len(iteration.records)} statuses={statuses}",
        flush=True,
    )


def run(args: argparse.Namespace) -> None:
    load_env_file(args.env_file)
    config = load_config(args.config)
    live = bool(args.i_understand_live_orders)
    args.confirm_read_only_mt5 = True  # adapter builder gate (we are mt5)

    market_adapter, account_adapter = _build_adapters(
        adapter_name="mt5", config=config, args=args
    )
    try:
        supported = market_adapter.supported_symbols()
        settings = LiveDryRunSettings(
            symbols=tuple(args.symbol or supported),
            strategy_name=args.strategy or config.active_strategy,
            strategy_by_symbol=_parse_strategy_map(args.strategy_map or ()),
            timeframe=args.timeframe or config.live_dry_run.timeframe,
            bars=args.bars or config.live_dry_run.bars,
            iterations=args.iterations or config.live_dry_run.iterations,
            poll_seconds=(config.live_dry_run.poll_seconds
                          if args.poll_seconds is None else args.poll_seconds),
            journal_path=args.journal,
        )
        _validate_requested_symbols(
            adapter_name="mt5", requested=settings.symbols, supported=supported
        )
        executor = Mt5LiveExecutor(
            journal_path=Path(args.journal),
            market_adapter=market_adapter,
            live=live,
            max_order_lots=args.max_order_lots,
        )
        mode = "LIVE — REAL ORDERS" if live else "SHADOW — no orders sent"
        print(f"[live-trade] mode: {mode}", flush=True)
        print(f"[live-trade] symbols: {', '.join(settings.symbols)}", flush=True)
        print(
            f"[live-trade] max order lots: {args.max_order_lots} | journal: {args.journal}",
            flush=True,
        )
        print(f"[live-trade] allocation profile: {args.allocation_profile}", flush=True)
        throttle = _live_risk_throttle_from_args(args)
        if throttle is not None:
            print(
                "[live-trade] live throttle: "
                f"max_positions={throttle.max_active_positions} "
                f"daily_loss_pct={throttle.reduce_only_daily_loss_pct} "
                f"rolling_sharpe={throttle.reduce_only_rolling_sharpe} "
                f"metrics={throttle.metrics_csv} "
                f"sentiment={throttle.sentiment_snapshot_path} "
                f"sentiment_conflict={throttle.sentiment_conflict_threshold} "
                f"symbol_state={throttle.symbol_state_snapshot_path} "
                f"blocked_states={','.join(throttle.blocked_symbol_states)} "
                f"small_only_states={','.join(throttle.small_only_symbol_states)} "
                f"small_only_max={throttle.small_only_max_notional_usd}",
                flush=True,
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
        try:
            result = engine.run(progress_callback=_print_live_progress)
        except LiveDryRunNoSuccessfulIterationsError as exc:
            raise SystemExit(str(exc)) from exc
        filled = sum(1 for r in result.records if r.status in ("MT5_FILLED", "MT5_SHADOW"))
        print(f"[live-trade] iterations={len(result.iterations)} "
              f"order-intents={filled} errors={len(result.errors)}", flush=True)
        for err in result.errors:
            print(
                f"[live-trade] skipped iteration {err.iteration_index}: {err.message}",
                flush=True,
            )
    finally:
        close = getattr(market_adapter, "close", None)
        if callable(close):
            close()


def _allocation_policy_for(
    strategy_name: str,
    config,
    *,
    profile: str = ALLOCATION_PROFILE_DEFAULT,
) -> AllocationPolicy | None:
    return allocation_policy_for_strategy(
        strategy_name,
        config,
        profile=profile,
    )


def _live_risk_throttle_from_args(args: argparse.Namespace) -> LiveRiskThrottle | None:
    if (
        args.max_live_positions is None
        and args.reduce_only_daily_loss_pct is None
        and args.reduce_only_rolling_sharpe is None
        and args.sentiment_conflict_threshold is None
        and args.symbol_state_snapshot is None
        and args.small_only_symbol_state is None
    ):
        return None
    return LiveRiskThrottle(
        max_active_positions=args.max_live_positions,
        reduce_only_daily_loss_pct=args.reduce_only_daily_loss_pct,
        reduce_only_rolling_sharpe=args.reduce_only_rolling_sharpe,
        metrics_csv=args.live_metrics_csv,
        sentiment_snapshot_path=args.sentiment_snapshot,
        sentiment_conflict_threshold=args.sentiment_conflict_threshold,
        symbol_state_snapshot_path=args.symbol_state_snapshot,
        blocked_symbol_states=tuple(
            args.blocked_symbol_state or ("cooldown_realized_drag",)
        ),
        small_only_symbol_states=tuple(args.small_only_symbol_state or ()),
        small_only_max_notional_usd=args.small_only_max_notional_usd,
    )


def main(argv: Sequence[str] | None = None) -> None:
    run(build_parser().parse_args(argv))
