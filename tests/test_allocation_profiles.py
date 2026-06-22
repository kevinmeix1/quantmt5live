from __future__ import annotations

from unittest import TestCase

from quanthack.backtesting.allocation_profiles import (
    ALLOCATION_PROFILE_DEFAULT,
    ALLOCATION_PROFILE_DIRECTIONAL_PROBE,
    allocation_policy_for_strategy,
)
from quanthack.backtesting.portfolio_allocator import PortfolioAllocator, SymbolIntent
from quanthack.cli import (
    champion_ensemble_optimize,
    kalman_trend_optimize,
    macd_momentum_optimize,
    portfolio_backtest,
    portfolio_fixed_warmup_walk_forward,
    portfolio_universe_scan,
    strategy_map_optimize,
    volatility_squeeze_optimize,
)
from quanthack.core.clock import CompetitionMode, FixedModeClock, UTC
from quanthack.core.config import load_config
from datetime import datetime


class AllocationProfilesTest(TestCase):
    def test_default_profile_leaves_standard_strategy_on_default_allocator(self) -> None:
        config = load_config("configs/default.toml")

        self.assertIsNone(
            allocation_policy_for_strategy(
                "macd_momentum",
                config,
                profile=ALLOCATION_PROFILE_DEFAULT,
            )
        )

    def test_default_profile_relaxes_opportunity_probe(self) -> None:
        config = load_config("configs/default.toml")

        policy = allocation_policy_for_strategy(
            "opportunity_probe",
            config,
            profile=ALLOCATION_PROFILE_DEFAULT,
        )

        self.assertIsNotNone(policy)
        assert policy is not None
        self.assertEqual(policy.max_net_directional_pct, 1.0)
        self.assertEqual(policy.min_active_symbols, 1)
        self.assertFalse(policy.apply_diversification_scale)

    def test_research_cli_parsers_accept_directional_probe_profile(self) -> None:
        backtest_args = portfolio_backtest.build_parser().parse_args(
            [
                "--allocation-profile",
                ALLOCATION_PROFILE_DIRECTIONAL_PROBE,
                "--force-qualify-mode",
            ]
        )
        warmup_args = portfolio_fixed_warmup_walk_forward.build_parser().parse_args(
            [
                "--allocation-profile",
                ALLOCATION_PROFILE_DIRECTIONAL_PROBE,
                "--force-qualify-mode",
            ]
        )
        universe_args = portfolio_universe_scan.build_parser().parse_args(
            [
                "--allocation-profile",
                ALLOCATION_PROFILE_DIRECTIONAL_PROBE,
                "--force-qualify-mode",
            ]
        )
        macd_args = macd_momentum_optimize.build_parser().parse_args(
            [
                "--allocation-profile",
                ALLOCATION_PROFILE_DIRECTIONAL_PROBE,
                "--force-qualify-mode",
            ]
        )
        champion_args = champion_ensemble_optimize.build_parser().parse_args(
            [
                "--allocation-profile",
                ALLOCATION_PROFILE_DIRECTIONAL_PROBE,
                "--force-qualify-mode",
            ]
        )
        strategy_map_args = strategy_map_optimize.build_parser().parse_args(
            [
                "--allocation-profile",
                ALLOCATION_PROFILE_DIRECTIONAL_PROBE,
                "--force-qualify-mode",
            ]
        )
        volatility_args = volatility_squeeze_optimize.build_parser().parse_args(
            [
                "--allocation-profile",
                ALLOCATION_PROFILE_DIRECTIONAL_PROBE,
                "--force-qualify-mode",
            ]
        )
        kalman_args = kalman_trend_optimize.build_parser().parse_args(
            [
                "--allocation-profile",
                ALLOCATION_PROFILE_DIRECTIONAL_PROBE,
                "--force-qualify-mode",
            ]
        )

        self.assertEqual(
            backtest_args.allocation_profile,
            ALLOCATION_PROFILE_DIRECTIONAL_PROBE,
        )
        self.assertEqual(
            warmup_args.allocation_profile,
            ALLOCATION_PROFILE_DIRECTIONAL_PROBE,
        )
        self.assertEqual(
            universe_args.allocation_profile,
            ALLOCATION_PROFILE_DIRECTIONAL_PROBE,
        )
        self.assertEqual(
            macd_args.allocation_profile,
            ALLOCATION_PROFILE_DIRECTIONAL_PROBE,
        )
        self.assertEqual(
            champion_args.allocation_profile,
            ALLOCATION_PROFILE_DIRECTIONAL_PROBE,
        )
        self.assertEqual(
            strategy_map_args.allocation_profile,
            ALLOCATION_PROFILE_DIRECTIONAL_PROBE,
        )
        self.assertEqual(
            volatility_args.allocation_profile,
            ALLOCATION_PROFILE_DIRECTIONAL_PROBE,
        )
        self.assertEqual(
            kalman_args.allocation_profile,
            ALLOCATION_PROFILE_DIRECTIONAL_PROBE,
        )
        self.assertTrue(backtest_args.force_qualify_mode)
        self.assertTrue(warmup_args.force_qualify_mode)
        self.assertTrue(universe_args.force_qualify_mode)
        self.assertTrue(macd_args.force_qualify_mode)
        self.assertTrue(champion_args.force_qualify_mode)
        self.assertTrue(strategy_map_args.force_qualify_mode)
        self.assertTrue(volatility_args.force_qualify_mode)
        self.assertTrue(kalman_args.force_qualify_mode)

    def test_fixed_mode_clock_always_returns_configured_mode(self) -> None:
        clock = FixedModeClock(CompetitionMode.QUALIFY)

        self.assertEqual(
            clock.mode_at(datetime(2020, 1, 1, tzinfo=UTC)),
            CompetitionMode.QUALIFY,
        )

    def test_directional_probe_caps_lone_signal_without_zeroing_it(self) -> None:
        config = load_config("configs/competition.toml")
        policy = allocation_policy_for_strategy(
            "macd_momentum",
            config,
            profile=ALLOCATION_PROFILE_DIRECTIONAL_PROBE,
        )

        self.assertIsNotNone(policy)
        assert policy is not None
        allocation = PortfolioAllocator(policy).allocate(
            (SymbolIntent("EURUSD", 800_000.0),),
            equity=1_000_000.0,
        )

        self.assertAlmostEqual(allocation.targets[0].adjusted_notional_usd, 50_000.0)
        self.assertEqual(policy.max_net_directional_pct, 1.0)
        self.assertEqual(policy.min_active_symbols, 1)
        self.assertFalse(policy.apply_diversification_scale)
