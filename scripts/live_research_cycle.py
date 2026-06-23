from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from datetime import UTC
except ImportError:  # Python < 3.11
    UTC = timezone.utc

project_root = Path(__file__).resolve().parents[1]
src_path = project_root / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from quanthack.backtesting.allocation_profiles import (
    ALLOCATION_PROFILE_DEFAULT,
    ALLOCATION_PROFILE_NAMES,
    allocation_policy_for_strategy,
)
from quanthack.backtesting.portfolio_universe_scan import (
    UniverseBasket,
    scan_portfolio_universes,
    write_portfolio_universe_scan_csv,
)
from quanthack.backtesting.signal_diagnostics import (
    SignalDiagnosticRow,
    evaluate_signal_diagnostics,
    write_signal_diagnostics_csv,
)
from quanthack.core.clock import FixedModeClock
from quanthack.core.config import load_config
from quanthack.core.instruments import instrument_for
from quanthack.market.market_data import load_price_history, load_quote_history
from quanthack.strategies.strategy import STRATEGY_NAMES


DEFAULT_SYMBOLS = (
    "AUDUSD",
    "EURGBP",
    "EURUSD",
    "GBPUSD",
    "USDCAD",
    "USDCHF",
    "USDJPY",
)
DEFAULT_BASKETS = (
    "current_live:AUDUSD,EURGBP,EURUSD,GBPUSD,USDCAD,USDCHF",
    "small_only_probe:EURUSD,GBPUSD",
    "clean_recovery:EURUSD,GBPUSD,USDCAD,USDJPY",
    "usd_ok:EURUSD,USDCAD,USDJPY",
)
DEFAULT_BASKET_STRATEGIES = ("macd_momentum", "champion_ensemble")
DEFAULT_SIGNAL_STRATEGIES = (
    "champion_ensemble",
    "cross_rate_reversion",
    "alpha_router",
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run a lightweight monitor-only research cycle for active live "
            "candidate discovery."
        )
    )
    parser.add_argument("--config", default="configs/competition.toml")
    parser.add_argument("--price-csv", default="data/full_20gb_15m_prices.csv")
    parser.add_argument("--quote-csv", default="data/full_20gb_15m_quotes.csv")
    parser.add_argument("--symbol", action="append", default=None)
    parser.add_argument("--basket", action="append", default=None)
    parser.add_argument(
        "--basket-strategy",
        action="append",
        choices=STRATEGY_NAMES,
        default=None,
    )
    parser.add_argument(
        "--signal-strategy",
        action="append",
        choices=STRATEGY_NAMES,
        default=None,
    )
    parser.add_argument("--horizon-bars", type=int, default=4)
    parser.add_argument("--min-basket-fills", type=int, default=1)
    parser.add_argument("--min-symbols", type=int, default=2)
    parser.add_argument("--max-symbols", type=int, default=6)
    parser.add_argument("--min-signal-active-count", type=int, default=4)
    parser.add_argument("--min-signal-hit-rate", type=float, default=0.55)
    parser.add_argument("--min-signal-signed-bps", type=float, default=0.0)
    parser.add_argument("--min-signal-edge-bps", type=float, default=0.0)
    parser.add_argument(
        "--basket-allocation-profile",
        choices=ALLOCATION_PROFILE_NAMES,
        default=ALLOCATION_PROFILE_DEFAULT,
        help="Monitor-only portfolio sizing profile for basket scans.",
    )
    parser.add_argument(
        "--force-qualify-mode",
        action="store_true",
        help="Run basket scans with a fixed QUALIFY research clock.",
    )
    parser.add_argument(
        "--basket-output",
        default="outputs/backtests/live_watch_activity_gated_basket_scan.csv",
    )
    parser.add_argument(
        "--signal-output-dir",
        default="outputs/backtests",
    )
    parser.add_argument(
        "--output-json",
        default="outputs/live_research_cycle_latest.json",
    )
    parser.add_argument(
        "--output-text",
        default="outputs/live_research_cycle_latest.txt",
    )
    parser.add_argument(
        "--history-jsonl",
        default="outputs/live_research_cycle_history.jsonl",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    summary = run_cycle(args)
    write_summary(summary, args.output_json, args.output_text, args.history_jsonl)
    print(
        "wrote live research cycle "
        f"to {args.output_json} qualified_signals="
        f"{summary['signal_diagnostics']['qualified_count']}"
    )


def run_cycle(args: argparse.Namespace) -> dict[str, Any]:
    config = load_config(args.config)
    prices = load_price_history(args.price_csv)
    quotes = load_quote_history(args.quote_csv)
    available_symbols = tuple(sorted(set(prices.symbols()) & set(quotes.symbols())))
    selected_symbols = _selected_symbols(args.symbol, available_symbols)
    baskets = _parse_baskets(args.basket or list(DEFAULT_BASKETS), available_symbols)
    basket_strategies = tuple(args.basket_strategy or DEFAULT_BASKET_STRATEGIES)
    signal_strategies = tuple(args.signal_strategy or DEFAULT_SIGNAL_STRATEGIES)
    basket_allocation_policy = allocation_policy_for_strategy(
        "live_research_cycle",
        config,
        profile=args.basket_allocation_profile,
    )

    basket_scan = scan_portfolio_universes(
        config=config,
        prices=prices,
        quotes=quotes,
        strategy_names=basket_strategies,
        baskets=baskets,
        min_symbols=args.min_symbols,
        max_symbols=args.max_symbols,
        max_baskets=max(len(baskets), 1),
        min_fills=args.min_basket_fills,
        allocation_policy=basket_allocation_policy,
        clock=FixedModeClock() if args.force_qualify_mode else None,
    )
    write_portfolio_universe_scan_csv(basket_scan, args.basket_output)

    signal_reports: list[dict[str, Any]] = []
    qualified_rows: list[dict[str, Any]] = []
    signal_output_dir = Path(args.signal_output_dir)
    for strategy_name in signal_strategies:
        diag_symbols = _signal_symbols_for(strategy_name, selected_symbols, available_symbols)
        if not diag_symbols:
            signal_reports.append(
                {
                    "strategy": strategy_name,
                    "status": "SKIPPED",
                    "reason": "no symbols with required context",
                    "rows": [],
                }
            )
            continue
        try:
            report = evaluate_signal_diagnostics(
                config=config,
                prices=prices,
                quotes=quotes,
                strategy_name=strategy_name,
                symbols=diag_symbols,
                horizon_bars=args.horizon_bars,
                min_confidence=0.0,
                min_edge_after_cost_bps=-999.0,
            )
        except ValueError as exc:
            signal_reports.append(
                {
                    "strategy": strategy_name,
                    "status": "ERROR",
                    "reason": str(exc),
                    "rows": [],
                }
            )
            continue

        output_path = signal_output_dir / (
            f"live_watch_signal_diag_{strategy_name}_h{args.horizon_bars}.csv"
        )
        write_signal_diagnostics_csv(report, output_path)
        rows = [_signal_row_payload(row) for row in report.ranked_rows[:10]]
        qualified = [
            row for row in report.ranked_rows
            if qualifies_signal_row(
                row,
                min_active_count=args.min_signal_active_count,
                min_hit_rate=args.min_signal_hit_rate,
                min_signed_bps=args.min_signal_signed_bps,
                min_edge_bps=args.min_signal_edge_bps,
            )
        ]
        qualified_rows.extend(
            {
                **_signal_row_payload(row),
                "strategy": strategy_name,
            }
            for row in qualified
        )
        signal_reports.append(
            {
                "strategy": strategy_name,
                "status": "OK",
                "output_csv": str(output_path),
                "row_count": len(report.rows),
                "qualified_count": len(qualified),
                "rows": rows,
            }
        )

    qualified_rows.sort(
        key=lambda row: (
            row["average_signed_forward_return_bps"],
            row["hit_rate"],
            row["active_count"],
        ),
        reverse=True,
    )

    return {
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "inputs": {
            "config": args.config,
            "price_csv": args.price_csv,
            "quote_csv": args.quote_csv,
            "symbols": selected_symbols,
            "basket_allocation_profile": args.basket_allocation_profile,
            "force_qualify_mode": args.force_qualify_mode,
        },
        "basket_scan": {
            "output_csv": args.basket_output,
            "candidate_count": len(basket_scan.rows),
            "active_count": sum(
                1 for row in basket_scan.rows
                if row.activity_status == "ACTIVE"
            ),
            "underactive_count": sum(
                1 for row in basket_scan.rows
                if row.activity_status != "ACTIVE"
            ),
            "top_candidates": [_basket_row_payload(row) for row in basket_scan.rows[:5]],
        },
        "signal_diagnostics": {
            "horizon_bars": args.horizon_bars,
            "qualified_count": len(qualified_rows),
            "qualified_rows": qualified_rows[:10],
            "reports": signal_reports,
        },
    }


def write_summary(
    summary: dict[str, Any],
    output_json: str | Path,
    output_text: str | Path,
    history_jsonl: str | Path,
) -> None:
    json_path = Path(output_json)
    text_path = Path(output_text)
    history_path = Path(history_jsonl)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    text_path.parent.mkdir(parents=True, exist_ok=True)
    history_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    text_path.write_text(summary_text(summary), encoding="utf-8")
    with history_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(summary, sort_keys=True) + "\n")


def summary_text(summary: dict[str, Any]) -> str:
    basket = summary["basket_scan"]
    signals = summary["signal_diagnostics"]
    inputs = summary.get("inputs", {})
    lines = [
        f"{summary['timestamp_utc']} live_research_cycle",
        (
            "basket_scan "
            f"candidates={basket['candidate_count']} "
            f"active={basket['active_count']} "
            f"underactive={basket['underactive_count']} "
            f"profile={inputs.get('basket_allocation_profile', 'default')} "
            f"force_qualify={str(inputs.get('force_qualify_mode', False)).lower()}"
        ),
    ]
    if basket["top_candidates"]:
        top = basket["top_candidates"][0]
        lines.append(
            "basket_top "
            f"{top['basket']}/{top['strategy']} "
            f"status={top['activity_status']} "
            f"fills={top['fills']} proxy={top['proxy_score']:.1f}"
        )
    lines.append(
        "signals "
        f"horizon={signals['horizon_bars']} "
        f"qualified={signals['qualified_count']}"
    )
    for row in signals["qualified_rows"][:5]:
        lines.append(
            "signal_candidate "
            f"{row['strategy']}:{row['symbol']}:{row['signal']} "
            f"active={row['active_count']} "
            f"hit={row['hit_rate']:.1%} "
            f"signed={row['average_signed_forward_return_bps']:.2f}bps "
            f"edge={row['average_edge_after_cost_bps']:.2f}bps"
        )
    return "\n".join(lines) + "\n"


def qualifies_signal_row(
    row: SignalDiagnosticRow,
    *,
    min_active_count: int,
    min_hit_rate: float,
    min_signed_bps: float,
    min_edge_bps: float,
) -> bool:
    return (
        row.active_count >= min_active_count
        and row.hit_rate >= min_hit_rate
        and row.average_signed_forward_return_bps >= min_signed_bps
        and row.average_edge_after_cost_bps >= min_edge_bps
    )


def _selected_symbols(
    requested: list[str] | None,
    available_symbols: tuple[str, ...],
) -> tuple[str, ...]:
    raw_symbols = tuple(requested or DEFAULT_SYMBOLS)
    selected: list[str] = []
    for raw_symbol in raw_symbols:
        symbol = instrument_for(raw_symbol).symbol
        if symbol in available_symbols and symbol not in selected:
            selected.append(symbol)
    if not selected:
        raise ValueError("no requested symbols are present in price/quote data")
    return tuple(selected)


def _parse_baskets(
    values: list[str],
    available_symbols: tuple[str, ...],
) -> tuple[UniverseBasket, ...]:
    baskets: list[UniverseBasket] = []
    for index, value in enumerate(values, start=1):
        if ":" in value:
            name, symbol_text = value.split(":", 1)
            name = name.strip()
        else:
            name = f"custom_{index}"
            symbol_text = value
        symbols = tuple(
            instrument_for(symbol.strip()).symbol
            for symbol in symbol_text.replace(" ", ",").split(",")
            if symbol.strip()
        )
        present = tuple(symbol for symbol in symbols if symbol in available_symbols)
        if present:
            baskets.append(UniverseBasket(name, present))
    if not baskets:
        raise ValueError("no basket symbols are present in price/quote data")
    return tuple(baskets)


def _signal_symbols_for(
    strategy_name: str,
    selected_symbols: tuple[str, ...],
    available_symbols: tuple[str, ...],
) -> tuple[str, ...]:
    if strategy_name == "cross_rate_reversion":
        required = ("EURGBP", "EURUSD", "GBPUSD")
        if all(symbol in available_symbols for symbol in required):
            return tuple(symbol for symbol in required if symbol in selected_symbols or symbol in required)
        return ()
    return selected_symbols


def _basket_row_payload(row: Any) -> dict[str, Any]:
    return {
        "basket": row.basket.name,
        "strategy": row.strategy_name,
        "symbols": " ".join(row.basket.symbols),
        "proxy_score": row.proxy_score,
        "activity_status": row.activity_status,
        "fills": len(row.result.fills),
        "return_pct": row.competition_metrics.return_pct,
        "max_drawdown_pct": row.competition_metrics.max_drawdown_pct,
        "sharpe_15m": row.competition_metrics.sharpe_15m,
    }


def _signal_row_payload(row: SignalDiagnosticRow) -> dict[str, Any]:
    payload = asdict(row)
    payload["signal"] = payload.pop("signal_name")
    return payload


if __name__ == "__main__":
    main()
