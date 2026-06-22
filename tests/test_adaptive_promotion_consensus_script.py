from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from scripts.adaptive_promotion_consensus import (
    build_consensus,
    read_observations,
    write_consensus_csv,
    write_consensus_text,
)


class AdaptivePromotionConsensusScriptTest(TestCase):
    def test_consensus_rejects_if_any_window_rejects(self) -> None:
        observations = [
            _observation("w480", "REJECT", False, 0.28, 0.45, 0.67),
            _observation("w672", "PAPER_ONLY", False, 0.38, 0.67, 0.81),
            _observation("w960", "PAPER_ONLY", False, 0.54, 0.78, 0.85),
        ]

        rows = build_consensus(observations)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].consensus_status, "REJECT")
        self.assertEqual(rows[0].reject_count, 1)
        self.assertEqual(rows[0].min_positive_fold_fraction, 0.28)
        self.assertEqual(rows[0].min_active_positive_fold_fraction, 0.45)
        self.assertEqual(rows[0].min_non_negative_fold_fraction, 0.67)

    def test_reads_summary_and_promotion_audit_files(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            first = root / "adaptive_w480_summary.csv"
            second = root / "adaptive_w960_summary.csv"
            output = root / "consensus.csv"
            text_output = root / "consensus.txt"
            _write_summary(first, "18", "0.28", "0.61", "0.45", "0.67")
            _write_promotion(root / "adaptive_w480_promotion.csv", "REJECT", "no")
            _write_summary(second, "13", "0.54", "0.69", "0.78", "0.85")
            _write_promotion(root / "adaptive_w960_promotion.csv", "PAPER_ONLY", "no")

            rows = build_consensus(
                read_observations([f"w480={first}", f"w960={second}"])
            )
            write_consensus_csv(rows, output)
            write_consensus_text(rows, text_output)
            csv_text = output.read_text(encoding="utf-8")
            text = text_output.read_text(encoding="utf-8")

        self.assertIn("consensus_status", csv_text)
        self.assertIn("candidate_signature", csv_text)
        self.assertIn("REJECT", csv_text)
        self.assertIn("statuses=REJECT|PAPER_ONLY", text)
        self.assertIn("min_pos=28.0%", text)

    def test_infers_status_when_promotion_audit_is_missing(self) -> None:
        with TemporaryDirectory() as tmpdir:
            summary = Path(tmpdir) / "adaptive_w480_summary.csv"
            _write_summary(summary, "18", "0.28", "0.61", "0.45", "0.67")

            rows = build_consensus(read_observations([f"w480={summary}"]))

        self.assertEqual(rows[0].consensus_status, "REJECT")
        self.assertEqual(rows[0].statuses, ("REJECT",))


def _observation(
    window: str,
    status: str,
    live_ready: bool,
    positive: float,
    active_positive: float,
    non_negative: float,
):
    from scripts.adaptive_promotion_consensus import AdaptiveObservation

    return AdaptiveObservation(
        window=window,
        label="adaptive_strategy_selection",
        candidate_signature=(
            "strategies=deployed expanded_lowdd symbols=AUDUSD EURUSD"
        ),
        promotion_status=status,
        promotion_live_ready=live_ready,
        decision_reason=status,
        folds=10,
        positive_fold_fraction=positive,
        active_fold_fraction=0.60,
        active_positive_fold_fraction=active_positive,
        non_negative_fold_fraction=non_negative,
        median_active_test_return_pct=0.001,
        worst_test_drawdown_pct=0.003,
        average_risk_discipline_score=100.0,
        total_evaluation_fills=20,
        selection_counts="deployed=2;expanded_lowdd=8",
    )


def _write_summary(
    path: Path,
    folds: str,
    positive: str,
    active: str,
    active_positive: str,
    non_negative: str,
) -> None:
    path.write_text(
        "\n".join(
            [
                (
                    "strategies,symbols,folds,positive_fold_fraction,"
                    "active_fold_fraction,active_positive_fold_fraction,"
                    "non_negative_fold_fraction,median_active_test_return_pct,"
                    "worst_test_drawdown_pct,average_risk_discipline_score,"
                    "total_evaluation_fills,selection_counts"
                ),
                (
                    "deployed expanded_lowdd,AUDUSD EURUSD,"
                    f"{folds},{positive},{active},{active_positive},"
                    f"{non_negative},0.001,0.003,100.0,20,"
                    "deployed=2;expanded_lowdd=8"
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def _write_promotion(path: Path, status: str, live_ready: str) -> None:
    path.write_text(
        "\n".join(
            [
                "status,live_ready,decision_reason",
                f"{status},{live_ready},{status} reason",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
