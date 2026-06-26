from __future__ import annotations

import importlib.util
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase


_SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "live_near_promotion.py"
_SPEC = importlib.util.spec_from_file_location("live_near_promotion_script", _SCRIPT_PATH)
assert _SPEC is not None and _SPEC.loader is not None
live_near_promotion = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(live_near_promotion)


class LiveNearPromotionTest(TestCase):
    def test_ranks_near_misses_by_gate_gap(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            scan = root / "scan.csv"
            scan.write_text(
                "\n".join(
                    [
                        (
                            "rank,label,symbols,promotion_status,promotion_live_ready,"
                            "promotion_reason,wf_positive_fold_fraction,"
                            "wf_active_positive_fold_fraction,wf_non_negative_fold_fraction,"
                            "wf_median_active_test_return_pct,wf_total_evaluation_fills"
                        ),
                        (
                            "1,wide,AUDUSD,PAPER_ONLY,False,total positive folds,"
                            "0.60,0.90,0.90,0.001,80"
                        ),
                        (
                            "2,weak,AUDUSD,REJECT,False,non-negative fold fraction,"
                            "0.40,0.50,0.50,-0.001,400"
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            summary = live_near_promotion.build_near_promotion_summary(
                (str(scan),),
                now_utc=datetime(2026, 6, 23, tzinfo=timezone.utc),
            )

        self.assertEqual(summary["scan_count"], 2)
        self.assertEqual(summary["top_candidates"][0]["label"], "wide")
        self.assertIn(
            "positive_folds",
            summary["top_candidates"][0]["failed_gates"][0],
        )

    def test_prefers_fresher_scan_when_near_miss_quality_ties(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            older = root / "older.csv"
            newer = root / "newer.csv"
            header = (
                "rank,label,symbols,promotion_status,promotion_live_ready,"
                "promotion_reason,wf_positive_fold_fraction,"
                "wf_active_positive_fold_fraction,wf_non_negative_fold_fraction,"
                "wf_median_active_test_return_pct,wf_total_evaluation_fills"
            )
            row = (
                "1,same_quality,AUDUSD EURUSD,PAPER_ONLY,False,total positive folds,"
                "0.6666666667,0.80,0.8333333333,0.002,54"
            )
            older.write_text(header + "\n" + row + "\n", encoding="utf-8")
            newer.write_text(header + "\n" + row + "\n", encoding="utf-8")
            now = datetime(2026, 6, 25, tzinfo=timezone.utc)
            os.utime(older, ((now - timedelta(days=2)).timestamp(),) * 2)
            os.utime(newer, ((now - timedelta(minutes=5)).timestamp(),) * 2)

            summary = live_near_promotion.build_near_promotion_summary(
                (str(older), str(newer)),
                now_utc=now,
            )

        self.assertEqual(summary["top_candidates"][0]["source_path"], str(newer))

    def test_build_summary_expands_glob_inputs(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            scan = root / "live_watch_fixed_map_candidate_w480_summary.csv"
            scan.write_text(
                "\n".join(
                    [
                        (
                            "strategy,symbols,promotion_status,promotion_live_ready,"
                            "promotion_reason,positive_fold_fraction,"
                            "active_positive_fold_fraction,non_negative_fold_fraction,"
                            "total_evaluation_fills"
                        ),
                        (
                            "map,AUDUSD EURGBP,PAPER_ONLY,False,"
                            "needs more positive folds,0.5556,0.6250,0.7222,130"
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            summary = live_near_promotion.build_near_promotion_summary(
                (str(root / "live_watch_fixed_map_*_summary.csv"),),
                now_utc=datetime(2026, 6, 26, tzinfo=timezone.utc),
            )

        self.assertEqual(summary["scan_count"], 1)
        self.assertEqual(
            Path(summary["top_candidates"][0]["source_path"]).name,
            "live_watch_fixed_map_candidate_w480_summary.csv",
        )

    def test_build_summary_deduplicates_overlapping_explicit_and_glob_inputs(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            scan = root / "live_watch_macd_candidate_w480.csv"
            scan.write_text(
                "\n".join(
                    [
                        (
                            "label,symbols,promotion_status,promotion_live_ready,"
                            "promotion_reason,positive_fold_fraction,"
                            "active_positive_fold_fraction,non_negative_fold_fraction,"
                            "total_evaluation_fills"
                        ),
                        (
                            "candidate,AUDUSD EURUSD,PAPER_ONLY,False,"
                            "needs more positive folds,0.66,0.80,0.80,54"
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            summary = live_near_promotion.build_near_promotion_summary(
                (str(scan), str(root / "live_watch_macd_*_w480.csv")),
                now_utc=datetime(2026, 6, 26, tzinfo=timezone.utc),
            )

        self.assertEqual(summary["scan_count"], 1)
        self.assertEqual(len(summary["top_candidates"]), 1)

    def test_newer_reject_suppresses_stale_same_candidate_paper_only_row(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            older = root / "older.csv"
            newer = root / "newer.csv"
            header = (
                "rank,label,symbols,promotion_status,promotion_live_ready,"
                "promotion_reason,wf_positive_fold_fraction,"
                "wf_active_positive_fold_fraction,wf_non_negative_fold_fraction,"
                "wf_median_active_test_return_pct,wf_total_evaluation_fills"
            )
            older.write_text(
                header
                + "\n"
                + (
                    "1,same_candidate,AUDUSD EURUSD,PAPER_ONLY,False,"
                    "almost promoted,0.6667,0.80,0.80,0.001,90"
                )
                + "\n",
                encoding="utf-8",
            )
            newer.write_text(
                header
                + "\n"
                + (
                    "1,same_candidate,EURUSD AUDUSD,REJECT,False,"
                    "non-negative fold fraction,0.4444,0.5333,0.6111,0.0,90"
                )
                + "\n",
                encoding="utf-8",
            )
            now = datetime(2026, 6, 26, tzinfo=timezone.utc)
            os.utime(older, ((now - timedelta(hours=2)).timestamp(),) * 2)
            os.utime(newer, ((now - timedelta(minutes=5)).timestamp(),) * 2)

            summary = live_near_promotion.build_near_promotion_summary(
                (str(older), str(newer)),
                now_utc=now,
            )

        self.assertEqual(summary["superseded_count"], 1)
        self.assertEqual(summary["scan_count"], 1)
        self.assertEqual(summary["top_candidates"][0]["promotion_status"], "REJECT")
        self.assertEqual(summary["top_candidates"][0]["source_path"], str(newer))

    def test_newer_paper_only_suppresses_stale_same_candidate_paper_only_row(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            older = root / "older.csv"
            newer = root / "newer.csv"
            header = (
                "rank,label,symbols,promotion_status,promotion_live_ready,"
                "promotion_reason,wf_positive_fold_fraction,"
                "wf_active_positive_fold_fraction,wf_non_negative_fold_fraction,"
                "wf_median_active_test_return_pct,wf_total_evaluation_fills"
            )
            older.write_text(
                header
                + "\n"
                + (
                    "1,same_candidate,AUDUSD EURUSD,PAPER_ONLY,False,"
                    "almost promoted,0.6667,0.80,0.80,0.001,90"
                )
                + "\n",
                encoding="utf-8",
            )
            newer.write_text(
                header
                + "\n"
                + (
                    "1,same_candidate,AUDUSD EURUSD,PAPER_ONLY,False,"
                    "still weak on full data,0.50,0.6923,0.7778,0.0005,90"
                )
                + "\n",
                encoding="utf-8",
            )
            now = datetime(2026, 6, 26, tzinfo=timezone.utc)
            os.utime(older, ((now - timedelta(hours=2)).timestamp(),) * 2)
            os.utime(newer, ((now - timedelta(minutes=5)).timestamp(),) * 2)

            summary = live_near_promotion.build_near_promotion_summary(
                (str(older), str(newer)),
                now_utc=now,
            )

        self.assertEqual(summary["superseded_count"], 1)
        self.assertEqual(summary["scan_count"], 1)
        self.assertEqual(summary["top_candidates"][0]["source_path"], str(newer))
        self.assertAlmostEqual(
            summary["top_candidates"][0]["positive_fold_fraction"],
            0.50,
        )

    def test_newer_strategy_map_alias_suppresses_stale_label_alias(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            older = root / "older.csv"
            newer = root / "newer.csv"
            older.write_text(
                "\n".join(
                    [
                        (
                            "rank,label,symbols,strategy_map,promotion_status,"
                            "promotion_live_ready,promotion_reason,"
                            "wf_positive_fold_fraction,wf_active_positive_fold_fraction,"
                            "wf_non_negative_fold_fraction,wf_total_evaluation_fills"
                        ),
                        (
                            "1,top_3_best_symbol_strategies,AUDUSD EURUSD USDCHF,"
                            "AUDUSD=macd_momentum EURUSD=macd_momentum "
                            "USDCHF=macd_momentum,PAPER_ONLY,False,"
                            "almost promoted,0.6667,0.80,0.8333,39"
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            newer.write_text(
                "\n".join(
                    [
                        (
                            "strategy,symbols,promotion_status,promotion_live_ready,"
                            "promotion_reason,positive_fold_fraction,"
                            "active_positive_fold_fraction,non_negative_fold_fraction,"
                            "total_evaluation_fills"
                        ),
                        (
                            '"champion_ensemble with overrides '
                            '(AUDUSD=macd_momentum, EURUSD=macd_momentum, '
                            'USDCHF=macd_momentum)",USDCHF AUDUSD EURUSD,'
                            "PAPER_ONLY,False,full data recheck still weak,"
                            "0.6154,0.7273,0.8462,73"
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            now = datetime(2026, 6, 26, tzinfo=timezone.utc)
            os.utime(older, ((now - timedelta(hours=2)).timestamp(),) * 2)
            os.utime(newer, ((now - timedelta(minutes=5)).timestamp(),) * 2)

            summary = live_near_promotion.build_near_promotion_summary(
                (str(older), str(newer)),
                now_utc=now,
            )

        self.assertEqual(summary["superseded_count"], 1)
        self.assertEqual(summary["scan_count"], 1)
        self.assertEqual(summary["top_candidates"][0]["source_path"], str(newer))
        self.assertAlmostEqual(
            summary["top_candidates"][0]["positive_fold_fraction"],
            0.6154,
        )

    def test_newer_consensus_row_suppresses_stale_strategy_map_window(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            older = root / "window_w672_summary.csv"
            newer = root / "window_consensus.csv"
            strategy_map = (
                "AUDUSD=macd_momentum EURGBP=macd_momentum "
                "EURUSD=macd_momentum GBPUSD=macd_momentum "
                "USDCAD=macd_momentum USDCHF=macd_momentum "
                "USDJPY=macd_momentum"
            )
            older.write_text(
                "\n".join(
                    [
                        (
                            "rank,label,symbols,strategy_map,promotion_status,"
                            "promotion_live_ready,promotion_reason,"
                            "wf_positive_fold_fraction,"
                            "wf_active_positive_fold_fraction,"
                            "wf_non_negative_fold_fraction,"
                            "wf_total_evaluation_fills"
                        ),
                        (
                            "1,all_macd_momentum,AUDUSD EURGBP EURUSD GBPUSD "
                            f"USDCAD USDCHF USDJPY,{strategy_map},"
                            "PAPER_ONLY,False,almost promoted,0.6364,0.7000,"
                            "0.7273,150"
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            newer.write_text(
                "\n".join(
                    [
                        (
                            "rank,label,candidate_signature,strategy_map,"
                            "consensus_status,all_live_ready,statuses,"
                            "min_wf_positive_fold_fraction,"
                            "min_wf_active_positive_fold_fraction,"
                            "min_wf_non_negative_fold_fraction"
                        ),
                        (
                            f"1,all_macd_momentum,{strategy_map},{strategy_map},"
                            "REJECT,False,REJECT|PAPER_ONLY|PROMOTE,"
                            "0.4444,0.5000,0.6111"
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            now = datetime(2026, 6, 26, tzinfo=timezone.utc)
            os.utime(older, ((now - timedelta(hours=2)).timestamp(),) * 2)
            os.utime(newer, ((now - timedelta(minutes=5)).timestamp(),) * 2)

            summary = live_near_promotion.build_near_promotion_summary(
                (str(older), str(newer)),
                now_utc=now,
            )

        self.assertEqual(summary["superseded_count"], 1)
        self.assertEqual(summary["scan_count"], 0)

    def test_newer_parameterized_macd_alias_suppresses_stale_label_alias(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            older = root / "older.csv"
            newer = root / "newer.csv"
            older_header = (
                "rank,label,symbols,fast_window,slow_window,signal_window,"
                "min_histogram_bps,min_macd_bps,min_histogram_slope_bps,"
                "min_trend_efficiency,max_holding_period,allowed_utc_hours,"
                "promotion_status,promotion_live_ready,promotion_reason,"
                "wf_positive_fold_fraction,wf_active_positive_fold_fraction,"
                "wf_non_negative_fold_fraction,wf_total_evaluation_fills"
            )
            newer_header = (
                "rank,label,symbols,fast_window,slow_window,signal_window,"
                "min_histogram_bps,min_macd_bps,min_histogram_slope_bps,"
                "require_macd_histogram_agreement,min_trend_efficiency,"
                "max_holding_period,allowed_utc_hours,promotion_status,"
                "promotion_live_ready,promotion_reason,wf_positive_fold_fraction,"
                "wf_active_positive_fold_fraction,wf_non_negative_fold_fraction,"
                "wf_total_evaluation_fills"
            )
            older.write_text(
                older_header
                + "\n"
                + (
                    "1,extended_low,AUDUSD EURUSD USDCAD USDCHF,6,18,5,"
                    "0.5,0.35,0.03,0.07,16,6|7|8|9|10|11|12|13|14|20|21|22,"
                    "PAPER_ONLY,False,almost promoted,0.6667,0.6667,0.8333,56"
                )
                + "\n",
                encoding="utf-8",
            )
            newer.write_text(
                newer_header
                + "\n"
                + (
                    "1,near_promo,USDCHF USDCAD EURUSD AUDUSD,6,18,5,"
                    "0.50,0.350,0.030,True,0.070,16,6|7|8|9|10|11|12|13|14|20|21|22,"
                    "PAPER_ONLY,False,full data recheck weaker,0.462,0.600,0.769,102"
                )
                + "\n",
                encoding="utf-8",
            )
            now = datetime(2026, 6, 26, tzinfo=timezone.utc)
            os.utime(older, ((now - timedelta(hours=2)).timestamp(),) * 2)
            os.utime(newer, ((now - timedelta(minutes=5)).timestamp(),) * 2)

            summary = live_near_promotion.build_near_promotion_summary(
                (str(older), str(newer)),
                now_utc=now,
            )

        self.assertEqual(summary["superseded_count"], 1)
        self.assertEqual(summary["scan_count"], 1)
        self.assertEqual(summary["top_candidates"][0]["label"], "near_promo")
        self.assertEqual(summary["top_candidates"][0]["source_path"], str(newer))
        self.assertAlmostEqual(
            summary["top_candidates"][0]["positive_fold_fraction"],
            0.462,
        )

    def test_newer_macd_parameter_consensus_suppresses_window_row(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            older = root / "window_w960.csv"
            newer = root / "parameter_consensus.csv"
            older.write_text(
                "\n".join(
                    [
                        (
                            "rank,label,symbols,fast_window,slow_window,"
                            "signal_window,min_histogram_bps,"
                            "exit_histogram_bps,min_macd_bps,"
                            "min_histogram_slope_bps,"
                            "require_macd_histogram_agreement,"
                            "slippage_bps,cost_buffer,min_trend_efficiency,"
                            "max_holding_period,allowed_utc_hours,"
                            "promotion_status,promotion_live_ready,"
                            "promotion_reason,wf_positive_fold_fraction,"
                            "wf_active_positive_fold_fraction,"
                            "wf_non_negative_fold_fraction,"
                            "wf_total_evaluation_fills"
                        ),
                        (
                            "1,micro,AUDUSD EURUSD,8,21,8,0.05,0.02,"
                            "0.05,0.0,True,1.0,1.0,0.04,6,"
                            "6|7|8,PAPER_ONLY,False,near,0.6154,"
                            "0.7273,0.8462,81"
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            newer.write_text(
                "\n".join(
                    [
                        (
                            "rank,label,symbols,candidate_signature,consensus_status,"
                            "all_live_ready,min_wf_positive_fold_fraction,"
                            "min_wf_active_positive_fold_fraction,"
                            "min_wf_non_negative_fold_fraction"
                        ),
                        (
                            "1,micro,AUDUSD EURUSD,\"micro fast_window=8 slow_window=21 "
                            "signal_window=8 min_histogram_bps=0.05 "
                            "exit_histogram_bps=0.02 min_macd_bps=0.05 "
                            "min_histogram_slope_bps=0.0 "
                            "require_macd_histogram_agreement=True "
                            "slippage_bps=1.0 cost_buffer=1.0 "
                            "min_trend_efficiency=0.04 "
                            "max_holding_period=6 allowed_utc_hours=6|7|8\","
                            "PAPER_ONLY,False,0.5556,0.6250,0.7222"
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            now = datetime(2026, 6, 26, tzinfo=timezone.utc)
            os.utime(older, ((now - timedelta(hours=2)).timestamp(),) * 2)
            os.utime(newer, ((now - timedelta(minutes=5)).timestamp(),) * 2)

            summary = live_near_promotion.build_near_promotion_summary(
                (str(older), str(newer)),
                now_utc=now,
            )

        self.assertEqual(summary["superseded_count"], 1)
        self.assertEqual(summary["scan_count"], 0)

    def test_newer_opportunity_consensus_suppresses_window_row(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            older = root / "opportunity_w960.csv"
            newer = root / "opportunity_consensus.csv"
            older.write_text(
                "\n".join(
                    [
                        (
                            "rank,label,symbols,fast_lookback,medium_lookback,"
                            "slow_lookback,min_score,exit_score,reverse_score,"
                            "min_fast_move_bps,volatility_penalty,"
                            "min_holding_period,max_holding_period,max_spread_bps,"
                            "promotion_status,promotion_live_ready,"
                            "promotion_reason,wf_positive_fold_fraction,"
                            "wf_active_positive_fold_fraction,"
                            "wf_non_negative_fold_fraction,"
                            "wf_total_evaluation_fills"
                        ),
                        (
                            "1,aud_probe,AUDUSD,4,12,32,5.0,0.25,5.5,"
                            "3.5,0.75,32,144,5.0,PAPER_ONLY,False,near,"
                            "0.8333,0.8333,0.8333,64"
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            newer.write_text(
                "\n".join(
                    [
                        (
                            "rank,label,symbols,candidate_signature,"
                            "consensus_status,all_live_ready,"
                            "min_wf_positive_fold_fraction,"
                            "min_wf_active_positive_fold_fraction,"
                            "min_wf_non_negative_fold_fraction"
                        ),
                        (
                            "1,aud_probe,AUDUSD,\"aud_probe fast_lookback=4 "
                            "medium_lookback=12 slow_lookback=32 "
                            "min_score=5.0 exit_score=0.25 "
                            "reverse_score=5.5 min_fast_move_bps=3.5 "
                            "volatility_penalty=0.75 min_holding_period=32 "
                            "max_holding_period=144 max_spread_bps=5.0\","
                            "REJECT,False,0.3333,0.3333,0.3333"
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            now = datetime(2026, 6, 26, tzinfo=timezone.utc)
            os.utime(older, ((now - timedelta(hours=2)).timestamp(),) * 2)
            os.utime(newer, ((now - timedelta(minutes=5)).timestamp(),) * 2)

            summary = live_near_promotion.build_near_promotion_summary(
                (str(older), str(newer)),
                now_utc=now,
            )

        self.assertEqual(summary["superseded_count"], 1)
        self.assertEqual(summary["scan_count"], 0)

    def test_cli_writes_json_and_text(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            scan = root / "scan.csv"
            output_json = root / "near.json"
            output_text = root / "near.txt"
            scan.write_text(
                "\n".join(
                    [
                        (
                            "rank,label,symbols,promotion_status,promotion_live_ready,"
                            "promotion_reason,positive_fold_fraction,"
                            "active_positive_fold_fraction,non_negative_fold_fraction,"
                            "total_evaluation_fills"
                        ),
                        "1,current,AUDUSD,PAPER_ONLY,False,needs more positive folds,0.65,0.80,0.80,20",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            live_near_promotion.main(
                [
                    "--scan-csv",
                    str(scan),
                    "--output-json",
                    str(output_json),
                    "--output-text",
                    str(output_text),
                ]
            )
            data = json.loads(output_json.read_text(encoding="utf-8"))
            text = output_text.read_text(encoding="utf-8")

        self.assertEqual(data["top_candidates"][0]["label"], "current")
        self.assertIn("near-promotion candidates=1", text)
