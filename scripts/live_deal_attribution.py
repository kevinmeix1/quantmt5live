from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

import MetaTrader5 as mt5


TERMINAL = os.getenv("MT5_TERMINAL_PATH") or r"C:\Program Files\MetaTrader 5\terminal64.exe"
SYMBOLS = ("AUDUSD", "EURGBP", "EURUSD", "GBPUSD", "USDCAD", "USDCHF", "USDJPY")
LATEST_JSON = Path("outputs/live_deal_attribution_latest.json")
LATEST_TEXT = Path("outputs/live_deal_attribution_latest.txt")
HISTORY_JSONL = Path("outputs/live_deal_attribution_history.jsonl")
BLOCKED_STATES = {
    "cooldown_realized_drag",
    "small_only_until_recovery",
    "observe",
    "keep_if_signal_aligned",
}


def main() -> None:
    args = _parse_args()
    now_utc = datetime.now(timezone.utc)
    if args.since_utc:
        since_utc = _parse_since(args.since_utc)
        query_since = since_utc.astimezone().replace(tzinfo=None)
    else:
        since_utc = now_utc - timedelta(hours=args.since_hours)
        query_since = datetime.now() - timedelta(hours=args.since_hours)
    # This MT5 server reports recent deal timestamps ahead of the Windows UTC
    # clock. Query with a forward cushion so just-filled live deals appear
    # immediately, but label the report in UTC.
    query_to = datetime.now() + timedelta(hours=3, minutes=5)

    if not mt5.initialize(path=args.terminal, timeout=180_000):
        raise SystemExit(f"initialize failed: {mt5.last_error()}")
    try:
        deals = mt5.history_deals_get(query_since, query_to)
        positions = mt5.positions_get()
        if deals is None:
            raise SystemExit(f"history_deals_get failed: {mt5.last_error()}")
        if positions is None:
            raise SystemExit(f"positions_get failed: {mt5.last_error()}")
        snapshot = build_snapshot(
            deals=deals,
            positions=positions,
            since_utc=since_utc,
            now_utc=now_utc,
            query_since=query_since,
            query_to=query_to,
            symbols=tuple(args.symbol),
        )
    finally:
        mt5.shutdown()

    _write(snapshot)
    print(
        json.dumps(
            {
                "timestamp_utc": snapshot["timestamp_utc"],
                "since_utc": snapshot["since_utc"],
                "symbols": {
                    symbol: {
                        "net_pnl": item["net_pnl"],
                        "closed_deals": item["closed_deals"],
                        "state": item["state"],
                    }
                    for symbol, item in snapshot["symbols"].items()
                },
            },
            sort_keys=True,
        )
    )


def build_snapshot(
    *,
    deals: Iterable,
    positions: Iterable,
    since_utc: datetime,
    now_utc: datetime,
    query_since: datetime,
    query_to: datetime,
    symbols: tuple[str, ...],
) -> dict:
    by_symbol = _empty_rows(symbols)
    deal_events_by_symbol: dict[str, list[dict]] = defaultdict(list)
    lookback = now_utc - since_utc
    for deal in deals:
        symbol = _canonical_symbol(getattr(deal, "symbol", ""))
        if symbol not in by_symbol:
            continue
        row = by_symbol[symbol]
        timestamp_utc = _deal_time(deal)
        profit = _float_attr(deal, "profit")
        commission = _float_attr(deal, "commission")
        swap = _float_attr(deal, "swap")
        fee = _float_attr(deal, "fee")
        net = profit + commission + swap + fee
        counted_closed = _is_closing_deal(deal) or abs(net) > 1e-9
        if timestamp_utc is not None:
            deal_events_by_symbol[symbol].append(
                {
                    "timestamp_utc": timestamp_utc,
                    "profit": profit,
                    "commission": commission,
                    "swap": swap,
                    "fee": fee,
                    "net": net,
                    "counted_closed": counted_closed,
                }
            )
        row["gross_profit"] += profit
        row["commission"] += commission
        row["swap"] += swap
        row["fee"] += fee
        row["net_pnl"] += net
        row["deals"] += 1
        if counted_closed:
            row["closed_deals"] += 1
            if net > 0:
                row["wins"] += 1
            elif net < 0:
                row["losses"] += 1
            row["last_close_utc"] = _format_utc(timestamp_utc)

    for position in positions:
        symbol = _canonical_symbol(getattr(position, "symbol", ""))
        if symbol not in by_symbol:
            continue
        row = by_symbol[symbol]
        row["open_positions"] += 1
        row["open_lots"] += _float_attr(position, "volume")
        row["floating_pnl"] += _float_attr(position, "profit")
        row["open_direction"] = "BUY" if int(getattr(position, "type", -1)) == 0 else "SELL"

    for symbol, row in by_symbol.items():
        closed = int(row["closed_deals"])
        row["win_rate"] = 0.0 if closed == 0 else row["wins"] / closed
        row["state"] = _state(row)
        clear_utc, state_after_clear = _estimate_state_clear_utc(
            row=row,
            events=deal_events_by_symbol[symbol],
            now_utc=now_utc,
            lookback=lookback,
        )
        row["estimated_state_clear_utc"] = clear_utc
        row["estimated_state_after_clear"] = state_after_clear
        _round_row(row)

    return {
        "timestamp_utc": now_utc.isoformat(timespec="seconds"),
        "since_utc": since_utc.isoformat(timespec="seconds"),
        "method": (
            "MT5 history_deals_get realized P/L plus current open-position floating P/L. "
            "State is advisory; live risk gates still control orders."
        ),
        "mt5_query_window_local": {
            "since": query_since.isoformat(timespec="seconds"),
            "to": query_to.isoformat(timespec="seconds"),
        },
        "symbols": dict(sorted(by_symbol.items())),
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Summarize live MT5 deal attribution by symbol.")
    parser.add_argument("--terminal", default=TERMINAL)
    parser.add_argument("--since-hours", type=float, default=12.0)
    parser.add_argument("--since-utc", default=None, help="Optional ISO UTC start timestamp.")
    parser.add_argument("--symbol", action="append", default=list(SYMBOLS))
    return parser.parse_args()


def _empty_rows(symbols: tuple[str, ...]) -> dict[str, dict]:
    return {
        symbol: {
            "deals": 0,
            "closed_deals": 0,
            "wins": 0,
            "losses": 0,
            "gross_profit": 0.0,
            "commission": 0.0,
            "swap": 0.0,
            "fee": 0.0,
            "net_pnl": 0.0,
            "win_rate": 0.0,
            "last_close_utc": None,
            "estimated_state_clear_utc": None,
            "estimated_state_after_clear": None,
            "open_positions": 0,
            "open_direction": "FLAT",
            "open_lots": 0.0,
            "floating_pnl": 0.0,
            "state": "observe",
        }
        for symbol in symbols
    }


def _state(row: dict) -> str:
    closed = int(row["closed_deals"])
    net = float(row["net_pnl"])
    floating = float(row["floating_pnl"])
    win_rate = float(row["win_rate"])
    if row["open_positions"] and floating > 0 and net >= -50:
        return "keep_if_signal_aligned"
    if closed >= 5 and int(row["wins"]) == 0 and net <= -50:
        return "cooldown_realized_drag"
    if closed >= 3 and net <= -75 and win_rate < 0.34:
        return "cooldown_realized_drag"
    if closed >= 2 and net <= -35:
        return "small_only_until_recovery"
    if closed == 0:
        return "no_closed_sample"
    if net > 0:
        return "working"
    return "observe"


def _is_closing_deal(deal) -> bool:
    entry = int(getattr(deal, "entry", -1))
    closing_entries = {
        getattr(mt5, "DEAL_ENTRY_OUT", 1),
        getattr(mt5, "DEAL_ENTRY_INOUT", 2),
        getattr(mt5, "DEAL_ENTRY_OUT_BY", 3),
    }
    return entry in closing_entries


def _deal_time_utc(deal) -> str | None:
    return _format_utc(_deal_time(deal))


def _deal_time(deal) -> datetime | None:
    raw = getattr(deal, "time", None)
    if raw is None:
        return None
    try:
        return datetime.fromtimestamp(int(raw), tz=timezone.utc)
    except (OverflowError, OSError, TypeError, ValueError):
        return None


def _format_utc(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat(timespec="seconds")


def _estimate_state_clear_utc(
    *,
    row: dict,
    events: list[dict],
    now_utc: datetime,
    lookback: timedelta,
) -> tuple[str | None, str | None]:
    if row.get("state") not in BLOCKED_STATES or lookback <= timedelta(0):
        return None, None
    expiry_times = sorted(
        {
            event["timestamp_utc"] + lookback + timedelta(seconds=1)
            for event in events
            if event.get("timestamp_utc") is not None
        }
    )
    for clear_at in expiry_times:
        if clear_at <= now_utc:
            continue
        simulated = _row_from_events(
            events=events,
            since_utc=clear_at - lookback,
            open_template=row,
        )
        state = _state(simulated)
        if state not in BLOCKED_STATES:
            return _format_utc(clear_at), state
    return None, None


def _row_from_events(
    *,
    events: list[dict],
    since_utc: datetime,
    open_template: dict,
) -> dict:
    row = _empty_rows(("SIM",))["SIM"]
    row["open_positions"] = open_template.get("open_positions", 0)
    row["open_lots"] = open_template.get("open_lots", 0.0)
    row["floating_pnl"] = open_template.get("floating_pnl", 0.0)
    row["open_direction"] = open_template.get("open_direction", "FLAT")
    for event in events:
        if event["timestamp_utc"] < since_utc:
            continue
        row["gross_profit"] += event["profit"]
        row["commission"] += event["commission"]
        row["swap"] += event["swap"]
        row["fee"] += event["fee"]
        row["net_pnl"] += event["net"]
        row["deals"] += 1
        if event["counted_closed"]:
            row["closed_deals"] += 1
            if event["net"] > 0:
                row["wins"] += 1
            elif event["net"] < 0:
                row["losses"] += 1
            row["last_close_utc"] = _format_utc(event["timestamp_utc"])
    closed = int(row["closed_deals"])
    row["win_rate"] = 0.0 if closed == 0 else row["wins"] / closed
    row["state"] = _state(row)
    return row


def _canonical_symbol(symbol: str) -> str:
    return str(symbol).split(".")[0].upper()


def _float_attr(obj, name: str) -> float:
    try:
        return float(getattr(obj, name, 0.0) or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _parse_since(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _round_row(row: dict) -> None:
    for key in ("gross_profit", "commission", "swap", "fee", "net_pnl", "open_lots", "floating_pnl", "win_rate"):
        row[key] = round(float(row[key]), 6)


def _write(snapshot: dict) -> None:
    LATEST_JSON.parent.mkdir(parents=True, exist_ok=True)
    LATEST_JSON.write_text(json.dumps(snapshot, indent=2, sort_keys=True), encoding="utf-8")
    with HISTORY_JSONL.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(snapshot, sort_keys=True) + "\n")
    lines = [f"{snapshot['timestamp_utc']} since={snapshot['since_utc']}", ""]
    for symbol, item in snapshot["symbols"].items():
        clear_utc = item.get("estimated_state_clear_utc")
        clear_text = ""
        if clear_utc:
            clear_text = (
                f" clear={clear_utc}->{item.get('estimated_state_after_clear')}"
            )
        lines.append(
            f"{symbol}: state={item['state']} net={item['net_pnl']:.2f} "
            f"closed={item['closed_deals']} win_rate={item['win_rate']:.2f} "
            f"float={item['floating_pnl']:.2f} open={item['open_direction']} "
            f"lots={item['open_lots']:.2f}{clear_text}"
        )
    LATEST_TEXT.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
