from __future__ import annotations

import csv
from dataclasses import dataclass, replace
from pathlib import Path

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
from quanthack.backtesting.portfolio_allocator import AllocationPolicy
from quanthack.core.clock import CompetitionClock, FixedModeClock
from quanthack.core.config import AppConfig
from quanthack.market.market_data import PriceHistory, QuoteHistory


@dataclass(frozen=True)
class OpportunityProbeParameterSet:
    label: str
    fast_lookback: int
    medium_lookback: int
    slow_lookback: int
    min_score: float
    exit_score: float
    reverse_score: float
    min_fast_move_bps: float
    volatility_penalty: float
    min_holding_period: int
    max_holding_period: int
    max_spread_bps: float = 12.0

    def __post_init__(self) -> None:
        if not self.label.strip():
            raise ValueError("opportunity probe parameter label is required")
        if self.fast_lookback < 1:
            raise ValueError("fast_lookback must be positive")
        if self.medium_lookback <= self.fast_lookback:
            raise ValueError("medium_lookback must be greater than fast_lookback")
        if self.slow_lookback <= self.medium_lookback:
            raise ValueError("slow_lookback must be greater than medium_lookback")
        if self.min_score <= 0:
            raise ValueError("min_score must be positive")
        if self.exit_score < 0:
            raise ValueError("exit_score cannot be negative")
        if self.reverse_score <= 0:
            raise ValueError("reverse_score must be positive")
        if self.min_fast_move_bps < 0:
            raise ValueError("min_fast_move_bps cannot be negative")
        if self.volatility_penalty < 0:
            raise ValueError("volatility_penalty cannot be negative")
        if self.min_holding_period < 0:
            raise ValueError("min_holding_period cannot be negative")
        if self.max_holding_period < 1:
            raise ValueError("max_holding_period must be positive")
        if self.min_holding_period > self.max_holding_period:
            raise ValueError("min_holding_period cannot exceed max_holding_period")
        if self.max_spread_bps <= 0:
            raise ValueError("max_spread_bps must be positive")


DEFAULT_OPPORTUNITY_PROBE_PARAMETER_SETS: tuple[OpportunityProbeParameterSet, ...] = (
    OpportunityProbeParameterSet(
        "current_3_8_20_s1_20_f1_00_v0_25_hold15_90",
        3,
        8,
        20,
        1.20,
        0.05,
        2.00,
        1.00,
        0.25,
        15,
        90,
    ),
    OpportunityProbeParameterSet(
        "strict_3_8_20_s2_00_f1_50_v0_35_hold20_90",
        3,
        8,
        20,
        2.00,
        0.10,
        2.50,
        1.50,
        0.35,
        20,
        90,
    ),
    OpportunityProbeParameterSet(
        "strict_4_12_32_s2_25_f1_75_v0_40_hold24_96",
        4,
        12,
        32,
        2.25,
        0.10,
        2.75,
        1.75,
        0.40,
        24,
        96,
    ),
    OpportunityProbeParameterSet(
        "selective_5_15_40_s2_75_f2_00_v0_50_hold24_120",
        5,
        15,
        40,
        2.75,
        0.15,
        3.25,
        2.00,
        0.50,
        24,
        120,
    ),
    OpportunityProbeParameterSet(
        "fast_but_filtered_3_10_30_s2_50_f2_00_v0_45_hold16_64",
        3,
        10,
        30,
        2.50,
        0.15,
        3.00,
        2.00,
        0.45,
        16,
        64,
    ),
)


@dataclass(frozen=True)
class OpportunityProbeOptimizationCandidate:
    parameters: OpportunityProbeParameterSet
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
class OpportunityProbeOptimizationResult:
    symbols: tuple[str, ...]
    candidates: tuple[OpportunityProbeOptimizationCandidate, ...]

    @property
    def best(self) -> OpportunityProbeOptimizationCandidate | None:
        if not self.candidates:
            return None
        return self.candidates[0]


def optimize_opportunity_probe_parameters(
    *,
    config: AppConfig,
    prices: PriceHistory,
    quotes: QuoteHistory,
    symbols: tuple[str, ...] | None = None,
    parameter_sets: tuple[
        OpportunityProbeParameterSet, ...
    ] = DEFAULT_OPPORTUNITY_PROBE_PARAMETER_SETS,
    include_walk_forward: bool = False,
    train_size: int = 960,
    test_size: int = 192,
    step_size: int = 192,
    allocation_policy: AllocationPolicy | None = None,
    clock: CompetitionClock | FixedModeClock | None = None,
) -> OpportunityProbeOptimizationResult:
    if not parameter_sets:
        raise ValueError("opportunity probe optimizer needs at least one parameter set")

    candidates: list[OpportunityProbeOptimizationCandidate] = []
    selected_symbols: tuple[str, ...] | None = None
    for parameters in parameter_sets:
        candidate_config = _config_with_parameters(config, parameters)
        comparison = compare_portfolio_strategies(
            config=candidate_config,
            prices=prices,
            quotes=quotes,
            strategy_names=("opportunity_probe",),
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
                strategy_name="opportunity_probe",
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
            OpportunityProbeOptimizationCandidate(
                parameters=parameters,
                comparison_row=comparison.best,
                walk_forward=walk_forward,
            )
        )

    candidates.sort(key=lambda candidate: candidate.rank_key, reverse=True)
    return OpportunityProbeOptimizationResult(
        symbols=selected_symbols or (),
        candidates=tuple(candidates),
    )


def write_opportunity_probe_optimization_csv(
    result: OpportunityProbeOptimizationResult,
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
                "fast_lookback",
                "medium_lookback",
                "slow_lookback",
                "min_score",
                "exit_score",
                "reverse_score",
                "min_fast_move_bps",
                "volatility_penalty",
                "min_holding_period",
                "max_holding_period",
                "max_spread_bps",
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
                    "fast_lookback": parameters.fast_lookback,
                    "medium_lookback": parameters.medium_lookback,
                    "slow_lookback": parameters.slow_lookback,
                    "min_score": parameters.min_score,
                    "exit_score": parameters.exit_score,
                    "reverse_score": parameters.reverse_score,
                    "min_fast_move_bps": parameters.min_fast_move_bps,
                    "volatility_penalty": parameters.volatility_penalty,
                    "min_holding_period": parameters.min_holding_period,
                    "max_holding_period": parameters.max_holding_period,
                    "max_spread_bps": parameters.max_spread_bps,
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
    parameters: OpportunityProbeParameterSet,
) -> AppConfig:
    opportunity_probe = replace(
        config.opportunity_probe,
        fast_lookback=parameters.fast_lookback,
        medium_lookback=parameters.medium_lookback,
        slow_lookback=parameters.slow_lookback,
        min_score=parameters.min_score,
        exit_score=parameters.exit_score,
        reverse_score=parameters.reverse_score,
        min_fast_move_bps=parameters.min_fast_move_bps,
        max_spread_bps=parameters.max_spread_bps,
        volatility_penalty=parameters.volatility_penalty,
        min_holding_period=parameters.min_holding_period,
        max_holding_period=parameters.max_holding_period,
    )
    return replace(config, opportunity_probe=opportunity_probe)


def _coverage_adjusted_active_score(
    walk_forward: FixedWarmupPortfolioWalkForwardResult,
    *,
    target_active_fold_fraction: float = 0.35,
) -> float:
    if target_active_fold_fraction <= 0:
        return walk_forward.active_positive_fold_fraction
    coverage = min(walk_forward.active_fold_fraction / target_active_fold_fraction, 1.0)
    return walk_forward.active_positive_fold_fraction * coverage
