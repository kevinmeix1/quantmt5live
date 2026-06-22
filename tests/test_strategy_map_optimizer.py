from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from quanthack.backtesting.strategy_map_optimizer import (
    optimize_strategy_map,
    write_strategy_map_optimization_csv,
    write_symbol_strategy_scores_csv,
)
from quanthack.backtesting.allocation_profiles import allocation_policy_for_strategy
from quanthack.cli.strategy_map_optimize import _parse_candidate_map
from quanthack.core.clock import FixedModeClock
from quanthack.core.config import load_config
from quanthack.market.sample_data import generate_synthetic_market_data


class StrategyMapOptimizerTest(TestCase):
    def test_optimizer_builds_ranked_strategy_maps(self) -> None:
        config = load_config("configs/default.toml")
        data = generate_synthetic_market_data(
            symbols=("EURUSD", "GBPUSD", "USDJPY"),
            periods=72,
            interval_minutes=15,
            seed=401,
        )

        result = optimize_strategy_map(
            config=config,
            prices=data.prices,
            quotes=data.quotes,
            strategy_names=("simple_momentum", "macd_momentum"),
            symbols=("EURUSD", "GBPUSD", "USDJPY"),
            top_symbol_counts=(2, 3),
        )

        self.assertEqual(result.available_symbols, ("EURUSD", "GBPUSD", "USDJPY"))
        self.assertEqual(result.strategy_names, ("simple_momentum", "macd_momentum"))
        self.assertGreaterEqual(len(result.symbol_scores), 6)
        self.assertGreaterEqual(len(result.candidates), 2)
        self.assertIsNotNone(result.best)
        rank_keys = [candidate.rank_key for candidate in result.candidates]
        self.assertEqual(rank_keys, sorted(rank_keys, reverse=True))

    def test_writes_candidate_and_score_csvs(self) -> None:
        config = load_config("configs/default.toml")
        data = generate_synthetic_market_data(
            symbols=("EURUSD", "GBPUSD", "USDJPY"),
            periods=72,
            interval_minutes=15,
            seed=402,
        )
        result = optimize_strategy_map(
            config=config,
            prices=data.prices,
            quotes=data.quotes,
            strategy_names=("simple_momentum", "macd_momentum"),
            symbols=("EURUSD", "GBPUSD", "USDJPY"),
            top_symbol_counts=(2,),
        )

        with TemporaryDirectory() as tmpdir:
            candidate_path = Path(tmpdir) / "maps.csv"
            score_path = Path(tmpdir) / "scores.csv"
            write_strategy_map_optimization_csv(result, candidate_path)
            write_symbol_strategy_scores_csv(result, score_path)
            candidate_text = candidate_path.read_text(encoding="utf-8")
            score_text = score_path.read_text(encoding="utf-8")

        self.assertIn("rank,label,symbols,strategy_map", candidate_text)
        self.assertIn("promotion_status,promotion_live_ready,promotion_reason", candidate_text)
        self.assertIn("rank,symbol,strategy,total_pnl_usd", score_text)
        self.assertIn("simple_momentum", score_text)

    def test_optimizer_rejects_empty_strategy_list(self) -> None:
        config = load_config("configs/default.toml")
        data = generate_synthetic_market_data(
            symbols=("EURUSD",),
            periods=24,
            interval_minutes=15,
            seed=403,
        )

        with self.assertRaisesRegex(ValueError, "at least one strategy"):
            optimize_strategy_map(
                config=config,
                prices=data.prices,
                quotes=data.quotes,
                strategy_names=(),
                symbols=("EURUSD",),
            )

    def test_optimizer_accepts_research_clock_and_allocation_policy(self) -> None:
        config = load_config("configs/competition.toml")
        data = generate_synthetic_market_data(
            symbols=("EURUSD", "GBPUSD"),
            periods=72,
            interval_minutes=15,
            seed=404,
        )

        result = optimize_strategy_map(
            config=config,
            prices=data.prices,
            quotes=data.quotes,
            strategy_names=("simple_momentum", "macd_momentum"),
            symbols=("EURUSD", "GBPUSD"),
            include_walk_forward=True,
            train_size=24,
            test_size=12,
            step_size=12,
            top_symbol_counts=(1, 2),
            allocation_policy=allocation_policy_for_strategy(
                "strategy_map",
                config,
                profile="directional_probe",
            ),
            clock=FixedModeClock(),
        )

        self.assertTrue(result.candidates)
        self.assertTrue(
            all(candidate.walk_forward is not None for candidate in result.candidates)
        )

    def test_optimizer_accepts_exact_candidate_map(self) -> None:
        config = load_config("configs/default.toml")
        data = generate_synthetic_market_data(
            symbols=("EURUSD", "GBPUSD"),
            periods=72,
            interval_minutes=15,
            seed=405,
        )

        result = optimize_strategy_map(
            config=config,
            prices=data.prices,
            quotes=data.quotes,
            strategy_names=("simple_momentum", "macd_momentum"),
            symbols=("EURUSD", "GBPUSD"),
            candidate_maps=(
                (
                    "manual_hybrid",
                    (
                        ("EURUSD", "simple_momentum"),
                        ("GBPUSD", "macd_momentum"),
                    ),
                ),
            ),
            top_symbol_counts=(1,),
        )

        manual = [
            candidate
            for candidate in result.candidates
            if candidate.label == "manual_hybrid"
        ]
        self.assertEqual(len(manual), 1)
        self.assertEqual(
            manual[0].strategy_map_text,
            "EURUSD=simple_momentum GBPUSD=macd_momentum",
        )

    def test_parse_candidate_map(self) -> None:
        label, pairs = _parse_candidate_map(
            "manual:AUDUSD=macd_momentum,GBPUSD=asset_adaptive_dual_squeeze",
            index=1,
        )

        self.assertEqual(label, "manual")
        self.assertEqual(
            pairs,
            (
                ("AUDUSD", "macd_momentum"),
                ("GBPUSD", "asset_adaptive_dual_squeeze"),
            ),
        )
