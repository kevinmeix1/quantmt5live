from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase


_SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "live_pair_analysis.py"
_SPEC = importlib.util.spec_from_file_location("live_pair_analysis_script", _SCRIPT_PATH)
assert _SPEC is not None and _SPEC.loader is not None
live_pair_analysis = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(live_pair_analysis)


class LivePairAnalysisActionTest(TestCase):
    def test_keep_if_aligned_flags_soft_opposite_drift(self) -> None:
        action = live_pair_analysis._action(
            position={"direction": "SELL", "profit": 0.5},
            combined_score=1.0,
            technical_score=0.8,
            spread_bps=0.1,
            deal_state="keep_if_signal_aligned",
        )

        self.assertEqual(action, "watch_signal_misalignment")

    def test_soft_opposite_drift_without_keep_state_holds(self) -> None:
        action = live_pair_analysis._action(
            position={"direction": "SELL", "profit": 0.5},
            combined_score=1.0,
            technical_score=0.8,
            spread_bps=0.1,
            deal_state="observe",
        )

        self.assertEqual(action, "hold_or_trail")

    def test_flat_observe_state_blocks_tiny_probe_label(self) -> None:
        action = live_pair_analysis._action(
            position=None,
            combined_score=2.0,
            technical_score=1.8,
            spread_bps=0.1,
            deal_state="observe",
        )

        self.assertEqual(action, "blocked_observe")

    def test_flat_small_only_state_allows_capped_probe_label(self) -> None:
        action = live_pair_analysis._action(
            position=None,
            combined_score=-2.0,
            technical_score=-1.8,
            spread_bps=0.1,
            deal_state="small_only_until_recovery",
        )

        self.assertEqual(action, "eligible_small_probe_sell")

    def test_flat_small_only_state_waits_without_strong_signal(self) -> None:
        action = live_pair_analysis._action(
            position=None,
            combined_score=-1.0,
            technical_score=-0.8,
            spread_bps=0.1,
            deal_state="small_only_until_recovery",
        )

        self.assertEqual(action, "small_only_wait")

    def test_strong_opposite_drift_still_prefers_exit_watch(self) -> None:
        action = live_pair_analysis._action(
            position={"direction": "SELL", "profit": 0.5},
            combined_score=1.5,
            technical_score=1.2,
            spread_bps=0.1,
            deal_state="keep_if_signal_aligned",
        )

        self.assertEqual(action, "watch_exit_or_reduce")

    def test_write_supports_custom_output_paths(self) -> None:
        snapshot = {
            "timestamp_utc": "2026-06-22T06:00:00+00:00",
            "account": {
                "equity": 999999.0,
                "day_pnl": -1.0,
                "positions_count": 0,
            },
            "pairs": {
                "EURUSD": {
                    "action": "wait",
                    "combined_score": 0.25,
                    "technical_score": 0.10,
                    "headline_sentiment_score": 0.50,
                    "deal_state": "working",
                    "realized_net_pnl": 1.23,
                    "spread_bps": 0.12,
                    "position": {"direction": "FLAT", "profit": 0.0},
                }
            },
        }

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            output_json = root / "custom" / "pair.json"
            output_text = root / "custom" / "pair.txt"
            history_jsonl = root / "history" / "pair.jsonl"

            live_pair_analysis._write(
                snapshot,
                output_json=output_json,
                output_text=output_text,
                history_jsonl=history_jsonl,
            )

            written = json.loads(output_json.read_text(encoding="utf-8"))
            text = output_text.read_text(encoding="utf-8")
            history = history_jsonl.read_text(encoding="utf-8")

        self.assertEqual(written["pairs"]["EURUSD"]["action"], "wait")
        self.assertIn("EURUSD: action=wait score=0.25", text)
        self.assertIn('"timestamp_utc": "2026-06-22T06:00:00+00:00"', history)
