from __future__ import annotations

import csv
from dataclasses import dataclass, replace
from pathlib import Path

from quanthack.backtesting.portfolio_allocator import AllocationPolicy
from quanthack.backtesting.portfolio_fixed_warmup_walk_forward import (
    FixedWarmupPromotionDecision,
    FixedWarmupPortfolioWalkForwardResult,
    decide_fixed_warmup_promotion,
    run_fixed_warmup_portfolio_walk_forward,
)
from quanthack.backtesting.portfolio_strategy_compare import (
    PortfolioStrategyComparisonRow,
    compare_portfolio_strategies,
)
from quanthack.core.clock import CompetitionClock, FixedModeClock
from quanthack.core.config import AppConfig
from quanthack.market.market_data import PriceHistory, QuoteHistory


@dataclass(frozen=True)
class QualityTrendParameterSet:
    label: str
    kalman_min_abs_slope_bps: float
    kalman_min_expected_edge_bps: float
    macd_min_histogram_bps: float
    macd_min_macd_bps: float
    macd_min_trend_efficiency: float
    min_combined_confidence: float
    min_expected_edge_bps: float
    max_holding_period: int
    allowed_utc_hours: tuple[int, ...] | None = None

    def __post_init__(self) -> None:
        if not self.label.strip():
            raise ValueError("quality trend parameter label is required")
        if self.kalman_min_abs_slope_bps < 0:
            raise ValueError("kalman_min_abs_slope_bps cannot be negative")
        if self.kalman_min_expected_edge_bps < 0:
            raise ValueError("kalman_min_expected_edge_bps cannot be negative")
        if self.macd_min_histogram_bps <= 0:
            raise ValueError("macd_min_histogram_bps must be positive")
        if self.macd_min_macd_bps < 0:
            raise ValueError("macd_min_macd_bps cannot be negative")
        if not 0 <= self.macd_min_trend_efficiency <= 1:
            raise ValueError("macd_min_trend_efficiency must be between 0 and 1")
        if not 0 <= self.min_combined_confidence <= 1:
            raise ValueError("min_combined_confidence must be between 0 and 1")
        if self.min_expected_edge_bps < 0:
            raise ValueError("min_expected_edge_bps cannot be negative")
        if self.max_holding_period < 1:
            raise ValueError("max_holding_period must be positive")
        if self.allowed_utc_hours is not None:
            if not self.allowed_utc_hours:
                raise ValueError("allowed_utc_hours cannot be empty")
            if any(hour < 0 or hour > 23 for hour in self.allowed_utc_hours):
                raise ValueError("allowed_utc_hours must be between 0 and 23")


DEFAULT_QUALITY_TREND_PARAMETER_SETS: tuple[QualityTrendParameterSet, ...] = (
    QualityTrendParameterSet(
        "current_h10_14",
        0.25,
        5.0,
        2.0,
        1.0,
        0.20,
        0.30,
        2.0,
        16,
    ),
    QualityTrendParameterSet(
        "extended_h10_17",
        0.25,
        5.0,
        2.0,
        1.0,
        0.20,
        0.30,
        2.0,
        16,
        allowed_utc_hours=(10, 11, 12, 13, 14, 15, 16, 17),
    ),
    QualityTrendParameterSet(
        "liquid_h11_19",
        0.25,
        5.0,
        2.0,
        1.0,
        0.20,
        0.30,
        2.0,
        16,
        allowed_utc_hours=(11, 12, 13, 14, 15, 16, 17, 18, 19),
    ),
    QualityTrendParameterSet(
        "late_strict_h14_19",
        0.30,
        6.0,
        2.5,
        1.25,
        0.25,
        0.35,
        2.5,
        16,
        allowed_utc_hours=(14, 15, 16, 17, 18, 19),
    ),
    QualityTrendParameterSet(
        "selective_h10_19",
        0.35,
        6.5,
        3.0,
        1.50,
        0.30,
        0.40,
        3.0,
        12,
        allowed_utc_hours=(10, 11, 12, 13, 14, 15, 16, 17, 18, 19),
    ),
)


@dataclass(frozen=True)
class QualityTrendOptimizationCandidate:
    parameters: QualityTrendParameterSet
    comparison_row: PortfolioStrategyComparisonRow
    walk_forward: FixedWarmupPortfolioWalkForwardResult | None = None

    @property
    def promotion_decision(self) -> FixedWarmupPromotionDecision | None:
        if self.walk_forward is None:
            return None
        return decide_fixed_warmup_promotion(self.walk_forward)

    @property
    def rank_key(self) -> tuple[float, ...]:
        metrics = self.comparison_row.competition_metrics
        if self.walk_forward is not None:
            return (
                _coverage_adjusted_active_score(self.walk_forward),
                self.walk_forward.active_positive_fold_fraction,
                self.walk_forward.non_negative_fold_fraction,
                self.walk_forward.median_active_test_return_pct,
                self.walk_forward.positive_fold_fraction,
                -self.walk_forward.losing_fold_fraction,
                self.comparison_row.proxy_score,
                metrics.return_pct,
                metrics.sharpe_15m,
                -metrics.max_drawdown_pct,
            )
        return (
            self.comparison_row.proxy_score,
            self.comparison_row.risk_discipline.score,
            metrics.return_pct,
            metrics.sharpe_15m,
            -metrics.max_drawdown_pct,
            -float(metrics.trade_count),
        )


@dataclass(frozen=True)
class QualityTrendOptimizationResult:
    symbols: tuple[str, ...]
    candidates: tuple[QualityTrendOptimizationCandidate, ...]

    @property
    def best(self) -> QualityTrendOptimizationCandidate | None:
        if not self.candidates:
            return None
        return self.candidates[0]


def optimize_quality_trend_parameters(
    *,
    config: AppConfig,
    prices: PriceHistory,
    quotes: QuoteHistory,
    symbols: tuple[str, ...] | None = None,
    parameter_sets: tuple[
        QualityTrendParameterSet, ...
    ] = DEFAULT_QUALITY_TREND_PARAMETER_SETS,
    include_walk_forward: bool = False,
    train_size: int = 960,
    test_size: int = 192,
    step_size: int = 192,
    allocation_policy: AllocationPolicy | None = None,
    clock: CompetitionClock | FixedModeClock | None = None,
) -> QualityTrendOptimizationResult:
    if not parameter_sets:
        raise ValueError("quality trend optimizer needs at least one parameter set")

    candidates: list[QualityTrendOptimizationCandidate] = []
    selected_symbols: tuple[str, ...] | None = None
    for parameters in parameter_sets:
        candidate_config = _config_with_parameters(config, parameters)
        comparison = compare_portfolio_strategies(
            config=candidate_config,
            prices=prices,
            quotes=quotes,
            strategy_names=("quality_trend",),
            symbols=symbols,
            allocation_policy=allocation_policy,
            clock=clock,
        )
        if comparison.best is None:
            continue
        selected_symbols = comparison.symbols
        walk_forward = (
            run_fixed_warmup_portfolio_walk_forward(
                config=candidate_config,
                prices=prices,
                quotes=quotes,
                strategy_name="quality_trend",
                symbols=comparison.symbols,
                train_size=train_size,
                test_size=test_size,
                step_size=step_size,
                allocation_policy=allocation_policy,
                clock=clock,
            )
            if include_walk_forward
            else None
        )
        candidates.append(
            QualityTrendOptimizationCandidate(
                parameters=parameters,
                comparison_row=comparison.best,
                walk_forward=walk_forward,
            )
        )

    candidates.sort(key=lambda candidate: candidate.rank_key, reverse=True)
    return QualityTrendOptimizationResult(
        symbols=selected_symbols or (),
        candidates=tuple(candidates),
    )


def write_quality_trend_optimization_csv(
    result: QualityTrendOptimizationResult,
    path: str | Path,
) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "rank",
                "label",
                "symbols",
                "kalman_min_abs_slope_bps",
                "kalman_min_expected_edge_bps",
                "macd_min_histogram_bps",
                "macd_min_macd_bps",
                "macd_min_trend_efficiency",
                "min_combined_confidence",
                "min_expected_edge_bps",
                "max_holding_period",
                "allowed_utc_hours",
                "proxy_score",
                "final_equity",
                "return_pct",
                "max_drawdown_pct",
                "sharpe_15m",
                "risk_discipline_score",
                "trade_count",
                "fills",
                "turnover_notional",
                "total_pnl_usd",
                "wf_positive_fold_fraction",
                "wf_active_fold_fraction",
                "wf_active_positive_fold_fraction",
                "wf_non_negative_fold_fraction",
                "wf_losing_fold_fraction",
                "wf_median_test_return_pct",
                "wf_median_active_test_return_pct",
                "wf_worst_test_drawdown_pct",
                "wf_total_evaluation_fills",
                "promotion_status",
                "promotion_live_ready",
                "promotion_reason",
            ],
        )
        writer.writeheader()
        for rank, candidate in enumerate(result.candidates, start=1):
            parameters = candidate.parameters
            row = candidate.comparison_row
            metrics = row.competition_metrics
            walk_forward = candidate.walk_forward
            promotion = candidate.promotion_decision
            writer.writerow(
                {
                    "rank": rank,
                    "label": parameters.label,
                    "symbols": " ".join(result.symbols),
                    "kalman_min_abs_slope_bps": parameters.kalman_min_abs_slope_bps,
                    "kalman_min_expected_edge_bps": (
                        parameters.kalman_min_expected_edge_bps
                    ),
                    "macd_min_histogram_bps": parameters.macd_min_histogram_bps,
                    "macd_min_macd_bps": parameters.macd_min_macd_bps,
                    "macd_min_trend_efficiency": parameters.macd_min_trend_efficiency,
                    "min_combined_confidence": parameters.min_combined_confidence,
                    "min_expected_edge_bps": parameters.min_expected_edge_bps,
                    "max_holding_period": parameters.max_holding_period,
                    "allowed_utc_hours": _hours_text(parameters.allowed_utc_hours),
                    "proxy_score": row.proxy_score,
                    "final_equity": metrics.final_equity,
                    "return_pct": metrics.return_pct,
                    "max_drawdown_pct": metrics.max_drawdown_pct,
                    "sharpe_15m": metrics.sharpe_15m,
                    "risk_discipline_score": row.risk_discipline.score,
                    "trade_count": metrics.trade_count,
                    "fills": len(row.result.fills),
                    "turnover_notional": row.result.metrics.turnover_notional,
                    "total_pnl_usd": row.result.total_pnl_usd,
                    "wf_positive_fold_fraction": (
                        "" if walk_forward is None else walk_forward.positive_fold_fraction
                    ),
                    "wf_active_fold_fraction": (
                        "" if walk_forward is None else walk_forward.active_fold_fraction
                    ),
                    "wf_active_positive_fold_fraction": (
                        ""
                        if walk_forward is None
                        else walk_forward.active_positive_fold_fraction
                    ),
                    "wf_non_negative_fold_fraction": (
                        ""
                        if walk_forward is None
                        else walk_forward.non_negative_fold_fraction
                    ),
                    "wf_losing_fold_fraction": (
                        "" if walk_forward is None else walk_forward.losing_fold_fraction
                    ),
                    "wf_median_test_return_pct": (
                        "" if walk_forward is None else walk_forward.median_test_return_pct
                    ),
                    "wf_median_active_test_return_pct": (
                        ""
                        if walk_forward is None
                        else walk_forward.median_active_test_return_pct
                    ),
                    "wf_worst_test_drawdown_pct": (
                        "" if walk_forward is None else walk_forward.worst_test_drawdown_pct
                    ),
                    "wf_total_evaluation_fills": (
                        "" if walk_forward is None else walk_forward.total_evaluation_fills
                    ),
                    "promotion_status": "" if promotion is None else promotion.status,
                    "promotion_live_ready": (
                        "" if promotion is None else promotion.live_ready
                    ),
                    "promotion_reason": "" if promotion is None else promotion.reason,
                }
            )


def _config_with_parameters(
    config: AppConfig,
    parameters: QualityTrendParameterSet,
) -> AppConfig:
    quality_trend = replace(
        config.quality_trend,
        kalman_min_abs_slope_bps=parameters.kalman_min_abs_slope_bps,
        kalman_min_expected_edge_bps=parameters.kalman_min_expected_edge_bps,
        macd_min_histogram_bps=parameters.macd_min_histogram_bps,
        macd_exit_histogram_bps=min(
            config.quality_trend.macd_exit_histogram_bps,
            parameters.macd_min_histogram_bps * 0.5,
        ),
        macd_min_macd_bps=parameters.macd_min_macd_bps,
        macd_min_trend_efficiency=parameters.macd_min_trend_efficiency,
        min_combined_confidence=parameters.min_combined_confidence,
        exit_combined_confidence=min(
            config.quality_trend.exit_combined_confidence,
            parameters.min_combined_confidence * 0.5,
        ),
        min_expected_edge_bps=parameters.min_expected_edge_bps,
        max_holding_period=parameters.max_holding_period,
        forex_allowed_utc_hours=(
            config.quality_trend.forex_allowed_utc_hours
            if parameters.allowed_utc_hours is None
            else parameters.allowed_utc_hours
        ),
        metal_allowed_utc_hours=(
            config.quality_trend.metal_allowed_utc_hours
            if parameters.allowed_utc_hours is None
            else parameters.allowed_utc_hours
        ),
    )
    return replace(config, quality_trend=quality_trend)


def _hours_text(hours: tuple[int, ...] | None) -> str:
    if hours is None:
        return ""
    return "|".join(str(hour) for hour in hours)


def _coverage_adjusted_active_score(
    walk_forward: FixedWarmupPortfolioWalkForwardResult,
    *,
    target_active_fold_fraction: float = 0.35,
) -> float:
    if target_active_fold_fraction <= 0:
        return walk_forward.active_positive_fold_fraction
    coverage = min(walk_forward.active_fold_fraction / target_active_fold_fraction, 1.0)
    return walk_forward.active_positive_fold_fraction * coverage
