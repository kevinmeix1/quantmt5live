from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from math import sqrt
from pathlib import Path

import MetaTrader5 as mt5


TERMINAL = r"C:\Program Files\MetaTrader 5\terminal64.exe"
STARTING_EQUITY = 1_000_000.0
OUT = Path("outputs/live_metrics.csv")
FIELDNAMES = (
    "timestamp_utc",
    "equity",
    "balance",
    "floating_pnl",
    "day_pnl",
    "drawdown_pct",
    "margin",
    "margin_level",
    "positions_count",
    "gross_lots",
    "rolling_sharpe_15",
)


def main() -> None:
    if not mt5.initialize(path=TERMINAL, timeout=180_000):
        raise SystemExit(f"initialize failed: {mt5.last_error()}")
    try:
        account = mt5.account_info()
        positions = mt5.positions_get()
        if account is None or positions is None:
            raise SystemExit(f"MT5 account/positions unavailable: {mt5.last_error()}")
        history = _read_history()
        equity = float(account.equity)
        peak = max([STARTING_EQUITY, equity, *[row["equity"] for row in history]])
        gross_lots = sum(float(position.volume) for position in positions)
        row = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "equity": equity,
            "balance": float(account.balance),
            "floating_pnl": equity - float(account.balance),
            "day_pnl": equity - STARTING_EQUITY,
            "drawdown_pct": 0.0 if peak <= 0 else (peak - equity) / peak,
            "margin": float(account.margin),
            "margin_level": float(account.margin_level),
            "positions_count": len(positions),
            "gross_lots": gross_lots,
            "rolling_sharpe_15": _rolling_sharpe([*history, {"equity": equity}], 15),
        }
        _append(row)
        print(json.dumps(row, sort_keys=True))
    finally:
        mt5.shutdown()


def _read_history() -> list[dict[str, float]]:
    if not OUT.exists():
        return []
    rows: list[dict[str, float]] = []
    with OUT.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for raw in reader:
            try:
                rows.append({"equity": float(raw["equity"])})
            except (KeyError, TypeError, ValueError):
                continue
    return rows[-240:]


def _rolling_sharpe(rows: list[dict[str, float]], window: int) -> float:
    equities = [row["equity"] for row in rows[-(window + 1):]]
    if len(equities) < 3:
        return 0.0
    returns = [
        current / previous - 1.0
        for previous, current in zip(equities, equities[1:])
        if previous > 0
    ]
    if len(returns) < 2:
        return 0.0
    mean = sum(returns) / len(returns)
    variance = sum((value - mean) ** 2 for value in returns) / (len(returns) - 1)
    if variance <= 0:
        return 0.0
    return mean / sqrt(variance) * sqrt(len(returns))


def _append(row: dict[str, float | int | str]) -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    needs_header = not OUT.exists() or OUT.stat().st_size == 0
    with OUT.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        if needs_header:
            writer.writeheader()
        writer.writerow(row)


if __name__ == "__main__":
    main()
