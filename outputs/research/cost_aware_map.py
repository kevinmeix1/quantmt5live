"""Iteration 3: cost-aware strategy re-selection.

Iteration 1 showed the edge is cost-sensitive (breakeven ~4 bps). So re-select
the per-symbol map using a REALISTIC 2 bps fill slippage instead of the
optimistic 1 bps, preferring lower-turnover trend strategies, then compare the
resulting portfolio to the current recipe at 2 and 3 bps slippage.

Usage: PYTHONPATH=src python3.11 outputs/research/cost_aware_map.py
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
PRICE = "data/full_20gb_15m_prices.csv"
QUOTE = "data/full_20gb_15m_quotes.csv"
ENV = {"PYTHONPATH": "src", "PATH": os.environ.get("PATH", "")}
SYMBOLS = ["EURUSD", "GBPUSD", "AUDUSD", "USDCHF", "USDCAD",
           "EURGBP", "EURCHF", "USDJPY", "XAUUSD", "XAGUSD"]
CANDIDATES = {"macd_momentum", "multi_horizon_momentum", "quality_trend",
              "trend_pullback", "volatility_squeeze", "session_momentum"}
CURRENT = {  # the recipe locked in last session (selected at 1 bps)
    "EURUSD": "macd_momentum", "GBPUSD": "multi_horizon_momentum",
    "AUDUSD": "macd_momentum", "USDCHF": "multi_horizon_momentum",
    "USDCAD": "macd_momentum", "EURGBP": "volatility_squeeze",
    "EURCHF": "volatility_squeeze", "XAUUSD": "macd_momentum",
    "XAGUSD": "macd_momentum", "USDJPY": "quality_trend",
}


def cfg_with_slippage(slip: float) -> Path:
    text = (ROOT / "configs" / "competition.toml").read_text()
    head, sep, tail = text.partition("[backtest]")
    tail = re.sub(r"slippage_bps = [0-9.]+", f"slippage_bps = {slip}", tail, count=1)
    p = RES / f"_ca_cfg_{slip}.toml"
    p.write_text(head + sep + tail)
    return p


def best_at_cost(symbol: str, cfg: Path, turnover_cap: int) -> str | None:
    """Highest-return candidate that is positive and not over the turnover cap."""
    out = RES / f"_ca_cmp_{symbol}.csv"
    subprocess.run([sys.executable, "qh.py", "compare", "--symbol", symbol,
                    "--config", str(cfg), "--price-csv", PRICE, "--quote-csv", QUOTE,
                    "--output", str(out)], cwd=ROOT, capture_output=True, text=True, env=ENV)
    if not out.exists():
        return None
    best, best_ret = None, 0.0
    with out.open() as f:
        for row in csv.DictReader(f):
            if row["strategy"] not in CANDIDATES:
                continue
            ret = float(row["total_return_pct"])
            fills = int(row["fills"])
            if ret > best_ret and fills <= turnover_cap:
                best, best_ret = row["strategy"], ret
    return best


def portfolio(slip: float, strategy_map: dict[str, str]) -> dict[str, float]:
    cfg = cfg_with_slippage(slip)
    cmd = [sys.executable, "qh.py", "portfolio-backtest", "--config", str(cfg),
           "--price-csv", PRICE, "--quote-csv", QUOTE]
    for s, st in strategy_map.items():
        cmd += ["--strategy-map", f"{s}={st}"]
    out = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, env=ENV)
    blob = out.stdout + out.stderr
    g = lambda p: float(m.group(1)) if (m := re.search(p, blob)) else float("nan")
    return {"ret": g(r"Official return:\s*([\-0-9.]+)%"),
            "dd": g(r"Official max drawdown:\s*([\-0-9.]+)%"),
            "rd": g(r"Risk discipline score:\s*([0-9]+)")}


def main() -> None:
    cfg2 = cfg_with_slippage(2.0)
    # Re-select at 2 bps, cap turnover at 40 fills/month to limit cost bleed.
    new_map: dict[str, str] = {}
    print("Cost-aware (2 bps, turnover<=40) selection per symbol:")
    for sym in SYMBOLS:
        pick = best_at_cost(sym, cfg2, turnover_cap=40)
        new_map[sym] = pick or CURRENT[sym]
        flag = "" if pick else "  (no positive low-turnover pick -> keep current)"
        chg = "" if new_map[sym] == CURRENT[sym] else f"  (was {CURRENT[sym]})"
        print(f"  {sym}: {new_map[sym]}{chg}{flag}")

    print("\nPortfolio comparison (full data):")
    print(f"{'slippage':>8} {'current ret/dd':>18} {'cost-aware ret/dd':>20}")
    for slip in (2.0, 3.0):
        cur = portfolio(slip, CURRENT)
        new = portfolio(slip, new_map)
        print(f"{slip:>6.1f}bps {cur['ret']:>8.3f}% /{cur['dd']:>6.3f}%   "
              f"{new['ret']:>8.3f}% /{new['dd']:>6.3f}%  (RD {int(new['rd'])})")


if __name__ == "__main__":
    main()
