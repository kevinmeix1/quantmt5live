from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase


_SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "live_status_summary.py"
_SPEC = importlib.util.spec_from_file_location("live_status_summary_script", _SCRIPT_PATH)
assert _SPEC is not None and _SPEC.loader is not None
live_status_summary = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(live_status_summary)


class LiveStatusSummaryScriptTest(TestCase):
    def test_build_summary_flags_flat_blocked_fresh_risk(self) -> None:
        summary = live_status_summary.build_summary(
            metrics=_metrics_row(positions_count="0"),
            live_loop={"iteration": 4, "timestamp_utc": "2026-01-01T00:04:00Z"},
            latest_order=None,
            pair_analysis={
                "pairs": {
                    "EURUSD": {
                        "action": "cooldown_realized_drag",
                        "combined_score": -2.0,
                        "technical_score": -1.7,
                    },
                    "USDJPY": {
                        "action": "blocked_observe",
                        "combined_score": 0.5,
                    }
                }
            },
            attribution={
                "symbols": {
                    "EURUSD": {
                        "state": "cooldown_realized_drag",
                        "net_pnl": -10.0,
                        "floating_pnl": 0.0,
                        "estimated_state_clear_utc": "2026-01-01T00:30:00+00:00",
                        "estimated_state_after_clear": "working",
                    },
                    "USDJPY": {
                        "state": "observe",
                        "net_pnl": -1.0,
                        "floating_pnl": 0.0,
                        "estimated_state_clear_utc": "2026-01-01T00:15:00+00:00",
                        "estimated_state_after_clear": "working",
                    }
                }
            },
            diagnostics={
                "allocation": {"status": "OK"},
                "symbols": {
                    "EURUSD": {
                        "status": "strategy_no_change",
                        "raw_reason_bucket": "threshold_gated",
                        "raw_reason": "histogram below threshold",
                        "raw_change_notional_usd": 0,
                        "allocation_change_notional_usd": 0,
                    }
                },
            },
            sentiment={"pairs": {"EURUSD": {"score": 0.0}}},
            research_consensus={"consensus_status": "REJECT"},
            generated_at_utc="2026-01-01T00:05:00+00:00",
        )

        self.assertEqual(summary["status"], "FLAT_FRESH_RISK_BLOCKED")
        self.assertEqual(summary["fixed_warmup_consensus"], {})
        self.assertEqual(
            summary["risk"]["blocked_symbols"],
            {"EURUSD": "cooldown_realized_drag", "USDJPY": "observe"},
        )
        self.assertEqual(summary["risk"]["fresh_risk_candidates"], [])
        self.assertEqual(summary["reentry_queue"]["candidate_count"], 2)
        self.assertEqual(
            summary["reentry_queue"]["top_candidates"][0]["symbol"],
            "EURUSD",
        )
        self.assertTrue(
            summary["reentry_queue"]["top_candidates"][0]["in_live_universe"]
        )

    def test_build_summary_flags_flat_small_only_ready(self) -> None:
        summary = live_status_summary.build_summary(
            metrics=_metrics_row(positions_count="0"),
            live_loop={"iteration": 4, "timestamp_utc": "2026-01-01T00:04:00Z"},
            latest_order=None,
            pair_analysis={
                "pairs": {
                    "EURUSD": {
                        "action": "small_only_until_recovery",
                        "combined_score": -2.0,
                    }
                }
            },
            attribution={
                "symbols": {
                    "EURUSD": {
                        "state": "small_only_until_recovery",
                        "net_pnl": -10.0,
                    }
                }
            },
            diagnostics={"allocation": {"status": "OK"}, "symbols": {}},
            sentiment={"pairs": {"EURUSD": {"score": 0.0}}},
            research_consensus=None,
            generated_at_utc="2026-01-01T00:05:00+00:00",
        )

        self.assertEqual(summary["status"], "FLAT_SMALL_ONLY_READY")
        self.assertEqual(summary["risk"]["blocked_symbols"], {})
        self.assertEqual(
            summary["risk"]["small_only_symbols"],
            {"EURUSD": "small_only_until_recovery"},
        )

    def test_build_summary_prefers_open_position_status(self) -> None:
        summary = live_status_summary.build_summary(
            metrics=_metrics_row(positions_count="1"),
            live_loop={"iteration": 4, "timestamp_utc": "2026-01-01T00:04:00Z"},
            latest_order=None,
            pair_analysis={"pairs": {}},
            attribution={"symbols": {}},
            diagnostics={"symbols": {}},
            sentiment={"pairs": {}},
            research_consensus=None,
            generated_at_utc="2026-01-01T00:05:00+00:00",
        )

        self.assertEqual(summary["status"], "LIVE_POSITIONS_OPEN")

    def test_read_json_treats_partial_optional_file_as_missing(self) -> None:
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "near_promotion.json"
            path.write_text("", encoding="utf-8")

            self.assertEqual(live_status_summary.read_json(path), {})

    def test_candidate_optimizer_evidence_flags_matching_rejection(self) -> None:
        evidence = live_status_summary._candidate_optimizer_evidence(
            {
                "top_candidates": [
                    {
                        "label": "candidate_all_opportunity_probe",
                        "actionable_symbols": ["AUDUSD", "EURUSD"],
                        "requested_symbols": ["AUDUSD", "EURUSD"],
                        "top_symbol": {
                            "symbol": "AUDUSD",
                            "strategy": "opportunity_probe",
                        },
                    }
                ]
            },
            {
                "top_candidates": [
                    {
                        "source_path": (
                            "outputs/backtests/"
                            "live_watch_opportunity_probe_audusd_eurusd_w480.csv"
                        ),
                        "source_label": (
                            "live_watch_opportunity_probe_audusd_eurusd_w480"
                        ),
                        "label": "aud_eur_score5",
                        "symbols": "AUDUSD EURUSD",
                        "promotion_status": "REJECT",
                        "promotion_live_ready": "False",
                        "wf_non_negative_fold_fraction": "0.3889",
                        "wf_active_positive_fold_fraction": "0.3889",
                        "wf_total_evaluation_fills": "92",
                    }
                ]
            },
        )

        self.assertEqual(evidence["candidate_count"], 1)
        top = evidence["top_candidates"][0]
        self.assertEqual(top["evidence_status"], "REJECTED_BY_SCAN")
        self.assertEqual(top["symbols"], ["AUDUSD", "EURUSD"])
        self.assertEqual(top["top_match"]["promotion_status"], "REJECT")

    def test_candidate_optimizer_evidence_prefers_actionable_exact_scan(self) -> None:
        evidence = live_status_summary._candidate_optimizer_evidence(
            {
                "top_candidates": [
                    {
                        "label": "candidate_all_opportunity_probe",
                        "actionable_symbols": ["AUDUSD", "EURUSD"],
                        "requested_symbols": [
                            "AUDUSD",
                            "EURUSD",
                            "GBPUSD",
                            "USDCAD",
                        ],
                        "top_symbol": {
                            "symbol": "AUDUSD",
                            "strategy": "opportunity_probe",
                        },
                    }
                ]
            },
            {
                "top_candidates": [
                    {
                        "source_path": (
                            "outputs/backtests/"
                            "live_watch_opportunity_probe_audusd_eurusd_w480.csv"
                        ),
                        "source_label": (
                            "live_watch_opportunity_probe_audusd_eurusd_w480"
                        ),
                        "label": "aud_eur_score5",
                        "symbols": "AUDUSD EURUSD",
                        "promotion_status": "REJECT",
                        "promotion_live_ready": "False",
                        "wf_non_negative_fold_fraction": "0.3889",
                        "wf_active_positive_fold_fraction": "0.3889",
                        "wf_total_evaluation_fills": "92",
                    },
                    {
                        "source_path": (
                            "outputs/backtests/"
                            "live_watch_opportunity_probe_aud_eur_gbp_cad_current_w960.csv"
                        ),
                        "source_label": (
                            "live_watch_opportunity_probe_aud_eur_gbp_cad_current_w960"
                        ),
                        "label": "ultra_strict",
                        "symbols": "AUDUSD EURUSD GBPUSD USDCAD",
                        "promotion_status": "REJECT",
                        "promotion_live_ready": "False",
                        "wf_non_negative_fold_fraction": "0.3333",
                        "wf_active_positive_fold_fraction": "0.3333",
                        "wf_total_evaluation_fills": "298",
                    },
                ]
            },
        )

        top = evidence["top_candidates"][0]
        self.assertEqual(
            top["symbols"],
            ["AUDUSD", "EURUSD"],
        )
        self.assertEqual(
            top["top_match"]["source_label"],
            "live_watch_opportunity_probe_audusd_eurusd_w480",
        )
        self.assertEqual(
            top["top_match"]["symbols"],
            ["AUDUSD", "EURUSD"],
        )

    def test_candidate_optimizer_evidence_prefers_actionable_w960_over_requested_w480(self) -> None:
        evidence = live_status_summary._candidate_optimizer_evidence(
            {
                "top_candidates": [
                    {
                        "label": "candidate_all_opportunity_probe",
                        "actionable_symbols": ["AUDUSD", "EURGBP"],
                        "requested_symbols": [
                            "AUDUSD",
                            "EURGBP",
                            "EURUSD",
                            "GBPUSD",
                            "USDCAD",
                            "USDCHF",
                        ],
                        "top_symbol": {
                            "symbol": "AUDUSD",
                            "strategy": "opportunity_probe",
                        },
                    }
                ]
            },
            {
                "top_candidates": [
                    {
                        "source_path": (
                            "outputs/backtests/"
                            "live_watch_live6_probe_candidate_maps_w480_summary.csv"
                        ),
                        "source_label": (
                            "live_watch_live6_probe_candidate_maps_w480_summary"
                        ),
                        "label": "recent_aud_eur_probe_map",
                        "symbols": "AUDUSD EURGBP EURUSD GBPUSD USDCAD USDCHF",
                        "promotion_status": "REJECT",
                        "promotion_live_ready": "False",
                        "wf_non_negative_fold_fraction": "0.1111",
                        "wf_active_positive_fold_fraction": "0.1111",
                        "wf_total_evaluation_fills": "1945",
                    },
                    {
                        "source_path": (
                            "outputs/backtests/"
                            "live_watch_opportunity_probe_audusd_eurgbp_current_w960.csv"
                        ),
                        "source_label": (
                            "live_watch_opportunity_probe_audusd_eurgbp_current_w960"
                        ),
                        "label": "aud_eurgbp_fast",
                        "symbols": "AUDUSD EURGBP",
                        "promotion_status": "REJECT",
                        "promotion_live_ready": "False",
                        "wf_non_negative_fold_fraction": "0.2000",
                        "wf_active_positive_fold_fraction": "0.2000",
                        "wf_total_evaluation_fills": "144",
                    },
                ]
            },
        )

        top = evidence["top_candidates"][0]
        self.assertEqual(top["symbols"], ["AUDUSD", "EURGBP"])
        self.assertEqual(
            top["top_match"]["source_label"],
            "live_watch_opportunity_probe_audusd_eurgbp_current_w960",
        )

    def test_candidate_optimizer_evidence_skips_inactive_top_symbol(self) -> None:
        evidence = live_status_summary._candidate_optimizer_evidence(
            {
                "top_candidates": [
                    {
                        "label": "candidate_all_opportunity_probe",
                        "actionable_symbols": [],
                        "requested_symbols": [],
                        "top_symbol": {
                            "symbol": "AUDUSD",
                            "status": "strategy_no_change",
                            "strategy": "opportunity_probe",
                            "raw_change_notional_usd": 0.0,
                            "allocation_change_notional_usd": 0.0,
                        },
                    }
                ]
            },
            {
                "top_candidates": [
                    {
                        "source_path": (
                            "outputs/backtests/"
                            "live_watch_opportunity_probe_audusd_usdjpy_w480.csv"
                        ),
                        "source_label": (
                            "live_watch_opportunity_probe_audusd_usdjpy_w480"
                        ),
                        "label": "aud_jpy_score5",
                        "symbols": "AUDUSD USDJPY",
                        "promotion_status": "REJECT",
                        "promotion_live_ready": "False",
                        "wf_non_negative_fold_fraction": "0.5000",
                        "wf_active_positive_fold_fraction": "0.4700",
                        "wf_total_evaluation_fills": "68",
                    }
                ]
            },
        )

        self.assertEqual(evidence, {})

    def test_candidate_optimizer_evidence_preserves_diagnostic_order(self) -> None:
        evidence = live_status_summary._candidate_optimizer_evidence(
            {
                "top_candidates": [
                    {
                        "label": "candidate_all_opportunity_probe",
                        "actionable_symbols": ["AUDUSD", "EURGBP"],
                        "top_symbol": {
                            "symbol": "AUDUSD",
                            "strategy": "opportunity_probe",
                        },
                    },
                    {
                        "label": "candidate_all_multi_horizon",
                        "actionable_symbols": ["USDCHF"],
                        "top_symbol": {
                            "symbol": "USDCHF",
                            "strategy": "multi_horizon_momentum",
                        },
                    },
                ]
            },
            {
                "top_candidates": [
                    {
                        "source_path": (
                            "outputs/backtests/"
                            "live_watch_late_usd_multi_horizon_w480.csv"
                        ),
                        "source_label": "live_watch_late_usd_multi_horizon_w480",
                        "label": "multi_horizon_momentum",
                        "symbols": "USDCHF",
                        "promotion_status": "REJECT",
                        "promotion_live_ready": "False",
                        "wf_non_negative_fold_fraction": "0.1111",
                        "wf_active_positive_fold_fraction": "0.1111",
                        "wf_total_evaluation_fills": "76",
                    },
                    {
                        "source_path": (
                            "outputs/backtests/"
                            "live_watch_opportunity_probe_audusd_eurgbp_current_w960.csv"
                        ),
                        "source_label": (
                            "live_watch_opportunity_probe_audusd_eurgbp_current_w960"
                        ),
                        "label": "current_live",
                        "symbols": "AUDUSD EURGBP",
                        "promotion_status": "PAPER_ONLY",
                        "promotion_live_ready": "False",
                        "wf_non_negative_fold_fraction": "0.2000",
                        "wf_active_positive_fold_fraction": "0.2000",
                        "wf_total_evaluation_fills": "144",
                    },
                ]
            },
        )

        self.assertEqual(evidence["candidate_count"], 2)
        self.assertEqual(
            evidence["top_candidates"][0]["candidate_label"],
            "candidate_all_opportunity_probe",
        )
        self.assertEqual(
            evidence["top_candidates"][0]["evidence_status"],
            "PAPER_ONLY_SCAN",
        )

    def test_fixed_warmup_summary_rows_are_normalized_for_evidence(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            scan = root / "live_watch_multi_horizon_aud_gbp_w480_summary.csv"
            scan.write_text(
                "\n".join(
                    [
                        (
                            "strategy,symbols,promotion_status,"
                            "promotion_live_ready,promotion_reason,"
                            "non_negative_fold_fraction,"
                            "active_positive_fold_fraction,"
                            "total_evaluation_fills"
                        ),
                        (
                            "multi_horizon_momentum,AUDUSD GBPUSD,REJECT,"
                            "False,non-negative fold fraction 44.4% is below 70.0%,"
                            "0.4444,0.4444,84"
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            scans = live_status_summary.read_optimizer_scans(
                (str(scan),),
                now_utc=live_status_summary.datetime(2026, 1, 1, tzinfo=live_status_summary.UTC),
            )
            evidence = live_status_summary._candidate_optimizer_evidence(
                {
                    "top_candidates": [
                        {
                            "label": "candidate_all_multi_horizon",
                            "actionable_symbols": ["AUDUSD", "GBPUSD"],
                            "top_symbol": {
                                "symbol": "AUDUSD",
                                "strategy": "multi_horizon_momentum",
                                "status": "actionable_allocation",
                                "raw_change_notional_usd": 800000.0,
                            },
                        }
                    ]
                },
                scans,
            )

        top_scan = scans["top_candidates"][0]
        self.assertEqual(top_scan["label"], "multi_horizon_momentum")
        self.assertEqual(top_scan["wf_non_negative_fold_fraction"], "0.4444")
        self.assertEqual(evidence["candidate_count"], 1)
        top = evidence["top_candidates"][0]
        self.assertEqual(top["evidence_status"], "REJECTED_BY_SCAN")
        self.assertEqual(top["symbols"], ["AUDUSD", "GBPUSD"])
        self.assertEqual(
            top["top_match"]["wf_non_negative_fold_fraction"],
            0.4444,
        )
        self.assertEqual(top["top_match"]["wf_total_evaluation_fills"], 84)

    def test_optimizer_scans_rank_all_rows_not_only_first(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            scan = root / "strategy_map_summary.csv"
            scan.write_text(
                "\n".join(
                    [
                        (
                            "rank,label,symbols,promotion_status,"
                            "promotion_live_ready,positive_fold_fraction,"
                            "active_positive_fold_fraction,"
                            "non_negative_fold_fraction,"
                            "median_active_test_return_pct,"
                            "total_evaluation_fills"
                        ),
                        (
                            "1,all_quality,AUDUSD EURUSD,PAPER_ONLY,False,"
                            "0.3333,1.0,1.0,0.0024,22"
                        ),
                        (
                            "2,current_live,AUDUSD EURUSD USDCAD USDCHF,"
                            "PROMOTE,True,0.8333,0.8333,0.8333,0.0018,86"
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            scans = live_status_summary.read_optimizer_scans(
                (str(scan),),
                now_utc=live_status_summary.datetime(
                    2026, 1, 1, tzinfo=live_status_summary.UTC
                ),
            )

        self.assertEqual(scans["scan_count"], 2)
        top = scans["top_candidates"][0]
        self.assertEqual(top["label"], "current_live")
        self.assertEqual(top["promotion_status"], "PROMOTE")
        self.assertEqual(top["source_row_index"], 2)

    def test_optimizer_scans_prefer_fresh_promoted_rows_over_stale_rows(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            stale_scan = root / "stale_promoted.csv"
            fresh_scan = root / "fresh_promoted.csv"
            header = (
                "rank,label,symbols,promotion_status,promotion_live_ready,"
                "active_positive_fold_fraction,non_negative_fold_fraction,"
                "median_active_test_return_pct,total_evaluation_fills"
            )
            stale_scan.write_text(
                "\n".join(
                    [
                        header,
                        "1,stale_better,AUDUSD EURUSD,PROMOTE,True,1.0,1.0,0.0030,44",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            fresh_scan.write_text(
                "\n".join(
                    [
                        header,
                        "1,fresh_current,AUDUSD EURUSD,PROMOTE,True,0.8333,0.8333,0.0018,47",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            now = live_status_summary.datetime(
                2026, 1, 1, 12, 0, tzinfo=live_status_summary.UTC
            )
            stale_epoch = now.timestamp() - (
                live_status_summary.OPTIMIZER_SCAN_STALE_MINUTES + 10
            ) * 60
            fresh_epoch = now.timestamp() - 5 * 60
            os.utime(stale_scan, (stale_epoch, stale_epoch))
            os.utime(fresh_scan, (fresh_epoch, fresh_epoch))

            scans = live_status_summary.read_optimizer_scans(
                (str(stale_scan), str(fresh_scan)),
                now_utc=now,
            )

        top = scans["top_candidates"][0]
        self.assertEqual(top["label"], "fresh_current")
        self.assertFalse(top["source_stale"])
        self.assertTrue(scans["top_candidates"][1]["source_stale"])

    def test_heuristic_evidence_matches_macd_scan_alias(self) -> None:
        evidence = live_status_summary._heuristic_optimizer_evidence(
            {
                "candidate_count": 1,
                "top_candidates": [
                    {
                        "symbol": "AUDUSD",
                        "strategy": "macd_momentum",
                        "action": "eligible_tiny_probe_buy",
                    }
                ],
            },
            {
                "top_candidates": [
                    {
                        "source_path": (
                            "outputs/backtests/"
                            "live_watch_macd_symbol_audusd_w480.csv"
                        ),
                        "source_label": "live_watch_macd_symbol_audusd_w480",
                        "label": "aud_6_18_h075_s000_hold8",
                        "symbols": "AUDUSD",
                        "promotion_status": "REJECT",
                        "promotion_live_ready": "False",
                        "wf_non_negative_fold_fraction": "0.7778",
                        "wf_active_positive_fold_fraction": "0.7143",
                        "wf_total_evaluation_fills": "40",
                    }
                ]
            },
        )

        self.assertEqual(evidence["candidate_count"], 1)
        top = evidence["top_candidates"][0]
        self.assertEqual(top["evidence_status"], "REJECTED_BY_SCAN")
        self.assertEqual(top["symbol"], "AUDUSD")
        self.assertEqual(top["top_match"]["wf_total_evaluation_fills"], 40)

    def test_watchlist_evidence_reports_mixed_cross_rate_windows(self) -> None:
        evidence = live_status_summary._watchlist_optimizer_evidence(
            {
                "candidate_count": 1,
                "top_candidates": [
                    {
                        "symbol": "EURGBP",
                        "candidate_strategy": "cross_rate_reversion",
                        "live_strategy": "champion_ensemble",
                        "live_gate": "strategy_mismatch",
                    },
                    {
                        "symbol": "EURGBP",
                        "candidate_strategy": "cross_rate_reversion",
                        "live_strategy": "champion_ensemble",
                        "live_gate": "strategy_mismatch",
                    }
                ],
            },
            {
                "top_candidates": [
                    {
                        "source_path": (
                            "outputs/backtests/"
                            "live_watch_candidate_eurgbp_cross_rate_w480_summary.csv"
                        ),
                        "source_label": (
                            "live_watch_candidate_eurgbp_cross_rate_w480_summary"
                        ),
                        "label": "cross_w480",
                        "symbols": "AUDUSD EURGBP EURUSD GBPUSD USDCAD USDCHF",
                        "promotion_status": "PAPER_ONLY",
                        "promotion_live_ready": "False",
                        "wf_positive_fold_fraction": "0.5556",
                        "wf_non_negative_fold_fraction": "0.7778",
                        "wf_active_positive_fold_fraction": "0.7143",
                        "wf_total_evaluation_fills": "74",
                    },
                    {
                        "source_path": (
                            "outputs/backtests/"
                            "live_watch_candidate_eurgbp_cross_rate_w960_summary.csv"
                        ),
                        "source_label": (
                            "live_watch_candidate_eurgbp_cross_rate_w960_summary"
                        ),
                        "label": "cross_w960",
                        "symbols": "AUDUSD EURGBP EURUSD GBPUSD USDCAD USDCHF",
                        "promotion_status": "PROMOTE",
                        "promotion_live_ready": "True",
                        "wf_positive_fold_fraction": "0.8333",
                        "wf_non_negative_fold_fraction": "1.0",
                        "wf_active_positive_fold_fraction": "1.0",
                        "wf_total_evaluation_fills": "48",
                    },
                ]
            },
        )

        self.assertEqual(evidence["candidate_count"], 1)
        top = evidence["top_candidates"][0]
        self.assertEqual(top["evidence_status"], "MIXED_SCAN_EVIDENCE")
        self.assertEqual(top["symbol"], "EURGBP")
        self.assertEqual(top["top_match"]["promotion_status"], "PAPER_ONLY")

    def test_research_live_evidence_matches_signal_alias(self) -> None:
        evidence = live_status_summary._research_live_optimizer_evidence(
            {
                "candidate_count": 1,
                "top_candidates": [
                    {
                        "symbol": "GBPUSD",
                        "strategy": "champion_ensemble",
                        "signal": "asset_adaptive_dual_squeeze",
                        "gate": "strategy_no_change",
                    }
                ],
            },
            {
                "top_candidates": [
                    {
                        "source_path": (
                            "outputs/backtests/"
                            "live_watch_gbpusd_asset_squeeze_w480_summary.csv"
                        ),
                        "source_label": "live_watch_gbpusd_asset_squeeze_w480_summary",
                        "label": "all_asset_adaptive_dual_squeeze",
                        "symbols": "GBPUSD",
                        "promotion_status": "PAPER_ONLY",
                        "promotion_live_ready": "False",
                        "source_age_minutes": "900",
                        "wf_positive_fold_fraction": "0.2222",
                        "wf_non_negative_fold_fraction": "1.0",
                        "wf_active_positive_fold_fraction": "1.0",
                        "wf_total_evaluation_fills": "4",
                    },
                    {
                        "source_path": (
                            "outputs/backtests/"
                            "live_watch_asset_squeeze_research_signals_w480_summary.csv"
                        ),
                        "source_label": (
                            "live_watch_asset_squeeze_research_signals_w480_summary"
                        ),
                        "label": "asset_squeeze_research",
                        "symbols": "GBPUSD AUDUSD",
                        "promotion_status": "REJECT",
                        "promotion_live_ready": "False",
                        "source_age_minutes": "10",
                        "wf_positive_fold_fraction": "0.2222",
                        "wf_non_negative_fold_fraction": "0.8333",
                        "wf_active_positive_fold_fraction": "0.5714",
                        "wf_total_evaluation_fills": "18",
                    }
                ]
            },
        )

        self.assertEqual(evidence["candidate_count"], 1)
        top = evidence["top_candidates"][0]
        self.assertEqual(top["evidence_status"], "MIXED_SCAN_EVIDENCE")
        self.assertEqual(top["signal"], "asset_adaptive_dual_squeeze")
        self.assertEqual(top["top_match"]["promotion_status"], "REJECT")
        self.assertEqual(top["top_match"]["wf_total_evaluation_fills"], 18)

    def test_reads_and_writes_summary_files(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            metrics = root / "metrics.csv"
            stdout = root / "stdout.log"
            journal = root / "journal.jsonl"
            pair = root / "pair.json"
            attribution = root / "attribution.json"
            diagnostics = root / "diagnostics.json"
            sentiment = root / "sentiment.json"
            consensus = root / "consensus.csv"
            fixed_consensus = root / "fixed_consensus.csv"
            watchlist = root / "watchlist.json"
            candidate_map_consensus = root / "candidate_map_consensus.csv"
            promoted_candidate_map_consensus = root / "promoted_candidate_map_consensus.csv"
            parameter_consensus = root / "parameter_consensus.csv"
            basket_activity_scan = root / "basket_activity_scan.csv"
            research_cycle = root / "research_cycle.json"
            candidate_diagnostics = (
                root / "candidate_eurgbp_cross_rate_live_strategy_diagnostics_latest.json"
            )
            optimizer_scan = root / "quality_trend_opt.csv"
            near_promotion = root / "near_promotion.json"
            output_json = root / "summary.json"
            output_text = root / "summary.txt"
            history = root / "summary.jsonl"
            _write_metrics(metrics)
            stdout.write_text(
                "[live-trade] iteration=9 timestamp=2026-01-01T00:09:00+00:00 records=0 statuses=no_order\n",
                encoding="utf-8",
            )
            journal.write_text(
                json.dumps(
                    {
                        "created_at_utc": "2026-01-01T00:01:00+00:00",
                        "status": "MT5_FILLED",
                        "request": {"symbol": "EURUSD", "side": "BUY"},
                        "account": {"equity": 999999.0},
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            pair.write_text(
                json.dumps(
                    {
                        "pairs": {
                            "AUDUSD": {
                                "action": "eligible_tiny_probe_sell",
                                "combined_score": -1.9,
                                "technical_score": -2.2,
                            },
                            "EURUSD": {
                                "action": "cooldown_realized_drag",
                                "combined_score": -2.0,
                                "technical_score": -1.5,
                            },
                            "GBPUSD": {
                                "action": "eligible_small_probe_buy",
                                "combined_score": 1.8,
                                "technical_score": 2.1,
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            attribution.write_text(
                json.dumps(
                    {
                        "symbols": {
                            "EURUSD": {
                                "state": "cooldown_realized_drag",
                                "net_pnl": -12.0,
                                "estimated_state_clear_utc": (
                                    "2026-01-01T02:00:00+00:00"
                                ),
                                "estimated_state_after_clear": "working",
                            },
                            "GBPUSD": {
                                "state": "small_only_until_recovery",
                                "net_pnl": -4.0,
                                "estimated_state_clear_utc": (
                                    "2026-01-01T01:00:00+00:00"
                                ),
                                "estimated_state_after_clear": "working",
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            diagnostics.write_text(
                json.dumps(
                    {
                        "allocation": {"status": "OK"},
                        "symbols": {
                            "AUDUSD": {
                                "status": "strategy_no_change",
                                "raw_reason_bucket": "threshold_gated",
                                "raw_reason": "live strategy flat",
                                "raw_change_notional_usd": 0,
                                "allocation_change_notional_usd": 0,
                            },
                            "EURUSD": {
                                "status": "strategy_no_change",
                                "raw_reason_bucket": "threshold_gated",
                                "raw_reason": "below threshold",
                            },
                            "GBPUSD": {
                                "status": "strategy_no_change",
                                "raw_reason_bucket": "threshold_gated",
                                "raw_reason": "live strategy flat",
                                "raw_change_notional_usd": 0,
                                "allocation_change_notional_usd": 0,
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            sentiment.write_text(
                json.dumps(
                    {
                        "pairs": {
                            "AUDUSD": {"score": 0.5},
                            "EURUSD": {"score": 0.0},
                            "GBPUSD": {"score": -1.25},
                        }
                    }
                ),
                encoding="utf-8",
            )
            consensus.write_text(
                "\n".join(
                    [
                        "consensus_status,statuses,min_positive_fold_fraction,min_active_positive_fold_fraction",
                        "REJECT,REJECT|PAPER_ONLY,0.25,0.50",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            fixed_consensus.write_text(
                "\n".join(
                    [
                        (
                            "consensus_status,statuses,min_positive_fold_fraction,"
                            "min_active_fold_fraction,candidate_signature"
                        ),
                        (
                            "PAPER_ONLY,PAPER_ONLY|PAPER_ONLY,0.125,0.125,"
                            "strategy=quality_trend symbols=AUDUSD EURUSD"
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            watchlist.write_text(
                json.dumps(
                    {
                        "timestamp_utc": "2026-01-01T00:04:30+00:00",
                        "candidates": [
                            {
                                "symbol": "EURGBP",
                                "label": "cross_rate_edge",
                                "source_path": (
                                    "outputs/backtests/"
                                    "live_watch_cross_rate_live6_h4_strict.csv"
                                ),
                                "candidate_strategy": "cross_rate_reversion",
                                "live_strategy": "champion_ensemble",
                                "strategy_aligned": False,
                                "live_gate": "blocked_fresh_risk",
                                "deal_state": "cooldown_realized_drag",
                                "estimated_state_clear_utc": (
                                    "2026-01-01T02:00:00+00:00"
                                ),
                                "quality_score": 1.47,
                                "hit_rate": 0.75,
                                "average_edge_after_cost_bps": 0.41,
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            candidate_map_consensus.write_text(
                "\n".join(
                    [
                        (
                            "consensus_status,statuses,min_positive_fold_fraction,"
                            "min_active_positive_fold_fraction,total_evaluation_fills,"
                            "candidate_signature"
                        ),
                        (
                            "PAPER_ONLY,PAPER_ONLY|PAPER_ONLY|PROMOTE,0.5556,"
                            "0.7143,182,map=paper"
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            promoted_candidate_map_consensus.write_text(
                "\n".join(
                    [
                        (
                            "consensus_status,statuses,min_positive_fold_fraction,"
                            "min_active_positive_fold_fraction,total_evaluation_fills,"
                            "candidate_signature"
                        ),
                        "PROMOTE,PROMOTE|PROMOTE|PROMOTE,0.9000,1.0000,44,map=promote",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            parameter_consensus.write_text(
                "\n".join(
                    [
                        (
                            "label,consensus_status,statuses,"
                            "min_wf_positive_fold_fraction,"
                            "min_wf_active_positive_fold_fraction"
                        ),
                        "live_current,REJECT,REJECT|PAPER_ONLY|PAPER_ONLY,0.5556,0.6250",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            basket_activity_scan.write_text(
                "\n".join(
                    [
                        (
                            "rank,basket,strategy,symbols,asset_mix,proxy_score,"
                            "activity_status,official_return_pct,"
                            "official_max_drawdown_pct,fills"
                        ),
                        (
                            "1,current_live,macd_momentum,"
                            "AUDUSD EURUSD,FOREX=2,0.0,UNDERACTIVE,0.0,0.0,0"
                        ),
                        (
                            "2,probe_fx,champion_ensemble,"
                            "EURUSD GBPUSD,FOREX=2,50.0,ACTIVE,0.01,0.001,4"
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            research_cycle.write_text(
                json.dumps(
                    {
                        "timestamp_utc": "2026-01-01T00:04:45+00:00",
                        "basket_scan": {
                            "active_count": 0,
                            "underactive_count": 2,
                        },
                        "signal_diagnostics": {
                            "qualified_count": 1,
                            "qualified_rows": [
                                {
                                    "strategy": "champion_ensemble",
                                    "symbol": "GBPUSD",
                                    "signal": "asset_adaptive_dual_squeeze",
                                    "active_count": 4,
                                    "hit_rate": 0.75,
                                    "average_signed_forward_return_bps": 6.5,
                                    "average_edge_after_cost_bps": 3.2,
                                }
                            ],
                        },
                    }
                ),
                encoding="utf-8",
            )
            candidate_diagnostics.write_text(
                json.dumps(
                    {
                        "timestamp_utc": "2026-01-01T00:04:50+00:00",
                        "allocation": {
                            "status": "OK",
                            "requested_gross_notional_usd": 0.0,
                            "adjusted_gross_notional_usd": 0.0,
                        },
                        "symbols": {
                            "AUDUSD": {
                                "status": "strategy_no_change",
                                "strategy": "macd_momentum",
                                "raw_reason_bucket": "threshold_gated",
                                "raw_change_notional_usd": 0.0,
                                "throttle_change_notional_usd": 0.0,
                                "allocation_change_notional_usd": 0.0,
                            },
                            "EURGBP": {
                                "status": "strategy_no_change",
                                "strategy": "cross_rate_reversion",
                                "raw_reason_bucket": "threshold_gated",
                                "raw_change_notional_usd": 0.0,
                                "throttle_change_notional_usd": 0.0,
                                "allocation_change_notional_usd": 0.0,
                            },
                        },
                    }
                ),
                encoding="utf-8",
            )
            optimizer_scan.write_text(
                "\n".join(
                    [
                        (
                            "rank,label,symbols,promotion_status,"
                            "promotion_live_ready,promotion_reason,return_pct,"
                            "max_drawdown_pct,wf_positive_fold_fraction,"
                            "wf_active_fold_fraction,"
                            "wf_active_positive_fold_fraction,"
                            "wf_non_negative_fold_fraction,"
                            "wf_median_active_test_return_pct,"
                            "wf_worst_test_drawdown_pct,"
                            "wf_total_evaluation_fills"
                        ),
                        (
                            "1,micro_current,AUDUSD EURUSD,REJECT,False,"
                            "average risk discipline 93.3/100 is below 95.0/100,"
                            "0.00031,0.00028,0.3333,0.4444,0.7500,"
                            "0.8889,0.000051,0.00014,28"
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            near_promotion.write_text(
                json.dumps(
                    {
                        "scan_count": 1,
                        "top_candidates": [
                            {
                                "source_path": str(optimizer_scan),
                                "label": "micro_current",
                                "promotion_status": "REJECT",
                                "promotion_gap_score": 0.11,
                                "positive_fold_fraction": 0.3333,
                                "active_positive_fold_fraction": 0.7500,
                                "non_negative_fold_fraction": 0.8889,
                                "median_active_test_return_pct": 0.000051,
                                "evaluation_fills": 28,
                                "failed_gates": ["positive_folds -33.7%"],
                                "promotion_reason": "average risk discipline",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            live_status_summary.main(
                [
                    "--metrics-csv",
                    str(metrics),
                    "--stdout-log",
                    str(stdout),
                    "--orders-journal",
                    str(journal),
                    "--pair-analysis-json",
                    str(pair),
                    "--attribution-json",
                    str(attribution),
                    "--diagnostics-json",
                    str(diagnostics),
                    "--sentiment-json",
                    str(sentiment),
                    "--research-consensus-csv",
                    str(consensus),
                    "--fixed-warmup-consensus-csv",
                    str(fixed_consensus),
                    "--candidate-watchlist-json",
                    str(watchlist),
                    "--candidate-map-consensus-csv",
                    str(candidate_map_consensus),
                    "--candidate-map-consensus-csv",
                    str(promoted_candidate_map_consensus),
                    "--parameter-consensus-csv",
                    str(parameter_consensus),
                    "--basket-activity-scan-csv",
                    str(basket_activity_scan),
                    "--research-cycle-json",
                    str(research_cycle),
                    "--candidate-diagnostics-json",
                    str(candidate_diagnostics),
                    "--optimizer-scan-csv",
                    str(optimizer_scan),
                    "--near-promotion-json",
                    str(near_promotion),
                    "--output-json",
                    str(output_json),
                    "--output-text",
                    str(output_text),
                    "--history-jsonl",
                    str(history),
                ]
            )

            summary = json.loads(output_json.read_text(encoding="utf-8"))
            text = output_text.read_text(encoding="utf-8")
            history_text = history.read_text(encoding="utf-8")

        self.assertEqual(summary["live_loop"]["iteration"], 9)
        self.assertEqual(summary["latest_order"]["symbol"], "EURUSD")
        self.assertEqual(summary["heuristic_only_probes"]["candidate_count"], 2)
        self.assertEqual(
            summary["heuristic_only_probes"]["top_candidates"][0]["symbol"],
            "AUDUSD",
        )
        self.assertIn("status=FLAT_FRESH_RISK_BLOCKED", text)
        self.assertIn("reentry_queue candidates=2 next=GBPUSD", text)
        self.assertIn("heuristic_only_probes candidates=2 top=AUDUSD", text)
        self.assertIn("gate=strategy_no_change state=", text)
        self.assertIn("after=working clear=2026-01-01T01:00:00+00:00", text)
        self.assertIn("research consensus=REJECT", text)
        self.assertIn("fixed_warmup consensus=PAPER_ONLY", text)
        self.assertIn("watchlist candidates=1 top=EURGBP", text)
        self.assertIn("source=live_watch_cross_rate_live6_h4_strict.csv", text)
        self.assertIn("gate=blocked_fresh_risk", text)
        self.assertIn("strategy=cross_rate_reversion live=champion_ensemble", text)
        self.assertEqual(
            summary["candidate_strategy_diagnostics"]["top_candidates"][0][
                "top_symbol"
            ]["symbol"],
            "EURGBP",
        )
        self.assertIn("candidate_diagnostics candidates=1", text)
        self.assertIn("alloc_status=OK", text)
        self.assertIn("focus=EURGBP", text)
        self.assertIn("strategy=cross_rate_reversion raw=0.00 alloc=0.00", text)
        self.assertEqual(summary["optimizer_scans"]["scan_count"], 1)
        self.assertEqual(
            summary["optimizer_scans"]["top_candidates"][0]["label"],
            "micro_current",
        )
        self.assertIn(
            "source_mtime_utc",
            summary["optimizer_scans"]["top_candidates"][0],
        )
        self.assertGreaterEqual(
            summary["optimizer_scans"]["top_candidates"][0]["source_age_minutes"],
            0.0,
        )
        self.assertFalse(
            summary["optimizer_scans"]["top_candidates"][0]["source_stale"]
        )
        self.assertIn("optimizer_scans scans=1 top=micro_current", text)
        self.assertIn("near_promotion candidates=1 top=micro_current", text)
        self.assertIn("blockers=positive_folds -33.7%", text)
        self.assertIn("age=", text)
        self.assertIn("stale=no", text)
        self.assertIn("status=REJECT live_ready=no", text)
        self.assertIn("nonneg=88.9%", text)
        self.assertIn("candidate_maps candidates=2 top_consensus=PROMOTE", text)
        self.assertIn("candidate=map=promote", text)
        self.assertIn("parameters consensus=REJECT top=live_current", text)
        self.assertIn("basket_scan candidates=2 active=1 underactive=1", text)
        self.assertIn("top=current_live/macd_momentum status=UNDERACTIVE", text)
        self.assertIn("research_cycle signals=1 basket_active=0", text)
        self.assertIn(
            "top=champion_ensemble:GBPUSD:asset_adaptive_dual_squeeze",
            text,
        )
        self.assertEqual(
            summary["research_live_gate"]["top_candidates"][0]["gate"],
            "small_only_research_only",
        )
        self.assertIn("research_live_gate candidates=1 top=GBPUSD", text)
        self.assertIn("gate=small_only_research_only", text)
        self.assertIn("diag=strategy_no_change", text)
        self.assertIn("FLAT_FRESH_RISK_BLOCKED", history_text)


def _metrics_row(*, positions_count: str) -> dict[str, str]:
    return {
        "timestamp_utc": "2026-01-01T00:00:00+00:00",
        "equity": "999999.0",
        "balance": "999999.0",
        "floating_pnl": "0.0",
        "day_pnl": "-1.0",
        "drawdown_pct": "0.000001",
        "margin": "0.0",
        "margin_level": "0.0",
        "positions_count": positions_count,
        "gross_lots": "0.0",
        "rolling_sharpe_15": "0.0",
    }


def _write_metrics(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                (
                    "timestamp_utc,equity,balance,floating_pnl,day_pnl,"
                    "drawdown_pct,margin,margin_level,positions_count,"
                    "gross_lots,rolling_sharpe_15"
                ),
                (
                    "2026-01-01T00:00:00+00:00,999999.0,999999.0,0.0,"
                    "-1.0,0.000001,0.0,0.0,0,0.0,0.0"
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
