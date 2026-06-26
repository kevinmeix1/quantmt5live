from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CandidateObservation:
    window: str
    label: str
    symbols: str
    candidate_signature: str
    strategy_map: str
    promotion_status: str
    promotion_live_ready: bool
    return_pct: float
    max_drawdown_pct: float
    wf_positive_fold_fraction: float
    wf_active_positive_fold_fraction: float
    wf_non_negative_fold_fraction: float


@dataclass(frozen=True)
class ConsensusRow:
    label: str
    symbols: str
    candidate_signature: str
    strategy_map: str
    windows_seen: tuple[str, ...]
    statuses: tuple[str, ...]
    promote_count: int
    paper_only_count: int
    reject_count: int
    consensus_status: str
    all_live_ready: bool
    min_return_pct: float
    max_drawdown_pct: float
    min_wf_positive_fold_fraction: float
    min_wf_active_positive_fold_fraction: float
    min_wf_non_negative_fold_fraction: float

    @property
    def rank_key(self) -> tuple[float, ...]:
        status_score = {
            "PROMOTE": 2.0,
            "PAPER_ONLY": 1.0,
            "UNVALIDATED": 0.5,
            "REJECT": 0.0,
        }.get(
            self.consensus_status,
            0.0,
        )
        return (
            status_score,
            self.min_wf_positive_fold_fraction,
            self.min_wf_active_positive_fold_fraction,
            self.min_wf_non_negative_fold_fraction,
            self.min_return_pct,
            -self.max_drawdown_pct,
        )


def build_consensus(observations: list[CandidateObservation]) -> list[ConsensusRow]:
    grouped: dict[tuple[str, str, str], list[CandidateObservation]] = {}
    for observation in observations:
        grouped.setdefault(
            (observation.label, observation.symbols, observation.candidate_signature),
            [],
        ).append(observation)

    rows: list[ConsensusRow] = []
    for (label, symbols, candidate_signature), group in grouped.items():
        ordered = sorted(group, key=lambda item: item.window)
        strategy_map = ordered[0].strategy_map
        statuses = tuple(item.promotion_status for item in ordered)
        promote_count = statuses.count("PROMOTE")
        paper_only_count = statuses.count("PAPER_ONLY")
        reject_count = statuses.count("REJECT")
        unvalidated_count = statuses.count("UNVALIDATED")
        all_live_ready = all(item.promotion_live_ready for item in ordered)
        if all_live_ready and promote_count == len(ordered):
            consensus_status = "PROMOTE"
        elif reject_count:
            consensus_status = "REJECT"
        elif unvalidated_count:
            consensus_status = "UNVALIDATED"
        else:
            consensus_status = "PAPER_ONLY"
        rows.append(
            ConsensusRow(
                label=label,
                symbols=symbols,
                candidate_signature=candidate_signature,
                strategy_map=strategy_map,
                windows_seen=tuple(item.window for item in ordered),
                statuses=statuses,
                promote_count=promote_count,
                paper_only_count=paper_only_count,
                reject_count=reject_count,
                consensus_status=consensus_status,
                all_live_ready=all_live_ready,
                min_return_pct=min(item.return_pct for item in ordered),
                max_drawdown_pct=max(item.max_drawdown_pct for item in ordered),
                min_wf_positive_fold_fraction=min(
                    item.wf_positive_fold_fraction for item in ordered
                ),
                min_wf_active_positive_fold_fraction=min(
                    item.wf_active_positive_fold_fraction for item in ordered
                ),
                min_wf_non_negative_fold_fraction=min(
                    item.wf_non_negative_fold_fraction for item in ordered
                ),
            )
        )
    return sorted(rows, key=lambda row: row.rank_key, reverse=True)


def read_observations(inputs: list[str]) -> list[CandidateObservation]:
    observations: list[CandidateObservation] = []
    for raw_input in inputs:
        window, path = _parse_input(raw_input)
        with path.open("r", encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                observations.append(_observation_from_row(window=window, row=row))
    return observations


def _observation_from_row(
    *,
    window: str,
    row: dict[str, str],
) -> CandidateObservation:
    label = row.get("label", "")
    strategy_map = row.get("strategy_map", "")
    return CandidateObservation(
        window=window,
        label=label,
        symbols=_normalize_symbols(row.get("symbols", "")),
        candidate_signature=_candidate_signature(row),
        strategy_map=strategy_map,
        promotion_status=row.get("promotion_status", "") or "UNVALIDATED",
        promotion_live_ready=_parse_bool(row.get("promotion_live_ready", "")),
        return_pct=_parse_float(row.get("return_pct", "")),
        max_drawdown_pct=_parse_float(row.get("max_drawdown_pct", "")),
        wf_positive_fold_fraction=_parse_float(
            row.get("wf_positive_fold_fraction", "")
        ),
        wf_active_positive_fold_fraction=_parse_float(
            row.get("wf_active_positive_fold_fraction", "")
        ),
        wf_non_negative_fold_fraction=_parse_float(
            row.get("wf_non_negative_fold_fraction", "")
        ),
    )


def write_consensus_csv(rows: list[ConsensusRow], path: str | Path) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "rank",
                "label",
                "symbols",
                "candidate_signature",
                "strategy_map",
                "windows_seen",
                "statuses",
                "promote_count",
                "paper_only_count",
                "reject_count",
                "consensus_status",
                "all_live_ready",
                "min_return_pct",
                "max_drawdown_pct",
                "min_wf_positive_fold_fraction",
                "min_wf_active_positive_fold_fraction",
                "min_wf_non_negative_fold_fraction",
            ],
        )
        writer.writeheader()
        for rank, row in enumerate(rows, start=1):
            writer.writerow(
                {
                    "rank": rank,
                    "label": row.label,
                    "symbols": row.symbols,
                    "candidate_signature": row.candidate_signature,
                    "strategy_map": row.strategy_map,
                    "windows_seen": "|".join(row.windows_seen),
                    "statuses": "|".join(row.statuses),
                    "promote_count": row.promote_count,
                    "paper_only_count": row.paper_only_count,
                    "reject_count": row.reject_count,
                    "consensus_status": row.consensus_status,
                    "all_live_ready": row.all_live_ready,
                    "min_return_pct": row.min_return_pct,
                    "max_drawdown_pct": row.max_drawdown_pct,
                    "min_wf_positive_fold_fraction": (
                        row.min_wf_positive_fold_fraction
                    ),
                    "min_wf_active_positive_fold_fraction": (
                        row.min_wf_active_positive_fold_fraction
                    ),
                    "min_wf_non_negative_fold_fraction": (
                        row.min_wf_non_negative_fold_fraction
                    ),
                }
            )


def write_consensus_text(
    rows: list[ConsensusRow],
    path: str | Path,
    *,
    limit: int = 10,
) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["Promotion consensus"]
    for rank, row in enumerate(rows[:limit], start=1):
        symbols = f"symbols={row.symbols} " if row.symbols else ""
        lines.append(
            f"{rank}. {row.label}: consensus={row.consensus_status} "
            f"statuses={'|'.join(row.statuses)} "
            f"{symbols}"
            f"min_pos={row.min_wf_positive_fold_fraction:.1%} "
            f"min_active_pos={row.min_wf_active_positive_fold_fraction:.1%} "
            f"min_nonneg={row.min_wf_non_negative_fold_fraction:.1%} "
            f"candidate={row.candidate_signature}"
        )
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Combine optimizer promotion CSVs across walk-forward windows."
    )
    parser.add_argument(
        "--input",
        action="append",
        required=True,
        help="CSV path, optionally prefixed as WINDOW=path.",
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
    print(f"wrote {len(rows)} consensus rows to {args.output}")


def _parse_input(raw_input: str) -> tuple[str, Path]:
    if "=" in raw_input:
        window, raw_path = raw_input.split("=", 1)
        return window.strip(), Path(raw_path.strip())
    path = Path(raw_input)
    return path.stem, path


def _candidate_signature(row: dict[str, str]) -> str:
    strategy_map = row.get("strategy_map", "")
    if strategy_map:
        return strategy_map

    label = row.get("label", "")
    parameter_keys = (
        "fast_window",
        "slow_window",
        "signal_window",
        "fast_lookback",
        "medium_lookback",
        "slow_lookback",
        "lookback",
        "squeeze_window",
        "max_squeeze_ratio",
        "breakout_buffer_bps",
        "band_stdev_multiplier",
        "min_prior_volatility_bps",
        "min_band_width_bps",
        "volatility_lookback",
        "baseline_volatility_lookback",
        "kalman_min_abs_slope_bps",
        "kalman_min_expected_edge_bps",
        "macd_min_histogram_bps",
        "macd_min_macd_bps",
        "macd_min_trend_efficiency",
        "min_combined_confidence",
        "min_expected_edge_bps",
        "min_score",
        "exit_score",
        "reverse_score",
        "min_fast_move_bps",
        "min_slow_move_bps",
        "volatility_penalty",
        "threshold_bps",
        "exit_threshold_bps",
        "min_histogram_bps",
        "exit_histogram_bps",
        "min_macd_bps",
        "min_histogram_slope_bps",
        "require_macd_histogram_agreement",
        "slippage_bps",
        "cost_buffer",
        "min_trend_efficiency",
        "min_volatility_ratio",
        "max_volatility_ratio",
        "min_holding_period",
        "max_holding_period",
        "max_spread_bps",
        "target_notional_usd",
        "max_target_notional_usd",
        "allowed_utc_hours",
        "forex_allowed_utc_hours",
        "metal_allowed_utc_hours",
        "crypto_allowed_utc_hours",
        "kalman_trend_weight",
        "asset_adaptive_dual_squeeze_weight",
        "dual_squeeze_weight",
        "trend_pullback_weight",
        "fixing_reversal_weight",
        "macd_momentum_weight",
        "entry_score",
        "strong_lead_score",
        "conflict_penalty",
    )
    parts = [label] if label else []
    for key in parameter_keys:
        value = row.get(key, "")
        if value != "":
            parts.append(f"{key}={value}")
    return " ".join(parts) if parts else label


def _normalize_symbols(raw_symbols: str) -> str:
    return " ".join(
        sorted(
            token.upper()
            for token in raw_symbols.replace(",", " ").replace("|", " ").split()
            if token
        )
    )


def _parse_bool(raw_value: str) -> bool:
    return raw_value.strip().lower() in {"1", "true", "yes"}


def _parse_float(raw_value: str) -> float:
    if not raw_value:
        return 0.0
    return float(raw_value)


if __name__ == "__main__":
    main()
