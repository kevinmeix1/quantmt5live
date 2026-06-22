from __future__ import annotations

import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import TestCase


_SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "live_deal_attribution.py"
_SPEC = importlib.util.spec_from_file_location("live_deal_attribution_script", _SCRIPT_PATH)
assert _SPEC is not None and _SPEC.loader is not None
live_deal_attribution = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(live_deal_attribution)


class LiveDealAttributionStateTest(TestCase):
    def test_zero_win_realized_drag_enters_cooldown(self) -> None:
        row = {
            "closed_deals": 9,
            "wins": 0,
            "net_pnl": -65.49,
            "floating_pnl": 0.0,
            "open_positions": 0,
            "win_rate": 0.0,
        }

        self.assertEqual(
            live_deal_attribution._state(row),
            "cooldown_realized_drag",
        )

    def test_small_sample_loss_stays_small_only(self) -> None:
        row = {
            "closed_deals": 2,
            "wins": 0,
            "net_pnl": -36.0,
            "floating_pnl": 0.0,
            "open_positions": 0,
            "win_rate": 0.0,
        }

        self.assertEqual(
            live_deal_attribution._state(row),
            "small_only_until_recovery",
        )

    def test_estimates_state_clear_when_losing_cluster_rolls_out(self) -> None:
        now = datetime(2026, 6, 22, 6, 0, tzinfo=timezone.utc)
        deal_time = datetime(2026, 6, 22, 1, 0, tzinfo=timezone.utc)
        row = {
            "closed_deals": 5,
            "wins": 0,
            "losses": 5,
            "net_pnl": -75.0,
            "floating_pnl": 0.0,
            "open_positions": 0,
            "open_lots": 0.0,
            "open_direction": "FLAT",
            "win_rate": 0.0,
            "state": "cooldown_realized_drag",
        }
        events = [
            {
                "timestamp_utc": deal_time,
                "profit": -15.0,
                "commission": 0.0,
                "swap": 0.0,
                "fee": 0.0,
                "net": -15.0,
                "counted_closed": True,
            }
            for _ in range(5)
        ]

        clear_utc, state_after_clear = live_deal_attribution._estimate_state_clear_utc(
            row=row,
            events=events,
            now_utc=now,
            lookback=timedelta(hours=12),
        )

        self.assertEqual(clear_utc, "2026-06-22T13:00:01+00:00")
        self.assertEqual(state_after_clear, "no_closed_sample")

    def test_estimate_state_clear_ignores_already_working_symbol(self) -> None:
        row = {
            "closed_deals": 2,
            "wins": 2,
            "losses": 0,
            "net_pnl": 12.0,
            "floating_pnl": 0.0,
            "open_positions": 0,
            "win_rate": 1.0,
            "state": "working",
        }

        clear_utc, state_after_clear = live_deal_attribution._estimate_state_clear_utc(
            row=row,
            events=[],
            now_utc=datetime(2026, 6, 22, 6, 0, tzinfo=timezone.utc),
            lookback=timedelta(hours=12),
        )

        self.assertIsNone(clear_utc)
        self.assertIsNone(state_after_clear)
