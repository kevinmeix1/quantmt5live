from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from quanthack.backtesting.allocation_profiles import (
    ALLOCATION_PROFILE_DIRECTIONAL_PROBE,
    allocation_policy_for_strategy,
)
from quanthack.backtesting.opportunity_probe_optimizer import (
    OpportunityProbeParameterSet,
    optimize_opportunity_probe_parameters,
    write_opportunity_probe_optimization_csv,
)
from quanthack.core.clock import FixedModeClock
from quanthack.core.config import load_config
from quanthack.market.sample_data import generate_synthetic_market_data


class OpportunityProbeOptimizerTest(TestCase):
    def test_optimizer_ranks_parameter_sets(self) -> None:
        config = load_config("configs/default.toml")
        data = generate_synthetic_market_data(
            symbols=("EURUSD", "GBPUSD", "USDJPY"),
            periods=96,
            interval_minutes=15,
            seed=701,
        )

        result = optimize_opportunity_probe_parameters(
            config=config,
            prices=data.prices,
            quotes=data.quotes,
            symbols=("EURUSD", "GBPUSD", "USDJPY"),
            parameter_sets=(
                OpportunityProbeParameterSet(
                    "loose", 3, 8, 20, 1.0, 0.1, 2.0, 0.5, 0.25, 2, 12
                ),
                OpportunityProbeParameterSet(
                    "strict", 4, 12, 32, 2.5, 0.2, 3.0, 1.5, 0.45, 4, 24
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
            periods=96,
            interval_minutes=15,
            seed=702,
        )
        result = optimize_opportunity_probe_parameters(
            config=config,
            prices=data.prices,
            quotes=data.quotes,
            symbols=("EURUSD", "GBPUSD", "USDJPY"),
            parameter_sets=(
                OpportunityProbeParameterSet(
                    "loose", 3, 8, 20, 1.0, 0.1, 2.0, 0.5, 0.25, 2, 12
                ),
            ),
        )

        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "opportunity_probe_opt.csv"
            write_opportunity_probe_optimization_csv(result, path)
            text = path.read_text(encoding="utf-8")

        self.assertIn("rank,label,symbols,fast_lookback", text)
        self.assertIn("volatility_penalty", text)
        self.assertIn("promotion_status", text)
        self.assertIn("loose", text)

    def test_writes_walk_forward_promotion_columns(self) -> None:
        config = load_config("configs/default.toml")
        data = generate_synthetic_market_data(
            symbols=("EURUSD", "GBPUSD", "USDJPY"),
            periods=128,
            interval_minutes=15,
            seed=703,
        )
        result = optimize_opportunity_probe_parameters(
            config=config,
            prices=data.prices,
            quotes=data.quotes,
            symbols=("EURUSD", "GBPUSD", "USDJPY"),
            parameter_sets=(
                OpportunityProbeParameterSet(
                    "loose", 3, 8, 20, 1.0, 0.1, 2.0, 0.5, 0.25, 2, 12
                ),
            ),
            include_walk_forward=True,
            train_size=48,
            test_size=24,
            step_size=24,
        )

        self.assertIsNotNone(result.candidates[0].promotion_decision)

        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "opportunity_probe_opt.csv"
            write_opportunity_probe_optimization_csv(result, path)
            text = path.read_text(encoding="utf-8")

        self.assertIn("promotion_status,promotion_live_ready,promotion_reason", text)

    def test_optimizer_accepts_research_clock_and_allocation_policy(self) -> None:
        config = load_config("configs/competition.toml")
        data = generate_synthetic_market_data(
            symbols=("EURUSD", "GBPUSD", "USDJPY"),
            periods=96,
            interval_minutes=15,
            seed=704,
        )

        result = optimize_opportunity_probe_parameters(
            config=config,
            prices=data.prices,
            quotes=data.quotes,
            symbols=("EURUSD", "GBPUSD", "USDJPY"),
            parameter_sets=(
                OpportunityProbeParameterSet(
                    "strict", 4, 12, 32, 2.5, 0.2, 3.0, 1.5, 0.45, 4, 24
                ),
            ),
            allocation_policy=allocation_policy_for_strategy(
                "opportunity_probe",
                config,
                profile=ALLOCATION_PROFILE_DIRECTIONAL_PROBE,
            ),
            clock=FixedModeClock(),
        )

        self.assertEqual(result.symbols, ("EURUSD", "GBPUSD", "USDJPY"))
        self.assertEqual(len(result.candidates), 1)

    def test_parameter_set_rejects_invalid_windows(self) -> None:
        with self.assertRaisesRegex(ValueError, "medium_lookback"):
            OpportunityProbeParameterSet(
                "bad", 8, 8, 20, 1.0, 0.1, 2.0, 0.5, 0.25, 2, 12
            )
