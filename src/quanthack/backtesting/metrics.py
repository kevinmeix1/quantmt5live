from __future__ import annotations

from dataclasses import dataclass
from math import isfinite, sqrt
from statistics import fmean, pstdev


# A finite stand-in for an "infinite" profit factor (gains but zero losses).
# Returning math.inf here breaks CSV serialization, ranking comparisons, and
# JSON reports, so we cap at a large sentinel instead.
MAX_PROFIT_FACTOR = 1_000_000.0


@dataclass(frozen=True)
class PerformanceMetrics:
    observations: int
    final_equity: float
    total_return_pct: float
    sharpe_ratio: float
    max_drawdown_pct: float
    win_rate: float
    profit_factor: float
    turnover_notional: float
    # Fraction of *all* periods (including flat ones) that were positive. Unlike
    # ``win_rate`` (which excludes flat periods), this does not flatter
    # low-activity strategies. Defaults to 0.0 so existing keyword construction
    # and any pickled/serialized instances remain valid.
    positive_period_rate: float = 0.0


def compute_returns(equity_curve: list[float]) -> list[float]:
    returns: list[float] = []
    for previous, current in zip(equity_curve, equity_curve[1:]):
        if previous <= 0:
            raise ValueError("equity values must stay positive to compute returns")
        returns.append((current / previous) - 1.0)
    return returns


def max_drawdown(equity_curve: list[float]) -> float:
    if not equity_curve:
        return 0.0

    peak = equity_curve[0]
    worst = 0.0
    for equity in equity_curve:
        if equity <= 0 or not isfinite(equity):
            raise ValueError("equity values must be positive finite numbers")
        peak = max(peak, equity)
        drawdown = 1.0 - (equity / peak)
        worst = max(worst, drawdown)
    return worst


def sharpe_ratio(returns: list[float], *, periods_per_year: float) -> float:
    if len(returns) < 2:
        return 0.0

    volatility = pstdev(returns)
    if volatility == 0:
        return 0.0

    return (fmean(returns) / volatility) * sqrt(periods_per_year)


def win_rate(returns: list[float]) -> float:
    non_zero = [value for value in returns if value != 0]
    if not non_zero:
        return 0.0
    wins = [value for value in non_zero if value > 0]
    return len(wins) / len(non_zero)


def positive_period_rate(returns: list[float]) -> float:
    """Fraction of all periods that were strictly positive (flat counts against)."""
    if not returns:
        return 0.0
    wins = sum(1 for value in returns if value > 0)
    return wins / len(returns)


def profit_factor_from_pnl(pnls: list[float]) -> float:
    gains = sum(value for value in pnls if value > 0)
    losses = abs(sum(value for value in pnls if value < 0))
    if losses == 0:
        # No losing periods: cap at a finite sentinel rather than +inf so the
        # value survives ranking/serialization. Zero gains stays 0.0.
        return MAX_PROFIT_FACTOR if gains > 0 else 0.0
    return min(gains / losses, MAX_PROFIT_FACTOR)


def summarize_performance(
    *,
    equity_curve: list[float],
    turnover_notional: float,
    periods_per_year: float,
) -> PerformanceMetrics:
    if not equity_curve:
        raise ValueError("equity_curve is required")

    returns = compute_returns(equity_curve)
    pnl_steps = [
        current - previous for previous, current in zip(equity_curve, equity_curve[1:])
    ]
    starting_equity = equity_curve[0]
    final_equity = equity_curve[-1]

    return PerformanceMetrics(
        observations=len(equity_curve),
        final_equity=final_equity,
        total_return_pct=(final_equity / starting_equity) - 1.0,
        sharpe_ratio=sharpe_ratio(returns, periods_per_year=periods_per_year),
        max_drawdown_pct=max_drawdown(equity_curve),
        win_rate=win_rate(returns),
        profit_factor=profit_factor_from_pnl(pnl_steps),
        turnover_notional=turnover_notional,
        positive_period_rate=positive_period_rate(returns),
    )

