from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from scripts.live_candidate_watchlist import (
    build_watchlist,
    read_candidate_files,
    read_candidate_rows,
    write_watchlist_json,
    write_watchlist_text,
)


class LiveCandidateWatchlistScriptTest(TestCase):
    def test_builds_live_gated_watchlist(self) -> None:
        watchlist = build_watchlist(
            candidate_rows=[
                {
                    "eligible": "True",
                    "quality_score": "1.47",
                    "symbol": "EURGBP",
                    "label": "cross_rate_edge",
                    "active_count": "20",
                    "hit_rate": "0.75",
                    "average_signed_forward_return_bps": "1.86",
                    "average_edge_after_cost_bps": "0.41",
                },
                {
                    "eligible": "False",
                    "quality_score": "0.90",
                    "symbol": "USDCHF",
                    "label": "ineligible",
                },
            ],
            attribution={
                "symbols": {
                    "EURGBP": {
                        "state": "cooldown_realized_drag",
                        "net_pnl": -131.12,
                        "estimated_state_clear_utc": "2026-06-22T10:57:11+00:00",
                    }
                }
            },
            pair_analysis={
                "pairs": {
                    "EURGBP": {
                        "action": "cooldown_realized_drag",
                        "combined_score": 1.29,
                    }
                }
            },
            sentiment={"pairs": {"EURGBP": {"score": 0.625}}},
            generated_at_utc="2026-06-22T08:55:00+00:00",
        )

        self.assertEqual(len(watchlist["candidates"]), 1)
        candidate = watchlist["candidates"][0]
        self.assertEqual(candidate["symbol"], "EURGBP")
        self.assertEqual(candidate["live_gate"], "blocked_fresh_risk")
        self.assertEqual(candidate["deal_state"], "cooldown_realized_drag")
        self.assertEqual(candidate["quality_score"], 1.47)
        self.assertEqual(candidate["hit_rate"], 0.75)
        self.assertTrue(candidate["strategy_aligned"])

    def test_marks_unblocked_candidate_with_live_strategy_mismatch(self) -> None:
        watchlist = build_watchlist(
            candidate_rows=[
                {
                    "eligible": "True",
                    "quality_score": "1.47",
                    "symbol": "EURGBP",
                    "label": "cross_rate_edge",
                    "active_count": "20",
                    "hit_rate": "0.75",
                    "average_signed_forward_return_bps": "1.86",
                    "average_edge_after_cost_bps": "0.41",
                }
            ],
            attribution={"symbols": {"EURGBP": {"state": "normal"}}},
            pair_analysis={"pairs": {}},
            sentiment={"pairs": {}},
            candidate_strategy="cross_rate_reversion",
            default_live_strategy="champion_ensemble",
        )

        candidate = watchlist["candidates"][0]
        self.assertEqual(candidate["live_gate"], "strategy_mismatch")
        self.assertEqual(candidate["candidate_strategy"], "cross_rate_reversion")
        self.assertEqual(candidate["live_strategy"], "champion_ensemble")
        self.assertFalse(candidate["strategy_aligned"])

    def test_marks_small_only_candidate_as_capped_not_blocked(self) -> None:
        watchlist = build_watchlist(
            candidate_rows=[
                {
                    "eligible": "True",
                    "quality_score": "1.47",
                    "symbol": "EURUSD",
                    "label": "cross_rate_edge",
                    "active_count": "20",
                    "hit_rate": "0.75",
                    "average_signed_forward_return_bps": "1.86",
                    "average_edge_after_cost_bps": "0.41",
                }
            ],
            attribution={
                "symbols": {
                    "EURUSD": {"state": "small_only_until_recovery"}
                }
            },
            pair_analysis={"pairs": {}},
            sentiment={"pairs": {}},
            candidate_strategy="cross_rate_reversion",
            default_live_strategy="cross_rate_reversion",
        )

        candidate = watchlist["candidates"][0]
        self.assertEqual(candidate["live_gate"], "small_only")
        self.assertTrue(candidate["strategy_aligned"])

    def test_strategy_map_override_can_align_candidate_strategy(self) -> None:
        watchlist = build_watchlist(
            candidate_rows=[
                {
                    "eligible": "True",
                    "quality_score": "1.47",
                    "symbol": "EURGBP",
                    "label": "cross_rate_edge",
                    "active_count": "20",
                    "hit_rate": "0.75",
                    "average_signed_forward_return_bps": "1.86",
                    "average_edge_after_cost_bps": "0.41",
                }
            ],
            attribution={"symbols": {"EURGBP": {"state": "normal"}}},
            pair_analysis={"pairs": {}},
            sentiment={"pairs": {}},
            candidate_strategy="cross_rate_reversion",
            default_live_strategy="champion_ensemble",
            live_strategy_by_symbol={"EURGBP": "cross_rate_reversion"},
        )

        candidate = watchlist["candidates"][0]
        self.assertEqual(candidate["live_gate"], "watch")
        self.assertTrue(candidate["strategy_aligned"])

    def test_reads_and_writes_watchlist_files(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            candidates = root / "candidates.csv"
            output_json = root / "watchlist.json"
            output_text = root / "watchlist.txt"
            candidates.write_text(
                "\n".join(
                    [
                        (
                            "eligible,quality_score,symbol,label,active_count,"
                            "hit_rate,average_signed_forward_return_bps,"
                            "average_edge_after_cost_bps"
                        ),
                        "True,1.47,EURGBP,cross_rate_edge,20,0.75,1.86,0.41",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            watchlist = build_watchlist(
                candidate_rows=read_candidate_rows(candidates),
                attribution={"symbols": {}},
                pair_analysis={"pairs": {}},
                sentiment={"pairs": {}},
                generated_at_utc="2026-06-22T08:55:00+00:00",
            )
            write_watchlist_json(watchlist, output_json)
            write_watchlist_text(watchlist, output_text)
            json_text = output_json.read_text(encoding="utf-8")
            text = output_text.read_text(encoding="utf-8")

        self.assertIn("EURGBP", json_text)
        self.assertIn("gate=watch", text)
        self.assertIn("strategy=unknown", text)
        self.assertIn("hit=75.0%", text)

    def test_reads_multiple_candidate_files_with_source_labels(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            first = root / "first.csv"
            second = root / "second.csv"
            output_text = root / "watchlist.txt"
            header = (
                "eligible,quality_score,symbol,label,active_count,"
                "hit_rate,average_signed_forward_return_bps,"
                "average_edge_after_cost_bps"
            )
            first.write_text(
                "\n".join([header, "True,1.10,EURUSD,a,5,0.60,1.0,0.5"])
                + "\n",
                encoding="utf-8",
            )
            second.write_text(
                "\n".join([header, "True,1.20,GBPUSD,b,4,0.75,2.0,1.5"])
                + "\n",
                encoding="utf-8",
            )

            watchlist = build_watchlist(
                candidate_rows=read_candidate_files((str(first), str(second))),
                attribution={"symbols": {}},
                pair_analysis={"pairs": {}},
                sentiment={"pairs": {}},
                generated_at_utc="2026-06-22T08:55:00+00:00",
            )
            write_watchlist_text(watchlist, output_text)
            text = output_text.read_text(encoding="utf-8")

        self.assertEqual(len(watchlist["candidates"]), 2)
        self.assertEqual(
            {row["source_path"] for row in watchlist["candidates"]},
            {str(first), str(second)},
        )
        self.assertIn("source=first.csv", text)
        self.assertIn("source=second.csv", text)

    def test_skips_missing_candidate_files(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            existing = root / "existing.csv"
            missing = root / "missing.csv"
            existing.write_text(
                "eligible,quality_score,symbol,label,active_count,hit_rate,"
                "average_signed_forward_return_bps,average_edge_after_cost_bps\n"
                "True,1.10,EURGBP,ok,12,0.60,0.7,0.2\n",
                encoding="utf-8",
            )

            rows = read_candidate_files((str(missing), str(existing)))

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["label"], "ok")
        self.assertEqual(rows[0]["_source_path"], str(existing))
