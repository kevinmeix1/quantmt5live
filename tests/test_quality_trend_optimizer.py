from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from quanthack.backtesting.allocation_profiles import (
    ALLOCATION_PROFILE_DIRECTIONAL_PROBE,
    allocation_policy_for_strategy,
)
from quanthack.backtesting.quality_trend_optimizer import (
    QualityTrendParameterSet,
    optimize_quality_trend_parameters,
    write_quality_trend_optimization_csv,
)
from quanthack.core.clock import FixedModeClock
from quanthack.core.config import load_config
from quanthack.market.sample_data import generate_synthetic_market_data


class QualityTrendOptimizerTest(TestCase):
    def test_optimizer_ranks_parameter_sets(self) -> None:
        config = load_config("configs/default.toml")
        data = generate_synthetic_market_data(
            symbols=("EURUSD", "GBPUSD", "USDJPY"),
            periods=128,
            interval_minutes=15,
            seed=801,
        )

        result = optimize_quality_trend_parameters(
            config=config,
            prices=data.prices,
            quotes=data.quotes,
            symbols=("EURUSD", "GBPUSD", "USDJPY"),
            parameter_sets=(
                QualityTrendParameterSet(
                    "current", 0.25, 5.0, 2.0, 1.0, 0.20, 0.30, 2.0, 16
                ),
                QualityTrendParameterSet(
                    "strict",
                    0.35,
                    6.0,
                    2.5,
                    1.25,
                    0.25,
                    0.35,
                    2.5,
                    12,
                    allowed_utc_hours=(10, 11, 12, 13, 14),
                ),
            ),
        )

        self.assertEqual(result.symbols, ("EURUSD", "GBPUSD", "USDJPY"))
        self.assertEqual(len(result.candidates), 2)
        self.assertIsNotNone(result.best)
        rank_keys = [candidate.rank_key for candidate in result.candidates]
        self.assertEqual(rank_keys, sorted(rank_keys, reverse=True))

    def test_writes_optimizer_csv(self) -> None:
        config = load_config("configs/default.toml")
        data = generate_synthetic_market_data(
            symbols=("EURUSD", "GBPUSD", "USDJPY"),
            periods=128,
            interval_minutes=15,
            seed=802,
        )
        result = optimize_quality_trend_parameters(
            config=config,
            prices=data.prices,
            quotes=data.quotes,
            symbols=("EURUSD", "GBPUSD", "USDJPY"),
            parameter_sets=(
                QualityTrendParameterSet(
                    "current", 0.25, 5.0, 2.0, 1.0, 0.20, 0.30, 2.0, 16
                ),
            ),
        )

        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "quality_trend_opt.csv"
            write_quality_trend_optimization_csv(result, path)
            text = path.read_text(encoding="utf-8")

        self.assertIn("rank,label,symbols,kalman_min_abs_slope_bps", text)
        self.assertIn("allowed_utc_hours", text)
        self.assertIn("promotion_status", text)
        self.assertIn("current", text)

    def test_writes_walk_forward_promotion_columns(self) -> None:
        config = load_config("configs/default.toml")
        data = generate_synthetic_market_data(
            symbols=("EURUSD", "GBPUSD", "USDJPY"),
            periods=144,
            interval_minutes=15,
            seed=803,
        )
        result = optimize_quality_trend_parameters(
            config=config,
            prices=data.prices,
            quotes=data.quotes,
            symbols=("EURUSD", "GBPUSD", "USDJPY"),
            parameter_sets=(
                QualityTrendParameterSet(
                    "current", 0.25, 5.0, 2.0, 1.0, 0.20, 0.30, 2.0, 16
                ),
            ),
            include_walk_forward=True,
            train_size=72,
            test_size=24,
            step_size=24,
        )

        self.assertIsNotNone(result.candidates[0].promotion_decision)

        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "quality_trend_opt.csv"
            write_quality_trend_optimization_csv(result, path)
            text = path.read_text(encoding="utf-8")

        self.assertIn("promotion_status,promotion_live_ready,promotion_reason", text)

    def test_optimizer_accepts_research_clock_and_allocation_policy(self) -> None:
        config = load_config("configs/competition.toml")
        data = generate_synthetic_market_data(
            symbols=("EURUSD", "GBPUSD", "USDJPY"),
            periods=128,
            interval_minutes=15,
            seed=804,
        )

        result = optimize_quality_trend_parameters(
            config=config,
            prices=data.prices,
            quotes=data.quotes,
            symbols=("EURUSD", "GBPUSD", "USDJPY"),
            parameter_sets=(
                QualityTrendParameterSet(
                    "current", 0.25, 5.0, 2.0, 1.0, 0.20, 0.30, 2.0, 16
                ),
            ),
            allocation_policy=allocation_policy_for_strategy(
                "quality_trend",
                config,
                profile=ALLOCATION_PROFILE_DIRECTIONAL_PROBE,
            ),
            clock=FixedModeClock(),
        )

        self.assertEqual(result.symbols, ("EURUSD", "GBPUSD", "USDJPY"))
        self.assertEqual(len(result.candidates), 1)

    def test_parameter_set_rejects_invalid_hours(self) -> None:
        with self.assertRaisesRegex(ValueError, "allowed_utc_hours"):
            QualityTrendParameterSet(
                "bad",
                0.25,
                5.0,
                2.0,
                1.0,
                0.20,
                0.30,
                2.0,
                16,
                allowed_utc_hours=(24,),
            )
