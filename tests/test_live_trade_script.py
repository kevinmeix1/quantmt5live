from __future__ import annotations

from unittest import TestCase

from quanthack.backtesting.portfolio_allocator import PortfolioAllocator, SymbolIntent
from quanthack.cli.live_trade import (
    ALLOCATION_PROFILE_DEFAULT,
    ALLOCATION_PROFILE_DIRECTIONAL_PROBE,
    _allocation_policy_for,
    build_parser,
)
from quanthack.core.config import load_config


class LiveTradeScriptTest(TestCase):
    def test_default_allocation_profile_preserves_standard_strategies(self) -> None:
        config = load_config("configs/default.toml")

        policy = _allocation_policy_for(
            "macd_momentum",
            config,
            profile=ALLOCATION_PROFILE_DEFAULT,
        )

        self.assertIsNone(policy)

    def test_default_opportunity_probe_keeps_single_signal_policy(self) -> None:
        config = load_config("configs/default.toml")

        policy = _allocation_policy_for(
            "opportunity_probe",
            config,
            profile=ALLOCATION_PROFILE_DEFAULT,
        )

        self.assertIsNotNone(policy)
        assert policy is not None
        self.assertEqual(policy.max_net_directional_pct, 1.0)
        self.assertEqual(policy.min_active_symbols, 1)
        self.assertFalse(policy.apply_diversification_scale)

    def test_directional_probe_is_bounded_but_does_not_zero_lone_signal(self) -> None:
        config = load_config("configs/competition.toml")
        policy = _allocation_policy_for(
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
        target = allocation.targets[0]

        self.assertAlmostEqual(target.adjusted_notional_usd, 50_000.0)
        self.assertEqual(policy.max_net_directional_pct, 1.0)
        self.assertEqual(policy.min_active_symbols, 1)
        self.assertFalse(policy.apply_diversification_scale)
        self.assertTrue(any("symbol cap" in reason for reason in target.reasons))
        self.assertFalse(any("net directional" in reason for reason in target.reasons))

    def test_unknown_allocation_profile_fails_fast(self) -> None:
        config = load_config("configs/default.toml")

        with self.assertRaisesRegex(ValueError, "unknown allocation profile"):
            _allocation_policy_for("macd_momentum", config, profile="wide_open")

    def test_parser_defaults_to_default_allocation_profile(self) -> None:
        args = build_parser().parse_args([])

        self.assertEqual(args.allocation_profile, ALLOCATION_PROFILE_DEFAULT)

    def test_parser_accepts_directional_probe_allocation_profile(self) -> None:
        args = build_parser().parse_args(
            ["--allocation-profile", ALLOCATION_PROFILE_DIRECTIONAL_PROBE]
        )

        self.assertEqual(args.allocation_profile, ALLOCATION_PROFILE_DIRECTIONAL_PROBE)
