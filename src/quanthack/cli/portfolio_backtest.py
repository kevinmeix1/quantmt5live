from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from dataclasses import replace

from quanthack.backtesting.allocation_profiles import (
    ALLOCATION_PROFILE_DEFAULT,
    ALLOCATION_PROFILE_NAMES,
    allocation_policy_for_strategy,
)
from quanthack.backtesting.backtest import FillModel
from quanthack.cli._competition import print_competition_view
from quanthack.cli._format import money
from quanthack.backtesting.competition_score import (
    build_competition_metrics,
    build_risk_discipline_report,
    risk_samples_from_portfolio_equity,
)
from quanthack.core.config import load_config
from quanthack.core.clock import FixedModeClock
from quanthack.core.instruments import instrument_for
from quanthack.market.market_data import load_price_history, load_quote_history
from quanthack.backtesting.portfolio_allocator import write_allocation_report_csv
from quanthack.backtesting.portfolio_backtest import (
    PortfolioBacktestEngine,
    write_portfolio_equity_curve_csv,
    write_portfolio_fills_csv,
    write_portfolio_pnl_summary_csv,
)
from quanthack.backtesting.warmup import evaluate_portfolio_after_warmup
from quanthack.strategies.strategy import STRATEGY_NAMES


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a shared-risk portfolio backtest.")
    parser.add_argument("--config", default="configs/default.toml")
    parser.add_argument("--strategy", choices=STRATEGY_NAMES, default=None)
    parser.add_argument(
        "--strategy-map",
        action="append",
        default=None,
        metavar="SYMBOL=STRATEGY",
        help=(
            "Optional per-symbol strategy override. Repeat for hybrid portfolios; "
            "symbols not listed use --strategy or the configured active strategy."
        ),
    )
    parser.add_argument("--symbol", action="append", default=None)
    parser.add_argument("--price-csv", default=None)
    parser.add_argument("--quote-csv", default=None)
    parser.add_argument(
        "--equity-output",
        default="outputs/backtests/portfolio_equity_curve.csv",
    )
    parser.add_argument(
        "--pnl-output",
        default="outputs/backtests/portfolio_pnl_summary.csv",
    )
    parser.add_argument(
        "--allocation-output",
        default="outputs/backtests/portfolio_allocation_report.csv",
    )
    parser.add_argument(
        "--fills-output",
        default="outputs/backtests/portfolio_fills.csv",
    )
    parser.add_argument(
        "--metrics-start",
        default=None,
        help=(
            "Optional timezone-aware ISO timestamp for competition metrics after "
            "a warmup period."
        ),
    )
    parser.add_argument(
        "--allocation-profile",
        choices=ALLOCATION_PROFILE_NAMES,
        default=ALLOCATION_PROFILE_DEFAULT,
        help=(
            "Optional allocation profile for research. 'directional_probe' "
            "matches bounded one-sided live probe diagnostics."
        ),
    )
    parser.add_argument(
        "--force-qualify-mode",
        action="store_true",
        help=(
            "Research-only: treat historical bars as QUALIFY even when they are "
            "before the configured live open_at."
        ),
    )
    return parser


def run(args: argparse.Namespace) -> None:
    config = load_config(args.config)
    strategy_name = args.strategy or config.active_strategy
    strategy_by_symbol = _parse_strategy_map(args.strategy_map or ())
    price_csv = args.price_csv or config.backtest.price_csv
    quote_csv = args.quote_csv or config.backtest.quote_csv
    prices = load_price_history(price_csv)
    quotes = load_quote_history(quote_csv)
    symbols = tuple(args.symbol or sorted(set(prices.symbols()) & set(quotes.symbols())))
    if not symbols:
        raise SystemExit("No symbols found in both price and quote data.")

    engine = PortfolioBacktestEngine(
        strategies={
            symbol: config.build_strategy(
                strategy_by_symbol.get(symbol, strategy_name),
                symbol=symbol,
            )
            for symbol in symbols
        },
        risk_limits=config.risk,
        quality_limits=config.market_quality,
        quality_limits_by_symbol={
            symbol: replace(
                config.market_quality,
                max_spread_bps=instrument_for(symbol).max_spread_bps,
            )
            for symbol in symbols
        },
        allocation_policy=allocation_policy_for_strategy(
            strategy_name,
            config,
            profile=args.allocation_profile,
        ),
        clock=FixedModeClock() if args.force_qualify_mode else config.competition.to_clock(),
        fill_model=FillModel(slippage_bps=config.backtest.slippage_bps),
        periods_per_year=config.backtest.periods_per_year,
    )
    result = engine.run(
        prices=prices,
        quotes=quotes,
        starting_equity=config.competition.starting_equity,
    )
    write_portfolio_equity_curve_csv(result, args.equity_output)
    write_portfolio_pnl_summary_csv(result, args.pnl_output)
    write_allocation_report_csv(result.allocation_reports, args.allocation_output)
    write_portfolio_fills_csv(result, args.fills_output)
    if args.metrics_start:
        warmup_evaluation = evaluate_portfolio_after_warmup(
            result,
            evaluation_start=args.metrics_start,
        )
        competition_metrics = warmup_evaluation.competition_metrics
        risk_discipline = warmup_evaluation.risk_discipline
    else:
        warmup_evaluation = None
        competition_metrics = build_competition_metrics(
            equity_points=result.equity_curve,
            fills=result.fills,
        )
        risk_discipline = build_risk_discipline_report(
            risk_samples_from_portfolio_equity(result.equity_curve)
        )

    metrics = result.metrics
    display_strategy = _strategy_display(strategy_name, strategy_by_symbol)
    print("Portfolio Backtest")
    print(f"  Strategy: {display_strategy}")
    print(f"  Symbols: {', '.join(result.symbols)}")
    print(f"  Price CSV: {price_csv}")
    print(f"  Quote CSV: {quote_csv}")
    print(f"  Allocation profile: {args.allocation_profile}")
    print(f"  Force qualify mode: {'yes' if args.force_qualify_mode else 'no'}")
    print(f"  Fills: {len(result.fills)}")
    if warmup_evaluation is not None:
        print(f"  Metrics start: {warmup_evaluation.evaluation_start}")
        print(f"  Evaluation fills: {len(warmup_evaluation.fills)}")
    print(f"  Observations: {metrics.observations}")
    print(f"  Final equity: {money(metrics.final_equity)}")
    print(f"  Total return: {metrics.total_return_pct:.3%}")
    print(f"  Sharpe ratio: {metrics.sharpe_ratio:.3f}")
    print(f"  Max drawdown: {metrics.max_drawdown_pct:.3%}")
    print(f"  Turnover: {money(metrics.turnover_notional)}")
    print(f"  Realized P&L: {money(result.realized_pnl_usd)}")
    print(f"  Open P&L: {money(result.open_pnl_usd)}")
    print(f"  Total attributed P&L: {money(result.total_pnl_usd)}")
    print(f"  Equity curve: {args.equity_output}")
    print(f"  P&L summary: {args.pnl_output}")
    print(f"  Allocation report: {args.allocation_output}")
    print(f"  Fills: {args.fills_output}")
    print_competition_view(
        metrics=competition_metrics,
        risk_discipline=risk_discipline,
    )
    _print_allocation_summary(result.allocation_reports)

    print("By symbol")
    for row in result.pnl_by_symbol:
        print(
            f"  {row.symbol}: "
            f"realized={money(row.ledger.realized_pnl_usd)}, "
            f"open={money(row.ledger.open_pnl_usd)}, "
            f"total={money(row.ledger.total_pnl_usd)}"
        )


def main(argv: Sequence[str] | None = None) -> None:
    run(build_parser().parse_args(argv))


def _print_allocation_summary(reports: tuple) -> None:
    if not reports:
        return
    trimmed_periods = len([report for report in reports if report.trimmed_targets])
    worst_net = max(report.net_directional_exposure for report in reports)
    worst_concentration = max(report.largest_symbol_concentration for report in reports)
    worst_leverage = max(report.leverage for report in reports)
    statuses = sorted({report.estimated_risk_status for report in reports})

    print("Allocation guardrails")
    print(f"  Periods trimmed: {trimmed_periods}/{len(reports)}")
    print(f"  Worst leverage: {worst_leverage:.2f}x")
    print(f"  Worst net directional exposure: {worst_net:.1%}")
    print(f"  Worst largest-symbol concentration: {worst_concentration:.1%}")
    print(f"  Estimated allocation statuses: {', '.join(statuses)}")


def _parse_strategy_map(values: Sequence[str]) -> dict[str, str]:
    strategy_by_symbol: dict[str, str] = {}
    for raw_value in values:
        if "=" not in raw_value:
            raise SystemExit(
                "--strategy-map values must use SYMBOL=STRATEGY, "
                f"got {raw_value!r}"
            )
        raw_symbol, raw_strategy = raw_value.split("=", 1)
        symbol = instrument_for(raw_symbol).symbol
        strategy = raw_strategy.strip()
        if not strategy:
            raise SystemExit("--strategy-map strategy name cannot be empty")
        if strategy not in STRATEGY_NAMES:
            valid = ", ".join(STRATEGY_NAMES)
            raise SystemExit(
                f"unknown strategy {strategy!r} in --strategy-map; expected one of: {valid}"
            )
        strategy_by_symbol[symbol] = strategy
    return strategy_by_symbol


def _strategy_display(
    fallback_strategy: str,
    strategy_by_symbol: Mapping[str, str],
) -> str:
    if not strategy_by_symbol:
        return fallback_strategy
    overrides = ", ".join(
        f"{symbol}={strategy}" for symbol, strategy in sorted(strategy_by_symbol.items())
    )
    return f"{fallback_strategy} with overrides ({overrides})"
