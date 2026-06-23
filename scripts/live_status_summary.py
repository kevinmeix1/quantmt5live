from __future__ import annotations

import argparse
import csv
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from datetime import UTC
except ImportError:  # Python < 3.11
    UTC = timezone.utc


BLOCKED_FRESH_RISK_STATES = {
    "cooldown_realized_drag",
    "observe",
    "keep_if_signal_aligned",
}
SMALL_ONLY_FRESH_RISK_STATES = {
    "small_only_until_recovery",
}
DEFAULT_CANDIDATE_MAP_CONSENSUS_CSVS = (
    "outputs/backtests/live_watch_current_jpy_quality_consensus.csv",
    "outputs/backtests/live_watch_candidate_eurgbp_cross_rate_consensus.csv",
    "outputs/backtests/live_watch_eurgbp_cross_jpy_quality_consensus.csv",
    "outputs/backtests/live_watch_top4_macd_consensus.csv",
)
DEFAULT_BASKET_ACTIVITY_SCAN_CSV = (
    "outputs/backtests/live_watch_activity_gated_basket_scan.csv"
)
DEFAULT_CANDIDATE_DIAGNOSTICS_JSONS = (
    "outputs/candidate_all_opportunity_probe_live_strategy_diagnostics_latest.json",
    "outputs/candidate_all_multi_horizon_live_strategy_diagnostics_latest.json",
    "outputs/candidate_eurgbp_cross_rate_live_strategy_diagnostics_latest.json",
    "outputs/candidate_current_jpy_quality_live_strategy_diagnostics_latest.json",
    "outputs/candidate_all_quality_trend_live_strategy_diagnostics_latest.json",
    "outputs/candidate_sentiment_no_jpy_live_strategy_diagnostics_latest.json",
    "outputs/candidate_best_symbol_mix_live_strategy_diagnostics_latest.json",
    "outputs/candidate_promoted_best_per_symbol_live_strategy_diagnostics_latest.json",
    "outputs/candidate_expanded_best_per_symbol_live_strategy_diagnostics_latest.json",
    "outputs/candidate_promoted_top4_macd_live_strategy_diagnostics_latest.json",
    "outputs/live_strategy_diagnostics_directional_probe_latest.json",
)
DEFAULT_OPTIMIZER_SCAN_CSVS = (
    "outputs/backtests/live_watch_active_lowdd_maps_default_w480_summary.csv",
    "outputs/backtests/live_watch_active_lowdd_maps_w480_summary.csv",
    "outputs/backtests/live_watch_sentiment_pressure_maps_w480_summary.csv",
    "outputs/backtests/live_watch_macd_threshold_pressure_w480.csv",
    "outputs/backtests/live_watch_macd_near_promotion_refine_w480.csv",
    "outputs/backtests/live_watch_macd_pressure5_refine_w480.csv",
    "outputs/backtests/live_watch_macd_fast_refine4_w480.csv",
    "outputs/backtests/live_watch_macd_fast_refine4_w672.csv",
    "outputs/backtests/live_watch_macd_fast_refine4_w960.csv",
    "outputs/backtests/live_watch_usdjpy_quality_preopen_w480.csv",
    "outputs/backtests/live_watch_usdcad_macd_intraday_w480.csv",
    "outputs/backtests/live_watch_eurgbp_cross_jpy_quality_w480.csv",
    "outputs/backtests/live_watch_eurgbp_cross_jpy_quality_w672.csv",
    "outputs/backtests/live_watch_eurgbp_cross_jpy_quality_w960.csv",
    "outputs/backtests/live_watch_single_eurgbp_macd_jpy_quality_w480_summary.csv",
    "outputs/backtests/live_watch_single_gbpusd_macd_jpy_quality_w480_summary.csv",
    "outputs/backtests/live_watch_quality_trend_risk_repair_live6_w480.csv",
    "outputs/backtests/live_watch_alpha_router_live6_w480_summary.csv",
    "outputs/backtests/live_watch_session_breakout_live7_w480_summary.csv",
    "outputs/backtests/live_watch_alpha_router_session_candidates_w480_summary.csv",
    "outputs/backtests/live_watch_session_breakout_router_candidates_w480_summary.csv",
    "outputs/backtests/live_watch_fixing_reversal_live7_w480_summary.csv",
    "outputs/backtests/live_watch_trend_pullback_live7_w480_summary.csv",
    "outputs/backtests/live_watch_usd_session_momentum_fixed_w480_summary.csv",
    "outputs/backtests/live_watch_mean_reversion_live7_w480_summary.csv",
    "outputs/backtests/live_watch_relative_strength_live7_w480_summary.csv",
    "outputs/backtests/live_watch_breakout_live7_w480_summary.csv",
    "outputs/backtests/live_watch_regime_switch_live7_w480_summary.csv",
    "outputs/backtests/live_watch_kalman_trend_live7_w480_summary.csv",
    "outputs/backtests/live_watch_late_usd_macd_w480.csv",
    "outputs/backtests/live_watch_late_usd_multi_horizon_w480.csv",
    "outputs/backtests/live_watch_late_usd_quality_w480.csv",
    "outputs/backtests/live_watch_live7_active_pressure_maps_w480_summary.csv",
    "outputs/backtests/live_watch_live6_positive_subset_maps_w480_summary.csv",
    "outputs/backtests/live_watch_live6_probe_candidate_maps_w480_summary.csv",
    "outputs/backtests/live_watch_live6_exact_candidate_maps_w480_summary.csv",
    "outputs/backtests/live_watch_gbpusd_asset_squeeze_w480_summary.csv",
    "outputs/backtests/live_watch_audusd_asset_squeeze_w480_summary.csv",
    "outputs/backtests/live_watch_multi_horizon_momentum_corrected.csv",
    "outputs/backtests/live_watch_multi_horizon_live6_w960.csv",
    "outputs/backtests/live_watch_multi_horizon_aud_gbp_w480_summary.csv",
    "outputs/backtests/live_watch_usdcad_usdchf_macd_aggressive_w480.csv",
    "outputs/backtests/live_watch_audusd_macd_aggressive_w480.csv",
    "outputs/backtests/live_watch_eurgbp_gbpusd_opportunity_probe_aggressive_w480.csv",
    "outputs/backtests/live_watch_eurgbp_gbpusd_champion_aggressive_w480.csv",
    "outputs/backtests/live_watch_champion_asset_signal_w672.csv",
    "outputs/backtests/live_watch_champion_asset_signal_w960.csv",
    "outputs/backtests/live_watch_eurusd_macd_evening_focus_w480.csv",
    "outputs/backtests/live_watch_quality_trend_size_opt_live6_w480.csv",
    "outputs/backtests/live_watch_quality_trend_opt_live6_w480.csv",
    "outputs/backtests/live_watch_opportunity_probe_opt_live6_w480.csv",
    "outputs/backtests/live_watch_opportunity_probe_pressure4_w480.csv",
    "outputs/backtests/live_watch_opportunity_probe_usdchf_usdjpy_w480.csv",
    "outputs/backtests/live_watch_opportunity_probe_usdchf_w480.csv",
    "outputs/backtests/live_watch_opportunity_probe_usdcad_w480.csv",
    "outputs/backtests/live_watch_opportunity_probe_audusd_eurgbp_w480.csv",
    "outputs/backtests/live_watch_opportunity_probe_audusd_eurusd_w480.csv",
    "outputs/backtests/live_watch_opportunity_probe_audusd_usdjpy_w480.csv",
    "outputs/backtests/live_watch_opportunity_probe_eurusd_gbpusd_w480.csv",
)
OPTIMIZER_SCAN_STALE_MINUTES = 6 * 60
DEFAULT_NEAR_PROMOTION_JSON = "outputs/backtests/live_watch_near_promotion_latest.json"

LIVE_LOOP_PATTERN = re.compile(
    r"iteration=(?P<iteration>\d+)\s+timestamp=(?P<timestamp>\S+)\s+"
    r"records=(?P<records>\d+)\s+statuses=(?P<statuses>\S+)"
)


def build_summary(
    *,
    metrics: dict[str, Any],
    live_loop: dict[str, Any] | None,
    latest_order: dict[str, Any] | None,
    pair_analysis: dict[str, Any],
    attribution: dict[str, Any],
    diagnostics: dict[str, Any],
    sentiment: dict[str, Any],
    research_consensus: dict[str, Any] | None,
    fixed_warmup_consensus: dict[str, Any] | None = None,
    candidate_watchlist: dict[str, Any] | None = None,
    candidate_map_consensus: dict[str, Any] | None = None,
    parameter_consensus: dict[str, Any] | None = None,
    basket_activity_scan: dict[str, Any] | None = None,
    research_cycle: dict[str, Any] | None = None,
    candidate_strategy_diagnostics: dict[str, Any] | None = None,
    optimizer_scans: dict[str, Any] | None = None,
    near_promotion: dict[str, Any] | None = None,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    generated_at = generated_at_utc or datetime.now(UTC).isoformat()
    pair_rows = _pair_rows(
        pair_analysis=pair_analysis,
        attribution=attribution,
        diagnostics=diagnostics,
        sentiment=sentiment,
    )
    blocked_symbols = {
        symbol: row["deal_state"]
        for symbol, row in pair_rows.items()
        if row["deal_state"] in BLOCKED_FRESH_RISK_STATES
    }
    small_only_symbols = {
        symbol: row["deal_state"]
        for symbol, row in pair_rows.items()
        if row["deal_state"] in SMALL_ONLY_FRESH_RISK_STATES
    }
    diagnostics_symbols = diagnostics.get("symbols", {})
    requested_changes = {
        symbol: data.get("raw_change_notional_usd", 0)
        for symbol, data in diagnostics_symbols.items()
        if data.get("raw_change_notional_usd", 0) != 0
    }
    adjusted_changes = {
        symbol: data.get("allocation_change_notional_usd", 0)
        for symbol, data in diagnostics_symbols.items()
        if data.get("allocation_change_notional_usd", 0) != 0
    }
    fresh_risk_candidates = [
        symbol
        for symbol, change in adjusted_changes.items()
        if change != 0 and symbol not in blocked_symbols
    ]
    account = {
        "timestamp_utc": metrics.get("timestamp_utc", ""),
        "equity": _float_or_zero(metrics.get("equity")),
        "balance": _float_or_zero(metrics.get("balance")),
        "day_pnl": _float_or_zero(metrics.get("day_pnl")),
        "floating_pnl": _float_or_zero(metrics.get("floating_pnl")),
        "drawdown_pct": _float_or_zero(metrics.get("drawdown_pct")),
        "margin": _float_or_zero(metrics.get("margin")),
        "margin_level": _float_or_zero(metrics.get("margin_level")),
        "positions_count": int(_float_or_zero(metrics.get("positions_count"))),
        "gross_lots": _float_or_zero(metrics.get("gross_lots")),
        "rolling_sharpe_15": _float_or_zero(metrics.get("rolling_sharpe_15")),
    }
    status = _overall_status(
        account=account,
        live_loop=live_loop,
        adjusted_changes=adjusted_changes,
        blocked_symbols=blocked_symbols,
        small_only_symbols=small_only_symbols,
    )
    compact_research_cycle = _compact_research_cycle(research_cycle)
    return {
        "timestamp_utc": generated_at,
        "status": status,
        "account": account,
        "live_loop": live_loop or {},
        "latest_order": _compact_order(latest_order),
        "risk": {
            "blocked_fresh_risk_states": sorted(BLOCKED_FRESH_RISK_STATES),
            "small_only_fresh_risk_states": sorted(SMALL_ONLY_FRESH_RISK_STATES),
            "blocked_symbols": blocked_symbols,
            "small_only_symbols": small_only_symbols,
            "fresh_risk_candidates": fresh_risk_candidates,
            "requested_change_symbols": requested_changes,
            "adjusted_change_symbols": adjusted_changes,
        },
        "strategy_allocation": diagnostics.get("allocation", {}),
        "pairs": pair_rows,
        "reentry_queue": _reentry_queue(
            pair_rows,
            live_symbols=set(diagnostics_symbols),
        ),
        "heuristic_only_probes": _heuristic_only_probes(pair_rows),
        "research_consensus": research_consensus or {},
        "fixed_warmup_consensus": fixed_warmup_consensus or {},
        "candidate_watchlist": _compact_candidate_watchlist(candidate_watchlist),
        "candidate_map_consensus": candidate_map_consensus or {},
        "parameter_consensus": parameter_consensus or {},
        "basket_activity_scan": _compact_basket_activity_scan(basket_activity_scan),
        "research_cycle": compact_research_cycle,
        "candidate_strategy_diagnostics": _compact_candidate_strategy_diagnostics(
            candidate_strategy_diagnostics
        ),
        "candidate_optimizer_evidence": _candidate_optimizer_evidence(
            candidate_strategy_diagnostics,
            optimizer_scans,
        ),
        "optimizer_scans": _compact_optimizer_scans(optimizer_scans),
        "near_promotion": _compact_near_promotion(near_promotion),
        "research_live_gate": _research_live_gate(
            research_cycle=compact_research_cycle,
            pair_rows=pair_rows,
        ),
    }


def write_summary_json(summary: dict[str, Any], path: str | Path) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def append_summary_history(summary: dict[str, Any], path: str | Path) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(summary, sort_keys=True) + "\n")


def write_summary_text(summary: dict[str, Any], path: str | Path) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(_summary_text(summary), encoding="utf-8")


def read_latest_metrics(path: str | Path) -> dict[str, str]:
    with Path(path).open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    return rows[-1] if rows else {}


def read_latest_order(path: str | Path) -> dict[str, Any] | None:
    journal_path = Path(path)
    if not journal_path.exists():
        return None
    last_line = ""
    with journal_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                last_line = line
    if not last_line:
        return None
    return json.loads(last_line)


def read_live_loop(path: str | Path) -> dict[str, Any] | None:
    log_path = Path(path)
    if not log_path.exists():
        return None
    latest_match: re.Match[str] | None = None
    with log_path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            match = LIVE_LOOP_PATTERN.search(line)
            if match:
                latest_match = match
    if latest_match is None:
        return None
    return {
        "iteration": int(latest_match.group("iteration")),
        "timestamp_utc": latest_match.group("timestamp"),
        "records": int(latest_match.group("records")),
        "statuses": latest_match.group("statuses"),
    }


def read_json(path: str | Path) -> dict[str, Any]:
    json_path = Path(path)
    if not json_path.exists():
        return {}
    try:
        return json.loads(json_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def read_research_consensus(path: str | Path) -> dict[str, str] | None:
    consensus_path = Path(path)
    if not consensus_path.exists():
        return None
    with consensus_path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    return rows[0] if rows else None


def read_candidate_map_consensus(paths: list[str] | tuple[str, ...]) -> dict[str, Any]:
    rows: list[dict[str, str]] = []
    for path in paths:
        consensus = read_research_consensus(path)
        if consensus is None:
            continue
        consensus = dict(consensus)
        consensus["source_path"] = str(path)
        rows.append(consensus)
    rows.sort(key=_candidate_map_rank_key)
    return {"candidate_count": len(rows), "top_candidates": rows}


def read_basket_activity_scan(path: str | Path) -> dict[str, Any]:
    scan_path = Path(path)
    if not scan_path.exists():
        return {}
    with scan_path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        return {}
    active_count = sum(
        1 for row in rows
        if row.get("activity_status") == "ACTIVE"
    )
    return {
        "candidate_count": len(rows),
        "active_count": active_count,
        "underactive_count": len(rows) - active_count,
        "top_candidates": rows[:3],
    }


def read_candidate_strategy_diagnostics(paths: list[str] | tuple[str, ...]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for path in paths:
        diagnostics = read_json(path)
        if not diagnostics:
            continue
        rows.append(_candidate_strategy_diagnostic_row(path, diagnostics))
    rows.sort(key=_candidate_strategy_diagnostic_rank_key)
    return {
        "candidate_count": len(rows),
        "top_candidates": rows,
    }


def read_optimizer_scans(
    paths: list[str] | tuple[str, ...],
    *,
    now_utc: datetime | None = None,
) -> dict[str, Any]:
    now = now_utc or datetime.now(UTC)
    rows: list[dict[str, Any]] = []
    for path in paths:
        scan_path = Path(path)
        if not scan_path.exists():
            continue
        mtime_utc = datetime.fromtimestamp(scan_path.stat().st_mtime, UTC)
        age_minutes = max(0.0, (now - mtime_utc).total_seconds() / 60.0)
        with scan_path.open("r", encoding="utf-8", newline="") as handle:
            scan_rows = list(csv.DictReader(handle))
        if not scan_rows:
            continue
        top_row = _normalize_optimizer_scan_row(dict(scan_rows[0]))
        top_row["source_path"] = str(scan_path)
        top_row["source_label"] = scan_path.stem
        top_row["source_mtime_utc"] = mtime_utc.isoformat()
        top_row["source_age_minutes"] = age_minutes
        top_row["source_stale"] = age_minutes > OPTIMIZER_SCAN_STALE_MINUTES
        rows.append(top_row)
    rows.sort(key=_optimizer_scan_rank_key)
    return {
        "scan_count": len(rows),
        "top_candidates": rows,
    }


def _normalize_optimizer_scan_row(row: dict[str, Any]) -> dict[str, Any]:
    """Accept both optimizer CSVs and fixed-warmup one-row summary CSVs."""
    normalized = dict(row)
    if not str(normalized.get("label", "")).strip():
        normalized["label"] = str(normalized.get("strategy", "")).strip()
    field_aliases = {
        "positive_fold_fraction": "wf_positive_fold_fraction",
        "active_fold_fraction": "wf_active_fold_fraction",
        "active_positive_fold_fraction": "wf_active_positive_fold_fraction",
        "non_negative_fold_fraction": "wf_non_negative_fold_fraction",
        "median_active_test_return_pct": "wf_median_active_test_return_pct",
        "worst_test_drawdown_pct": "wf_worst_test_drawdown_pct",
        "total_evaluation_fills": "wf_total_evaluation_fills",
        "average_risk_discipline_score": "risk_discipline_score",
    }
    for source, target in field_aliases.items():
        if target not in normalized and source in normalized:
            normalized[target] = normalized[source]
    return normalized


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a compact monitor-only summary of live MT5 readiness."
    )
    parser.add_argument("--metrics-csv", default="outputs/live_metrics.csv")
    parser.add_argument("--stdout-log", default="outputs/live_trading_stdout.log")
    parser.add_argument("--orders-journal", default="outputs/live_orders_journal.jsonl")
    parser.add_argument("--pair-analysis-json", default="outputs/live_pair_analysis_latest.json")
    parser.add_argument("--attribution-json", default="outputs/live_deal_attribution_latest.json")
    parser.add_argument(
        "--diagnostics-json",
        default="outputs/live_strategy_diagnostics_latest.json",
    )
    parser.add_argument("--sentiment-json", default="outputs/fx_sentiment_snapshot.json")
    parser.add_argument(
        "--research-consensus-csv",
        default="outputs/backtests/live_watch_adaptive_explicit_recipes_consensus.csv",
    )
    parser.add_argument(
        "--fixed-warmup-consensus-csv",
        default="outputs/backtests/live_watch_quality_top3_fixed_warmup_consensus.csv",
    )
    parser.add_argument(
        "--candidate-watchlist-json",
        default="outputs/live_candidate_watchlist_latest.json",
    )
    parser.add_argument(
        "--candidate-map-consensus-csv",
        action="append",
        default=None,
        help="Candidate map consensus CSV to surface; repeatable.",
    )
    parser.add_argument(
        "--parameter-consensus-csv",
        default="outputs/backtests/live_watch_macd_aggressive_consensus.csv",
    )
    parser.add_argument(
        "--basket-activity-scan-csv",
        default=DEFAULT_BASKET_ACTIVITY_SCAN_CSV,
    )
    parser.add_argument(
        "--research-cycle-json",
        default="outputs/live_research_cycle_latest.json",
    )
    parser.add_argument(
        "--candidate-diagnostics-json",
        action="append",
        default=None,
        help="Read-only candidate strategy diagnostics JSON to surface; repeatable.",
    )
    parser.add_argument(
        "--optimizer-scan-csv",
        action="append",
        default=None,
        help="Optimizer result CSV to surface; repeatable.",
    )
    parser.add_argument("--near-promotion-json", default=DEFAULT_NEAR_PROMOTION_JSON)
    parser.add_argument("--output-json", default="outputs/live_status_summary_latest.json")
    parser.add_argument("--output-text", default="outputs/live_status_summary_latest.txt")
    parser.add_argument("--history-jsonl", default="outputs/live_status_summary_history.jsonl")
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    summary = build_summary(
        metrics=read_latest_metrics(args.metrics_csv),
        live_loop=read_live_loop(args.stdout_log),
        latest_order=read_latest_order(args.orders_journal),
        pair_analysis=read_json(args.pair_analysis_json),
        attribution=read_json(args.attribution_json),
        diagnostics=read_json(args.diagnostics_json),
        sentiment=read_json(args.sentiment_json),
        research_consensus=read_research_consensus(args.research_consensus_csv),
        fixed_warmup_consensus=read_research_consensus(
            args.fixed_warmup_consensus_csv
        ),
        candidate_watchlist=read_json(args.candidate_watchlist_json),
        candidate_map_consensus=read_candidate_map_consensus(
            tuple(
                args.candidate_map_consensus_csv
                or DEFAULT_CANDIDATE_MAP_CONSENSUS_CSVS
            )
        ),
        parameter_consensus=read_research_consensus(args.parameter_consensus_csv),
        basket_activity_scan=read_basket_activity_scan(args.basket_activity_scan_csv),
        research_cycle=read_json(args.research_cycle_json),
        candidate_strategy_diagnostics=read_candidate_strategy_diagnostics(
            tuple(
                args.candidate_diagnostics_json
                or DEFAULT_CANDIDATE_DIAGNOSTICS_JSONS
            )
        ),
        optimizer_scans=read_optimizer_scans(
            tuple(args.optimizer_scan_csv or DEFAULT_OPTIMIZER_SCAN_CSVS)
        ),
        near_promotion=read_json(args.near_promotion_json),
    )
    write_summary_json(summary, args.output_json)
    write_summary_text(summary, args.output_text)
    append_summary_history(summary, args.history_jsonl)
    print(
        f"wrote live status summary to {args.output_json} "
        f"status={summary['status']}"
    )


def _pair_rows(
    *,
    pair_analysis: dict[str, Any],
    attribution: dict[str, Any],
    diagnostics: dict[str, Any],
    sentiment: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    pair_data = pair_analysis.get("pairs", {})
    attribution_data = attribution.get("symbols", {})
    diagnostic_data = diagnostics.get("symbols", {})
    sentiment_data = sentiment.get("pairs", {})
    symbols = sorted(
        set(pair_data)
        | set(attribution_data)
        | set(diagnostic_data)
        | set(sentiment_data)
    )
    rows: dict[str, dict[str, Any]] = {}
    for symbol in symbols:
        pair = pair_data.get(symbol, {})
        deal = attribution_data.get(symbol, {})
        diagnostic = diagnostic_data.get(symbol, {})
        sent = sentiment_data.get(symbol, {})
        rows[symbol] = {
            "action": pair.get("action", ""),
            "deal_state": deal.get("state", pair.get("deal_state", "")),
            "estimated_state_clear_utc": deal.get("estimated_state_clear_utc", ""),
            "estimated_state_after_clear": deal.get("estimated_state_after_clear", ""),
            "realized_net_pnl": _float_or_zero(
                deal.get("net_pnl", pair.get("realized_net_pnl"))
            ),
            "floating_pnl": _float_or_zero(deal.get("floating_pnl", 0.0)),
            "open_direction": deal.get("open_direction", ""),
            "open_lots": _float_or_zero(deal.get("open_lots", 0.0)),
            "combined_score": _float_or_zero(pair.get("combined_score", 0.0)),
            "technical_score": _float_or_zero(pair.get("technical_score", 0.0)),
            "sentiment_score": _float_or_zero(
                sent.get("score", pair.get("headline_sentiment_score", 0.0))
            ),
            "diagnostic_status": diagnostic.get("status", ""),
            "diagnostic_bucket": diagnostic.get("raw_reason_bucket", ""),
            "diagnostic_reason": diagnostic.get("raw_reason", ""),
            "raw_change_notional_usd": _float_or_zero(
                diagnostic.get("raw_change_notional_usd", 0.0)
            ),
            "allocation_change_notional_usd": _float_or_zero(
                diagnostic.get("allocation_change_notional_usd", 0.0)
            ),
        }
    return rows


def _overall_status(
    *,
    account: dict[str, Any],
    live_loop: dict[str, Any] | None,
    adjusted_changes: dict[str, Any],
    blocked_symbols: dict[str, str],
    small_only_symbols: dict[str, str],
) -> str:
    if not live_loop:
        return "LIVE_LOOP_UNKNOWN"
    if account["positions_count"] > 0:
        return "LIVE_POSITIONS_OPEN"
    if adjusted_changes:
        return "PENDING_OR_APPROVED_RISK_CHANGE"
    if blocked_symbols:
        return "FLAT_FRESH_RISK_BLOCKED"
    if small_only_symbols:
        return "FLAT_SMALL_ONLY_READY"
    return "FLAT_NO_APPROVED_RISK"


def _compact_order(order: dict[str, Any] | None) -> dict[str, Any]:
    if not order:
        return {}
    request = order.get("request", {})
    account = order.get("account", {})
    return {
        "created_at_utc": order.get("created_at_utc", ""),
        "status": order.get("status", ""),
        "symbol": request.get("symbol", ""),
        "side": request.get("side", ""),
        "target_notional_usd": request.get("target_notional_usd", 0.0),
        "reason": request.get("reason", ""),
        "equity": account.get("equity"),
    }


def _reentry_queue(
    pair_rows: dict[str, dict[str, Any]],
    *,
    live_symbols: set[str],
) -> dict[str, Any]:
    rows = []
    for symbol, row in pair_rows.items():
        state = row.get("deal_state", "")
        clear_utc = row.get("estimated_state_clear_utc", "")
        state_after_clear = row.get("estimated_state_after_clear", "")
        if not clear_utc or state not in (BLOCKED_FRESH_RISK_STATES | SMALL_ONLY_FRESH_RISK_STATES):
            continue
        rows.append(
            {
                "symbol": symbol,
                "in_live_universe": symbol in live_symbols,
                "deal_state": state,
                "estimated_state_clear_utc": clear_utc,
                "estimated_state_after_clear": state_after_clear,
                "action": row.get("action", ""),
                "combined_score": _float_or_zero(row.get("combined_score")),
                "diagnostic_status": row.get("diagnostic_status", ""),
                "diagnostic_bucket": row.get("diagnostic_bucket", ""),
            }
        )
    rows.sort(
        key=lambda item: (
            0 if item["in_live_universe"] else 1,
            item["estimated_state_clear_utc"],
            item["symbol"],
        )
    )
    return {
        "candidate_count": len(rows),
        "top_candidates": rows[:5],
    }


def _heuristic_only_probes(
    pair_rows: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    rows = []
    for symbol, row in pair_rows.items():
        action = str(row.get("action", ""))
        raw_change = _float_or_zero(row.get("raw_change_notional_usd"))
        alloc_change = _float_or_zero(row.get("allocation_change_notional_usd"))
        if not action.startswith("eligible_") or "probe" not in action:
            continue
        if raw_change != 0 or alloc_change != 0:
            continue
        diagnostic_status = row.get("diagnostic_status", "")
        rows.append(
            {
                "symbol": symbol,
                "action": action,
                "live_gate": diagnostic_status or "no_live_strategy_signal",
                "deal_state": row.get("deal_state", ""),
                "combined_score": _float_or_zero(row.get("combined_score")),
                "sentiment_score": _float_or_zero(row.get("sentiment_score")),
                "diagnostic_status": diagnostic_status,
                "diagnostic_bucket": row.get("diagnostic_bucket", ""),
            }
        )
    rows.sort(
        key=lambda item: (
            -abs(item["combined_score"]),
            item["symbol"],
        )
    )
    return {
        "candidate_count": len(rows),
        "top_candidates": rows[:5],
    }


def _compact_candidate_watchlist(
    watchlist: dict[str, Any] | None,
) -> dict[str, Any]:
    if not watchlist:
        return {}
    candidates = watchlist.get("candidates", [])
    compact_rows = []
    for row in candidates[:3]:
        compact_rows.append(
            {
                "symbol": row.get("symbol", ""),
                "label": row.get("label", ""),
                "source_path": row.get("source_path", ""),
                "candidate_strategy": row.get("candidate_strategy", ""),
                "live_strategy": row.get("live_strategy", ""),
                "strategy_aligned": bool(row.get("strategy_aligned", False)),
                "live_gate": row.get("live_gate", ""),
                "deal_state": row.get("deal_state", ""),
                "estimated_state_clear_utc": row.get(
                    "estimated_state_clear_utc",
                    "",
                ),
                "quality_score": _float_or_zero(row.get("quality_score")),
                "hit_rate": _float_or_zero(row.get("hit_rate")),
                "average_edge_after_cost_bps": _float_or_zero(
                    row.get("average_edge_after_cost_bps")
                ),
            }
        )
    return {
        "timestamp_utc": watchlist.get("timestamp_utc", ""),
        "candidate_count": len(candidates),
        "top_candidates": compact_rows,
    }


def _compact_basket_activity_scan(
    scan: dict[str, Any] | None,
) -> dict[str, Any]:
    if not scan:
        return {}
    compact_rows = []
    for row in scan.get("top_candidates", [])[:3]:
        if not isinstance(row, dict):
            continue
        compact_rows.append(
            {
                "basket": row.get("basket", ""),
                "strategy": row.get("strategy", ""),
                "symbols": row.get("symbols", ""),
                "proxy_score": _float_or_zero(row.get("proxy_score")),
                "activity_status": row.get("activity_status", ""),
                "fills": int(_float_or_zero(row.get("fills"))),
                "return_pct": _float_or_zero(row.get("official_return_pct")),
                "drawdown_pct": _float_or_zero(
                    row.get("official_max_drawdown_pct")
                ),
            }
        )
    return {
        "candidate_count": int(_float_or_zero(scan.get("candidate_count"))),
        "active_count": int(_float_or_zero(scan.get("active_count"))),
        "underactive_count": int(_float_or_zero(scan.get("underactive_count"))),
        "top_candidates": compact_rows,
    }


def _candidate_strategy_diagnostic_row(
    path: str | Path,
    diagnostics: dict[str, Any],
) -> dict[str, Any]:
    source_path = str(path)
    allocation = diagnostics.get("allocation", {})
    symbol_rows = [
        _candidate_strategy_symbol_row(source_path, symbol, item)
        for symbol, item in diagnostics.get("symbols", {}).items()
        if isinstance(item, dict)
    ]
    symbol_rows.sort(key=_candidate_strategy_symbol_rank_key)
    actionable_count = sum(
        1 for row in symbol_rows
        if row["status"] == "actionable_allocation"
    )
    requested_count = sum(
        1 for row in symbol_rows
        if abs(row["raw_change_notional_usd"]) > 0.0
    )
    return {
        "source_path": source_path,
        "label": _candidate_strategy_label(source_path),
        "timestamp_utc": diagnostics.get("timestamp_utc", ""),
        "allocation_profile": diagnostics.get("allocation_profile", "default"),
        "allocation_status": allocation.get("status", ""),
        "requested_gross_notional_usd": _float_or_zero(
            allocation.get("requested_gross_notional_usd")
        ),
        "adjusted_gross_notional_usd": _float_or_zero(
            allocation.get("adjusted_gross_notional_usd")
        ),
        "actionable_symbol_count": actionable_count,
        "requested_symbol_count": requested_count,
        "actionable_symbols": [
            row["symbol"]
            for row in symbol_rows
            if row["status"] == "actionable_allocation"
        ],
        "requested_symbols": [
            row["symbol"]
            for row in symbol_rows
            if abs(row["raw_change_notional_usd"]) > 0.0
        ],
        "top_symbol": symbol_rows[0] if symbol_rows else {},
    }


def _candidate_strategy_symbol_row(
    source_path: str,
    symbol: str,
    item: dict[str, Any],
) -> dict[str, Any]:
    return {
        "source_path": source_path,
        "symbol": symbol,
        "source_focus": symbol.lower() in Path(source_path).stem.lower(),
        "status": item.get("status", ""),
        "strategy": item.get("strategy", ""),
        "raw_reason_bucket": item.get("raw_reason_bucket", ""),
        "raw_reason": item.get("raw_reason", ""),
        "raw_change_notional_usd": _float_or_zero(
            item.get("raw_change_notional_usd")
        ),
        "throttle_change_notional_usd": _float_or_zero(
            item.get("throttle_change_notional_usd")
        ),
        "allocation_change_notional_usd": _float_or_zero(
            item.get("allocation_change_notional_usd")
        ),
    }


def _compact_candidate_strategy_diagnostics(
    diagnostics: dict[str, Any] | None,
) -> dict[str, Any]:
    if not diagnostics:
        return {}
    rows = diagnostics.get("top_candidates", [])
    compact_rows = []
    for row in rows[:3]:
        if not isinstance(row, dict):
            continue
        top_symbol = row.get("top_symbol", {})
        if not isinstance(top_symbol, dict):
            top_symbol = {}
        compact_rows.append(
            {
                "source_path": row.get("source_path", ""),
                "label": row.get("label", ""),
                "timestamp_utc": row.get("timestamp_utc", ""),
                "allocation_profile": row.get("allocation_profile", "default"),
                "allocation_status": row.get("allocation_status", ""),
                "requested_gross_notional_usd": _float_or_zero(
                    row.get("requested_gross_notional_usd")
                ),
                "adjusted_gross_notional_usd": _float_or_zero(
                    row.get("adjusted_gross_notional_usd")
                ),
                "actionable_symbol_count": int(
                    _float_or_zero(row.get("actionable_symbol_count"))
                ),
                "requested_symbol_count": int(
                    _float_or_zero(row.get("requested_symbol_count"))
                ),
                "actionable_symbols": list(row.get("actionable_symbols", []))[:7],
                "requested_symbols": list(row.get("requested_symbols", []))[:7],
                "top_symbol": {
                    "symbol": top_symbol.get("symbol", ""),
                    "status": top_symbol.get("status", ""),
                    "strategy": top_symbol.get("strategy", ""),
                    "raw_reason_bucket": top_symbol.get("raw_reason_bucket", ""),
                    "raw_change_notional_usd": _float_or_zero(
                        top_symbol.get("raw_change_notional_usd")
                    ),
                    "allocation_change_notional_usd": _float_or_zero(
                        top_symbol.get("allocation_change_notional_usd")
                    ),
                },
            }
        )
    return {
        "candidate_count": int(_float_or_zero(diagnostics.get("candidate_count"))),
        "top_candidates": compact_rows,
    }


def _candidate_optimizer_evidence(
    diagnostics: dict[str, Any] | None,
    scans: dict[str, Any] | None,
) -> dict[str, Any]:
    if not diagnostics or not scans:
        return {}
    evidence_rows: list[dict[str, Any]] = []
    for candidate in diagnostics.get("top_candidates", []):
        if not isinstance(candidate, dict):
            continue
        strategy = _candidate_evidence_strategy(candidate)
        symbols = _candidate_evidence_symbols(candidate)
        if not strategy or not symbols:
            continue
        matches = _matching_optimizer_scan_rows(
            strategy=strategy,
            symbols=symbols,
            scans=scans,
        )
        if not matches:
            continue
        evidence_pool = [
            match for match in matches
            if match.get("exact_symbols")
        ] or matches
        evidence_status = _optimizer_evidence_status(evidence_pool)
        top_match = sorted(evidence_pool, key=_optimizer_evidence_rank_key)[0]
        evidence_rows.append(
            {
                "candidate_label": candidate.get("label", ""),
                "strategy": strategy,
                "symbols": symbols,
                "evidence_status": evidence_status,
                "match_count": len(matches),
                "top_match": {
                    "source_path": top_match.get("source_path", ""),
                    "source_label": top_match.get("source_label", ""),
                    "label": top_match.get("label", ""),
                    "promotion_status": top_match.get("promotion_status", ""),
                    "promotion_live_ready": _boolish(
                        top_match.get("promotion_live_ready")
                    ),
                    "promotion_reason": top_match.get("promotion_reason", ""),
                    "return_pct": _float_or_zero(top_match.get("return_pct")),
                    "wf_non_negative_fold_fraction": _float_or_zero(
                        top_match.get("wf_non_negative_fold_fraction")
                    ),
                    "wf_active_positive_fold_fraction": _float_or_zero(
                        top_match.get("wf_active_positive_fold_fraction")
                    ),
                    "wf_total_evaluation_fills": int(
                        _float_or_zero(top_match.get("wf_total_evaluation_fills"))
                    ),
                    "source_age_minutes": _float_or_zero(
                        top_match.get("source_age_minutes")
                    ),
                },
            }
        )
    if not evidence_rows:
        return {}
    evidence_rows.sort(key=_candidate_optimizer_evidence_rank_key)
    return {
        "candidate_count": len(evidence_rows),
        "top_candidates": evidence_rows[:3],
    }


def _candidate_evidence_strategy(candidate: dict[str, Any]) -> str:
    top_symbol = candidate.get("top_symbol", {})
    if isinstance(top_symbol, dict):
        strategy = str(top_symbol.get("strategy", "")).strip()
        if strategy:
            return strategy
    label = str(candidate.get("label", "")).lower()
    for strategy in (
        "opportunity_probe",
        "macd_momentum",
        "quality_trend",
        "champion_ensemble",
        "cross_rate_reversion",
        "multi_horizon_momentum",
    ):
        if strategy in label:
            return strategy
    return ""


def _candidate_evidence_symbols(candidate: dict[str, Any]) -> list[str]:
    for key in ("actionable_symbols", "requested_symbols"):
        symbols = [
            str(symbol).strip().upper()
            for symbol in candidate.get(key, [])
            if str(symbol).strip()
        ]
        if symbols:
            return sorted(set(symbols))
    top_symbol = candidate.get("top_symbol", {})
    if isinstance(top_symbol, dict):
        symbol = str(top_symbol.get("symbol", "")).strip().upper()
        status = str(top_symbol.get("status", "")).strip()
        raw_change = _float_or_zero(top_symbol.get("raw_change_notional_usd"))
        allocation_change = _float_or_zero(
            top_symbol.get("allocation_change_notional_usd")
        )
        if (
            symbol
            and (
                status == "actionable_allocation"
                or abs(raw_change) > 0.0
                or abs(allocation_change) > 0.0
            )
        ):
            return [symbol]
    return []


def _matching_optimizer_scan_rows(
    *,
    strategy: str,
    symbols: list[str],
    scans: dict[str, Any],
) -> list[dict[str, Any]]:
    wanted_symbols = set(symbols)
    matches: list[dict[str, Any]] = []
    for row in scans.get("top_candidates", []):
        if not isinstance(row, dict):
            continue
        source_text = " ".join(
            str(row.get(key, "")).lower()
            for key in ("source_path", "source_label", "label")
        )
        if strategy.lower() not in source_text:
            continue
        scan_symbols = set(_split_symbol_text(row.get("symbols", "")))
        if not scan_symbols or not wanted_symbols.issubset(scan_symbols):
            continue
        match = dict(row)
        match["exact_symbols"] = scan_symbols == wanted_symbols
        matches.append(match)
    return matches


def _split_symbol_text(raw: Any) -> list[str]:
    if not raw:
        return []
    return [
        part.strip().upper()
        for part in re.split(r"[\s,;|]+", str(raw))
        if part.strip()
    ]


def _optimizer_evidence_status(matches: list[dict[str, Any]]) -> str:
    statuses = {
        str(match.get("promotion_status", "")).upper()
        for match in matches
    }
    if statuses == {"REJECT"}:
        return "REJECTED_BY_SCAN"
    if "PROMOTE" in statuses:
        return "SUPPORTED_BY_SCAN"
    if "PAPER_ONLY" in statuses:
        return "PAPER_ONLY_SCAN"
    return "MIXED_SCAN_EVIDENCE"


def _optimizer_evidence_rank_key(row: dict[str, Any]) -> tuple[int, int, float, str]:
    status_rank = {"REJECT": 0, "PAPER_ONLY": 1, "PROMOTE": 2}
    return (
        0 if row.get("exact_symbols") else 1,
        status_rank.get(str(row.get("promotion_status", "")).upper(), 3),
        _float_or_zero(row.get("source_age_minutes")),
        str(row.get("source_label", "")),
    )


def _candidate_optimizer_evidence_rank_key(
    row: dict[str, Any],
) -> tuple[int, str]:
    status_rank = {
        "REJECTED_BY_SCAN": 0,
        "PAPER_ONLY_SCAN": 1,
        "MIXED_SCAN_EVIDENCE": 2,
        "SUPPORTED_BY_SCAN": 3,
    }
    return (
        status_rank.get(row.get("evidence_status", ""), 4),
        row.get("candidate_label", ""),
    )


def _compact_optimizer_scans(
    scans: dict[str, Any] | None,
) -> dict[str, Any]:
    if not scans:
        return {}
    compact_rows = []
    for row in scans.get("top_candidates", [])[:5]:
        if not isinstance(row, dict):
            continue
        compact_rows.append(
            {
                "source_path": row.get("source_path", ""),
                "source_label": row.get("source_label", ""),
                "source_mtime_utc": row.get("source_mtime_utc", ""),
                "source_age_minutes": _float_or_zero(
                    row.get("source_age_minutes")
                ),
                "source_stale": _boolish(row.get("source_stale")),
                "label": row.get("label", ""),
                "symbols": row.get("symbols", ""),
                "promotion_status": row.get("promotion_status", ""),
                "promotion_live_ready": _boolish(row.get("promotion_live_ready")),
                "promotion_reason": row.get("promotion_reason", ""),
                "return_pct": _float_or_zero(row.get("return_pct")),
                "max_drawdown_pct": _float_or_zero(row.get("max_drawdown_pct")),
                "wf_positive_fold_fraction": _float_or_zero(
                    row.get("wf_positive_fold_fraction")
                ),
                "wf_active_fold_fraction": _float_or_zero(
                    row.get("wf_active_fold_fraction")
                ),
                "wf_active_positive_fold_fraction": _float_or_zero(
                    row.get("wf_active_positive_fold_fraction")
                ),
                "wf_non_negative_fold_fraction": _float_or_zero(
                    row.get("wf_non_negative_fold_fraction")
                ),
                "wf_median_active_test_return_pct": _float_or_zero(
                    row.get("wf_median_active_test_return_pct")
                ),
                "wf_total_evaluation_fills": int(
                    _float_or_zero(row.get("wf_total_evaluation_fills"))
                ),
            }
        )
    return {
        "scan_count": int(_float_or_zero(scans.get("scan_count"))),
        "top_candidates": compact_rows,
    }


def _compact_near_promotion(summary: dict[str, Any] | None) -> dict[str, Any]:
    if not summary:
        return {}
    compact_rows = []
    for row in summary.get("top_candidates", [])[:3]:
        if not isinstance(row, dict):
            continue
        compact_rows.append(
            {
                "source_path": row.get("source_path", ""),
                "label": row.get("label", ""),
                "promotion_status": row.get("promotion_status", ""),
                "promotion_gap_score": _float_or_zero(
                    row.get("promotion_gap_score")
                ),
                "positive_fold_fraction": _float_or_zero(
                    row.get("positive_fold_fraction")
                ),
                "active_positive_fold_fraction": _float_or_zero(
                    row.get("active_positive_fold_fraction")
                ),
                "non_negative_fold_fraction": _float_or_zero(
                    row.get("non_negative_fold_fraction")
                ),
                "median_active_test_return_pct": _float_or_zero(
                    row.get("median_active_test_return_pct")
                ),
                "evaluation_fills": int(_float_or_zero(row.get("evaluation_fills"))),
                "failed_gates": row.get("failed_gates", []),
                "promotion_reason": row.get("promotion_reason", ""),
            }
        )
    return {
        "candidate_count": int(_float_or_zero(summary.get("scan_count"))),
        "top_candidates": compact_rows,
    }


def _compact_research_cycle(
    cycle: dict[str, Any] | None,
) -> dict[str, Any]:
    if not cycle:
        return {}
    basket = cycle.get("basket_scan", {})
    signals = cycle.get("signal_diagnostics", {})
    qualified_rows = signals.get("qualified_rows", [])
    if not isinstance(qualified_rows, list):
        qualified_rows = []
    compact_rows = []
    for row in qualified_rows[:3]:
        if not isinstance(row, dict):
            continue
        compact_rows.append(
            {
                "strategy": row.get("strategy", ""),
                "symbol": row.get("symbol", ""),
                "signal": row.get("signal", ""),
                "active_count": int(_float_or_zero(row.get("active_count"))),
                "hit_rate": _float_or_zero(row.get("hit_rate")),
                "average_signed_forward_return_bps": _float_or_zero(
                    row.get("average_signed_forward_return_bps")
                ),
                "average_edge_after_cost_bps": _float_or_zero(
                    row.get("average_edge_after_cost_bps")
                ),
            }
        )
    return {
        "timestamp_utc": cycle.get("timestamp_utc", ""),
        "basket_active_count": int(_float_or_zero(basket.get("active_count"))),
        "basket_underactive_count": int(
            _float_or_zero(basket.get("underactive_count"))
        ),
        "qualified_signal_count": int(
            _float_or_zero(signals.get("qualified_count"))
        ),
        "qualified_rows": compact_rows,
    }


def _research_live_gate(
    *,
    research_cycle: dict[str, Any],
    pair_rows: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    rows = research_cycle.get("qualified_rows", [])
    if not rows:
        return {}
    gated_rows = []
    for row in rows[:3]:
        if not isinstance(row, dict):
            continue
        symbol = row.get("symbol", "")
        pair = pair_rows.get(symbol, {})
        state = pair.get("deal_state", "")
        raw_change = _float_or_zero(pair.get("raw_change_notional_usd"))
        alloc_change = _float_or_zero(pair.get("allocation_change_notional_usd"))
        diagnostic_status = pair.get("diagnostic_status", "")
        if state in BLOCKED_FRESH_RISK_STATES:
            gate = "blocked_fresh_risk"
        elif state in SMALL_ONLY_FRESH_RISK_STATES and (
            raw_change != 0 or alloc_change != 0
        ):
            gate = "small_only_live_signal"
        elif state in SMALL_ONLY_FRESH_RISK_STATES:
            gate = "small_only_research_only"
        elif raw_change != 0 and alloc_change != 0:
            gate = "live_signal"
        elif raw_change != 0:
            gate = "allocation_blocked"
        elif diagnostic_status == "strategy_no_change":
            gate = "strategy_no_change"
        else:
            gate = "unknown"
        gated_rows.append(
            {
                "symbol": symbol,
                "strategy": row.get("strategy", ""),
                "signal": row.get("signal", ""),
                "gate": gate,
                "action": pair.get("action", ""),
                "deal_state": state,
                "diagnostic_status": diagnostic_status,
                "diagnostic_bucket": pair.get("diagnostic_bucket", ""),
                "raw_change_notional_usd": raw_change,
                "allocation_change_notional_usd": alloc_change,
            }
        )
    return {
        "candidate_count": len(gated_rows),
        "top_candidates": gated_rows,
    }


def _candidate_map_rows(candidate_map: dict[str, Any]) -> list[dict[str, Any]]:
    raw_candidates = candidate_map.get("top_candidates")
    if isinstance(raw_candidates, list):
        return [
            row for row in raw_candidates
            if isinstance(row, dict)
        ]
    return [candidate_map] if candidate_map else []


def _summary_text(summary: dict[str, Any]) -> str:
    account = summary["account"]
    loop = summary.get("live_loop", {})
    research = summary.get("research_consensus", {})
    fixed_warmup = summary.get("fixed_warmup_consensus", {})
    watchlist = summary.get("candidate_watchlist", {})
    candidate_map = summary.get("candidate_map_consensus", {})
    parameter = summary.get("parameter_consensus", {})
    basket_scan = summary.get("basket_activity_scan", {})
    research_cycle = summary.get("research_cycle", {})
    candidate_diagnostics = summary.get("candidate_strategy_diagnostics", {})
    candidate_evidence = summary.get("candidate_optimizer_evidence", {})
    optimizer_scans = summary.get("optimizer_scans", {})
    near_promotion = summary.get("near_promotion", {})
    research_live_gate = summary.get("research_live_gate", {})
    heuristic_only = summary.get("heuristic_only_probes", {})
    lines = [
        f"{summary['timestamp_utc']} status={summary['status']}",
        (
            "account "
            f"equity={account['equity']:.2f} "
            f"day_pnl={account['day_pnl']:.2f} "
            f"floating={account['floating_pnl']:.2f} "
            f"positions={account['positions_count']} "
            f"gross_lots={account['gross_lots']:.2f} "
            f"sharpe15={account['rolling_sharpe_15']:.2f}"
        ),
        (
            "live_loop "
            f"iteration={loop.get('iteration', '')} "
            f"timestamp={loop.get('timestamp_utc', '')} "
            f"statuses={loop.get('statuses', '')}"
        ),
    ]
    latest_order = summary.get("latest_order", {})
    if latest_order:
        lines.append(
            "latest_order "
            f"{latest_order.get('created_at_utc', '')} "
            f"{latest_order.get('symbol', '')} {latest_order.get('side', '')} "
            f"status={latest_order.get('status', '')}"
        )
    risk = summary["risk"]
    lines.append(
        "risk "
        f"blocked_symbols={','.join(risk['blocked_symbols']) or 'none'} "
        f"small_only_symbols={','.join(risk.get('small_only_symbols', {})) or 'none'} "
            f"fresh_candidates={','.join(risk['fresh_risk_candidates']) or 'none'}"
    )
    reentry_queue = summary.get("reentry_queue", {})
    if reentry_queue.get("candidate_count", 0) > 0:
        top = reentry_queue.get("top_candidates", [{}])[0]
        lines.append(
            "reentry_queue "
            f"candidates={reentry_queue.get('candidate_count', 0)} "
            f"next={top.get('symbol', '')} "
            f"live={'yes' if top.get('in_live_universe') else 'no'} "
            f"state={top.get('deal_state', '')} "
            f"after={top.get('estimated_state_after_clear') or 'n/a'} "
            f"clear={top.get('estimated_state_clear_utc') or 'n/a'} "
            f"action={top.get('action', '')} "
            f"diag={top.get('diagnostic_status', '')} "
            f"score={top.get('combined_score', 0.0):.2f}"
        )
    if heuristic_only.get("candidate_count", 0) > 0:
        top = heuristic_only.get("top_candidates", [{}])[0]
        lines.append(
            "heuristic_only_probes "
            f"candidates={heuristic_only.get('candidate_count', 0)} "
            f"top={top.get('symbol', '')} "
            f"action={top.get('action', '')} "
            f"gate={top.get('live_gate', '')} "
            f"state={top.get('deal_state', '')} "
            f"diag={top.get('diagnostic_status', '')} "
            f"bucket={top.get('diagnostic_bucket', '')} "
            f"score={top.get('combined_score', 0.0):.2f}"
        )
    if research:
        lines.append(
            "research "
            f"consensus={research.get('consensus_status', '')} "
            f"statuses={research.get('statuses', '')} "
            f"min_pos={_format_pct(research.get('min_positive_fold_fraction'))} "
            f"min_active_pos={_format_pct(research.get('min_active_positive_fold_fraction'))}"
        )
    if fixed_warmup:
        lines.append(
            "fixed_warmup "
            f"consensus={fixed_warmup.get('consensus_status', '')} "
            f"statuses={fixed_warmup.get('statuses', '')} "
            f"min_pos={_format_pct(fixed_warmup.get('min_positive_fold_fraction'))} "
            f"min_active={_format_pct(fixed_warmup.get('min_active_fold_fraction'))} "
            f"candidate={fixed_warmup.get('candidate_signature', '')}"
        )
    if watchlist.get("candidate_count", 0) > 0:
        top = watchlist["top_candidates"][0]
        lines.append(
            "watchlist "
            f"candidates={watchlist['candidate_count']} "
            f"top={top.get('symbol', '')} "
            f"source={Path(top.get('source_path', '')).name if top.get('source_path') else 'n/a'} "
            f"gate={top.get('live_gate', '')} "
            f"state={top.get('deal_state', '')} "
            f"strategy={top.get('candidate_strategy') or 'unknown'} "
            f"live={top.get('live_strategy') or 'unknown'} "
            f"quality={top.get('quality_score', 0.0):.2f} "
            f"hit={top.get('hit_rate', 0.0):.1%} "
            f"edge={top.get('average_edge_after_cost_bps', 0.0):.2f}bps "
            f"clear={top.get('estimated_state_clear_utc') or 'n/a'}"
        )
    if candidate_diagnostics.get("candidate_count", 0) > 0:
        top = candidate_diagnostics.get("top_candidates", [{}])[0]
        top_symbol = top.get("top_symbol", {})
        lines.append(
            "candidate_diagnostics "
            f"candidates={candidate_diagnostics.get('candidate_count', 0)} "
            f"top={top.get('label', '')} "
            f"profile={top.get('allocation_profile', 'default')} "
            f"alloc_status={top.get('allocation_status', '')} "
            f"requested={top.get('requested_gross_notional_usd', 0.0):.2f} "
            f"adjusted={top.get('adjusted_gross_notional_usd', 0.0):.2f} "
            f"actionable={top.get('actionable_symbol_count', 0)} "
            f"requested_symbols={top.get('requested_symbol_count', 0)} "
            f"focus={top_symbol.get('symbol', '')} "
            f"status={top_symbol.get('status', '')} "
            f"strategy={top_symbol.get('strategy', '')} "
            f"raw={top_symbol.get('raw_change_notional_usd', 0.0):.2f} "
            f"alloc={top_symbol.get('allocation_change_notional_usd', 0.0):.2f} "
            f"bucket={top_symbol.get('raw_reason_bucket', '')}"
        )
    if candidate_evidence.get("candidate_count", 0) > 0:
        top = candidate_evidence.get("top_candidates", [{}])[0]
        match = top.get("top_match", {})
        lines.append(
            "candidate_evidence "
            f"candidates={candidate_evidence.get('candidate_count', 0)} "
            f"top={top.get('candidate_label', '')} "
            f"strategy={top.get('strategy', '')} "
            f"symbols={' '.join(top.get('symbols', []))} "
            f"evidence={top.get('evidence_status', '')} "
            f"source={Path(match.get('source_path', '')).name if match.get('source_path') else 'n/a'} "
            f"status={match.get('promotion_status', '')} "
            f"nonneg={match.get('wf_non_negative_fold_fraction', 0.0):.1%} "
            f"active_pos={match.get('wf_active_positive_fold_fraction', 0.0):.1%} "
            f"fills={match.get('wf_total_evaluation_fills', 0)}"
        )
    if optimizer_scans.get("scan_count", 0) > 0:
        top = optimizer_scans.get("top_candidates", [{}])[0]
        lines.append(
            "optimizer_scans "
            f"scans={optimizer_scans.get('scan_count', 0)} "
            f"top={top.get('label', '')} "
            f"source={Path(top.get('source_path', '')).name if top.get('source_path') else 'n/a'} "
            f"age={_format_age_minutes(top.get('source_age_minutes'))} "
            f"stale={'yes' if top.get('source_stale') else 'no'} "
            f"status={top.get('promotion_status', '')} "
            f"live_ready={'yes' if top.get('promotion_live_ready') else 'no'} "
            f"active={top.get('wf_active_fold_fraction', 0.0):.1%} "
            f"active_pos={top.get('wf_active_positive_fold_fraction', 0.0):.1%} "
            f"nonneg={top.get('wf_non_negative_fold_fraction', 0.0):.1%} "
            f"median_active={top.get('wf_median_active_test_return_pct', 0.0):.3%} "
            f"fills={top.get('wf_total_evaluation_fills', 0)} "
            f"reason={top.get('promotion_reason', '')}"
        )
    if near_promotion.get("candidate_count", 0) > 0:
        top = near_promotion.get("top_candidates", [{}])[0]
        blockers = top.get("failed_gates", [])
        lines.append(
            "near_promotion "
            f"candidates={near_promotion.get('candidate_count', 0)} "
            f"top={top.get('label', '')} "
            f"source={Path(top.get('source_path', '')).name if top.get('source_path') else 'n/a'} "
            f"status={top.get('promotion_status', '')} "
            f"gap={top.get('promotion_gap_score', 0.0):.3f} "
            f"pos={top.get('positive_fold_fraction', 0.0):.1%} "
            f"active_pos={top.get('active_positive_fold_fraction', 0.0):.1%} "
            f"nonneg={top.get('non_negative_fold_fraction', 0.0):.1%} "
            f"fills={top.get('evaluation_fills', 0)} "
            f"blockers={';'.join(blockers) if isinstance(blockers, list) else blockers}"
        )
    candidate_map_rows = _candidate_map_rows(candidate_map)
    if candidate_map_rows:
        top_map = candidate_map_rows[0]
        prefix = (
            f"candidate_maps candidates={len(candidate_map_rows)} "
            if len(candidate_map_rows) > 1
            else "candidate_map "
        )
        lines.append(
            prefix +
            f"top_consensus={top_map.get('consensus_status', '')} "
            f"statuses={top_map.get('statuses', '')} "
            f"min_pos={_format_pct(top_map.get('min_positive_fold_fraction'))} "
            f"min_active_pos={_format_pct(top_map.get('min_active_positive_fold_fraction'))} "
            f"fills={top_map.get('total_evaluation_fills', '')} "
            f"candidate={top_map.get('candidate_signature', '')}"
        )
    if parameter:
        lines.append(
            "parameters "
            f"consensus={parameter.get('consensus_status', '')} "
            f"top={parameter.get('label', '')} "
            f"statuses={parameter.get('statuses', '')} "
            f"min_pos={_format_pct(parameter.get('min_wf_positive_fold_fraction'))} "
            f"min_active_pos={_format_pct(parameter.get('min_wf_active_positive_fold_fraction'))}"
        )
    if basket_scan:
        top_candidates = basket_scan.get("top_candidates", [])
        top = top_candidates[0] if top_candidates else {}
        lines.append(
            "basket_scan "
            f"candidates={basket_scan.get('candidate_count', 0)} "
            f"active={basket_scan.get('active_count', 0)} "
            f"underactive={basket_scan.get('underactive_count', 0)} "
            f"top={top.get('basket', '')}/{top.get('strategy', '')} "
            f"status={top.get('activity_status', '')} "
            f"fills={top.get('fills', 0)} "
            f"proxy={top.get('proxy_score', 0.0):.1f}"
        )
    if research_cycle:
        rows = research_cycle.get("qualified_rows", [])
        top = rows[0] if rows else {}
        lines.append(
            "research_cycle "
            f"signals={research_cycle.get('qualified_signal_count', 0)} "
            f"basket_active={research_cycle.get('basket_active_count', 0)} "
            f"basket_underactive={research_cycle.get('basket_underactive_count', 0)} "
            f"top={top.get('strategy', '')}:{top.get('symbol', '')}:{top.get('signal', '')} "
            f"active={top.get('active_count', 0)} "
            f"hit={top.get('hit_rate', 0.0):.1%} "
            f"signed={top.get('average_signed_forward_return_bps', 0.0):.2f}bps"
        )
    if research_live_gate:
        rows = research_live_gate.get("top_candidates", [])
        top = rows[0] if rows else {}
        lines.append(
            "research_live_gate "
            f"candidates={research_live_gate.get('candidate_count', 0)} "
            f"top={top.get('symbol', '')} "
            f"gate={top.get('gate', '')} "
            f"state={top.get('deal_state', '')} "
            f"action={top.get('action', '')} "
            f"diag={top.get('diagnostic_status', '')} "
            f"bucket={top.get('diagnostic_bucket', '')} "
            f"raw={top.get('raw_change_notional_usd', 0.0):.2f} "
            f"alloc={top.get('allocation_change_notional_usd', 0.0):.2f}"
        )
    for symbol, row in summary["pairs"].items():
        lines.append(
            f"{symbol}: action={row['action']} state={row['deal_state']} "
            f"score={row['combined_score']:.2f} "
            f"diag={row['diagnostic_status']} "
            f"bucket={row['diagnostic_bucket']} "
            f"clear={row['estimated_state_clear_utc'] or 'n/a'}"
        )
    return "\n".join(lines) + "\n"


def _format_pct(raw_value: Any) -> str:
    try:
        return f"{float(raw_value):.1%}"
    except (TypeError, ValueError):
        return ""


def _format_age_minutes(raw_value: Any) -> str:
    minutes = _float_or_zero(raw_value)
    if minutes < 60:
        return f"{minutes:.0f}m"
    return f"{minutes / 60:.1f}h"


def _candidate_map_rank_key(row: dict[str, str]) -> tuple[int, float, float, float]:
    status_rank = {"PROMOTE": 0, "PAPER_ONLY": 1, "REJECT": 2}
    return (
        status_rank.get(row.get("consensus_status", ""), 3),
        -_float_or_zero(row.get("min_active_positive_fold_fraction")),
        -_float_or_zero(row.get("min_positive_fold_fraction")),
        _float_or_zero(row.get("max_worst_test_drawdown_pct")),
    )


def _candidate_strategy_diagnostic_rank_key(row: dict[str, Any]) -> tuple[int, float, float, str]:
    return (
        0 if row.get("actionable_symbol_count", 0) else 1,
        -abs(_float_or_zero(row.get("adjusted_gross_notional_usd"))),
        -abs(_float_or_zero(row.get("requested_gross_notional_usd"))),
        row.get("label", ""),
    )


def _optimizer_scan_rank_key(row: dict[str, Any]) -> tuple[int, float, float, float, float, str]:
    status_rank = {"PROMOTE": 0, "PAPER_ONLY": 1, "REJECT": 2}
    return (
        status_rank.get(row.get("promotion_status", ""), 3),
        -_float_or_zero(row.get("wf_active_positive_fold_fraction")),
        -_float_or_zero(row.get("wf_non_negative_fold_fraction")),
        -_float_or_zero(row.get("wf_median_active_test_return_pct")),
        _float_or_zero(row.get("wf_worst_test_drawdown_pct")),
        row.get("source_label", ""),
    )


def _candidate_strategy_symbol_rank_key(row: dict[str, Any]) -> tuple[int, int, float, float, str]:
    status_rank = {
        "actionable_allocation": 0,
        "live_throttle_blocked": 1,
        "allocation_trimmed_to_no_change": 2,
        "allocation_no_change": 3,
        "strategy_no_change": 4,
    }
    return (
        status_rank.get(row.get("status", ""), 5),
        0 if row.get("source_focus") else 1,
        -abs(_float_or_zero(row.get("allocation_change_notional_usd"))),
        -abs(_float_or_zero(row.get("raw_change_notional_usd"))),
        row.get("symbol", ""),
    )


def _candidate_strategy_label(path: str | Path) -> str:
    stem = Path(path).stem
    if stem == "live_strategy_diagnostics_directional_probe_latest":
        return "live_directional_probe"
    if stem == "live_strategy_diagnostics_latest":
        return "live_current"
    return stem.replace("_live_strategy_diagnostics_latest", "")


def _float_or_zero(raw_value: Any) -> float:
    if raw_value in (None, ""):
        return 0.0
    return float(raw_value)


def _boolish(raw_value: Any) -> bool:
    if isinstance(raw_value, bool):
        return raw_value
    if raw_value is None:
        return False
    return str(raw_value).strip().lower() in {"1", "true", "yes", "y"}


if __name__ == "__main__":
    main()
