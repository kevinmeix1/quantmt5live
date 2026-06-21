"""KILL-SWITCH: flatten all open MT5 positions immediately.

Use this to de-risk instantly — e.g. if the bot misbehaves, before a round cut
to lock in the round's return, or to avoid a developing stop-out. In shadow mode
(default) it only reports what it WOULD close.
"""
from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from quanthack.cli.live_dry_run import _build_adapters
from quanthack.core.config import load_config
from quanthack.core.env import load_env_file
from quanthack.trading.mt5_executor import Mt5LiveExecutor


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Close ALL open MT5 positions (kill-switch).")
    p.add_argument("--config", default="configs/competition.toml")
    p.add_argument("--env-file", default=".env")
    p.add_argument("--journal", default="outputs/live_orders_journal.jsonl")
    p.add_argument("--mt5-terminal-path", default=None)
    p.add_argument("--mt5-login", type=int, default=None)
    p.add_argument("--mt5-password", default=None)
    p.add_argument("--mt5-server", default=None)
    p.add_argument("--mt5-timeout-ms", type=int, default=60_000)
    p.add_argument("--mt5-portable", action="store_true")
    p.add_argument("--mt5-symbol-map", action="append", default=None)
    p.add_argument("--i-understand-live-orders", action="store_true",
                   help="REQUIRED to actually close positions. Without it, shadow only.")
    return p


def run(args: argparse.Namespace) -> None:
    load_env_file(args.env_file)
    config = load_config(args.config)
    args.confirm_read_only_mt5 = True
    market_adapter, _ = _build_adapters(adapter_name="mt5", config=config, args=args)
    try:
        executor = Mt5LiveExecutor(
            journal_path=Path(args.journal),
            market_adapter=market_adapter,
            live=bool(args.i_understand_live_orders),
        )
        mode = "LIVE — closing positions" if executor.live else "SHADOW — reporting only"
        print(f"[mt5-flatten] {mode}")
        results = executor.flatten_all(reason="manual kill-switch")
        if not results:
            print("[mt5-flatten] no open positions.")
        for r in results:
            tag = "would close" if r.get("shadow") else ("closed" if r.get("ok") else "FAILED")
            print(f"  {tag}: {r.get('symbol')} {r.get('close_side', r.get('side'))} "
                  f"{r.get('lots')} lots {('retcode=' + str(r.get('retcode'))) if not r.get('shadow') else ''}")
    finally:
        close = getattr(market_adapter, "close", None)
        if callable(close):
            close()


def main(argv: Sequence[str] | None = None) -> None:
    run(build_parser().parse_args(argv))
