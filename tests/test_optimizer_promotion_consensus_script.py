from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from scripts.optimizer_promotion_consensus import (
    build_consensus,
    read_observations,
    write_consensus_csv,
    write_consensus_text,
)


class OptimizerPromotionConsensusScriptTest(TestCase):
    def test_consensus_requires_all_windows_to_promote(self) -> None:
        observations = [
            _observation("w480", "candidate", "PAPER_ONLY", False, 0.50),
            _observation("w672", "candidate", "PAPER_ONLY", False, 0.62),
            _observation("w960", "candidate", "PROMOTE", True, 0.83),
        ]

        rows = build_consensus(observations)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].consensus_status, "PAPER_ONLY")
        self.assertEqual(rows[0].promote_count, 1)
        self.assertEqual(rows[0].min_wf_positive_fold_fraction, 0.50)

    def test_consensus_rejects_if_any_window_rejects(self) -> None:
        observations = [
            _observation("w480", "candidate", "REJECT", False, 0.40),
            _observation("w672", "candidate", "PROMOTE", True, 0.80),
        ]

        rows = build_consensus(observations)

        self.assertEqual(rows[0].consensus_status, "REJECT")
        self.assertEqual(rows[0].reject_count, 1)

    def test_reads_and_writes_consensus_files(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            first = root / "w480.csv"
            second = root / "w960.csv"
            output = root / "consensus.csv"
            text_output = root / "consensus.txt"
            _write_input_csv(first, "PAPER_ONLY", "False", "0.50")
            _write_input_csv(second, "PROMOTE", "True", "0.80")

            rows = build_consensus(
                read_observations([f"w480={first}", f"w960={second}"])
            )
            write_consensus_csv(rows, output)
            write_consensus_text(rows, text_output)

            csv_text = output.read_text(encoding="utf-8")
            text = text_output.read_text(encoding="utf-8")

        self.assertIn("consensus_status", csv_text)
        self.assertIn("candidate_signature", csv_text)
        self.assertIn("symbols", csv_text)
        self.assertIn("PAPER_ONLY", csv_text)
        self.assertIn("statuses=PAPER_ONLY|PROMOTE", text)
        self.assertIn("symbols=AUDUSD", text)
        self.assertIn("candidate=AUDUSD=macd_momentum", text)

    def test_builds_signature_for_parameter_optimizer_csv(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            first = root / "w480.csv"
            second = root / "w960.csv"
            _write_input_csv(first, "PAPER_ONLY", "False", "0.50", macd=True)
            _write_input_csv(second, "PROMOTE", "True", "0.80", macd=True)

            rows = build_consensus(
                read_observations([f"w480={first}", f"w960={second}"])
            )

        self.assertIn("fast_window=8", rows[0].candidate_signature)
        self.assertIn("min_histogram_bps=1.25", rows[0].candidate_signature)
        self.assertIn("exit_histogram_bps=0.50", rows[0].candidate_signature)
        self.assertIn(
            "require_macd_histogram_agreement=True",
            rows[0].candidate_signature,
        )
        self.assertIn("slippage_bps=1.0", rows[0].candidate_signature)
        self.assertIn("cost_buffer=1.0", rows[0].candidate_signature)
        self.assertEqual(rows[0].symbols, "AUDUSD EURUSD")
        self.assertEqual(rows[0].strategy_map, "")

    def test_builds_signature_for_multi_horizon_optimizer_csv(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            first = root / "w960.csv"
            _write_input_csv(first, "REJECT", "False", "0.31", multi_horizon=True)

            rows = build_consensus(read_observations([f"w960={first}"]))

        self.assertIn("fast_lookback=6", rows[0].candidate_signature)
        self.assertIn("slow_lookback=24", rows[0].candidate_signature)
        self.assertIn("min_fast_move_bps=2.0", rows[0].candidate_signature)
        self.assertIn("allowed_utc_hours=10|11|12|13|14", rows[0].candidate_signature)

    def test_builds_signature_for_opportunity_probe_optimizer_csv(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            first = root / "opportunity.csv"
            first.write_text(
                "\n".join(
                    [
                        (
                            "label,symbols,fast_lookback,medium_lookback,"
                            "slow_lookback,min_score,exit_score,reverse_score,"
                            "min_fast_move_bps,volatility_penalty,"
                            "min_holding_period,max_holding_period,max_spread_bps,"
                            "promotion_status,promotion_live_ready,return_pct,"
                            "max_drawdown_pct,wf_positive_fold_fraction,"
                            "wf_active_positive_fold_fraction,"
                            "wf_non_negative_fold_fraction"
                        ),
                        (
                            "aud_probe,AUDUSD,4,12,32,5.0,0.25,5.5,3.5,"
                            "0.75,32,144,5.0,PAPER_ONLY,False,0.01,0.001,"
                            "0.5,0.6,0.7"
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            rows = build_consensus(read_observations([f"w480={first}"]))

        self.assertIn("medium_lookback=12", rows[0].candidate_signature)
        self.assertIn("min_score=5.0", rows[0].candidate_signature)
        self.assertIn("reverse_score=5.5", rows[0].candidate_signature)
        self.assertIn("volatility_penalty=0.75", rows[0].candidate_signature)
        self.assertIn("min_holding_period=32", rows[0].candidate_signature)
        self.assertIn("max_spread_bps=5.0", rows[0].candidate_signature)

    def test_builds_signature_for_quality_trend_optimizer_csv(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            first = root / "quality.csv"
            first.write_text(
                "\n".join(
                    [
                        (
                            "label,symbols,kalman_min_abs_slope_bps,"
                            "kalman_min_expected_edge_bps,"
                            "macd_min_histogram_bps,macd_min_macd_bps,"
                            "macd_min_trend_efficiency,"
                            "min_combined_confidence,min_expected_edge_bps,"
                            "max_holding_period,allowed_utc_hours,"
                            "target_notional_usd,max_target_notional_usd,"
                            "promotion_status,promotion_live_ready,return_pct,"
                            "max_drawdown_pct,wf_positive_fold_fraction,"
                            "wf_active_positive_fold_fraction,"
                            "wf_non_negative_fold_fraction"
                        ),
                        (
                            "jpy_quality,USDJPY,0.2,4.0,1.25,0.75,"
                            "0.15,0.25,1.25,16,0|1|2,100000,100000,"
                            "PAPER_ONLY,False,0.01,0.001,0.5,0.6,0.7"
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            rows = build_consensus(read_observations([f"w480={first}"]))

        self.assertIn("kalman_min_abs_slope_bps=0.2", rows[0].candidate_signature)
        self.assertIn("kalman_min_expected_edge_bps=4.0", rows[0].candidate_signature)
        self.assertIn("macd_min_histogram_bps=1.25", rows[0].candidate_signature)
        self.assertIn("macd_min_macd_bps=0.75", rows[0].candidate_signature)
        self.assertIn("min_combined_confidence=0.25", rows[0].candidate_signature)
        self.assertIn("target_notional_usd=100000", rows[0].candidate_signature)
        self.assertIn("max_target_notional_usd=100000", rows[0].candidate_signature)

    def test_missing_promotion_status_is_unvalidated(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            first = root / "screen.csv"
            _write_input_csv(first, "", "", "0.0", multi_horizon=True)

            rows = build_consensus(read_observations([f"screen={first}"]))

        self.assertEqual(rows[0].statuses, ("UNVALIDATED",))
        self.assertEqual(rows[0].consensus_status, "UNVALIDATED")

    def test_builds_signature_for_volatility_squeeze_optimizer_csv(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            first = root / "vol_screen.csv"
            _write_input_csv(first, "", "", "0.0", volatility_squeeze=True)

            rows = build_consensus(read_observations([f"screen={first}"]))

        self.assertIn("lookback=24", rows[0].candidate_signature)
        self.assertIn("squeeze_window=8", rows[0].candidate_signature)
        self.assertIn("max_squeeze_ratio=0.6", rows[0].candidate_signature)
        self.assertIn("forex_allowed_utc_hours=7 8 9 10", rows[0].candidate_signature)


def _observation(
    window: str,
    label: str,
    status: str,
    live_ready: bool,
    positive_fraction: float,
):
    from scripts.optimizer_promotion_consensus import CandidateObservation

    return CandidateObservation(
        window=window,
        label=label,
        symbols="AUDUSD",
        candidate_signature="AUDUSD=macd_momentum",
        strategy_map="AUDUSD=macd_momentum",
        promotion_status=status,
        promotion_live_ready=live_ready,
        return_pct=0.01,
        max_drawdown_pct=0.001,
        wf_positive_fold_fraction=positive_fraction,
        wf_active_positive_fold_fraction=0.80,
        wf_non_negative_fold_fraction=0.90,
    )


def _write_input_csv(
    path: Path,
    status: str,
    live_ready: str,
    positive_fraction: str,
    *,
    macd: bool = False,
    multi_horizon: bool = False,
    volatility_squeeze: bool = False,
) -> None:
    header = (
        "label,symbols,strategy_map,promotion_status,promotion_live_ready,"
        "return_pct,max_drawdown_pct,wf_positive_fold_fraction,"
        "wf_active_positive_fold_fraction,wf_non_negative_fold_fraction"
    )
    row = (
        "candidate,AUDUSD,AUDUSD=macd_momentum,"
        f"{status},{live_ready},0.01,0.001,{positive_fraction},0.80,0.90"
    )
    if macd:
        header = (
            "label,symbols,fast_window,slow_window,signal_window,min_histogram_bps,"
            "exit_histogram_bps,min_macd_bps,min_histogram_slope_bps,"
            "require_macd_histogram_agreement,slippage_bps,cost_buffer,"
            "promotion_status,promotion_live_ready,return_pct,"
            "max_drawdown_pct,wf_positive_fold_fraction,"
            "wf_active_positive_fold_fraction,wf_non_negative_fold_fraction"
        )
        row = (
            "candidate,AUDUSD EURUSD,8,21,8,1.25,0.50,0.75,0.0,True,1.0,1.0,"
            f"{status},{live_ready},0.01,0.001,{positive_fraction},0.80,0.90"
        )
    if multi_horizon:
        header = (
            "label,fast_lookback,slow_lookback,volatility_lookback,"
            "baseline_volatility_lookback,min_fast_move_bps,min_slow_move_bps,"
            "min_trend_efficiency,min_volatility_ratio,max_volatility_ratio,"
            "max_holding_period,allowed_utc_hours,promotion_status,"
            "promotion_live_ready,return_pct,max_drawdown_pct,"
            "wf_positive_fold_fraction,wf_active_positive_fold_fraction,"
            "wf_non_negative_fold_fraction"
        )
        row = (
            "current_10_14_live6,6,24,12,48,2.0,5.0,0.25,0.35,2.5,"
            "24,10|11|12|13|14,"
            f"{status},{live_ready},0.01,0.001,{positive_fraction},0.40,0.54"
        )
    if volatility_squeeze:
        header = (
            "label,lookback,squeeze_window,max_squeeze_ratio,"
            "breakout_buffer_bps,band_stdev_multiplier,"
            "min_prior_volatility_bps,min_band_width_bps,max_holding_period,"
            "forex_allowed_utc_hours,promotion_status,promotion_live_ready,"
            "return_pct,max_drawdown_pct,wf_positive_fold_fraction,"
            "wf_active_positive_fold_fraction,wf_non_negative_fold_fraction"
        )
        row = (
            "london_bridge_live6,24,8,0.6,2.0,2.0,0.5,1.0,24,"
            f"7 8 9 10,{status},{live_ready},0.001,0.001,{positive_fraction},0.0,0.0"
        )
    path.write_text(
        "\n".join(
            [
                header,
                row,
            ]
        )
        + "\n",
        encoding="utf-8",
    )
