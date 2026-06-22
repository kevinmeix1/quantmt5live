from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from quanthack.backtesting.macd_momentum_optimizer import (
    MacdMomentumParameterSet,
    optimize_macd_momentum_parameters,
    write_macd_momentum_optimization_csv,
)
from quanthack.backtesting.allocation_profiles import (
    ALLOCATION_PROFILE_DIRECTIONAL_PROBE,
    allocation_policy_for_strategy,
)
from quanthack.core.clock import FixedModeClock
from quanthack.core.config import load_config
from quanthack.market.sample_data import generate_synthetic_market_data


class MacdMomentumOptimizerTest(TestCase):
    def test_optimizer_ranks_parameter_sets(self) -> None:
        config = load_config("configs/default.toml")
        data = generate_synthetic_market_data(
            symbols=("EURUSD", "GBPUSD", "USDJPY"),
            periods=96,
            interval_minutes=15,
            seed=301,
        )

        result = optimize_macd_momentum_parameters(
            config=config,
            prices=data.prices,
            quotes=data.quotes,
            symbols=("EURUSD", "GBPUSD", "USDJPY"),
            parameter_sets=(
                MacdMomentumParameterSet("fast", 3, 8, 3, 0.5, 0.1, 0.0, 8),
                MacdMomentumParameterSet("strict", 6, 14, 5, 2.0, 1.0, 0.2, 12),
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
            periods=96,
            interval_minutes=15,
            seed=302,
        )
        result = optimize_macd_momentum_parameters(
            config=config,
            prices=data.prices,
            quotes=data.quotes,
            symbols=("EURUSD", "GBPUSD", "USDJPY"),
            parameter_sets=(
                MacdMomentumParameterSet("fast", 3, 8, 3, 0.5, 0.1, 0.0, 8),
            ),
        )

        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "macd_momentum_opt.csv"
            write_macd_momentum_optimization_csv(result, path)
            text = path.read_text(encoding="utf-8")

        self.assertIn("rank,label,symbols,fast_window", text)
        self.assertIn("min_histogram_slope_bps", text)
        self.assertIn("allowed_utc_hours", text)
        self.assertIn("fast", text)
        self.assertIn("wf_active_positive_fold_fraction", text)

    def test_writes_walk_forward_promotion_columns(self) -> None:
        config = load_config("configs/default.toml")
        data = generate_synthetic_market_data(
            symbols=("EURUSD", "GBPUSD", "USDJPY"),
            periods=128,
            interval_minutes=15,
            seed=303,
        )
        result = optimize_macd_momentum_parameters(
            config=config,
            prices=data.prices,
            quotes=data.quotes,
            symbols=("EURUSD", "GBPUSD", "USDJPY"),
            parameter_sets=(
                MacdMomentumParameterSet("fast", 3, 8, 3, 0.5, 0.1, 0.0, 8),
            ),
            include_walk_forward=True,
            train_size=48,
            test_size=24,
            step_size=24,
        )

        self.assertIsNotNone(result.candidates[0].promotion_decision)

        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "macd_momentum_opt.csv"
            write_macd_momentum_optimization_csv(result, path)
            text = path.read_text(encoding="utf-8")

        self.assertIn("promotion_status,promotion_live_ready,promotion_reason", text)

    def test_optimizer_accepts_research_clock_and_allocation_policy(self) -> None:
        config = load_config("configs/competition.toml")
        data = generate_synthetic_market_data(
            symbols=("EURUSD", "GBPUSD", "USDJPY"),
            periods=96,
            interval_minutes=15,
            seed=304,
        )

        result = optimize_macd_momentum_parameters(
            config=config,
            prices=data.prices,
            quotes=data.quotes,
            symbols=("EURUSD", "GBPUSD", "USDJPY"),
            parameter_sets=(
                MacdMomentumParameterSet("fast", 3, 8, 3, 0.5, 0.1, 0.0, 8),
            ),
            allocation_policy=allocation_policy_for_strategy(
                "macd_momentum",
                config,
                profile=ALLOCATION_PROFILE_DIRECTIONAL_PROBE,
            ),
            clock=FixedModeClock(),
        )

        self.assertEqual(result.symbols, ("EURUSD", "GBPUSD", "USDJPY"))
        self.assertEqual(len(result.candidates), 1)

    def test_parameter_set_rejects_invalid_windows(self) -> None:
        with self.assertRaisesRegex(ValueError, "slow_window"):
            MacdMomentumParameterSet("bad", 8, 8, 3, 0.5, 0.1, 0.0, 8)

    def test_parameter_set_accepts_session_hours(self) -> None:
        parameters = MacdMomentumParameterSet(
            "london_ny",
            6,
            18,
            5,
            2.0,
            1.0,
            0.2,
            12,
            allowed_utc_hours=(11, 12, 13, 14, 15, 16),
        )

        self.assertEqual(parameters.allowed_utc_hours, (11, 12, 13, 14, 15, 16))

    def test_parameter_set_accepts_histogram_slope(self) -> None:
        parameters = MacdMomentumParameterSet(
            "slope",
            6,
            18,
            5,
            2.0,
            1.0,
            0.2,
            12,
            min_histogram_slope_bps=0.25,
        )

        self.assertEqual(parameters.min_histogram_slope_bps, 0.25)

    def test_parameter_set_rejects_negative_histogram_slope(self) -> None:
        with self.assertRaisesRegex(ValueError, "min_histogram_slope_bps"):
            MacdMomentumParameterSet(
                "bad_slope",
                6,
                18,
                5,
                2.0,
                1.0,
                0.2,
                12,
                min_histogram_slope_bps=-0.1,
            )

    def test_parameter_set_rejects_invalid_session_hours(self) -> None:
        with self.assertRaisesRegex(ValueError, "between 0 and 23"):
            MacdMomentumParameterSet(
                "bad_hours",
                6,
                18,
                5,
                2.0,
                1.0,
                0.2,
                12,
                allowed_utc_hours=(11, 24),
            )
