from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from math import isfinite, sqrt
from pathlib import Path
from statistics import mean, pstdev

import MetaTrader5 as mt5

from quanthack.core.instruments import instrument_for


TERMINAL = os.getenv("MT5_TERMINAL_PATH") or r"C:\Program Files\MetaTrader 5\terminal64.exe"
STARTING_EQUITY = 1_000_000.0
SYMBOLS = ("AUDUSD", "EURGBP", "EURUSD", "GBPUSD", "USDCAD", "USDCHF", "USDJPY")
SENTIMENT_PATH = Path("outputs/fx_sentiment_snapshot.json")
ATTRIBUTION_PATH = Path("outputs/live_deal_attribution_latest.json")
LATEST = Path("outputs/live_pair_analysis_latest.json")
HISTORY = Path("outputs/live_pair_analysis_history.jsonl")
TEXT = Path("outputs/live_pair_analysis_latest.txt")
BLOCKED_FRESH_RISK_STATES = {
    "cooldown_realized_drag",
    "observe",
    "keep_if_signal_aligned",
}
SMALL_ONLY_FRESH_RISK_STATES = {
    "small_only_until_recovery",
}


def main() -> None:
    args = _parse_args()
    if not mt5.initialize(path=args.terminal, timeout=180_000):
        raise SystemExit(f"initialize failed: {mt5.last_error()}")
    try:
        account = mt5.account_info()
        positions = mt5.positions_get()
        if account is None or positions is None:
            raise SystemExit(f"MT5 account/positions unavailable: {mt5.last_error()}")
        sentiment = _read_sentiment()
        attribution = _read_attribution()
        analyses = _analyze_pairs(
            positions=positions,
            sentiment=sentiment,
            attribution=attribution,
        )
        snapshot = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "account": {
                "balance": float(account.balance),
                "equity": float(account.equity),
                "floating_pnl": float(account.profit),
                "day_pnl": float(account.equity) - STARTING_EQUITY,
                "margin": float(account.margin),
                "margin_level": float(account.margin_level),
                "positions_count": len(positions),
            },
            "sentiment_timestamp_utc": sentiment.get("timestamp_utc"),
            "deal_attribution_timestamp_utc": attribution.get("timestamp_utc"),
            "pairs": analyses,
            "currency_strength_m5_1h_bps": _currency_strength(),
        }
        _write(
            snapshot,
            output_json=Path(args.output_json),
            output_text=Path(args.output_text),
            history_jsonl=Path(args.history_jsonl),
        )
        print(
            json.dumps(
                {
                    "timestamp_utc": snapshot["timestamp_utc"],
                    "equity": snapshot["account"]["equity"],
                    "day_pnl": snapshot["account"]["day_pnl"],
                    "actions": {
                        symbol: item["action"]
                        for symbol, item in snapshot["pairs"].items()
                    },
                },
                sort_keys=True,
            )
        )
    finally:
        mt5.shutdown()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Summarize live MT5 pair state.")
    parser.add_argument("--terminal", default=TERMINAL)
    parser.add_argument("--output-json", default=str(LATEST))
    parser.add_argument("--output-text", default=str(TEXT))
    parser.add_argument("--history-jsonl", default=str(HISTORY))
    return parser.parse_args()


def _analyze_pairs(*, positions, sentiment: dict, attribution: dict) -> dict[str, dict]:
    position_by_symbol = _positions_by_symbol(positions)
    pair_sentiment = sentiment.get("pairs", {}) if isinstance(sentiment, dict) else {}
    pair_attribution = (
        attribution.get("symbols", {}) if isinstance(attribution, dict) else {}
    )
    analyses: dict[str, dict] = {}
    for symbol in SYMBOLS:
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            analyses[symbol] = {"error": f"missing tick: {mt5.last_error()}"}
            continue
        m1 = _closes(symbol, mt5.TIMEFRAME_M1, 121)
        m5 = _closes(symbol, mt5.TIMEFRAME_M5, 97)
        h1 = _closes(symbol, mt5.TIMEFRAME_H1, 49)
        if len(m1) < 21 or len(m5) < 13 or len(h1) < 7:
            analyses[symbol] = {"error": "insufficient MT5 bars"}
            continue

        spread_bps = _spread_bps(float(tick.bid), float(tick.ask))
        m1_fast = _move_bps(m1, 3)
        m1_medium = _move_bps(m1, 8)
        m1_slow = _move_bps(m1, 20)
        m5_hour = _move_bps(m5, 12)
        h1_six = _move_bps(h1, 6)
        vol = _volatility_bps(m1[-61:])
        weighted_move = 0.35 * m1_fast + 0.25 * m1_medium + 0.15 * m1_slow
        weighted_move += 0.15 * m5_hour + 0.10 * h1_six
        technical_score = weighted_move / max(spread_bps + 0.25 * vol, 1e-9)
        sent_score = float(pair_sentiment.get(symbol, {}).get("score", 0.0) or 0.0)
        deal_state = str(pair_attribution.get(symbol, {}).get("state", "unknown"))
        combined_score = technical_score + 0.25 * sent_score
        position = position_by_symbol.get(symbol)
        action = _action(
            position=position,
            combined_score=combined_score,
            technical_score=technical_score,
            spread_bps=spread_bps,
            deal_state=deal_state,
        )
        analyses[symbol] = {
            "bid": float(tick.bid),
            "ask": float(tick.ask),
            "spread_bps": spread_bps,
            "m1_fast_bps": m1_fast,
            "m1_medium_bps": m1_medium,
            "m1_slow_bps": m1_slow,
            "m5_1h_bps": m5_hour,
            "h1_6h_bps": h1_six,
            "realized_vol_bps": vol,
            "technical_score": technical_score,
            "headline_sentiment_score": sent_score,
            "deal_state": deal_state,
            "realized_net_pnl": float(
                pair_attribution.get(symbol, {}).get("net_pnl", 0.0) or 0.0
            ),
            "closed_deals": int(
                pair_attribution.get(symbol, {}).get("closed_deals", 0) or 0
            ),
            "combined_score": combined_score,
            "position": position or {"direction": "FLAT", "volume": 0.0, "profit": 0.0},
            "action": action,
        }
    return analyses


def _positions_by_symbol(positions) -> dict[str, dict]:
    by_symbol: dict[str, dict] = {}
    for position in positions:
        symbol = str(position.symbol).split(".")[0]
        by_symbol[symbol] = {
            "ticket": int(position.ticket),
            "direction": "BUY" if int(position.type) == 0 else "SELL",
            "volume": float(position.volume),
            "open": float(position.price_open),
            "profit": float(position.profit),
        }
    return by_symbol


def _action(
    *,
    position: dict | None,
    combined_score: float,
    technical_score: float,
    spread_bps: float,
    deal_state: str,
) -> str:
    if spread_bps > 12.0:
        return "wait_wide_spread" if position is None else "avoid_add_wide_spread"
    if position is None and deal_state in BLOCKED_FRESH_RISK_STATES:
        return (
            "cooldown_realized_drag"
            if deal_state == "cooldown_realized_drag"
            else f"blocked_{deal_state}"
        )
    direction = _sign(combined_score)
    if position is None:
        if deal_state in SMALL_ONLY_FRESH_RISK_STATES:
            if abs(combined_score) >= 1.75 and abs(technical_score) >= 1.25:
                return (
                    "eligible_small_probe_buy"
                    if direction > 0
                    else "eligible_small_probe_sell"
                )
            return "small_only_wait"
        if abs(combined_score) >= 1.75 and abs(technical_score) >= 1.25:
            return "eligible_tiny_probe_buy" if direction > 0 else "eligible_tiny_probe_sell"
        return "wait"
    position_direction = 1 if position["direction"] == "BUY" else -1
    if direction != 0 and direction != position_direction:
        if abs(combined_score) >= 1.25:
            return "watch_exit_or_reduce"
        if deal_state == "keep_if_signal_aligned" and abs(combined_score) >= 0.75:
            return "watch_signal_misalignment"
    if position.get("profit", 0.0) < -35 and abs(combined_score) < 0.75:
        return "watch_loss_stall"
    return "hold_or_trail"


def _currency_strength() -> dict[str, float]:
    totals: dict[str, list[float]] = {}
    for symbol in SYMBOLS:
        inst = instrument_for(symbol)
        closes = _closes(symbol, mt5.TIMEFRAME_M5, 13)
        if len(closes) < 13:
            continue
        move = _move_bps(closes, 12)
        totals.setdefault(inst.base_currency, []).append(move)
        totals.setdefault(inst.quote_currency, []).append(-move)
    return {currency: mean(values) for currency, values in sorted(totals.items())}


def _closes(symbol: str, timeframe: int, count: int) -> list[float]:
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, count)
    if rates is None:
        return []
    closes: list[float] = []
    for row in rates:
        close = float(row["close"])
        if isfinite(close) and close > 0:
            closes.append(close)
    return closes


def _move_bps(closes: list[float], lookback: int) -> float:
    if len(closes) <= lookback or closes[-lookback - 1] <= 0:
        return 0.0
    return (closes[-1] / closes[-lookback - 1] - 1.0) * 10_000.0


def _volatility_bps(closes: list[float]) -> float:
    returns = [
        (current / previous - 1.0) * 10_000.0
        for previous, current in zip(closes, closes[1:])
        if previous > 0
    ]
    if len(returns) < 2:
        return 0.0
    return pstdev(returns) * sqrt(len(returns))


def _spread_bps(bid: float, ask: float) -> float:
    mid = (bid + ask) / 2
    if mid <= 0:
        return 0.0
    return (ask - bid) / mid * 10_000.0


def _sign(value: float) -> int:
    if value > 0:
        return 1
    if value < 0:
        return -1
    return 0


def _read_sentiment() -> dict:
    if not SENTIMENT_PATH.exists():
        return {}
    try:
        return json.loads(SENTIMENT_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _read_attribution() -> dict:
    if not ATTRIBUTION_PATH.exists():
        return {}
    try:
        return json.loads(ATTRIBUTION_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _write(
    snapshot: dict,
    *,
    output_json: Path = LATEST,
    output_text: Path = TEXT,
    history_jsonl: Path = HISTORY,
) -> None:
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(snapshot, indent=2, sort_keys=True), encoding="utf-8")
    history_jsonl.parent.mkdir(parents=True, exist_ok=True)
    with history_jsonl.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(snapshot, sort_keys=True) + "\n")
    lines = [
        f"{snapshot['timestamp_utc']} equity={snapshot['account']['equity']:.2f} "
        f"day_pnl={snapshot['account']['day_pnl']:.2f} "
        f"positions={snapshot['account']['positions_count']}",
        "",
    ]
    for symbol, item in snapshot["pairs"].items():
        if "error" in item:
            lines.append(f"{symbol}: {item['error']}")
            continue
        lines.append(
            f"{symbol}: action={item['action']} score={item['combined_score']:.2f} "
            f"tech={item['technical_score']:.2f} sent={item['headline_sentiment_score']:.2f} "
            f"deal={item['deal_state']} net={item['realized_net_pnl']:.2f} "
            f"spread={item['spread_bps']:.2f}bps pos={item['position']['direction']} "
            f"pnl={item['position']['profit']:.2f}"
        )
    output_text.parent.mkdir(parents=True, exist_ok=True)
    output_text.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
