"""Iteration 1: cost-stress robustness of the recommended portfolio.

Re-runs the validated best-trend-per-symbol map while scaling the realized fill
slippage (config.backtest.slippage_bps) up to 5x. A real edge should survive
worse-than-expected execution; a cost-artifact edge collapses.

Usage: PYTHONPATH=src python3.11 outputs/research/cost_stress.py
"""
from __future__ import annotations

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

MAP = {
    "EURUSD": "macd_momentum", "GBPUSD": "multi_horizon_momentum",
    "AUDUSD": "macd_momentum", "USDCHF": "multi_horizon_momentum",
    "USDCAD": "macd_momentum", "EURGBP": "volatility_squeeze",
    "EURCHF": "volatility_squeeze", "XAUUSD": "macd_momentum",
    "XAGUSD": "macd_momentum", "USDJPY": "quality_trend",
}


def run(slippage_bps: float) -> dict[str, float]:
    text = (ROOT / "configs" / "competition.toml").read_text()
    # Only touch the [backtest] section's slippage (realized fill cost), NOT the
    # per-strategy slippage_bps (those drive the cost filter). Split on the
    # section header so per-strategy lines above are untouched.
    head, sep, tail = text.partition("[backtest]")
    tail = re.sub(r"slippage_bps = [0-9.]+", f"slippage_bps = {slippage_bps}", tail, count=1)
    text = head + sep + tail
    cfg = RES / "_coststress_config.toml"
    cfg.write_text(text)
    cmd = [sys.executable, "qh.py", "portfolio-backtest", "--config", str(cfg),
           "--price-csv", PRICE, "--quote-csv", QUOTE]
    for s, st in MAP.items():
        cmd += ["--strategy-map", f"{s}={st}"]
    blob = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, env=ENV)
    out = blob.stdout + blob.stderr
    g = lambda pat: float(m.group(1)) if (m := re.search(pat, out)) else float("nan")
    return {
        "return": g(r"Official return:\s*([\-0-9.]+)%"),
        "maxdd": g(r"Official max drawdown:\s*([\-0-9.]+)%"),
        "sharpe": g(r"Official 15m Sharpe:\s*([\-0-9.]+)"),
        "rd": g(r"Risk discipline score:\s*([0-9]+)"),
    }


def main() -> None:
    print(f"{'slip_bps':>8} {'ret%':>7} {'maxDD%':>7} {'sharpe':>7} {'RD':>4}")
    base = None
    for slip in [1.0, 2.0, 3.0, 5.0]:
        m = run(slip)
        if base is None:
            base = m["return"]
        print(f"{slip:>8.1f} {m['return']:>7.3f} {m['maxdd']:>7.3f} "
              f"{m['sharpe']:>7.3f} {int(m['rd']):>4}")
    print("\nInterpretation: if return stays clearly positive at 3-5x slippage,")
    print("the edge is execution-robust, not a cost artifact.")


if __name__ == "__main__":
    main()
