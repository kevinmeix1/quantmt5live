from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class FixedWarmupObservation:
    window: str
    strategy: str
    symbols: str
    candidate_signature: str
    promotion_status: str
    promotion_live_ready: bool
    promotion_reason: str
    folds: int
    positive_fold_fraction: float
    active_fold_fraction: float
    active_positive_fold_fraction: float
    non_negative_fold_fraction: float
    median_active_test_return_pct: float
    worst_test_drawdown_pct: float
    average_risk_discipline_score: float
    total_evaluation_fills: int


@dataclass(frozen=True)
class FixedWarmupConsensusRow:
    strategy: str
    symbols: str
    candidate_signature: str
    windows_seen: tuple[str, ...]
    statuses: tuple[str, ...]
    reasons: tuple[str, ...]
    promote_count: int
    paper_only_count: int
    reject_count: int
    consensus_status: str
    all_live_ready: bool
    min_positive_fold_fraction: float
    min_active_fold_fraction: float
    min_active_positive_fold_fraction: float
    min_non_negative_fold_fraction: float
    min_median_active_test_return_pct: float
    max_worst_test_drawdown_pct: float
    min_average_risk_discipline_score: float
    total_evaluation_fills: int

    @property
    def rank_key(self) -> tuple[float, ...]:
        status_score = {"PROMOTE": 2.0, "PAPER_ONLY": 1.0, "REJECT": 0.0}.get(
            self.consensus_status,
            0.0,
        )
        return (
            status_score,
            self.min_positive_fold_fraction,
            self.min_active_positive_fold_fraction,
            self.min_non_negative_fold_fraction,
            self.min_median_active_test_return_pct,
            -self.max_worst_test_drawdown_pct,
        )


def build_consensus(
    observations: list[FixedWarmupObservation],
) -> list[FixedWarmupConsensusRow]:
    grouped: dict[tuple[str, str], list[FixedWarmupObservation]] = {}
    for observation in observations:
        grouped.setdefault(
            (observation.strategy, observation.candidate_signature),
            [],
        ).append(observation)

    rows: list[FixedWarmupConsensusRow] = []
    for (_strategy, _signature), group in grouped.items():
        ordered = sorted(group, key=lambda item: item.window)
        statuses = tuple(item.promotion_status for item in ordered)
        promote_count = statuses.count("PROMOTE")
        paper_only_count = statuses.count("PAPER_ONLY")
        reject_count = statuses.count("REJECT")
        all_live_ready = all(item.promotion_live_ready for item in ordered)
        if all_live_ready and promote_count == len(ordered):
            consensus_status = "PROMOTE"
        elif reject_count:
            consensus_status = "REJECT"
        else:
            consensus_status = "PAPER_ONLY"
        rows.append(
            FixedWarmupConsensusRow(
                strategy=ordered[0].strategy,
                symbols=ordered[0].symbols,
                candidate_signature=ordered[0].candidate_signature,
                windows_seen=tuple(item.window for item in ordered),
                statuses=statuses,
                reasons=tuple(item.promotion_reason for item in ordered),
                promote_count=promote_count,
                paper_only_count=paper_only_count,
                reject_count=reject_count,
                consensus_status=consensus_status,
                all_live_ready=all_live_ready,
                min_positive_fold_fraction=min(
                    item.positive_fold_fraction for item in ordered
                ),
                min_active_fold_fraction=min(
                    item.active_fold_fraction for item in ordered
                ),
                min_active_positive_fold_fraction=min(
                    item.active_positive_fold_fraction for item in ordered
                ),
                min_non_negative_fold_fraction=min(
                    item.non_negative_fold_fraction for item in ordered
                ),
                min_median_active_test_return_pct=min(
                    item.median_active_test_return_pct for item in ordered
                ),
                max_worst_test_drawdown_pct=max(
                    item.worst_test_drawdown_pct for item in ordered
                ),
                min_average_risk_discipline_score=min(
                    item.average_risk_discipline_score for item in ordered
                ),
                total_evaluation_fills=sum(
                    item.total_evaluation_fills for item in ordered
                ),
            )
        )
    return sorted(rows, key=lambda row: row.rank_key, reverse=True)


def read_observations(inputs: list[str]) -> list[FixedWarmupObservation]:
    observations: list[FixedWarmupObservation] = []
    for raw_input in inputs:
        window, path = _parse_input(raw_input)
        row = _read_single_csv_row(path)
        observations.append(_observation_from_row(window=window, row=row))
    return observations


def _observation_from_row(
    *,
    window: str,
    row: dict[str, str],
) -> FixedWarmupObservation:
    strategy = row.get("strategy", "")
    symbols = row.get("symbols", "")
    return FixedWarmupObservation(
        window=window,
        strategy=strategy,
        symbols=symbols,
        candidate_signature=_candidate_signature(strategy=strategy, symbols=symbols),
        promotion_status=row.get("promotion_status", ""),
        promotion_live_ready=_parse_bool(row.get("promotion_live_ready", "")),
        promotion_reason=row.get("promotion_reason", ""),
        folds=int(_parse_float(row.get("folds", ""))),
        positive_fold_fraction=_parse_float(row.get("positive_fold_fraction", "")),
        active_fold_fraction=_parse_float(row.get("active_fold_fraction", "")),
        active_positive_fold_fraction=_parse_float(
            row.get("active_positive_fold_fraction", "")
        ),
        non_negative_fold_fraction=_parse_float(
            row.get("non_negative_fold_fraction", "")
        ),
        median_active_test_return_pct=_parse_float(
            row.get("median_active_test_return_pct", "")
        ),
        worst_test_drawdown_pct=_parse_float(row.get("worst_test_drawdown_pct", "")),
        average_risk_discipline_score=_parse_float(
            row.get("average_risk_discipline_score", "")
        ),
        total_evaluation_fills=int(_parse_float(row.get("total_evaluation_fills", ""))),
    )


def write_consensus_csv(rows: list[FixedWarmupConsensusRow], path: str | Path) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "rank",
                "strategy",
                "symbols",
                "candidate_signature",
                "windows_seen",
                "statuses",
                "promote_count",
                "paper_only_count",
                "reject_count",
                "consensus_status",
                "all_live_ready",
                "min_positive_fold_fraction",
                "min_active_fold_fraction",
                "min_active_positive_fold_fraction",
                "min_non_negative_fold_fraction",
                "min_median_active_test_return_pct",
                "max_worst_test_drawdown_pct",
                "min_average_risk_discipline_score",
                "total_evaluation_fills",
                "reasons",
            ],
        )
        writer.writeheader()
        for rank, row in enumerate(rows, start=1):
            writer.writerow(
                {
                    "rank": rank,
                    "strategy": row.strategy,
                    "symbols": row.symbols,
                    "candidate_signature": row.candidate_signature,
                    "windows_seen": "|".join(row.windows_seen),
                    "statuses": "|".join(row.statuses),
                    "promote_count": row.promote_count,
                    "paper_only_count": row.paper_only_count,
                    "reject_count": row.reject_count,
                    "consensus_status": row.consensus_status,
                    "all_live_ready": row.all_live_ready,
                    "min_positive_fold_fraction": row.min_positive_fold_fraction,
                    "min_active_fold_fraction": row.min_active_fold_fraction,
                    "min_active_positive_fold_fraction": (
                        row.min_active_positive_fold_fraction
                    ),
                    "min_non_negative_fold_fraction": (
                        row.min_non_negative_fold_fraction
                    ),
                    "min_median_active_test_return_pct": (
                        row.min_median_active_test_return_pct
                    ),
                    "max_worst_test_drawdown_pct": row.max_worst_test_drawdown_pct,
                    "min_average_risk_discipline_score": (
                        row.min_average_risk_discipline_score
                    ),
                    "total_evaluation_fills": row.total_evaluation_fills,
                    "reasons": "|".join(row.reasons),
                }
            )


def write_consensus_text(
    rows: list[FixedWarmupConsensusRow],
    path: str | Path,
    *,
    limit: int = 10,
) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["Fixed-warmup promotion consensus"]
    for rank, row in enumerate(rows[:limit], start=1):
        lines.append(
            f"{rank}. {row.strategy}: consensus={row.consensus_status} "
            f"statuses={'|'.join(row.statuses)} "
            f"min_pos={row.min_positive_fold_fraction:.1%} "
            f"min_active={row.min_active_fold_fraction:.1%} "
            f"min_active_pos={row.min_active_positive_fold_fraction:.1%} "
            f"min_nonneg={row.min_non_negative_fold_fraction:.1%} "
            f"max_dd={row.max_worst_test_drawdown_pct:.3%} "
            f"fills={row.total_evaluation_fills} "
            f"candidate={row.candidate_signature}"
        )
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Combine fixed-warmup summary CSVs across validation windows."
    )
    parser.add_argument(
        "--input",
        action="append",
        required=True,
        help="Summary CSV path, optionally prefixed as WINDOW=path.",
    )
    parser.add_argument("--output", required=True)
    parser.add_argument("--text-output", default=None)
    parser.add_argument("--text-limit", type=int, default=10)
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    rows = build_consensus(read_observations(args.input))
    write_consensus_csv(rows, args.output)
    if args.text_output:
        write_consensus_text(rows, args.text_output, limit=args.text_limit)
    print(f"wrote {len(rows)} fixed-warmup consensus rows to {args.output}")


def _read_single_csv_row(path: Path) -> dict[str, str]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != 1:
        raise ValueError(f"{path} must contain exactly one summary row")
    return rows[0]


def _parse_input(raw_input: str) -> tuple[str, Path]:
    if "=" in raw_input:
        window, raw_path = raw_input.split("=", 1)
        return window.strip(), Path(raw_path.strip())
    path = Path(raw_input)
    return path.stem, path


def _candidate_signature(*, strategy: str, symbols: str) -> str:
    return f"strategy={strategy} symbols={symbols}".strip()


def _parse_bool(raw_value: str) -> bool:
    return raw_value.strip().lower() in {"1", "true", "yes"}


def _parse_float(raw_value: str) -> float:
    if raw_value == "":
        return 0.0
    return float(raw_value)


if __name__ == "__main__":
    main()
