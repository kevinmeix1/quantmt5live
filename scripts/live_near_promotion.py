from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from datetime import UTC
except ImportError:  # Python < 3.11
    UTC = timezone.utc

try:
    REPO_ROOT = Path(__file__).resolve().parents[1]
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    from scripts.live_status_summary import DEFAULT_OPTIMIZER_SCAN_CSVS
except ImportError:  # pragma: no cover - direct script fallback
    DEFAULT_OPTIMIZER_SCAN_CSVS = ()


POSITIVE_FOLD_TARGET = 0.67
ACTIVE_POSITIVE_FOLD_TARGET = 0.67
NON_NEGATIVE_FOLD_TARGET = 0.70
RISK_DISCIPLINE_TARGET = 95.0
_STRATEGY_ASSIGNMENT_RE = re.compile(
    r"\b([A-Z]{6})\s*=\s*([A-Za-z_][A-Za-z0-9_]*)\b",
    re.IGNORECASE,
)


def build_near_promotion_summary(
    paths: tuple[str, ...],
    *,
    top_n: int = 8,
    min_evaluation_fills: int = 1,
    now_utc: datetime | None = None,
) -> dict[str, Any]:
    now = now_utc or datetime.now(UTC)
    rows: list[dict[str, Any]] = []
    evidence_rows: list[dict[str, Any]] = []
    for scan_path in _iter_scan_paths(paths):
        if not scan_path.exists():
            continue
        mtime = datetime.fromtimestamp(scan_path.stat().st_mtime, UTC)
        age_minutes = max(0.0, (now - mtime).total_seconds() / 60.0)
        with scan_path.open("r", encoding="utf-8", newline="") as handle:
            for row_number, raw_row in enumerate(csv.DictReader(handle), start=1):
                row = _candidate_row(
                    raw_row,
                    source_path=scan_path,
                    source_mtime_utc=mtime,
                    source_age_minutes=age_minutes,
                    source_row_number=row_number,
                )
                if not row:
                    continue
                if row["evaluation_fills"] < min_evaluation_fills:
                    continue
                evidence_rows.append(row)
                if row["promotion_live_ready"]:
                    continue
                rows.append(row)
    superseded_count = _mark_superseded_by_newer_evidence(rows, evidence_rows)
    rows = [row for row in rows if not row.pop("_superseded_by_newer_evidence", False)]
    rows.sort(key=_rank_key)
    return {
        "timestamp_utc": now.isoformat(),
        "scan_count": len(rows),
        "superseded_count": superseded_count,
        "targets": {
            "positive_fold_fraction": POSITIVE_FOLD_TARGET,
            "active_positive_fold_fraction": ACTIVE_POSITIVE_FOLD_TARGET,
            "non_negative_fold_fraction": NON_NEGATIVE_FOLD_TARGET,
            "average_risk_discipline_score": RISK_DISCIPLINE_TARGET,
        },
        "top_candidates": rows[:top_n],
    }


def _iter_scan_paths(paths: tuple[str, ...]) -> list[Path]:
    scan_paths: list[Path] = []
    seen_paths: set[str] = set()

    def add_scan_path(path: Path) -> None:
        key = str(path.resolve()) if path.exists() else str(path)
        if key in seen_paths:
            return
        seen_paths.add(key)
        scan_paths.append(path)

    for raw_path in paths:
        path_text = str(raw_path)
        if any(token in path_text for token in ("*", "?", "[")):
            pattern_path = Path(path_text)
            parent = pattern_path.parent if pattern_path.parent != Path("") else Path(".")
            for scan_path in sorted(parent.glob(pattern_path.name)):
                add_scan_path(scan_path)
            continue
        add_scan_path(Path(path_text))
    return scan_paths


def write_summary_json(summary: dict[str, Any], path: str | Path) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def write_summary_text(summary: dict[str, Any], path: str | Path) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"{summary['timestamp_utc']} near-promotion candidates={summary['scan_count']}"
    ]
    for rank, row in enumerate(summary.get("top_candidates", []), start=1):
        lines.append(
            f"{rank}. {row['label']} source={Path(row['source_path']).name} "
            f"status={row['promotion_status']} gap={row['promotion_gap_score']:.3f} "
            f"pos={row['positive_fold_fraction']:.1%} "
            f"active_pos={row['active_positive_fold_fraction']:.1%} "
            f"nonneg={row['non_negative_fold_fraction']:.1%} "
            f"risk={_format_optional(row['average_risk_discipline_score'])} "
            f"fills={row['evaluation_fills']} "
            f"blockers={';'.join(row['failed_gates']) or 'none'} "
            f"reason={row['promotion_reason']}"
        )
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Rank optimizer scan rows by closeness to live-promotion gates."
    )
    parser.add_argument("--scan-csv", action="append", default=None)
    parser.add_argument("--top-n", type=int, default=8)
    parser.add_argument("--min-evaluation-fills", type=int, default=1)
    parser.add_argument(
        "--output-json",
        default="outputs/backtests/live_watch_near_promotion_latest.json",
    )
    parser.add_argument(
        "--output-text",
        default="outputs/backtests/live_watch_near_promotion_latest.txt",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    paths = tuple(args.scan_csv or DEFAULT_OPTIMIZER_SCAN_CSVS)
    summary = build_near_promotion_summary(
        paths,
        top_n=args.top_n,
        min_evaluation_fills=args.min_evaluation_fills,
    )
    write_summary_json(summary, args.output_json)
    write_summary_text(summary, args.output_text)
    top = summary["top_candidates"][0] if summary["top_candidates"] else {}
    print(
        json.dumps(
            {
                "candidate_count": summary["scan_count"],
                "top_label": top.get("label", ""),
                "top_status": top.get("promotion_status", ""),
                "top_gap": top.get("promotion_gap_score", 0.0),
            },
            sort_keys=True,
        )
    )


def _candidate_row(
    raw_row: dict[str, str],
    *,
    source_path: Path,
    source_mtime_utc: datetime,
    source_age_minutes: float,
    source_row_number: int,
) -> dict[str, Any] | None:
    status = raw_row.get("promotion_status", "").strip()
    if not status:
        return None
    positive = _metric(raw_row, "wf_positive_fold_fraction", "positive_fold_fraction")
    active = _metric(raw_row, "wf_active_fold_fraction", "active_fold_fraction")
    active_positive = _metric(
        raw_row,
        "wf_active_positive_fold_fraction",
        "active_positive_fold_fraction",
    )
    non_negative = _metric(
        raw_row,
        "wf_non_negative_fold_fraction",
        "non_negative_fold_fraction",
    )
    median_active = _metric(
        raw_row,
        "wf_median_active_test_return_pct",
        "median_active_test_return_pct",
    )
    drawdown = _metric(
        raw_row,
        "wf_worst_test_drawdown_pct",
        "worst_test_drawdown_pct",
        "max_worst_test_drawdown_pct",
        "max_drawdown_pct",
    )
    fills = int(
        _metric(
            raw_row,
            "wf_total_evaluation_fills",
            "total_evaluation_fills",
            "fills",
            "trade_count",
        )
    )
    reason = raw_row.get("promotion_reason", "").strip()
    risk = _risk_metric(raw_row, reason)
    failed_gates = _failed_gates(
        positive=positive,
        active_positive=active_positive,
        non_negative=non_negative,
        risk=risk,
    )
    gap_score = _promotion_gap_score(
        positive=positive,
        active_positive=active_positive,
        non_negative=non_negative,
        risk=risk,
    )
    return {
        "source_path": str(source_path),
        "source_label": source_path.stem,
        "source_mtime_utc": source_mtime_utc.isoformat(),
        "source_age_minutes": source_age_minutes,
        "source_row_number": source_row_number,
        "label": _label_for(raw_row, source_path),
        "symbols": raw_row.get("symbols", ""),
        "candidate_signature": _candidate_signature(raw_row),
        "promotion_status": status,
        "promotion_live_ready": _boolish(raw_row.get("promotion_live_ready")),
        "promotion_reason": reason,
        "return_pct": _metric(raw_row, "return_pct"),
        "max_drawdown_pct": _metric(raw_row, "max_drawdown_pct"),
        "positive_fold_fraction": positive,
        "active_fold_fraction": active,
        "active_positive_fold_fraction": active_positive,
        "non_negative_fold_fraction": non_negative,
        "median_active_test_return_pct": median_active,
        "worst_test_drawdown_pct": drawdown,
        "average_risk_discipline_score": risk,
        "evaluation_fills": fills,
        "failed_gates": failed_gates,
        "promotion_gap_score": gap_score,
    }


def _promotion_gap_score(
    *,
    positive: float,
    active_positive: float,
    non_negative: float,
    risk: float | None,
) -> float:
    gap = 0.0
    gap += max(0.0, POSITIVE_FOLD_TARGET - positive) * 2.0
    gap += max(0.0, ACTIVE_POSITIVE_FOLD_TARGET - active_positive) * 1.5
    gap += max(0.0, NON_NEGATIVE_FOLD_TARGET - non_negative) * 1.5
    if risk is not None:
        gap += max(0.0, RISK_DISCIPLINE_TARGET - risk) / 100.0
    return gap


def _failed_gates(
    *,
    positive: float,
    active_positive: float,
    non_negative: float,
    risk: float | None,
) -> list[str]:
    gates: list[str] = []
    if positive < POSITIVE_FOLD_TARGET:
        gates.append(f"positive_folds -{(POSITIVE_FOLD_TARGET - positive):.1%}")
    if active_positive < ACTIVE_POSITIVE_FOLD_TARGET:
        gates.append(
            f"active_positive_folds -{(ACTIVE_POSITIVE_FOLD_TARGET - active_positive):.1%}"
        )
    if non_negative < NON_NEGATIVE_FOLD_TARGET:
        gates.append(f"non_negative_folds -{(NON_NEGATIVE_FOLD_TARGET - non_negative):.1%}")
    if risk is not None and risk < RISK_DISCIPLINE_TARGET:
        gates.append(f"risk_discipline -{(RISK_DISCIPLINE_TARGET - risk):.1f}")
    return gates


def _rank_key(row: dict[str, Any]) -> tuple[int, float, int, float, float, str]:
    status_rank = {"PAPER_ONLY": 0, "REJECT": 1, "UNVALIDATED": 2}
    return (
        status_rank.get(row["promotion_status"], 3),
        row["promotion_gap_score"],
        -row["evaluation_fills"],
        -row["median_active_test_return_pct"],
        row["source_age_minutes"],
        row["label"],
    )


def _mark_superseded_by_newer_evidence(
    rows: list[dict[str, Any]],
    evidence_rows: list[dict[str, Any]],
) -> int:
    newest_mtime_by_candidate: dict[tuple[str, str], str] = {}
    for row in evidence_rows:
        key = _candidate_key(row)
        current = newest_mtime_by_candidate.get(key)
        mtime = row["source_mtime_utc"]
        if current is None or mtime > current:
            newest_mtime_by_candidate[key] = mtime

    superseded_count = 0
    for row in rows:
        newest_mtime = newest_mtime_by_candidate.get(_candidate_key(row))
        if newest_mtime is None:
            continue
        if row["source_mtime_utc"] < newest_mtime:
            row["_superseded_by_newer_evidence"] = True
            superseded_count += 1
    return superseded_count


def _candidate_key(row: dict[str, Any]) -> tuple[str, str]:
    signature = _normalize_candidate_signature(
        row.get("candidate_signature") or row.get("label") or ""
    )
    symbols = _normalize_symbols(str(row.get("symbols") or ""))
    return signature, symbols


def _normalize_candidate_signature(raw_signature: Any) -> str:
    signature = str(raw_signature or "").strip()
    assignments = _strategy_assignments(signature)
    if assignments:
        assignment_text = " ".join(
            f"{symbol}={strategy}" for symbol, strategy in sorted(assignments.items())
        )
        return f"map:{assignment_text}"
    return "raw:" + re.sub(r"\s+", " ", signature).lower()


def _strategy_assignments(raw_signature: str) -> dict[str, str]:
    assignments: dict[str, str] = {}
    for match in _STRATEGY_ASSIGNMENT_RE.finditer(raw_signature):
        assignments[match.group(1).upper()] = match.group(2).lower()
    return assignments


def _normalize_symbols(raw_symbols: str) -> str:
    return " ".join(sorted(token.upper() for token in raw_symbols.split() if token))


def _risk_metric(raw_row: dict[str, str], reason: str) -> float | None:
    value = _metric_or_none(
        raw_row,
        "average_risk_discipline_score",
        "min_average_risk_discipline_score",
    )
    if value is not None:
        return value
    match = re.search(r"average risk discipline\s+([0-9]+(?:\.[0-9]+)?)\s*/\s*100", reason)
    if match:
        return float(match.group(1))
    return None


def _label_for(raw_row: dict[str, str], source_path: Path) -> str:
    for key in ("label", "strategy", "candidate_signature"):
        value = raw_row.get(key, "").strip()
        if value:
            return value
    return source_path.stem


def _candidate_signature(raw_row: dict[str, str]) -> str:
    for key in ("candidate_signature", "strategy_map", "strategy", "label"):
        value = raw_row.get(key, "").strip()
        if value:
            return value
    return ""


def _metric(raw_row: dict[str, str], *keys: str) -> float:
    value = _metric_or_none(raw_row, *keys)
    return 0.0 if value is None else value


def _metric_or_none(raw_row: dict[str, str], *keys: str) -> float | None:
    for key in keys:
        raw_value = raw_row.get(key)
        if raw_value not in (None, ""):
            return _parse_float(raw_value)
    return None


def _parse_float(raw_value: str) -> float:
    cleaned = str(raw_value).strip().replace(",", "")
    if cleaned.endswith("%"):
        return float(cleaned[:-1]) / 100.0
    return float(cleaned)


def _boolish(raw_value: Any) -> bool:
    if isinstance(raw_value, bool):
        return raw_value
    return str(raw_value).strip().lower() in {"1", "true", "yes", "y"}


def _format_optional(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.1f}"


if __name__ == "__main__":
    main()
