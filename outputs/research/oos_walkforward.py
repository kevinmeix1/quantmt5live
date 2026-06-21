"""Honest out-of-sample check for the trend-map portfolio.

Guards against the selection bias of picking the best strategy per symbol on the
same data we then report. Procedure:
  1. Split the 15m dataset chronologically into TRAIN (first ~60%) and TEST.
  2. On TRAIN only, pick the best *positive* strategy per symbol via `compare`.
  3. Backtest that frozen map on TEST at the chosen sizing.
  4. Report TEST return / drawdown / Sharpe / risk discipline.

Usage: PYTHONPATH=src python3.11 outputs/research/oos_walkforward.py [sym_pct]
"""
from __future__ import annotations

import csv
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RES = ROOT / "outputs" / "research"
PRICE = ROOT / "data" / "full_20gb_15m_prices.csv"
QUOTE = ROOT / "data" / "full_20gb_15m_quotes.csv"
SPLIT = "2026-05-28"  # ~60/40 chronological split of the 2026-05-11..06-10 window
ENV = {"PYTHONPATH": "src", "PATH": os.environ.get("PATH", "")}
SYM_PCT = float(sys.argv[1]) if len(sys.argv) > 1 else 0.80

# Trend/robust candidates only (high-turnover mean-reversion bleeds on costs).
CANDIDATES = [
    "macd_momentum", "multi_horizon_momentum", "quality_trend",
    "trend_pullback", "volatility_squeeze", "session_momentum",
]


def split_csv(src: Path, dst_train: Path, dst_test: Path) -> None:
    with src.open() as f:
        rows = list(csv.reader(f))
    header, body = rows[0], rows[1:]
    ts = header.index("timestamp")
    train = [r for r in body if r[ts] < SPLIT]
    test = [r for r in body if r[ts] >= SPLIT]
    for dst, part in ((dst_train, train), (dst_test, test)):
        with dst.open("w", newline="") as f:
            w = csv.writer(f)
            w.writerow(header)
            w.writerows(part)


def best_strategy_on_train(symbol: str, ptrain: Path, qtrain: Path) -> str | None:
    out = RES / f"_oos_cmp_{symbol}.csv"
    cmd = [sys.executable, "qh.py", "compare", "--symbol", symbol,
           "--price-csv", str(ptrain), "--quote-csv", str(qtrain), "--output", str(out)]
    subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, env=ENV)
    if not out.exists():
        return None
    # Pick the highest-return candidate that is strictly positive on train.
    best, best_ret = None, 0.0
    with out.open() as f:
        for row in csv.DictReader(f):
            strat = row.get("strategy", "")
            if strat not in CANDIDATES:
                continue
            ret = float(row.get("total_return_pct", row.get("return_pct", 0)) or 0)
            if ret > best_ret:
                best, best_ret = strat, ret
    return best


def run_test(strategy_map: dict[str, str], ptest: Path, qtest: Path) -> str:
    cfg_text = (ROOT / "configs" / "competition.toml").read_text()
    cfg_text = re.sub(r"max_symbol_notional_pct = [0-9.]+",
                      f"max_symbol_notional_pct = {SYM_PCT}", cfg_text)
    cfg_text = re.sub(r"target_notional_usd = [0-9.]+",
                      f"target_notional_usd = {int(SYM_PCT * 1_000_000)}", cfg_text)
    cfg_text = re.sub(r"max_target_notional_usd = [0-9.]+",
                      f"max_target_notional_usd = {int(SYM_PCT * 1_000_000)}", cfg_text)
    cfg = RES / "_oos_test_config.toml"
    cfg.write_text(cfg_text)
    cmd = [sys.executable, "qh.py", "portfolio-backtest", "--config", str(cfg),
           "--price-csv", str(ptest), "--quote-csv", str(qtest)]
    for sym, strat in strategy_map.items():
        cmd += ["--strategy-map", f"{sym}={strat}"]
    out = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, env=ENV)
    return out.stdout + out.stderr


def main() -> None:
    ptrain, qtrain = RES / "_train_p.csv", RES / "_train_q.csv"
    ptest, qtest = RES / "_test_p.csv", RES / "_test_q.csv"
    split_csv(PRICE, ptrain, ptest)
    split_csv(QUOTE, qtrain, qtest)

    symbols = ["EURUSD", "GBPUSD", "AUDUSD", "USDCHF", "USDCAD",
               "EURGBP", "EURCHF", "USDJPY", "XAUUSD", "XAGUSD"]
    print(f"Selecting best TRAIN strategy per symbol (split={SPLIT}, sym%={SYM_PCT})...")
    strategy_map: dict[str, str] = {}
    for sym in symbols:
        pick = best_strategy_on_train(sym, ptrain, qtrain)
        if pick:
            strategy_map[sym] = pick
        print(f"  {sym}: {pick or '(no positive trend strategy -> skip)'}")

    if not strategy_map:
        print("No symbols selected; nothing to test.")
        return

    print("\nEvaluating frozen TRAIN-selected map on held-out TEST data:")
    blob = run_test(strategy_map, ptest, qtest)
    for key in ("Official return", "Official max drawdown", "Official 15m Sharpe",
                "Trades", "Risk discipline score", "Worst leverage",
                "Worst net directional", "Worst largest-symbol concentration"):
        m = re.search(rf"{re.escape(key)}[^\n]*", blob)
        if m:
            print("  " + m.group(0).strip())


if __name__ == "__main__":
    main()
