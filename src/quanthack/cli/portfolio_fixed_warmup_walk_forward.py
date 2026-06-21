from __future__ import annotations

import argparse
from collections.abc import Sequence

from quanthack.backtesting.portfolio_fixed_warmup_walk_forward import (
    decide_fixed_warmup_promotion,
    run_fixed_warmup_portfolio_walk_forward,
    write_fixed_warmup_folds_csv,
    write_fixed_warmup_summary_csv,
)
from quanthack.core.config import load_config
from quanthack.core.instruments import instrument_for
from quanthack.market.market_data import load_price_history, load_quote_history
from quanthack.strategies.strategy import STRATEGY_NAMES


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run fixed-symbol portfolio walk-forward with warmup history."
    )
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
    parser.add_argument("--train-size", type=int, default=960)
    parser.add_argument("--test-size", type=int, default=192)
    parser.add_argument("--step-size", type=int, default=192)
    parser.add_argument(
        "--summary-output",
        default="outputs/backtests/fixed_warmup_walk_forward_summary.csv",
    )
    parser.add_argument(
        "--folds-output",
        default="outputs/backtests/fixed_warmup_walk_forward_folds.csv",
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

    result = run_fixed_warmup_portfolio_walk_forward(
        config=config,
        prices=prices,
        quotes=quotes,
        strategy_name=strategy_name,
        symbols=symbols,
        strategy_by_symbol=strategy_by_symbol,
        train_size=args.train_size,
        test_size=args.test_size,
        step_size=args.step_size,
    )
    write_fixed_warmup_summary_csv(result, args.summary_output)
    write_fixed_warmup_folds_csv(result, args.folds_output)
    promotion = decide_fixed_warmup_promotion(result)

    print("Fixed Warmup Portfolio Walk-Forward")
    print(f"  Strategy: {result.strategy_name}")
    print(f"  Symbols: {', '.join(result.symbols)}")
    print(f"  Price CSV: {price_csv}")
    print(f"  Quote CSV: {quote_csv}")
    print(f"  Folds: {len(result.folds)}")
    print(f"  Positive fold fraction: {result.positive_fold_fraction:.1%}")
    print(f"  Active fold fraction: {result.active_fold_fraction:.1%}")
    print(
        "  Active positive fold fraction: "
        f"{result.active_positive_fold_fraction:.1%}"
    )
    print(f"  Non-negative fold fraction: {result.non_negative_fold_fraction:.1%}")
    print(f"  Median test return: {result.median_test_return_pct:.3%}")
    print(f"  Median active test return: {result.median_active_test_return_pct:.3%}")
    print(f"  Median test Sharpe 15m: {result.median_test_sharpe_15m:.3f}")
    print(f"  Worst test drawdown: {result.worst_test_drawdown_pct:.3%}")
    print(f"  Average risk discipline: {result.average_risk_discipline_score:.1f}/100")
    print(f"  Evaluation fills: {result.total_evaluation_fills}")
    print(
        "  Largest positive fold contribution: "
        f"{result.largest_positive_fold_contribution:.1%}"
    )
    print(f"  Promotion: {promotion.status} ({promotion.reason})")
    print(f"  Summary CSV: {args.summary_output}")
    print(f"  Folds CSV: {args.folds_output}")
    print("Folds")
    for fold in result.folds:
        metrics = fold.metrics
        print(
            f"  {fold.fold_index}. {fold.test_start} -> {fold.test_end}: "
            f"return={metrics.return_pct:.3%}, "
            f"drawdown={metrics.max_drawdown_pct:.3%}, "
            f"sharpe15={metrics.sharpe_15m:.3f}, "
            f"fills={len(fold.evaluation.fills)}, "
            f"risk={fold.risk_discipline.score}/100"
        )


def main(argv: Sequence[str] | None = None) -> None:
    run(build_parser().parse_args(argv))


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
