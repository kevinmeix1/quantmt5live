from __future__ import annotations

import importlib.util
import json
from datetime import datetime, timezone
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
