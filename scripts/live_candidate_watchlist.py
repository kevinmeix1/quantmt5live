from __future__ import annotations

import argparse
import csv
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


BLOCKED_FRESH_RISK_STATES = {
    "cooldown_realized_drag",
    "observe",
    "keep_if_signal_aligned",
}
SMALL_ONLY_FRESH_RISK_STATES = {
    "small_only_until_recovery",
}


def build_watchlist(
    *,
    candidate_rows: list[dict[str, str]],
    attribution: dict[str, Any],
    pair_analysis: dict[str, Any],
    sentiment: dict[str, Any],
    candidate_strategy: str = "",
    default_live_strategy: str = "",
    live_strategy_by_symbol: dict[str, str] | None = None,
    min_quality_score: float = 0.0,
    eligible_only: bool = True,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    generated_at = generated_at_utc or datetime.now(UTC).isoformat()
    attribution_by_symbol = attribution.get("symbols", {})
    pair_by_symbol = pair_analysis.get("pairs", {})
    sentiment_by_symbol = sentiment.get("pairs", {})
    live_strategy_map = live_strategy_by_symbol or {}
    rows: list[dict[str, Any]] = []
    for candidate in candidate_rows:
        if eligible_only and not _parse_bool(candidate.get("eligible", "")):
            continue
        quality_score = _float_or_zero(candidate.get("quality_score"))
        if quality_score < min_quality_score:
            continue
        symbol = candidate.get("symbol", "")
        deal = attribution_by_symbol.get(symbol, {})
        pair = pair_by_symbol.get(symbol, {})
        sent = sentiment_by_symbol.get(symbol, {})
        deal_state = deal.get("state", "")
        blocked = deal_state in BLOCKED_FRESH_RISK_STATES
        small_only = deal_state in SMALL_ONLY_FRESH_RISK_STATES
        row_candidate_strategy = (
            candidate.get("strategy_name", "").strip()
            or candidate_strategy.strip()
        )
        live_strategy = live_strategy_map.get(symbol, default_live_strategy).strip()
        strategy_aligned = (
            not row_candidate_strategy
            or not live_strategy
            or row_candidate_strategy == live_strategy
        )
        live_gate = "blocked_fresh_risk" if blocked else "watch"
        if not blocked and small_only:
            live_gate = "small_only"
        if live_gate == "watch" and not strategy_aligned:
            live_gate = "strategy_mismatch"
        rows.append(
            {
                "symbol": symbol,
                "label": candidate.get("label", ""),
                "source_path": candidate.get("_source_path", ""),
                "candidate_strategy": row_candidate_strategy,
                "live_strategy": live_strategy,
                "strategy_aligned": strategy_aligned,
                "eligible": _parse_bool(candidate.get("eligible", "")),
                "live_gate": live_gate,
                "deal_state": deal_state,
                "estimated_state_clear_utc": deal.get("estimated_state_clear_utc", ""),
                "estimated_state_after_clear": deal.get(
                    "estimated_state_after_clear",
                    "",
                ),
                "realized_net_pnl": _float_or_zero(deal.get("net_pnl")),
                "quality_score": quality_score,
                "active_count": int(_float_or_zero(candidate.get("active_count"))),
                "hit_rate": _float_or_zero(candidate.get("hit_rate")),
                "average_signed_forward_return_bps": _float_or_zero(
                    candidate.get("average_signed_forward_return_bps")
                ),
                "average_edge_after_cost_bps": _float_or_zero(
                    candidate.get("average_edge_after_cost_bps")
                ),
                "pair_action": pair.get("action", ""),
                "pair_score": _float_or_zero(pair.get("combined_score")),
                "sentiment_score": _float_or_zero(sent.get("score")),
            }
        )
    rows.sort(
        key=lambda row: (
            _gate_rank(row["live_gate"]),
            -row["quality_score"],
            -row["hit_rate"],
            row["symbol"],
        )
    )
    return {
        "timestamp_utc": generated_at,
        "eligible_only": eligible_only,
        "min_quality_score": min_quality_score,
        "candidate_strategy": candidate_strategy,
        "default_live_strategy": default_live_strategy,
        "live_strategy_by_symbol": live_strategy_map,
        "blocked_fresh_risk_states": sorted(BLOCKED_FRESH_RISK_STATES),
        "small_only_fresh_risk_states": sorted(SMALL_ONLY_FRESH_RISK_STATES),
        "candidates": rows,
    }


def write_watchlist_json(watchlist: dict[str, Any], path: str | Path) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(watchlist, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def write_watchlist_text(watchlist: dict[str, Any], path: str | Path) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"{watchlist['timestamp_utc']} high-conviction watchlist "
        f"candidates={len(watchlist['candidates'])}"
    ]
    for row in watchlist["candidates"]:
        source = f" source={Path(row['source_path']).name}" if row["source_path"] else ""
        lines.append(
            f"{row['symbol']} {row['label']}: gate={row['live_gate']}{source} "
            f"state={row['deal_state'] or 'none'} "
            f"strategy={row['candidate_strategy'] or 'unknown'} "
            f"live={row['live_strategy'] or 'unknown'} "
            f"quality={row['quality_score']:.2f} "
            f"hit={row['hit_rate']:.1%} "
            f"edge={row['average_edge_after_cost_bps']:.2f}bps "
            f"pair_score={row['pair_score']:.2f} "
            f"sentiment={row['sentiment_score']:.2f} "
            f"clear={row['estimated_state_clear_utc'] or 'n/a'}"
        )
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def read_candidate_rows(path: str | Path) -> list[dict[str, str]]:
    with Path(path).open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def read_candidate_files(paths: list[str] | tuple[str, ...]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for path in paths:
        for row in read_candidate_rows(path):
            row = dict(row)
            row["_source_path"] = str(path)
            rows.append(row)
    return rows


def read_json(path: str | Path) -> dict[str, Any]:
    json_path = Path(path)
    if not json_path.exists():
        return {}
    return json.loads(json_path.read_text(encoding="utf-8"))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a live-gated watchlist from optimizer candidates."
    )
    parser.add_argument("--candidates-csv", action="append", required=True)
    parser.add_argument(
        "--attribution-json",
        default="outputs/live_deal_attribution_latest.json",
    )
    parser.add_argument(
        "--pair-analysis-json",
        default="outputs/live_pair_analysis_latest.json",
    )
    parser.add_argument(
        "--sentiment-json",
        default="outputs/fx_sentiment_snapshot.json",
    )
    parser.add_argument(
        "--candidate-strategy",
        default="",
        help="Strategy represented by the candidate CSV when it has no strategy_name column.",
    )
    parser.add_argument(
        "--default-live-strategy",
        default="",
        help="Default live strategy used when a symbol has no live strategy override.",
    )
    parser.add_argument(
        "--live-strategy-map",
        action="append",
        default=None,
        metavar="SYMBOL=STRATEGY",
        help="Live strategy override for a symbol; repeatable.",
    )
    parser.add_argument("--min-quality-score", type=float, default=0.0)
    parser.add_argument("--include-ineligible", action="store_true")
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--output-text", required=True)
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    watchlist = build_watchlist(
        candidate_rows=read_candidate_files(tuple(args.candidates_csv)),
        attribution=read_json(args.attribution_json),
        pair_analysis=read_json(args.pair_analysis_json),
        sentiment=read_json(args.sentiment_json),
        candidate_strategy=args.candidate_strategy,
        default_live_strategy=args.default_live_strategy,
        live_strategy_by_symbol=_parse_strategy_map(args.live_strategy_map or ()),
        min_quality_score=args.min_quality_score,
        eligible_only=not args.include_ineligible,
    )
    write_watchlist_json(watchlist, args.output_json)
    write_watchlist_text(watchlist, args.output_text)
    print(
        f"wrote {len(watchlist['candidates'])} watchlist candidates "
        f"to {args.output_json}"
    )


def _parse_bool(raw_value: str) -> bool:
    return raw_value.strip().lower() in {"1", "true", "yes"}


def _parse_strategy_map(raw_values: list[str] | tuple[str, ...]) -> dict[str, str]:
    strategy_map: dict[str, str] = {}
    for raw_value in raw_values:
        if "=" not in raw_value:
            raise ValueError(f"strategy map entry must be SYMBOL=STRATEGY: {raw_value}")
        symbol, strategy = raw_value.split("=", 1)
        symbol = symbol.strip().upper()
        strategy = strategy.strip()
        if not symbol or not strategy:
            raise ValueError(f"strategy map entry must be SYMBOL=STRATEGY: {raw_value}")
        strategy_map[symbol] = strategy
    return strategy_map


def _gate_rank(live_gate: str) -> int:
    if live_gate == "watch":
        return 0
    if live_gate == "small_only":
        return 1
    if live_gate == "strategy_mismatch":
        return 2
    if live_gate == "blocked_fresh_risk":
        return 3
    return 3


def _float_or_zero(raw_value: Any) -> float:
    if raw_value in (None, ""):
        return 0.0
    return float(raw_value)


if __name__ == "__main__":
    main()
