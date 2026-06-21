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

from quanthack.cli.live_dry_run import (
    _build_adapters,
    _parse_strategy_map,
    _validate_requested_symbols,
)
from quanthack.core.config import load_config
from quanthack.core.env import load_env_file
from quanthack.strategies.strategy import STRATEGY_NAMES
from quanthack.trading.live_dry_run import LiveDryRunEngine, LiveDryRunSettings
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
    p.add_argument("--i-understand-live-orders", action="store_true",
                   help="REQUIRED to place real orders. Without it, runs in shadow mode.")
    return p


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
        print(f"[live-trade] mode: {mode}")
        print(f"[live-trade] symbols: {', '.join(settings.symbols)}")
        print(f"[live-trade] max order lots: {args.max_order_lots} | journal: {args.journal}")
        engine = LiveDryRunEngine(
            config=config,
            settings=settings,
            market_data=market_adapter,
            account_adapter=account_adapter,
            executor=executor,
        )
        result = engine.run()
        filled = sum(1 for r in result.records if r.status in ("MT5_FILLED", "MT5_SHADOW"))
        print(f"[live-trade] iterations={len(result.iterations)} "
              f"order-intents={filled} errors={len(result.errors)}")
        for err in result.errors:
            print(f"[live-trade] skipped iteration {err.iteration_index}: {err.message}")
    finally:
        close = getattr(market_adapter, "close", None)
        if callable(close):
            close()


def main(argv: Sequence[str] | None = None) -> None:
    run(build_parser().parse_args(argv))
