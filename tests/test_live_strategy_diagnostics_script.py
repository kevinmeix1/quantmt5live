from __future__ import annotations

import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import TestCase

from quanthack.backtesting.portfolio_allocator import AllocatedTarget, SymbolIntent
from quanthack.market.market_data import QuoteSnapshot


_SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "live_strategy_diagnostics.py"
_SPEC = importlib.util.spec_from_file_location("live_strategy_diagnostics_script", _SCRIPT_PATH)
assert _SPEC is not None and _SPEC.loader is not None
live_strategy_diagnostics = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(live_strategy_diagnostics)


class LiveStrategyDiagnosticsTest(TestCase):
    def test_reason_bucket_identifies_session_gate(self) -> None:
        bucket = live_strategy_diagnostics._reason_bucket(
            "outside momentum UTC hours (10,11,12); current hour=4"
        )

        self.assertEqual(bucket, "session_gated")

    def test_reason_bucket_identifies_live_throttle(self) -> None:
        bucket = live_strategy_diagnostics._reason_bucket(
            "macd long; live throttle: symbol_state cooldown_realized_drag"
        )

        self.assertEqual(bucket, "live_throttle")

    def test_reason_bucket_identifies_inside_exit_band_as_threshold(self) -> None:
        bucket = live_strategy_diagnostics._reason_bucket(
            "MACD histogram 0.23 bps is inside exit band 0.25 bps"
        )

        self.assertEqual(bucket, "threshold_gated")

    def test_intent_status_strategy_no_change(self) -> None:
        raw = SymbolIntent("EURUSD", 0.0, current_notional_usd=0.0)
        adjusted = SymbolIntent("EURUSD", 0.0, current_notional_usd=0.0)
        target = AllocatedTarget(
            symbol="EURUSD",
            requested_notional_usd=0.0,
            adjusted_notional_usd=0.0,
            current_notional_usd=0.0,
        )

        status = live_strategy_diagnostics._intent_status(
            raw=raw,
            adjusted=adjusted,
            target=target,
        )

        self.assertEqual(status, "strategy_no_change")

    def test_intent_status_live_throttle_blocked(self) -> None:
        raw = SymbolIntent("EURUSD", 25_000.0, current_notional_usd=0.0)
        adjusted = SymbolIntent("EURUSD", 0.0, current_notional_usd=0.0)
        target = AllocatedTarget(
            symbol="EURUSD",
            requested_notional_usd=0.0,
            adjusted_notional_usd=0.0,
            current_notional_usd=0.0,
        )

        status = live_strategy_diagnostics._intent_status(
            raw=raw,
            adjusted=adjusted,
            target=target,
        )

        self.assertEqual(status, "live_throttle_blocked")

    def test_intent_status_actionable_allocation(self) -> None:
        raw = SymbolIntent("EURUSD", 25_000.0, current_notional_usd=0.0)
        adjusted = SymbolIntent("EURUSD", 25_000.0, current_notional_usd=0.0)
        target = AllocatedTarget(
            symbol="EURUSD",
            requested_notional_usd=25_000.0,
            adjusted_notional_usd=25_000.0,
            current_notional_usd=0.0,
        )

        status = live_strategy_diagnostics._intent_status(
            raw=raw,
            adjusted=adjusted,
            target=target,
        )

        self.assertEqual(status, "actionable_allocation")

    def test_default_strategy_map_is_filtered_to_requested_symbols(self) -> None:
        strategy_map = live_strategy_diagnostics._default_strategy_map_for(
            ("AUDUSD", "USDCHF")
        )

        self.assertEqual(
            strategy_map,
            ("AUDUSD=macd_momentum", "USDCHF=macd_momentum"),
        )

    def test_non_default_strategy_does_not_inherit_default_live_map(self) -> None:
        args = live_strategy_diagnostics.build_parser().parse_args(
            ["--strategy", "opportunity_probe"]
        )

        strategy_map = live_strategy_diagnostics._strategy_map_for_args(
            args,
            ("AUDUSD", "EURUSD"),
        )

        self.assertEqual(strategy_map, ())

    def test_default_strategy_keeps_default_live_map(self) -> None:
        args = live_strategy_diagnostics.build_parser().parse_args([])

        strategy_map = live_strategy_diagnostics._strategy_map_for_args(
            args,
            ("AUDUSD", "EURUSD"),
        )

        self.assertEqual(
            strategy_map,
            ("AUDUSD=macd_momentum", "EURUSD=macd_momentum"),
        )

    def test_parser_accepts_directional_probe_allocation_profile(self) -> None:
        args = live_strategy_diagnostics.build_parser().parse_args(
            ["--allocation-profile", "directional_probe"]
        )

        self.assertEqual(args.allocation_profile, "directional_probe")

    def test_parser_accepts_staged_max_order_lots(self) -> None:
        args = live_strategy_diagnostics.build_parser().parse_args(
            ["--max-order-lots", "0.25"]
        )

        self.assertEqual(args.max_order_lots, 0.25)

    def test_default_symbol_states_match_live_throttle_shape(self) -> None:
        self.assertNotIn(
            "small_only_until_recovery",
            live_strategy_diagnostics.BLOCKED_STATES,
        )
        self.assertIn(
            "small_only_until_recovery",
            live_strategy_diagnostics.SMALL_ONLY_STATES,
        )

    def test_parser_accepts_small_only_live_throttle_args(self) -> None:
        args = live_strategy_diagnostics.build_parser().parse_args(
            [
                "--small-only-symbol-state",
                "small_only_until_recovery",
                "--small-only-max-notional-usd",
                "25000",
            ]
        )

        self.assertEqual(args.small_only_symbol_state, ["small_only_until_recovery"])
        self.assertEqual(args.small_only_max_notional_usd, 25_000)

    def test_symbol_diagnostic_records_quote_wall_clock_skew(self) -> None:
        wall_clock = datetime(2026, 6, 22, 6, 30, tzinfo=timezone.utc)
        raw = SymbolIntent("EURUSD", 0.0, current_notional_usd=0.0, reason="wait")
        adjusted = SymbolIntent("EURUSD", 0.0, current_notional_usd=0.0, reason="wait")
        target = AllocatedTarget(
            symbol="EURUSD",
            requested_notional_usd=0.0,
            adjusted_notional_usd=0.0,
            current_notional_usd=0.0,
        )

        diagnostic = live_strategy_diagnostics._symbol_diagnostic(
            symbol="EURUSD",
            strategy="macd_momentum",
            quote=QuoteSnapshot(
                timestamp=wall_clock + timedelta(hours=1),
                symbol="EURUSD",
                bid=1.1,
                ask=1.1002,
            ),
            wall_clock_utc=wall_clock,
            raw=raw,
            adjusted=adjusted,
            target=target,
        )

        self.assertEqual(diagnostic["quote_wall_clock_skew_seconds"], 3600.0)

    def test_snapshot_text_includes_quote_skew(self) -> None:
        text = live_strategy_diagnostics._snapshot_text(
            {
                "timestamp_utc": "2026-06-22T06:30:00+00:00",
                "allocation": {
                    "status": "OK",
                    "requested_gross_notional_usd": 0.0,
                    "adjusted_gross_notional_usd": 0.0,
                },
                "allocation_profile": "directional_probe",
                "symbols": {
                    "EURUSD": {
                        "status": "strategy_no_change",
                        "strategy": "macd_momentum",
                        "raw_change_notional_usd": 0.0,
                        "throttle_change_notional_usd": 0.0,
                        "allocation_change_notional_usd": 0.0,
                        "raw_reason_bucket": "threshold_gated",
                        "quote_wall_clock_skew_seconds": 3600.0,
                        "throttle_reason": "MACD histogram below threshold",
                    }
                },
            }
        )

        self.assertIn("quote_skew=+3600s", text)
        self.assertIn("profile=directional_probe", text)
