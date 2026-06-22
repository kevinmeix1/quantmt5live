from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from scripts.fixed_warmup_promotion_consensus import (
    build_consensus,
    read_observations,
    write_consensus_csv,
    write_consensus_text,
)


class FixedWarmupPromotionConsensusScriptTest(TestCase):
    def test_consensus_requires_all_windows_to_promote(self) -> None:
        observations = [
            _observation("w480", "PAPER_ONLY", False, 0.16),
            _observation("w672", "PAPER_ONLY", False, 0.12),
            _observation("w960", "PROMOTE", True, 0.72),
        ]

        rows = build_consensus(observations)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].consensus_status, "PAPER_ONLY")
        self.assertEqual(rows[0].promote_count, 1)
        self.assertEqual(rows[0].paper_only_count, 2)
        self.assertEqual(rows[0].min_positive_fold_fraction, 0.12)

    def test_consensus_rejects_if_any_window_rejects(self) -> None:
        observations = [
            _observation("w480", "PAPER_ONLY", False, 0.60),
            _observation("w672", "REJECT", False, 0.20),
            _observation("w960", "PROMOTE", True, 0.80),
        ]

        rows = build_consensus(observations)

        self.assertEqual(rows[0].consensus_status, "REJECT")
        self.assertEqual(rows[0].reject_count, 1)

    def test_reads_and_writes_consensus_files(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            first = root / "quality_w480_summary.csv"
            second = root / "quality_w960_summary.csv"
            output = root / "consensus.csv"
            text_output = root / "consensus.txt"
            _write_summary(first, "PAPER_ONLY", "False", "0.1666666667")
            _write_summary(second, "PAPER_ONLY", "False", "0.1538461538")

            rows = build_consensus(
                read_observations([f"w480={first}", f"w960={second}"])
            )
            write_consensus_csv(rows, output)
            write_consensus_text(rows, text_output)
            csv_text = output.read_text(encoding="utf-8")
            text = text_output.read_text(encoding="utf-8")

        self.assertIn("consensus_status", csv_text)
        self.assertIn("candidate_signature", csv_text)
        self.assertIn("PAPER_ONLY", csv_text)
        self.assertIn("statuses=PAPER_ONLY|PAPER_ONLY", text)
        self.assertIn("candidate=strategy=quality_trend symbols=AUDUSD EURUSD", text)


def _observation(
    window: str,
    status: str,
    live_ready: bool,
    positive_fraction: float,
):
    from scripts.fixed_warmup_promotion_consensus import FixedWarmupObservation

    return FixedWarmupObservation(
        window=window,
        strategy="quality_trend",
        symbols="AUDUSD EURUSD",
        candidate_signature="strategy=quality_trend symbols=AUDUSD EURUSD",
        promotion_status=status,
        promotion_live_ready=live_ready,
        promotion_reason=f"{status} reason",
        folds=10,
        positive_fold_fraction=positive_fraction,
        active_fold_fraction=positive_fraction,
        active_positive_fold_fraction=1.0,
        non_negative_fold_fraction=1.0,
        median_active_test_return_pct=0.001,
        worst_test_drawdown_pct=0.0015,
        average_risk_discipline_score=100.0,
        total_evaluation_fills=10,
    )


def _write_summary(path: Path, status: str, live_ready: str, positive: str) -> None:
    path.write_text(
        "\n".join(
            [
                (
                    "strategy,symbols,folds,promotion_status,promotion_live_ready,"
                    "promotion_reason,positive_fold_fraction,active_fold_fraction,"
                    "active_positive_fold_fraction,non_negative_fold_fraction,"
                    "median_active_test_return_pct,worst_test_drawdown_pct,"
                    "average_risk_discipline_score,total_evaluation_fills"
                ),
                (
                    "quality_trend,AUDUSD EURUSD,18,"
                    f"{status},{live_ready},{status} reason,{positive},"
                    f"{positive},1.0,1.0,0.001,0.0015,100.0,20"
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
