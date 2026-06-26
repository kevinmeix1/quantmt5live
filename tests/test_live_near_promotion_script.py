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
