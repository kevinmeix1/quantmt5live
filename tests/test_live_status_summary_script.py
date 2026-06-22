from __future__ import annotations

import importlib.util
import json
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
