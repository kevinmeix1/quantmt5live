from __future__ import annotations

import argparse
from collections.abc import Sequence

from quanthack.cli._format import money
from quanthack.core.config import load_config
from quanthack.market.market_data import load_price_history, load_quote_history
from quanthack.backtesting.router_optimizer import (
    DEFAULT_ROUTER_WEIGHT_SETS,
    RouterWeightSet,
    optimize_router_weights,
    write_router_optimization_csv,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Optimize alpha-router weights with allocator-aware portfolio backtests."
    )
    parser.add_argument("--config", default="configs/default.toml")
    parser.add_argument("--symbol", action="append", default=None)
    parser.add_argument("--price-csv", default=None)
    parser.add_argument("--quote-csv", default=None)
    parser.add_argument(
        "--candidate",
        action="append",
        default=None,
        help=(
            "Weight tuple as momentum,ma,breakout,mean_reversion or "
            "momentum,ma,breakout,mean_reversion,session_breakout,cross_rate "
            "or momentum,ma,breakout,mean_reversion,session_breakout,cross_rate,"
            "relative_strength or momentum,ma,breakout,mean_reversion,"
            "session_breakout,cross_rate,relative_strength,volatility_squeeze "
            "or momentum,ma,breakout,mean_reversion,session_breakout,cross_rate,"
            "relative_strength,volatility_squeeze,dual_squeeze"
        ),
    )
    parser.add_argument(
        "--output",
        default="outputs/backtests/router_weight_optimization.csv",
    )
    return parser


def run(args: argparse.Namespace) -> None:
    config = load_config(args.config)
    price_csv = args.price_csv or config.backtest.price_csv
    quote_csv = args.quote_csv or config.backtest.quote_csv
    weight_sets = (
        tuple(_parse_candidate(value) for value in args.candidate)
        if args.candidate
        else DEFAULT_ROUTER_WEIGHT_SETS
    )
    result = optimize_router_weights(
        config=config,
        prices=load_price_history(price_csv),
        quotes=load_quote_history(quote_csv),
        symbols=tuple(args.symbol) if args.symbol else None,
        weight_sets=weight_sets,
    )
    write_router_optimization_csv(result, args.output)

    print("Router Weight Optimization")
    print(f"  Symbols: {', '.join(result.symbols)}")
    print(f"  Price CSV: {price_csv}")
    print(f"  Quote CSV: {quote_csv}")
    print(f"  Output CSV: {args.output}")
    print("Ranked candidates")
    for rank, candidate in enumerate(result.candidates, start=1):
        metrics = candidate.competition_metrics
        print(
            f"  {rank}. {candidate.weights.label}: "
            f"proxy={candidate.proxy_score:.1f}, "
            f"return={metrics.return_pct:.3%}, "
            f"drawdown={metrics.max_drawdown_pct:.3%}, "
            f"sharpe15={metrics.sharpe_15m:.3f}, "
            f"risk={candidate.risk_discipline.score}/100, "
            f"final={money(metrics.final_equity)}, "
            f"trades={metrics.trade_count}"
        )


def main(argv: Sequence[str] | None = None) -> None:
    run(build_parser().parse_args(argv))


def _parse_candidate(raw: str) -> RouterWeightSet:
    parts = [part.strip() for part in raw.split(",")]
    if len(parts) not in {4, 6, 7, 8, 9}:
        raise argparse.ArgumentTypeError(
            "candidate must contain four, six, seven, eight, or nine comma-separated weights"
        )
    try:
        values = tuple(float(part) for part in parts)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("candidate weights must be numbers") from exc
    return RouterWeightSet(*values)
