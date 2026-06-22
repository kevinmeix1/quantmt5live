from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from quanthack.backtesting.champion_ensemble_optimizer import (
    ChampionEnsembleParameterSet,
    optimize_champion_ensemble_parameters,
    write_champion_ensemble_optimization_csv,
)
from quanthack.backtesting.allocation_profiles import (
    ALLOCATION_PROFILE_DIRECTIONAL_PROBE,
    allocation_policy_for_strategy,
)
from quanthack.core.clock import FixedModeClock
from quanthack.core.config import load_config
from quanthack.market.sample_data import generate_synthetic_market_data


class ChampionEnsembleOptimizerTest(TestCase):
    def test_optimizer_ranks_parameter_sets(self) -> None:
        config = load_config("configs/default.toml")
        data = generate_synthetic_market_data(
            symbols=("EURUSD", "GBPUSD", "USDJPY"),
            periods=96,
            interval_minutes=15,
            seed=201,
        )

        result = optimize_champion_ensemble_parameters(
            config=config,
            prices=data.prices,
            quotes=data.quotes,
            symbols=("EURUSD", "GBPUSD", "USDJPY"),
            parameter_sets=(
                ChampionEnsembleParameterSet("strict", 0.70, 0.30, 0.0, 0.0, 0.50, 0.50, 0.70),
                ChampionEnsembleParameterSet("loose", 0.60, 0.25, 0.10, 0.05, 0.50, 0.25, 0.65),
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
            seed=202,
        )
        result = optimize_champion_ensemble_parameters(
            config=config,
            prices=data.prices,
            quotes=data.quotes,
            symbols=("EURUSD", "GBPUSD", "USDJPY"),
            parameter_sets=(
                ChampionEnsembleParameterSet("strict", 0.70, 0.30, 0.0, 0.0, 0.50, 0.50, 0.70),
            ),
        )

        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "champion_ensemble_opt.csv"
            write_champion_ensemble_optimization_csv(result, path)
            text = path.read_text(encoding="utf-8")

        self.assertIn("rank,label,symbols,kalman_trend_weight", text)
        self.assertIn("strict", text)
        self.assertIn("wf_positive_fold_fraction", text)
        self.assertIn("wf_active_positive_fold_fraction", text)
        self.assertIn("wf_non_negative_fold_fraction", text)
        self.assertIn("wf_largest_positive_fold_contribution", text)

    def test_writes_walk_forward_promotion_columns(self) -> None:
        config = load_config("configs/default.toml")
        data = generate_synthetic_market_data(
            symbols=("EURUSD", "GBPUSD", "USDJPY"),
            periods=128,
            interval_minutes=15,
            seed=203,
        )
        result = optimize_champion_ensemble_parameters(
            config=config,
            prices=data.prices,
            quotes=data.quotes,
            symbols=("EURUSD", "GBPUSD", "USDJPY"),
            parameter_sets=(
                ChampionEnsembleParameterSet(
                    "strict",
                    0.70,
                    0.30,
                    0.0,
                    0.0,
                    0.50,
                    0.50,
                    0.70,
                ),
            ),
            include_walk_forward=True,
            train_size=48,
            test_size=24,
            step_size=24,
        )

        self.assertIsNotNone(result.candidates[0].promotion_decision)

        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "champion_ensemble_opt.csv"
            write_champion_ensemble_optimization_csv(result, path)
            text = path.read_text(encoding="utf-8")

        self.assertIn("promotion_status,promotion_live_ready,promotion_reason", text)

    def test_optimizer_accepts_research_clock_and_allocation_policy(self) -> None:
        config = load_config("configs/competition.toml")
        data = generate_synthetic_market_data(
            symbols=("EURUSD", "GBPUSD", "USDJPY"),
            periods=96,
            interval_minutes=15,
            seed=204,
        )

        result = optimize_champion_ensemble_parameters(
            config=config,
            prices=data.prices,
            quotes=data.quotes,
            symbols=("EURUSD", "GBPUSD", "USDJPY"),
            parameter_sets=(
                ChampionEnsembleParameterSet(
                    "strict",
                    0.70,
                    0.30,
                    0.0,
                    0.0,
                    0.50,
                    0.50,
                    0.70,
                ),
            ),
            allocation_policy=allocation_policy_for_strategy(
                "champion_ensemble",
                config,
                profile=ALLOCATION_PROFILE_DIRECTIONAL_PROBE,
            ),
            clock=FixedModeClock(),
        )

        self.assertEqual(result.symbols, ("EURUSD", "GBPUSD", "USDJPY"))
        self.assertEqual(len(result.candidates), 1)

    def test_parameter_set_rejects_invalid_strong_lead_score(self) -> None:
        with self.assertRaisesRegex(ValueError, "strong_lead_score"):
            ChampionEnsembleParameterSet("bad", 0.70, 0.30, 0.0, 0.0, 0.50, 0.60, 0.70)
